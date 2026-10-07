from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

from .catalog import AssetFile, case_metadata_name

SCENARIO_ROOT_ORDER = ("FileHeader", "ParameterDeclarations", "VariableDeclarations",
                       "CatalogLocations", "RoadNetwork", "Entities", "Storyboard")


@dataclass(frozen=True, slots=True)
class SimImportReport:
    source_name: str
    case_count: int
    imported_count: int
    contained_road_count: int
    missing_road_references: tuple[str, ...]
    # Imported cases whose road is still missing: matchable, not previewable.
    road_missing_count: int = 0


def expand_sim_archives(files: list[AssetFile]) -> tuple[list[AssetFile], list[SimImportReport]]:
    """Expand `.sim` ZIP containers into pairable XOSC/XODR asset files.

    Standalone XODR uploads supplement roads omitted from a SIM archive. Cases whose
    referenced road is still unavailable (a simulator built-in map) are reported but
    still imported: each case's map name and environment presets travel in a
    `.case.json` sidecar, and the catalog marks the road file as missing.
    """

    regular = [item for item in files if not item.name.casefold().endswith(".sim")]
    supplemental_roads = {
        PurePosixPath(item.name.replace("\\", "/")).name.casefold(): item
        for item in regular
        if item.name.casefold().endswith(".xodr")
    }
    expanded = list(regular)
    reports: list[SimImportReport] = []
    for sim_file in (item for item in files if item.name.casefold().endswith(".sim")):
        sim_assets, report = _expand_sim(sim_file, supplemental_roads)
        expanded.extend(sim_assets)
        reports.append(report)
    return expanded, reports


def _expand_sim(
    sim_file: AssetFile,
    supplemental_roads: dict[str, AssetFile],
) -> tuple[list[AssetFile], SimImportReport]:
    with zipfile.ZipFile(io.BytesIO(sim_file.data)) as archive:
        contained_road_files: list[AssetFile] = []
        contained_roads: dict[str, AssetFile] = {}
        for name in archive.namelist():
            if not name.casefold().endswith(".xodr"):
                continue
            path = PurePosixPath(name)
            logical_name = _logical_road_name(path)
            road = AssetFile(logical_name, archive.read(name))
            contained_road_files.append(road)
            contained_roads[path.name.casefold()] = road
            contained_roads[logical_name.casefold()] = road

        roads = {**supplemental_roads, **contained_roads}
        case_names = [
            name for name in archive.namelist()
            if "/case/" in name and name.casefold().endswith(".json")
        ]
        assets: list[AssetFile] = list(contained_road_files)
        missing: set[str] = set()
        imported = road_missing = 0
        sim_stem = PurePosixPath(sim_file.name.replace("\\", "/")).stem

        for index, case_name in enumerate(case_names, start=1):
            payload = json.loads(archive.read(case_name).decode("utf-8"))
            case_def = payload.get("caseDef") or {}
            case_data = payload.get("caseData") or {}
            open_scenario = case_data.get("openSCENARIO") or {}
            road_ref = (
                (open_scenario.get("RoadNetwork") or {})
                .get("LogicFile", {})
                .get("filepath", "")
            )
            road_key = PurePosixPath(str(road_ref).replace("\\", "/")).name.casefold()
            has_road = bool(road_key) and road_key in roads
            if not has_road:
                missing.add(str(road_ref) or "<unspecified>")
                road_missing += 1

            case_id = str(case_def.get("id") or f"case-{index:04d}")
            case_title = str(case_def.get("name") or case_id)
            xosc_name = f"{sim_stem}/{case_id}.xosc"
            assets.append(AssetFile(xosc_name, _osc_json_to_xml(open_scenario, case_title)))
            assets.append(AssetFile(case_metadata_name(xosc_name), _case_metadata(
                case_id, case_def, case_data, str(road_ref), road_missing=not has_road)))
            imported += 1

    return assets, SimImportReport(
        source_name=sim_file.name,
        case_count=len(case_names),
        imported_count=imported,
        contained_road_count=len(contained_road_files),
        missing_road_references=tuple(sorted(missing, key=str.casefold)),
        road_missing_count=road_missing,
    )


