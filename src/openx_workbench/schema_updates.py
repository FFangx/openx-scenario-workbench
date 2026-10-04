"""User-started updates of the XSD registry from esmini: check, stage and preview, switch, roll back.

Nothing here runs unless the user asks for it; validation itself stays offline. A new registry is
staged beside the active one, compared against the asset library, and only switched in on request.
The registry it replaces is kept for one-step rollback.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
import shutil
import time
from pathlib import Path
from threading import Lock
from urllib.error import URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from .atomic_write import write_json
from .schema_validation import ENTRIES, SCHEMA_REVISION, _load_schema, _local_path, schema_root, validate_xml

API = "https://api.github.com/repos/esmini/esmini"
RAW = "https://raw.githubusercontent.com/esmini/esmini/{revision}/resources/schema/"
SCHEMA_PATH = "resources/schema"
SIZE_LIMIT = 4 * 1024 * 1024
KIND = "schema_update"
PREVIEW = "preview.json"
_swap_lock = Lock()

OSC_FILE = re.compile(r"OpenSCENARIOv(\d+)\.(\d+)(?:\.(\d+))?\.xsd")
ODR_FILE = re.compile(r"OpenDRIVE_(\d+)\.(\d+)(?:\.(\d+))?[A-Za-z]?\.xsd")
ODR_FOLDER = re.compile(r"OpenDRIVE_(\d+)\.(\d+)(?:\.(\d+))?/")
# XSD 1.1 constructs; a registry compiled as XSD 1.0 would reject or ignore them.
XSD11 = re.compile(rb"<\w+:(?:assert|assertion|alternative|openContent)\b|minVersion=[\"']1\.1")


class SchemaUpdateError(ValueError):
    pass


def staging_root(root: Path) -> Path:
    return root.with_name(root.name + ".staging")


def previous_root(root: Path) -> Path:
    return root.with_name(root.name + ".previous")


def git_blob_sha(data: bytes) -> str:
    """The id GitHub lists for a file, so local files compare without downloading them."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _get(url: str, *, accept: str = "application/vnd.github+json") -> bytes:
    request = Request(url, headers={"Accept": accept, "User-Agent": "openx-scenario-workbench"})
    try:
        with urlopen(request, timeout=30) as response:
            data = response.read(SIZE_LIMIT + 1)
    except (URLError, TimeoutError, OSError) as error:
        raise SchemaUpdateError(f"无法连接 esmini 仓库 / Could not reach the esmini repository: {error}") from None
    if len(data) > SIZE_LIMIT:
        raise SchemaUpdateError("Schema exceeds size limit")
    return data


def _get_json(url: str):
    return json.loads(_get(url))


# ---------- reading registries ----------

