"""V2 structure → scene-first v6 → anchored, classified requirement scenes."""
from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .asset_store import default_store_root
from .llm_service import ModelClient, ModelError, base_url
from .pdf_v2.parser import parse_pdf_structure
from .pdf_v2.quality import assess_structure_quality
from .pdf_v2.section_tree import build_section_tree
from .pdf_v2.scene_first import run_scene_first_extraction
from .scene_package import EvidenceRef, ScenePackage, canonical_features, extract_parameters

ENGINE_VERSION = "openx-v2-scene-first-1"
PROMPT_VERSION = "scene-first-prompt-v6"


@dataclass
class ExtractionResult:
    packages: list[ScenePackage]
    audit: dict


class ExtractionError(ValueError):
    def __init__(self, message, audit):
        super().__init__(message)
        self.audit = audit


def extract_pdf(data: bytes, filename: str, standard: str = "", *, client=None, root=None, progress=None) -> ExtractionResult:
    client = client or ModelClient()
    if not client.config.api_key:
        raise ModelError("PDF 场景提取需要模型。请先在设置中填写 Key 并测试模型 / Configure and test a model first.")
    notify = progress or (lambda message: None)
    notify("解析文字、表格与章节树 / Parsing document structure")
    with tempfile.TemporaryDirectory(prefix="openx-pdf-") as directory:
        path = Path(directory) / "document.pdf"
        path.write_bytes(data)
        document, outline = parse_pdf_structure(path, heading_decoder="chain")
    if document.document_type != "born_digital":
        raise ValueError("这份 PDF 含扫描页，当前版本只支持文字版 PDF / Scanned or mixed PDF requires OCR, not enabled yet.")
    tree = build_section_tree(document, outline=outline)
    quality = assess_structure_quality(document, tree)
    severe = [issue.code for issue in quality.issues if issue.code in {"empty_section_tree", "low_block_coverage"}]
    if severe:
        raise ValueError("PDF 章节结构不可靠，请检查文档 / Unreliable PDF structure: " + ", ".join(severe))
    blocks = {block.block_id: block for block in document.blocks}
    texts = {node.node_id: "\n".join(blocks[bid].text for bid in node.block_ids if bid in blocks) for node in tree.nodes}
    flagged = {flag.block_id for flag in document.structure_flags}
    flagged_nodes = frozenset(node.node_id for node in tree.nodes if node.heading_block_id in flagged)
    cache_root = Path(root or default_store_root()) / "model_cache"
    calls = 0
    requests = []

    def transport(body):
        nonlocal calls
        actual = {**body, "model": client.config.model, "max_tokens": min(body.get("max_tokens", 64000), client.config.max_tokens)}
        identity = {"engine": ENGINE_VERSION, "endpoint": base_url(client.config.base_url),
                    "thinking": client.config.thinking, "request": actual}
        checksum = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        cached = cache_root / (checksum + ".json")
        if cached.exists():
            requests.append({"sha256": checksum, "cached": True})
            return json.loads(cached.read_text(encoding="utf-8"))
        if calls >= 2:
            raise ModelError("单文档模型调用达到上限 / Document model call limit reached.")
        calls += 1
        notify("模型正在识别、分类并提取场景 / Identifying and classifying scenes")
        result = client.complete(actual)
        # Cache complete responses only. Interrupted/truncated requests remain retryable.
        if result.get("choices", [{}])[0].get("finish_reason") == "stop":
            cache_root.mkdir(parents=True, exist_ok=True)
            _write_json(cached, result)
        requests.append({"sha256": checksum, "cached": False})
        return result

    run = run_scene_first_extraction(tree, texts, standard=standard or "PDF", heading_decoder="chain",
                                     model=client.config.model, prompt_version=PROMPT_VERSION,
                                     transport=transport, retry_enabled=True, flagged_node_ids=flagged_nodes)
    audit = {"engine": ENGINE_VERSION, "pdf_sha256": hashlib.sha256(data).hexdigest(),
             "source_pdf": filename, "structure_quality": quality.model_dump(mode="json"),
             "nodes": [dict(node.model_dump(mode="json"), source_text=texts[node.node_id]) for node in tree.nodes],
             "run": run.model_dump(mode="json"), "requests": requests}
    if run.status not in {"ok", "retried_ok"} or run.extraction is None:
        raise ExtractionError(f"场景提取未完成 / Extraction failed ({run.status}): {run.failure_detail or ''}", audit)
    if not run.extraction.scenes and run.extraction.rejected_node_ids:
        raise ExtractionError("模型的场景引用均无效，请重新提取或检查原文 / All scene references were invalid.", audit)
    notify("校验原文引用并保存场景 / Validating evidence and saving scenes")
    nodes = {node.node_id: node for node in tree.nodes}
    packages = []
    for scene in run.extraction.scenes:
        # Anchor first makes the default evidence preview the scene itself, not shared setup.
        ids = [scene.anchor_node_id, *[item for item in scene.node_ids if item != scene.anchor_node_id]]
        evidence = [EvidenceRef(filename, nodes[nid].section_id, nodes[nid].page_start, nodes[nid].page_end,
                                texts[nid]) for nid in ids]
        structure = scene.structure.model_dump(mode="json") if scene.structure else {}
        entities, actions, triggers, roads = canonical_features(scene.name + "\n" + scene.story)
        # Keep the complete typed structure; legacy search fields are a compatibility view.
        fn = structure.get("tested_function", "未知")
        metadata = {"method": "llm", "model": client.config.model, "function": fn,
                    "road_type": structure.get("road_class", "未知"), "actors": list(scene.actors),
                    "confidence": scene.confidence, "intent": structure.get("test_intent", "未知")}
        params = structure.get("params") or {}
        parameters = {key: params[source] for source, key in (("ego_speed_kph", "ego_speed_kph"), ("ttc_value", "ttc_s")) if params.get(source) is not None}
        packages.append(ScenePackage(
            package_id=scene.scene_id, title=scene.name, preferred_text=scene.story, source_standard=standard,
            evidence=evidence, entities=sorted(entities), actions=sorted(actions), triggers=sorted(triggers),
            road_types=sorted(roads), parameters=parameters,
            weather=[params["weather"]] if params.get("weather") not in {None, "未知"} else [],
            time_of_day=[params["time_of_day"]] if params.get("time_of_day") not in {None, "未知"} else [],
            classification=metadata, structure=structure,
            extraction={"engine": ENGINE_VERSION, "prompt": PROMPT_VERSION, "model": client.config.model,
                        "anchor_node_id": scene.anchor_node_id, "node_ids": list(scene.node_ids),
                        "shared_node_ids": list(scene.declared_shared_node_ids),
                        "validation": {**run.validation.model_dump(mode="json"),
                                       "issues": [issue.model_dump(mode="json") for issue in run.validation.issues if issue.scene_id in {None, scene.scene_id}]} if run.validation else {},
                        "review_status": "pending"},
        ))
    return ExtractionResult(packages, audit)


def _write_json(path, data):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        temporary = Path(handle.name)
    temporary.replace(path)
