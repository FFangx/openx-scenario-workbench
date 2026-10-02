"""Audited SIM export copies; originals and unsupported extensions are retained."""
from dataclasses import dataclass
import hashlib
import io
import json
import re
import zipfile

from lxml import etree

from .schema_validation import standard_gate, validate_xml
from .sim_archive import SCENARIO_ROOT_ORDER

EXPORT_VERSION = "sim-standard-copy-1"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class StandardExport:
    scenario: bytes
    road: bytes
    original_scenario: bytes
    original_road: bytes
    source: bytes
    audit: dict

    @property
    def ready(self):
        return self.audit["ready"]

    def package(self, *, diagnostic=False):
        if not self.ready and not diagnostic:
            raise ValueError("标准副本未通过检查，仅可下载诊断包 / Standard copy is not ready; download a diagnostic package.")
        folder = "candidate" if diagnostic else "standard"
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in {
                f"{folder}/scenario.xosc": self.scenario, f"{folder}/road.xodr": self.road,
                "original/scenario.xosc": self.original_scenario,
                "original/road.xodr": self.original_road, "original/source.sim": self.source,
                "audit.json": json.dumps(self.audit, ensure_ascii=False, indent=2).encode("utf-8"),
            }.items():
                archive.writestr(name, data)
        return output.getvalue()


def build_standard_export(store, version):
    if not version.source_name.casefold().endswith(".sim"):
        raise ValueError("此导出仅用于 SIM 资产 / This export is for SIM assets.")
    originals = {role: store.file_bytes(version, role) for role in ("scenario", "road", "source")}
    changes, unresolved = [], []

    def parse(data):
        if b"<!DOCTYPE" in data.upper():
            raise ValueError("DTD declarations are not supported")
        return etree.fromstring(data, etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True))

    scenario, road = parse(originals["scenario"]), parse(originals["road"])

    def tag(node):
        return etree.QName(node).localname if node is not None and isinstance(node.tag, str) else ""

    def change(node, field, before, after, rule):
        changes.append({"path": node.getroottree().getpath(node), "field": field,
                        "before": before, "after": after, "rule": rule})

    children = list(scenario)
    ordered = sorted(children, key=lambda n: SCENARIO_ROOT_ORDER.index(tag(n))
                     if tag(n) in SCENARIO_ROOT_ORDER else len(SCENARIO_ROOT_ORDER))
    if children != ordered:
        change(scenario, "children", [tag(n) for n in children], [tag(n) for n in ordered], "scenario_root_sequence")
        scenario[:] = ordered
    for container in scenario.iter():
        if tag(container) != "ParameterDeclarations":
            continue
        declarations = [n for n in container if tag(n) == "ParameterDeclaration"]
        names = [n.get("name", "").removeprefix("$") for n in declarations]
        for node in declarations:
            name = node.get("name", "")
            if not re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*", name):
                continue
            if names.count(name[1:]) != 1:
                unresolved.append({"path": node.getroottree().getpath(node), "reason": "ambiguous_parameter_name"})
                continue
            change(node, "name", name, name[1:], "parameter_reference_marker")
            node.set("name", name[1:])
    referenced_labels = {n.get("storyboardElementRef") for n in scenario.iter() if n.get("storyboardElementRef")}
    standard_action_names = {n.get("name") for n in scenario.iter() if tag(n) == "Action"}
    for node in scenario.iter():
        if tag(node) == "PrivateAction" and "name" in node.attrib:
            if node.get("name") in referenced_labels - standard_action_names:
                unresolved.append({"path": node.getroottree().getpath(node), "reason": "referenced_private_action_label"})
                continue
            change(node, "name", node.get("name"), None, "nonstandard_private_action_label_to_audit")
            del node.attrib["name"]
        if tag(node) == "CustomCommandAction" and "content" in node.attrib:
            content = node.get("content")
            if node.text and node.text != content:
                unresolved.append({"path": node.getroottree().getpath(node), "reason": "conflicting_command_content"})
                continue
            change(node, "content", content, content, "command_attribute_to_text")
            node.text = content
            del node.attrib["content"]
        if tag(node) == "LogicFile" and tag(node.getparent()) == "RoadNetwork":
            if node.get("filepath") != "road.xodr":
                change(node, "filepath", node.get("filepath"), "road.xodr", "bundled_road_reference")
                node.set("filepath", "road.xodr")
    # An omitted side and an empty side both describe zero lanes. Remove only
    # empty optional groups; never synthesize lanes, geometry or controller data.
    for node in list(road.iter()):
        if tag(node) in {"left", "right"} and tag(node.getparent()) == "laneSection":
            if not node.attrib and not len(node) and not (node.text or "").strip():
                change(node, "element", tag(node), None, "empty_optional_lane_side")
                node.getparent().remove(node)
    external = []
    for role, root in (("scenario", scenario), ("road", road)):
        for node in root.iter():
            if not isinstance(node.tag, str) or (tag(node) == "LogicFile" and tag(node.getparent()) == "RoadNetwork"):
                continue
            for field in ("filepath", "filePath", "path", "file", "model3d", "uri"):
                if node.get(field):
                    external.append({"role": role, "path": root.getroottree().getpath(node),
                                     "field": field, "reference": node.get(field)})
    extension_points = [{"path": scenario.getroottree().getpath(n), "type": n.get("type", "")}
                        for n in scenario.iter() if tag(n) == "CustomCommandAction"]
    candidate = {"scenario": etree.tostring(scenario, encoding="utf-8", xml_declaration=True),
                 "road": etree.tostring(road, encoding="utf-8", xml_declaration=True)}
    validation = {role: validate_xml(data) for role, data in candidate.items()}
    gate = standard_gate(validation)
    from .parser import parse_xosc
    parameter_issues = parse_xosc(candidate["scenario"]).parameter_issues
    audit = {"export_version": EXPORT_VERSION, "asset_id": version.asset_id, "version_id": version.version_id,
             "content_sha256": version.content_sha256, "source_name": version.source_name,
             "original_sha256": {role: _sha(data) for role, data in originals.items()},
             "export_sha256": {role: _sha(data) for role, data in candidate.items()},
             "original_validation": {role: validate_xml(originals[role]) for role in candidate},
             "validation": validation, "standard_checks": gate, "changes": changes,
             "unresolved": unresolved, "external_dependencies": external,
             "runtime_extension_points": extension_points,
             "parameter_issues": parameter_issues,
             "ready": gate["passed"] and not unresolved and not external and not parameter_issues,
             "scope": "XSD-checked copy; simulation behavior and private SIM metadata are not certified. Unsupported extensions remain in the candidate and original archive."}
    return StandardExport(candidate["scenario"], candidate["road"], originals["scenario"],
                          originals["road"], originals["source"], audit)
