"""Version-specific, offline XSD validation, separate from parsing and simulation."""
from __future__ import annotations

import argparse
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import os
from functools import lru_cache, partial
from itertools import islice
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname
from xml.etree import ElementTree as ET

from .asset_store import default_store_root
from .atomic_write import write_json

# Published ASAM schemas mirrored by esmini. Installation is explicit and local;
# no schema or network request is introduced into normal asset parsing. The pin is
# what the command line installs; the settings page can move to a newer revision.
SCHEMA_REVISION = "61b44a717d2ade513b4d66d1348b35c5d3dbdc3b"
ENTRIES = {
    **{f"OpenSCENARIO:{version}": f"OpenSCENARIOv{filename}.xsd" for version, filename in
       (("1.0", "1.0"), ("1.1", "1.1.1"), ("1.2", "1.2"), ("1.3", "1.3"), ("1.4", "1.4"))},
    "OpenDRIVE:1.4": "OpenDRIVE_1.4H.xsd",
    "OpenDRIVE:1.5": "OpenDRIVE_1.5.xsd",
    "OpenDRIVE:1.6": "OpenDRIVE_1.6/opendrive_16_core.xsd",
    "OpenDRIVE:1.7": "OpenDRIVE_1.7/localSchema/opendrive_17_core.xsd",
    "OpenDRIVE:1.8": "OpenDRIVE_1.8/local_schema/OpenDRIVE_Core.xsd",
}
VERDICTS = ".verdicts"  # kept validation results, inside the registry folder they were made with
VERDICT_FORMAT = 1  # raise when a kept verdict would no longer match what validate_xml returns
# Checking a file against its XSD is pure Python, so only separate processes check several at once.
# Starting one costs about a second (imports and compiling the schemas), so a few files stay in place.
CHECK_PROCESSES = max(1, min(8, (os.cpu_count() or 2) - 1))
FILES_PER_PROCESS = 16


def schema_root():
    return Path(os.environ.get("OPENX_SCHEMA_DIR") or default_store_root() / "schemas")


def registry_stamp(root=None):
    """Changes whenever a registry is installed, switched or rolled back; parsed assets carry its verdicts."""
    try:
        stat = ((Path(root) if root is not None else schema_root()) / "registry.json").stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size, stat.st_ino


def standard_gate(validation):
    """Both declared standards must pass before confirming direct reuse."""
    records = validation if isinstance(validation, dict) else {}
    checks = {role: records.get(role) if isinstance(records.get(role), dict) else {"status": "unavailable"}
              for role in ("scenario", "road")}
    pending = {role: record.get("status", "unavailable") for role, record in checks.items()
               if record.get("status") != "valid"}
    return {"passed": not pending, "pending": pending, "checks": checks}


@lru_cache(maxsize=1024)
def _resolved(path):
    # Resolving is a system call per path component on Windows; every validation checks every
    # registry file, so a library parse resolved the same few dozen paths thousands of times.
    return path.resolve()


def _local_path(root, name):
    path = _resolved(root / name)
    if not path.is_relative_to(_resolved(root)):
        raise ValueError("Schema path escapes its registry")
    return path


@lru_cache(maxsize=128)
def _file_digest(path, modified, size):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=20)
def _load_schema(path, checksum, xsd_version="1.0"):
    import xmlschema

    # Inspect every include before compilation: missing or forbidden includes
    # must not become a warning that silently weakens the installed standard.
    pending, visited = [Path(path)], set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        for reference in ET.parse(current).getroot().iter():
            url = reference.get("schemaLocation")
            if not url:
                continue
            parsed = urlsplit(url)
            if parsed.scheme == "file" and not parsed.netloc:
                candidate = Path(url2pathname(parsed.path)).resolve()
            elif Path(url).is_absolute():
                candidate = Path(url).resolve()
            elif parsed.scheme:
                raise ValueError("External schema reference is forbidden")
            else:
                candidate = (current.parent / url).resolve()
            if not candidate.is_relative_to(Path(path).parent.resolve()):
                raise ValueError("External schema reference is forbidden")
            pending.append(candidate)
    cls = xmlschema.XMLSchema11 if xsd_version == "1.1" else xmlschema.XMLSchema10
    return cls(path, base_url=Path(path).parent, allow="sandbox", defuse="always", use_fallback=False)


@lru_cache(maxsize=8)
def _manifest(root, raw):
    """The manifest read from `raw`, its schema files as checked local paths with their expected digests,
    and the manifest's own digest."""
    registry = json.loads(raw)
    files = tuple((str(_local_path(root, name)), expected) for name, expected in sorted(registry["sha256"].items()))
    return registry, files, hashlib.sha256(raw).hexdigest()


def _verified(root):
    """The manifest (shared: read it, never change it), one checksum over its schema files, each checked
    against it, and the manifest's own digest."""
    registry, files, manifest = _manifest(root, (root / "registry.json").read_bytes())
    digests = []
    for path, expected in files:
        # Validate all includes before compiling; preserve the exact source
        # revision in reports instead of silently switching schema versions.
        stat = os.stat(path)
        digest = _file_digest(path, stat.st_mtime_ns, stat.st_size)
        if digest != expected:
            raise ValueError("Installed XSD failed integrity verification")
        digests.append(digest)
    return registry, hashlib.sha256("".join(digests).encode()).hexdigest(), manifest