def read_registry(root: Path) -> dict | None:
    try:
        return json.loads((root / "registry.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def summary(root: Path) -> dict | None:
    registry = read_registry(root)
    if registry is None:
        return None
    installed = registry.get("installed_at")
    if installed is None:
        installed = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime((root / "registry.json").stat().st_mtime))
    return {"revision": registry.get("revision", ""), "commit_date": registry.get("commit_date"),
            "installed_at": installed, "versions": sorted(registry.get("entries", {})),
            "skipped": registry.get("skipped", {})}


def status(root: Path | None = None) -> dict:
    root = Path(root) if root is not None else schema_root()
    staged = summary(staging_root(root))
    if staged is not None:
        try:
            staged["preview"] = json.loads((staging_root(root) / PREVIEW).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            staged["preview"] = None
    return {"active": summary(root), "previous": summary(previous_root(root)), "staged": staged}


# ---------- remote ----------

def discover_entries(paths) -> tuple[dict[str, str], dict[str, str]]:
    """Entry schema per declared version, by esmini's file layout; ambiguous versions are not guessed."""
    candidates: dict[str, list[tuple[int, str]]] = {}
    folders: dict[str, list[tuple[int, str]]] = {}
    for path in paths:
        if "/" not in path:
            match = OSC_FILE.fullmatch(path) or ODR_FILE.fullmatch(path)
            if match:
                standard = "OpenSCENARIO" if path.startswith("OpenSCENARIO") else "OpenDRIVE"
                key = f"{standard}:{int(match[1])}.{int(match[2])}"
                candidates.setdefault(key, []).append((int(match[3] or 0), path))
            continue
        match = ODR_FOLDER.match(path)
        if match and path.casefold().endswith("core.xsd"):
            folders.setdefault(f"OpenDRIVE:{int(match[1])}.{int(match[2])}", []).append((int(match[3] or 0), path))
    entries, unmapped = {}, {}
    for key in sorted(set(candidates) | set(folders)):
        # The newest patch release wins; among equals, the path known to work, then esmini's local copy.
        found = candidates.get(key, []) + folders.get(key, [])
        best = max(patch for patch, _ in found)
        top = [path for patch, path in found if patch == best]
        if ENTRIES.get(key) in top:
            top = [ENTRIES[key]]
        top = [path for path in top if "local" in path.casefold()] or top
        if len(top) == 1:
            entries[key] = top[0]
        else:
            unmapped[key] = "找到多个候选入口文件，需要人工确认 / Several entry candidates; needs a manual choice"
    return entries, unmapped


def remote_snapshot(revision: str | None = None) -> dict:
    """The schema folder at `revision`, or at the newest commit that changed it."""
    if revision is None:
        commits = _get_json(f"{API}/commits?path={SCHEMA_PATH}&per_page=1")
        if not commits:
            raise SchemaUpdateError("esmini 仓库中没有 schema 目录 / The esmini repository has no schema folder")
        commit = commits[0]
    else:
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise SchemaUpdateError("Unknown revision")
        commit = _get_json(f"{API}/commits/{revision}")
    revision = commit["sha"]
    listing = _get_json(f"{API}/contents/resources?ref={revision}")
    folder = next((item for item in listing if item.get("name") == "schema" and item.get("type") == "dir"), None)
    if folder is None:
        raise SchemaUpdateError("esmini 仓库中没有 schema 目录 / The esmini repository has no schema folder")
    tree = _get_json(f"{API}/git/trees/{folder['sha']}?recursive=1")
    if tree.get("truncated"):
        raise SchemaUpdateError("Schema listing is incomplete")
    files = {item["path"]: item["sha"] for item in tree["tree"]
             if item.get("type") == "blob" and item["path"].endswith(".xsd")}
    entries, unmapped = discover_entries(files)
    return {"revision": revision, "date": commit["commit"]["committer"]["date"],
            "message": commit["commit"]["message"].split("\n", 1)[0], "files": files,
            "entries": entries, "unmapped": unmapped}


def check(root: Path | None = None) -> dict:
    """What the newest esmini schema folder would change; reads GitHub, writes nothing."""
    root = Path(root) if root is not None else schema_root()
    remote = remote_snapshot()
    registry = read_registry(root) or {"entries": {}, "sha256": {}}
    local = {}
    for name in registry.get("sha256", {}):
        try:
            local[name] = git_blob_sha(_local_path(root, name).read_bytes())
        except (OSError, ValueError):
            local[name] = ""
    files = remote["files"]
    changed = sorted(name for name in local if name in files and files[name] != local[name])
    removed = sorted(name for name in local if name not in files)
    added = sorted(name for name in files if name not in local)
    active = registry.get("entries", {})
    return {"revision": remote["revision"], "date": remote["date"], "message": remote["message"],
            "installed": bool(active),
            "up_to_date": bool(active) and not (changed or removed or added) and active == remote["entries"],
            "changed": changed, "added": added, "removed": removed,
            "new_versions": sorted(set(remote["entries"]) - set(active)),
            "dropped_versions": sorted(set(active) - set(remote["entries"])),
            "unmapped": remote["unmapped"]}


# ---------- installing ----------

def _references(data: bytes, name: str) -> list[str]:
    found = []
    for node in ET.fromstring(data).iter():
        location = node.get("schemaLocation")
        if not location:
            continue
        if re.match(r"^[a-zA-Z][\w+.-]*:", location) or location.startswith(("/", "\\")):
            raise ValueError("External schema reference is forbidden")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), location))
        if resolved.startswith("../") or resolved == "..":
            raise ValueError("External schema reference is forbidden")
        found.append(resolved)
    return found


