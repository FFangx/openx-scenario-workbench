"""Project-local PDF evidence with immutable source and scene revisions."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .atomic_write import write_bytes, write_json
from .asset_store import AssetStore
from .pdf_pipeline import extract_scene_packages_from_pdf
from .project_store import ProjectStore
from .scene_package import EvidenceRef, ScenePackage, synchronize_structure
from .store_lock import serialized


@dataclass(frozen=True, slots=True)
class PdfDocument:
    document_id: str
    project_id: str
    filename: str
    source_standard: str
    sha256: str
    imported_at: str
    page_count: int
    scene_count: int
    extraction_engine: str = "legacy-rules"


@dataclass(frozen=True, slots=True)
class StoredScene:
    document: PdfDocument
    scene_id: str
    revision: int
    package: ScenePackage


class PdfStore:
    EDITABLE = frozenset({"title", "preferred_text", "road_types", "weather", "time_of_day",
                          "entities", "actions", "triggers", "parameters", "structure", "classification"})

    def __init__(self, assets: AssetStore | None = None):
        self.assets = assets or AssetStore()
        self.root = self.assets.root
        self.projects = ProjectStore(self.assets)
        self.blobs = self.assets.root / "pdf_blobs"

    def _project_root(self, project_id: str) -> Path:
        if not any(item.project_id == project_id for item in self.projects.projects()):
            raise ValueError("Select an existing project for PDF imports.")
        return self.projects.root / project_id / "documents"

    def _document_root(self, project_id: str, document_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{20}", document_id):
            raise ValueError("Invalid PDF document ID.")
        root = self._project_root(project_id) / document_id
        if not (root / "document.json").is_file():
            raise ValueError("Unknown PDF document.")
        return root

    def import_pdf(self, project_id: str, filename: str, data: bytes,
                   source_standard: str = "", *, engine="v2", client=None, progress=None) -> PdfDocument:
        root = self._project_root(project_id)
        if not filename.casefold().endswith(".pdf"):
            raise ValueError("Select a PDF file.")
        digest = hashlib.sha256(data).hexdigest()
        if engine not in {"v2", "legacy"}:
            raise ValueError("Unknown extraction engine.")
        identity = ""
        if engine == "v2":
            from .pdf_extraction import ENGINE_VERSION, PROMPT_VERSION
            from .llm_service import ModelClient, base_url
            from .pdf_ocr import ocr_identity
            from .native_layout import layout_identity
            client = client or ModelClient()
            identity = json.dumps([ENGINE_VERSION, PROMPT_VERSION, base_url(client.config.base_url),
                                   client.config.model, client.config.thinking, client.config.max_tokens,
                                   ocr_identity(self.assets.root), layout_identity(self.assets.root)]
                                  # Appended only when set, so documents extracted before keep their ids.
                                  + ([client.config.reasoning_effort] if client.config.reasoning_effort else [])
                                  + (["figures"] if client.config.image_input else []))
        document_id = hashlib.sha256((digest + "\0" + source_standard + ("\0" + identity if identity else "")).encode()).hexdigest()[:20]
        manifest = root / document_id / "document.json"
        if manifest.is_file():
            return PdfDocument(**json.loads(manifest.read_text(encoding="utf-8")))
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as document:
            page_count = len(document)
        audit = {}
        if engine == "v2":
            from .pdf_extraction import extract_pdf, ExtractionError
            try:
                result = extract_pdf(data, filename, source_standard, client=client, root=self.assets.root, progress=progress)
            except ExtractionError as error:
                import uuid
                self._write_json(self.assets.root / "extraction_failures" / (uuid.uuid4().hex + ".json"), error.audit)
                raise
            packages, audit = result.packages, result.audit
        else:
            packages = extract_scene_packages_from_pdf(data, filename, source_standard)
        self.blobs.mkdir(parents=True, exist_ok=True)
        blob = self.blobs / digest
        if not blob.exists():
            self._write_bytes(blob, data)
        folder = manifest.parent
        folder.mkdir(parents=True, exist_ok=True)
        if audit:
            self._write_json(folder / "extraction.json", audit)
        for index, package in enumerate(packages, 1):
            scene_dir = folder / "scenes" / f"scene-{index:04d}"
            self._write_json(scene_dir / "0001.json", asdict(package))
        record = PdfDocument(document_id, project_id, filename, source_standard, digest,
                             datetime.now(timezone.utc).isoformat(), page_count, len(packages),
                             audit.get("engine", "legacy-rules"))
        self._write_json(manifest, asdict(record))
        return record

    def extraction_audit(self, document: PdfDocument) -> dict:
        path = self._document_root(document.project_id, document.document_id) / "extraction.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    @serialized
    def publish_scene(self, scene: StoredScene) -> dict:
        """Explicit review publishes an immutable requirement revision to the shared library."""
        revisions = self.revisions(scene.document.project_id, scene.document.document_id, scene.scene_id)
        stored = next((item for item in revisions if item.revision == scene.revision), None)
        if stored is None:
            raise ValueError("Unknown scene revision.")
        key = hashlib.sha256((scene.document.project_id + "\0" + scene.document.sha256 + "\0" + scene.document.document_id + "\0" + scene.scene_id).encode()).hexdigest()[:20]
        record = {"library_id": key, "revision": stored.revision, "kind": "pdf_requirement",
                  "project_id": stored.document.project_id, "document_id": stored.document.document_id,
                  "pdf_sha256": stored.document.sha256, "scene_id": stored.scene_id,
                  "reviewed_at": datetime.now(timezone.utc).isoformat(), "package": asdict(stored.package)}
        record["package"]["extraction"]["review_status"] = "confirmed"
        path = self.assets.root / "requirements" / key / f"{stored.revision:04d}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        self._write_json(path, record)
        return record

    def library(self) -> list[dict]:
        records = []
        for folder in sorted((self.assets.root / "requirements").glob("*")):
            versions = sorted(folder.glob("[0-9][0-9][0-9][0-9].json"))
            if versions:
                records.append(json.loads(versions[-1].read_text(encoding="utf-8")))
        return records

    def documents(self, project_id: str) -> list[PdfDocument]:
        root = self._project_root(project_id)
        result = [PdfDocument(**json.loads(path.read_text(encoding="utf-8")))
                  for path in root.glob("*/document.json")]
        return sorted(result, key=lambda item: item.imported_at, reverse=True)

    def pdf_bytes(self, document: PdfDocument) -> bytes:
        self._document_root(document.project_id, document.document_id)
        data = (self.blobs / document.sha256).read_bytes()
        if hashlib.sha256(data).hexdigest() != document.sha256:
            raise ValueError("Stored PDF failed integrity check.")
        return data

    @staticmethod
    def _package(payload: dict[str, Any]) -> ScenePackage:
        return ScenePackage(**{**payload, "evidence": [EvidenceRef(**item) for item in payload.get("evidence", [])]})

    @classmethod
    def _revision(cls, document: PdfDocument, scene_id: str, path: Path) -> StoredScene:
        return StoredScene(document, scene_id, int(path.stem),
                           cls._package(json.loads(path.read_text(encoding="utf-8"))))

    def _scene_document(self, project_id: str, document_id: str) -> tuple[Path, PdfDocument]:
        root = self._document_root(project_id, document_id)
        return root, PdfDocument(**json.loads((root / "document.json").read_text(encoding="utf-8")))

    def scenes(self, project_id: str, document_id: str) -> list[StoredScene]:
        root, document = self._scene_document(project_id, document_id)
        result = []
        for folder in sorted((root / "scenes").glob("scene-*")):
            revision_files = sorted(folder.glob("[0-9][0-9][0-9][0-9].json"))
            if revision_files:
                result.append(self._revision(document, folder.name, revision_files[-1]))
        return result

    def all_scenes(self, project_id: str) -> list[StoredScene]:
        return [scene for document in self.documents(project_id)
                for scene in self.scenes(project_id, document.document_id)]

    def revisions(self, project_id: str, document_id: str, scene_id: str) -> list[StoredScene]:
        if not re.fullmatch(r"scene-[0-9]{4}", scene_id):
            raise ValueError("Invalid scene ID.")
        root, document = self._scene_document(project_id, document_id)
        return [self._revision(document, scene_id, path)
                for path in sorted((root / "scenes" / scene_id).glob("[0-9][0-9][0-9][0-9].json"))]

    @serialized
    def revise_scene(self, project_id: str, document_id: str, scene_id: str,
                     edits: dict[str, Any]) -> StoredScene:
        unknown = set(edits) - self.EDITABLE
        if unknown:
            raise ValueError(f"Only extracted facts may be edited: {', '.join(sorted(unknown))}.")
        scenes = self.scenes(project_id, document_id)
        current = next((item for item in scenes if item.scene_id == scene_id), None)
        if current is None:
            raise ValueError("Unknown extracted scene.")
        if current.package.structure and set(edits) - {"title", "preferred_text", "structure"}:
            raise ValueError("Edit the typed structure; compatibility fields are derived from it.")
        payload = asdict(current.package)
        for key, value in edits.items():
            if key == "title":
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("Scene title cannot be empty.")
                value = value.strip()
            elif key == "preferred_text":
                if not isinstance(value, str):
                    raise ValueError("Preferred text must be text.")
            elif key == "parameters":
                if not isinstance(value, dict) or any(not isinstance(k, str) or
                    not isinstance(v, (float, int)) or isinstance(v, bool) or not math.isfinite(v)
                    for k, v in value.items()):
                    raise ValueError("Parameters must be finite numeric values.")
                value = {key: float(number) for key, number in value.items()}
            elif key == "structure":
                from .pdf_v2.scene_schemas import SceneStructure
                value = SceneStructure.model_validate(value).model_dump(mode="json")
            elif key == "classification":
                if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
                    raise ValueError("Classification must be a JSON object.")
                value = {**value, "method": "manual"}
            elif not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ValueError(f"{key} must be a list of text values.")
            payload[key] = value
        original = (self._document_root(project_id, document_id) / "scenes" / scene_id / "0001.json")
        if "structure" in edits and payload["structure"]:
            payload["classification"] = {**payload.get("classification", {}), "method": "manual",
                                         "function": payload["structure"]["tested_function"],
                                         "road_type": payload["structure"]["road_class"],
                                         "intent": payload["structure"]["test_intent"]}
        payload["evidence"] = json.loads(original.read_text(encoding="utf-8"))["evidence"]
        payload.setdefault("extraction", {})["review_status"] = "pending"
        if payload["structure"]:
            package = ScenePackage(**{**payload, "evidence": []})
            derived = asdict(synchronize_structure(package))
            payload.update({key: value for key, value in derived.items() if key != "evidence"})
        revision = current.revision + 1
        path = original.parent / f"{revision:04d}.json"
        self._write_json(path, payload)
        return StoredScene(current.document, scene_id, revision, self._package(payload))

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, value, ensure_ascii=False, indent=2, prefix="writing-", suffix=".tmp")

    @staticmethod
    def _write_bytes(path: Path, data: bytes) -> None:
        write_bytes(path, data, prefix="writing-", suffix=".tmp")