def _kept(root, data, checksum, manifest):
    """Where the verdict on these exact bytes is kept. It depends only on the file, the verified schemas,
    the manifest that routes versions to them and the validator, so a library is checked once, not on
    every service start; the folder moves with its registry when one is switched or rolled back."""
    import xmlschema
    identity = [hashlib.sha256(data).hexdigest(), checksum, manifest, xmlschema.__version__, VERDICT_FORMAT]
    return root / VERDICTS / (hashlib.sha256(json.dumps(identity).encode()).hexdigest() + ".json")


def validate_xml(data: bytes | str, *, root=None):
    root = Path(root) if root is not None else schema_root()
    data = data.encode("utf-8") if isinstance(data, str) else data
    try:
        return json.loads(_kept(root, data, *_verified(root)[1:]).read_bytes())
    except (ImportError, OSError, ValueError, KeyError, TypeError):
        pass  # not checked yet, or the registry is missing or broken: the full path below reports why
    result = {"status": "unavailable", "standard": None, "version": None, "issues": []}
    if b"<!DOCTYPE" in data.upper():
        return {**result, "status": "invalid", "issues": [{"line": 0, "message": "DTD declarations are not supported"}]}
    try:
        xml = ET.fromstring(data)
    except ET.ParseError as error:
        return {**result, "status": "invalid", "issues": [{"line": error.position[0], "message": str(error)}]}
    standard = xml.tag.rsplit("}", 1)[-1]
    header = next((node for node in xml if node.tag.rsplit("}", 1)[-1] == ("FileHeader" if standard == "OpenSCENARIO" else "header")), None)
    result["standard"] = standard
    if standard not in {"OpenSCENARIO", "OpenDRIVE"} or header is None:
        return {**result, "status": "invalid", "issues": [{"line": 0, "message": "Missing OpenX root or version header"}]}
    version = f"{header.get('revMajor', '')}.{header.get('revMinor', '')}"
    result["version"] = version
    key = standard + ":" + version
    manifest = root / "registry.json"
    if not manifest.is_file():
        return {**result, "detail": "No local XSD registry installed"}
    try:
        from lxml import etree
        import xmlschema
    except ImportError:
        return {**result, "detail": "Install OpenX dependencies to run XSD validation"}
    try:
        registry = json.loads(manifest.read_text(encoding="utf-8"))
        if key not in registry["entries"]:
            return {**result, "status": "unsupported", "detail": "No XSD installed for declared version"}
        entry = _local_path(root, registry["entries"][key])
        registry, checksum, manifest_digest = _verified(root)
        if entry.relative_to(_resolved(root)).as_posix() not in registry["sha256"]:
            raise ValueError("Schema entry is absent from its manifest")
        xsd_version = registry.get("xsd_versions", {}).get(key, "1.0")
        schema = _load_schema(str(entry), checksum, xsd_version)
        parsed = etree.fromstring(data, etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True))
        # lxml supplies source lines; xmlschema alone performs XSD validation,
        # including OpenDRIVE 1.8's XSD 1.1 assertions. No rules are stripped.
        errors = list(islice(schema.iter_errors(parsed, use_location_hints=False), 100))
        result["status"] = "invalid" if errors else "valid"
        result["issues"] = [{"line": e.sourceline or 0, "path": e.path, "message": e.reason} for e in errors]
        result.update(schema=registry["entries"][key], schema_sha256=registry["sha256"][registry["entries"][key]],
                      registry_sha256=checksum, source_revision=registry["revision"], xsd_version=xsd_version)
        kept = _kept(root, data, checksum, manifest_digest)
        try:
            kept.parent.mkdir(exist_ok=True)
            write_json(kept, result, ensure_ascii=False, prefix="verdict-", suffix=".tmp")
        except OSError:
            pass  # a read-only registry still validates, only without keeping the verdict
        return result
    except (etree.LxmlError, xmlschema.XMLSchemaException, ET.ParseError, OSError, ValueError, KeyError) as error:
        return {**result, "detail": str(error)}


def check_ahead(files: Iterable[bytes], *, root=None) -> int:
    """Check many files at once in worker processes and keep their verdicts, so the `validate_xml` calls
    that follow, one file at a time, find them. Returns how many files were checked here; a few files, a
    missing or broken registry or a failed worker leave the checking to those calls."""
    root = Path(root) if root is not None else schema_root()
    try:
        _, checksum, manifest = _verified(root)
        pending = {}
        for data in files:
            kept = _kept(root, data, checksum, manifest)
            if not kept.is_file():
                pending.setdefault(kept, data)
    except (ImportError, OSError, ValueError, KeyError, TypeError):
        return 0
    workers = min(CHECK_PROCESSES, len(pending) // FILES_PER_PROCESS)
    if workers < 2:
        return 0
    try:
        with ProcessPoolExecutor(workers) as pool:
            for _ in pool.map(partial(validate_xml, root=root), pending.values(),
                              chunksize=max(1, len(pending) // (workers * 4))):
                pass
    except Exception:  # noqa: BLE001 - a worker that fails leaves its files to be checked in place
        return 0
    return len(pending)


def install_schemas(root=None):
    """Install the pinned registry: staged, compiled, then switched in; the replaced one is kept for rollback."""
    from .schema_updates import install_pinned
    return install_pinned(Path(root) if root is not None else schema_root())


def main():
    parser = argparse.ArgumentParser(description="Offline OpenX XSD validation")
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--install-schemas", action="store_true")
    parser.add_argument("--schema-dir", type=Path)
    args = parser.parse_args()
    if args.install_schemas:
        install_schemas(args.schema_dir)
    results = {str(path): validate_xml(path.read_bytes(), root=args.schema_dir) for path in args.files}
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if any(result["status"] != "valid" for result in results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