def install(root: Path, revision: str, entries: dict[str, str], *, commit_date: str | None = None,
            skipped: dict[str, str] | None = None, progress=None, cancelled=None) -> dict:
    """Download each entry and every schema it includes into an empty `root`, compile, then publish.

    A version whose files cannot be fetched or compiled is left out and reported; the others install.
    """
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    base = RAW.format(revision=revision)
    fetched: dict[str, bytes] = {}
    closures: dict[str, list[str]] = {}
    skipped = dict(skipped or {})
    for key, entry in sorted(entries.items()):
        pending, closure = [entry], []
        try:
            while pending:
                if cancelled:
                    cancelled()
                name = pending.pop()
                if name in closure:
                    continue
                if name not in fetched:
                    if progress:
                        progress(name)
                    fetched[name] = _get(base + name, accept="*/*")
                closure.append(name)
                pending.extend(_references(fetched[name], name))
        except (SchemaUpdateError, ValueError, ET.ParseError) as error:
            skipped[key] = str(error)
            continue
        closures[key] = closure
    for name in sorted({name for closure in closures.values() for name in closure}):
        path = _local_path(root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fetched[name])
    digests = {name: hashlib.sha256(fetched[name]).hexdigest()
               for name in sorted({name for closure in closures.values() for name in closure})}
    checksum = hashlib.sha256("".join(digests[name] for name in sorted(digests)).encode()).hexdigest()
    installed, xsd_versions = {}, {}
    for key, closure in closures.items():
        version = "1.1" if any(XSD11.search(fetched[name]) for name in closure) else "1.0"
        try:
            _load_schema(str(_local_path(root, entries[key])), checksum, version)
        except Exception as error:  # noqa: BLE001 - a schema that does not compile is reported, never installed
            skipped[key] = f"Schema does not compile: {error}"
            continue
        installed[key] = entries[key]
        if version != "1.0":
            xsd_versions[key] = version
    if not installed:
        raise SchemaUpdateError("没有可安装的规范 / No schema could be installed: "
                                + "; ".join(f"{key}: {reason}" for key, reason in sorted(skipped.items())))
    registry = {"revision": revision, "source": base, "commit_date": commit_date,
                "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "entries": installed,
                "sha256": digests, "xsd_versions": xsd_versions, "skipped": skipped}
    write_json(root / "registry.json", registry, indent=2)
    return registry


def _promote(root: Path, incoming: Path) -> None:
    """Make `incoming` the active registry and keep the one it replaces as the rollback copy."""
    parked = root.with_name(root.name + ".parked")
    if parked.exists():
        shutil.rmtree(parked)
    if root.exists():
        root.rename(parked)
    try:
        incoming.rename(root)
    except OSError:
        if parked.exists():
            parked.rename(root)
        raise
    previous = previous_root(root)
    if previous.exists():
        shutil.rmtree(previous)
    if parked.exists():
        parked.rename(previous)


def install_pinned(root: Path) -> dict:
    """The command line's install: the revision pinned in code, switched in without a library preview."""
    staging = staging_root(root)
    registry = install(staging, SCHEMA_REVISION, ENTRIES)
    with _swap_lock:
        _promote(root, staging)
    return registry


def preview(store, job, revision: str, root: Path | None = None) -> dict:
    """Stage `revision` and record which library verdicts it would change. The active registry is untouched."""
    root = Path(root) if root is not None else schema_root()
    staging = staging_root(root)
    job.update(stage="downloading")
    remote = remote_snapshot(revision)
    install(staging, remote["revision"], remote["entries"], commit_date=remote["date"],
            skipped=remote["unmapped"], progress=job.note, cancelled=job.check)
    versions = store.latest()
    job.update(stage="comparing", total=len(versions), done=0)
    changes = []
    for index, version in enumerate(versions):
        job.check()
        job.note(version.title or version.source_name)
        for role in ("scenario", "road"):
            data = store.file_bytes(version, role)
            before, after = validate_xml(data, root=root), validate_xml(data, root=staging)
            if before["status"] != after["status"] or len(before["issues"]) != len(after["issues"]):
                changes.append({"asset_id": version.asset_id, "version_id": version.version_id,
                                "title": version.title or version.source_name, "role": role,
                                "standard": after["standard"], "version": after["version"],
                                "before": {"status": before["status"], "issues": len(before["issues"])},
                                "after": {"status": after["status"], "issues": len(after["issues"])}})
        job.update(done=index + 1)
    changes.sort(key=lambda change: (change["title"], change["asset_id"], change["role"] != "scenario"))
    result = {"revision": remote["revision"], "date": remote["date"], "message": remote["message"],
              "compared": len(versions), "changes": changes,
              "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    write_json(staging / PREVIEW, result, ensure_ascii=False, indent=2)
    return result


def apply(revision: str, root: Path | None = None) -> dict:
    root = Path(root) if root is not None else schema_root()
    staging = staging_root(root)
    with _swap_lock:
        staged = read_registry(staging)
        if staged is None or not (staging / PREVIEW).is_file():
            raise SchemaUpdateError("没有已预览的新规范 / No previewed registry is staged")
        if staged.get("revision") != revision:
            raise SchemaUpdateError("暂存的规范与所选版本不一致，请重新预览 / The staged registry is a different revision; preview again")
        _promote(root, staging)
    return status(root)


def rollback(root: Path | None = None) -> dict:
    root = Path(root) if root is not None else schema_root()
    with _swap_lock:
        if read_registry(previous_root(root)) is None:
            raise SchemaUpdateError("没有可回退的旧版本 / No earlier registry to roll back to")
        _promote(root, previous_root(root))
    return status(root)


def discard(root: Path | None = None) -> dict:
    root = Path(root) if root is not None else schema_root()
    with _swap_lock:
        shutil.rmtree(staging_root(root), ignore_errors=True)
    return status(root)
