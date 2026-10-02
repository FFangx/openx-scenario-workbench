"""Version-specific, offline XSD validation, separate from parsing and simulation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from functools import lru_cache
from itertools import islice
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen, url2pathname
from xml.etree import ElementTree as ET

from .asset_store import default_store_root

# Published ASAM schemas mirrored by esmini. Installation is explicit and local;
# no schema or network request is introduced into normal asset parsing.
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


def schema_root():
    return Path(os.environ.get("OPENX_SCHEMA_DIR") or default_store_root() / "schemas")


def standard_gate(validation):
    """Both declared standards must pass before confirming direct reuse."""
    records = validation if isinstance(validation, dict) else {}
    checks = {role: records.get(role) if isinstance(records.get(role), dict) else {"status": "unavailable"}
              for role in ("scenario", "road")}
    pending = {role: record.get("status", "unavailable") for role, record in checks.items()
               if record.get("status") != "valid"}
    return {"passed": not pending, "pending": pending, "checks": checks}


def _local_path(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
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


def validate_xml(data: bytes | str, *, root=None):
    root = Path(root) if root is not None else schema_root()
    data = data.encode("utf-8") if isinstance(data, str) else data
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
        digests = []
        for name, expected in sorted(registry["sha256"].items()):
            # Validate all includes before compiling; preserve the exact source
            # revision in reports instead of silently switching schema versions.
            path = _local_path(root, name)
            stat = path.stat()
            digest = _file_digest(str(path), stat.st_mtime_ns, stat.st_size)
            if digest != expected:
                raise ValueError("Installed XSD failed integrity verification")
            digests.append(digest)
        if entry.relative_to(root.resolve()).as_posix() not in registry["sha256"]:
            raise ValueError("Schema entry is absent from its manifest")
        checksum = hashlib.sha256("".join(digests).encode()).hexdigest()
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
        return result
    except (etree.LxmlError, xmlschema.XMLSchemaException, ET.ParseError, OSError, ValueError, KeyError) as error:
        return {**result, "detail": str(error)}


def install_schemas(root=None):
    """Download a pinned registry to machine-local storage, including all includes."""
    root = Path(root) if root is not None else schema_root()
    base = f"https://raw.githubusercontent.com/esmini/esmini/{SCHEMA_REVISION}/resources/schema/"
    names = set(ENTRIES.values())
    for prefix, stem in (("OpenDRIVE_1.6/", "opendrive_16_"), ("OpenDRIVE_1.7/localSchema/", "opendrive_17_"),
                         ("OpenDRIVE_1.8/local_schema/", "OpenDRIVE_")):
        names.update(prefix + stem + part + ".xsd" for part in
                     ([p.capitalize() for p in ("core", "junction", "lane", "object", "railroad", "road", "signal")] if "1.8" in prefix
                      else ("core", "junction", "lane", "object", "railroad", "road", "signal")))
    digests = {}
    root.mkdir(parents=True, exist_ok=True)
    for name in sorted(names):
        with urlopen(base + name, timeout=30) as response:
            data = response.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise ValueError("Schema exceeds size limit")
        path = _local_path(root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        digests[name] = hashlib.sha256(data).hexdigest()
    xsd_versions = {"OpenDRIVE:1.8": "1.1"}
    # Publish a registry only after every installed standard compiles.
    checksum = hashlib.sha256("".join(digests[name] for name in sorted(digests)).encode()).hexdigest()
    for key, name in ENTRIES.items():
        _load_schema(str(_local_path(root, name)), checksum, xsd_versions.get(key, "1.0"))
    registry = {"revision": SCHEMA_REVISION, "source": base, "entries": ENTRIES, "sha256": digests, "xsd_versions": xsd_versions}
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=root, delete=False) as stream:
        json.dump(registry, stream, indent=2)
        temporary = Path(stream.name)
    temporary.replace(root / "registry.json")
    return registry


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