def _case_metadata(case_id: str, case_def: dict, case_data: dict, road_reference: str,
                   *, road_missing: bool) -> bytes:
    """Case facts the OpenSCENARIO JSON leaves out: the map, the environment presets, the scoring.

    ScenarioManager keeps weather and time of day as presets in
    `caseData.environments` unless the story sets them with an EnvironmentAction,
    and what a run is scored by in `caseData.judgements`.
    """
    environments = case_data.get("environments") or {}
    by_id = environments.get("byId") or {}
    metadata = {
        "case_id": case_id,
        "map_id": str(case_def.get("mapId") or ""),
        "map_name": str(case_def.get("mapName") or ""),
        "road_reference": road_reference,
        "road_missing": road_missing,
        "environments": [by_id[key] for key in environments.get("allIds") or []
                         if isinstance(by_id.get(key), dict)],
        "current_environment_id": case_data.get("currEnvId"),
        "judgements": _judgements(case_data),
    }
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _judgements(case_data: dict) -> list[dict]:
    """The case's scoring criteria in authoring order, without the editor's bookkeeping.

    A criterion has a type (timeout, collision, offtrack, stopandgo, customized), conditions
    on a variable (dtlc gt 1.75, lonacc lt -5), the region it applies to and what a hit does.
    """
    judgements = case_data.get("judgements") or {}
    by_id = judgements.get("byId") or {}
    items = (by_id.get(key) for key in judgements.get("allIds") or by_id)
    return [{"type": str(item.get("type") or ""), "name": str(item.get("name") or ""),
             "enabled": item.get("enabled") is not False,
             "scope": str((item.get("scope") or {}).get("type") or ""),
             "conditions": [condition for condition in item.get("conditions") or []
                            if isinstance(condition, dict)],
             "action": str((item.get("settings") or {}).get("action") or "")}
            for item in items if isinstance(item, dict)]


def _logical_road_name(path: PurePosixPath) -> str:
    """Return the road name used by ScenarioManager case references.

    ScenarioManager stores a road under ``map/<map-id>/<display-name>.xodr``
    while OpenSCENARIO refers to it as ``<map-id>.xodr``. Preserve that logical
    identity so the extracted XOSC can be paired with the embedded road.
    """

    parts = path.parts
    for index, part in enumerate(parts[:-1]):
        if part.casefold() == "map" and index + 2 < len(parts):
            return f"{parts[index + 1]}.xodr"
    return path.name


def _osc_json_to_xml(open_scenario: dict, case_title: str) -> bytes:
    root = ET.Element("OpenSCENARIO")
    # JSON object order is not semantic, while the scenario's XML root is an
    # ordered sequence. Parameter editing in 51sim can append declarations last.
    order = SCENARIO_ROOT_ORDER
    for tag in (*order, *(key for key in open_scenario if key not in order)):
        if tag in open_scenario:
            _append_xml(root, str(tag), open_scenario[tag])
    header = root.find("FileHeader")
    if header is None:
        header = ET.Element("FileHeader")
        root.insert(0, header)
    header.set("description", case_title)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _append_xml(parent: ET.Element, tag: str, value: object) -> None:
    if isinstance(value, list):
        for item in value:
            _append_xml(parent, tag, item)
        return

    node = ET.SubElement(parent, tag)
    if not isinstance(value, dict):
        if value is not None:
            node.text = _scalar(value)
        return

    for key, child in value.items():
        if isinstance(child, (dict, list)):
            _append_xml(node, str(key), child)
        elif tag == "CustomCommandAction" and key == "content" and child is not None:
            # The SIM JSON stores command text as a field; OpenSCENARIO's
            # simpleContent type carries it as element text, not an attribute.
            node.text = _scalar(child)
        elif child is not None:
            node.set(str(key), _scalar(child))


def _scalar(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)
