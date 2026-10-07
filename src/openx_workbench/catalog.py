from __future__ import annotations

import hashlib
import json
import posixpath
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .models import ParseBundle
from .parser import parse_bundle_without_road, parse_xosc
from .workflow import InputFile, inspect_pair

# Sidecar next to `<case>.xosc` with authoring-tool facts the scenario file
# leaves out (see sim_archive): the map name and environment presets.
CASE_METADATA_SUFFIX = ".case.json"


def case_metadata_name(xosc_name: str) -> str:
    """Name of the sidecar that keeps a SIM case's map and environment presets next to its XOSC."""
    return xosc_name[:-len(".xosc")] + CASE_METADATA_SUFFIX if xosc_name.casefold().endswith(".xosc") else ""


@dataclass(frozen=True, slots=True)
class AssetFile:
    name: str
    data: bytes


@dataclass(slots=True)
class OpenXAsset:
    asset_id: str
    title: str
    xosc_name: str
    xodr_name: str
    bundle: ParseBundle
    classification: dict[str, str] = field(default_factory=dict)


def build_catalog(files: list[AssetFile]) -> list[OpenXAsset]:
    """Build paired OpenSCENARIO/OpenDRIVE assets from a file collection.

    A scenario with a `.case.json` sidecar (an expanded SIM case) whose road file
    is unavailable is still cataloged, with its road marked missing.
    """

    cases = {item.name.replace("\\", "/").casefold(): item for item in files
             if item.name.casefold().endswith(CASE_METADATA_SUFFIX)}
    roads = [item for item in files if item.name.casefold().endswith(".xodr")]
    roads_by_path = {item.name.replace("\\", "/").casefold(): item for item in roads}
    roads_by_basename: dict[str, list[AssetFile]] = {}
    for road in roads:
        roads_by_basename.setdefault(
            PurePosixPath(road.name.replace("\\", "/")).name.casefold(), []
        ).append(road)
    assets: list[OpenXAsset] = []

    for scenario_file in sorted(
        (item for item in files if item.name.casefold().endswith(".xosc")),
        key=lambda item: item.name.casefold(),
    ):
        scenario = parse_xosc(scenario_file.data)
        sidecar = cases.get(case_metadata_name(scenario_file.name.replace("\\", "/")).casefold())
        case = json.loads(sidecar.data.decode("utf-8")) if sidecar else {}
        if not scenario.road_file and not case:
            raise ValueError(f"{scenario_file.name} does not reference an OpenDRIVE file.")
        reference = (scenario.road_file or "").replace("\\", "/")
        road_name = PurePosixPath(reference).name
        relative = posixpath.normpath(posixpath.join(
            posixpath.dirname(scenario_file.name.replace("\\", "/")), reference
        ))
        road_file = roads_by_path.get(relative.casefold()) if road_name else None
        if road_file is None and road_name:
            matches = roads_by_basename.get(road_name.casefold(), [])
            if len(matches) > 1:
                raise ValueError(f"{scenario_file.name} has ambiguous road reference {scenario.road_file}.")
            road_file = matches[0] if matches else None
        if road_file is None and not case:
            raise ValueError(f"{scenario_file.name} references missing road file {road_name}.")

        if road_file is None:
            bundle = parse_bundle_without_road(
                scenario_file.data, (case.get("map_id"), case.get("map_name")), case)
        else:
            bundle = inspect_pair(
                InputFile(scenario_file.name, scenario_file.data),
                InputFile(road_file.name, road_file.data),
                case,
            )
        digest = hashlib.sha256(
            scenario_file.name.encode("utf-8") + b"\0" + scenario_file.data
        ).hexdigest()[:12]
        assets.append(
            OpenXAsset(
                asset_id=digest,
                title=bundle.scenario.name or Path(scenario_file.name).stem,
                xosc_name=scenario_file.name,
                xodr_name=road_file.name if road_file else "",
                bundle=bundle,
            )
        )
    return assets


def build_catalog_from_directory(root: Path) -> list[OpenXAsset]:
    files = [
        AssetFile(path.relative_to(root).as_posix(), path.read_bytes())
        for path in root.rglob("*")
        if path.is_file() and path.suffix.casefold() in {".xosc", ".xodr"}
    ]
    return build_catalog(files)
