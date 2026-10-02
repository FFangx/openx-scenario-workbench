from __future__ import annotations

import hashlib
import posixpath
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .models import ParseBundle
from .parser import parse_xosc
from .workflow import InputFile, inspect_pair


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
    """Build paired OpenSCENARIO/OpenDRIVE assets from a file collection."""

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
        if not scenario.road_file:
            raise ValueError(f"{scenario_file.name} does not reference an OpenDRIVE file.")
        reference = scenario.road_file.replace("\\", "/")
        road_name = PurePosixPath(reference).name
        relative = posixpath.normpath(posixpath.join(
            posixpath.dirname(scenario_file.name.replace("\\", "/")), reference
        ))
        road_file = roads_by_path.get(relative.casefold())
        if road_file is None:
            matches = roads_by_basename.get(road_name.casefold(), [])
            if len(matches) > 1:
                raise ValueError(f"{scenario_file.name} has ambiguous road reference {scenario.road_file}.")
            road_file = matches[0] if matches else None
        if road_file is None:
            raise ValueError(f"{scenario_file.name} references missing road file {road_name}.")

        bundle = inspect_pair(
            InputFile(scenario_file.name, scenario_file.data),
            InputFile(road_file.name, road_file.data),
        )
        digest = hashlib.sha256(
            scenario_file.name.encode("utf-8") + b"\0" + scenario_file.data
        ).hexdigest()[:12]
        assets.append(
            OpenXAsset(
                asset_id=digest,
                title=bundle.scenario.name or Path(scenario_file.name).stem,
                xosc_name=scenario_file.name,
                xodr_name=road_file.name,
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
