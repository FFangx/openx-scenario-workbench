"""Previews for the whole library: an esmini frame of every version and a drawing of its road from above.

The road drawing needs no simulator: it is drawn from the OpenDRIVE reference lines and lane widths
(road_geometry), with where each participant starts. Frames come from the worker a single preview
uses (esmini_preview), one version at a time, so the computer stays usable; the job stops between
versions and skips versions that already have a frame. A version whose road was not imported has
neither.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import time
from pathlib import Path
from threading import Event
from typing import Any

from . import jobs
from .asset_store import AssetStore, AssetVersion
from .atomic_write import write_bytes
from .esmini_preview import find_esmini, record_outcome, start_preview
from .models import ParseBundle
from .preferences import read_preferences
from .preview_frames import read_frame
from .road_geometry import LaneSection, RoadReferenceLine
from .scene_facts import _world_pose

KIND = "preview_batch"
DRAWING = 1  # bump when the drawing changes, so saved drawings are made again
SIZE = (640, 400)
MARGIN = 18
CLOSE_UP = 400.0  # metres: a larger road network is shown around where the participants start
SURROUNDINGS = 80.0  # metres kept around the participants in a close-up
CAPTURE_SECONDS = 2  # esmini runs this long; the still frame is the tenth (1 s simulated)
CAPTURE_TIMEOUT = 40.0

BACKGROUND, ASPHALT, LINE, CENTRE = (32, 36, 42), (74, 80, 90), (196, 202, 210), (226, 190, 80)
COLOURS = {"ego": (79, 140, 255), "vehicle": (240, 160, 64), "vru": (76, 195, 138), "object": (160, 164, 171)}


# ---------- the road from above ----------

Line = list[tuple[float, float]]


def _borders(section: LaneSection, s: float) -> tuple[list[float], int]:
    """Signed lateral offsets of the section's lane borders at `s`, right to left, and which one is the
    reference line."""
    offset_in = s - section.s
    right, left = [], []
    for step, side in ((1, left), (-1, right)):
        total, lane = 0.0, step
        while (entries := section.widths.get(lane)):
            entry = next((item for item in reversed(entries) if item.s_offset <= offset_in), entries[0])
            total += max(0.0, entry.at(offset_in))
            side.append(step * total)
            lane += step
    return [*reversed(right), 0.0, *left], len(right)


def _road_lines(road: RoadReferenceLine) -> list[tuple[list[Line], int]]:
    """Per lane section, its lane borders as world polylines (right to left) and the reference line's index."""
    if not road.segments or road.length <= 0:
        return []
    sections = road.lane_sections or [LaneSection(0.0, {})]
    step = max(0.5, road.length / 600)
    result = []
    for number, section in enumerate(sections):
        start = max(0.0, section.s)
        end = min(road.length, sections[number + 1].s if number + 1 < len(sections) else road.length)
        if end <= start:
            continue
        count = max(2, math.ceil((end - start) / step) + 1)
        lines: list[Line] = []
        reference = 0
        for index in range(count):
            s = start + (end - start) * index / (count - 1)
            offsets, reference = _borders(section, s)
            if not lines:
                lines = [[] for _ in offsets]
            for line, offset in zip(lines, offsets):
                pose = road.world_from_road(s, offset)
                if pose is not None:
                    line.append(pose[:2])
        result.append((lines, reference))
    return result


def _participants(bundle: ParseBundle) -> list[tuple[str, float, float, float]]:
    """Where each participant starts: its role colour, world x, y and heading."""
    kinds = {entity.name: entity for entity in bundle.scenario.entities}
    seen, result = set(), []
    for position in bundle.scenario.positions:
        actor = position.actor or ""
        if actor in seen:
            continue
        pose = _world_pose(position, bundle.road_geometry)
        if pose is None:
            continue
        seen.add(actor)
        entity = kinds.get(actor)
        kind = (entity.kind if entity else "").casefold()
        category = (entity.category or "" if entity else "").casefold()
        role = ("ego" if actor.casefold() == "ego" else "object" if kind == "miscobject"
                else "vru" if kind == "pedestrian" or category in {"bicycle", "motorbike", "pedestrian"} else "vehicle")
        result.append((role, *pose))
    return result


def draw_road(bundle: ParseBundle) -> bytes | None:
    """A PNG of the road network from above with where the participants start; None without a road."""
    from PIL import Image, ImageDraw

    drawn = [(road, lines, reference) for road in bundle.road_geometry.values()
             for lines, reference in _road_lines(road)]
    points = [point for _, lines, _ in drawn for line in lines for point in line]
    if not points:
        return None
    starts = _participants(bundle)
    xs, ys = [x for x, _ in points], [y for _, y in points]
    left, right, bottom, top = min(xs), max(xs), min(ys), max(ys)
    if max(right - left, top - bottom) > CLOSE_UP and starts:
        sx, sy = [item[1] for item in starts], [item[2] for item in starts]
        left, right = max(left, min(sx) - SURROUNDINGS), min(right, max(sx) + SURROUNDINGS)
        bottom, top = max(bottom, min(sy) - SURROUNDINGS), min(top, max(sy) + SURROUNDINGS)
    width, height = SIZE
    scale = min((width - 2 * MARGIN) / max(right - left, 1.0), (height - 2 * MARGIN) / max(top - bottom, 1.0))
    cx, cy = (left + right) / 2, (bottom + top) / 2

    def pixel(x: float, y: float) -> tuple[float, float]:
        return width / 2 + (x - cx) * scale, height / 2 - (y - cy) * scale

    image = Image.new("RGB", SIZE, BACKGROUND)
    canvas = ImageDraw.Draw(image)
    for _, lines, _ in drawn:
        for right_border, left_border in zip(lines, lines[1:]):  # neighbouring borders enclose one lane
            if len(right_border) == len(left_border) > 1:
                canvas.polygon([pixel(*p) for p in right_border + left_border[::-1]], fill=ASPHALT)
    for road, lines, reference in drawn:
        if road.junction != "-1":
            continue  # lanes through a junction overlap; the asphalt says enough
        both_ways = 0 < reference < len(lines) - 1
        for index, line in enumerate(lines):
            if len(line) > 1:
                centre = both_ways and index == reference
                canvas.line([pixel(*p) for p in line], fill=CENTRE if centre else LINE, width=2 if centre else 1)
    # Scenery first and as dots (a construction zone has dozens of cones), the ego last, on top.
    for role, x, y, heading in sorted(starts, key=lambda item: (item[0] != "object", item[0] == "ego")):
        px, py = pixel(x, y)
        if role == "object":
            canvas.ellipse((px - 2.5, py - 2.5, px + 2.5, py + 2.5), fill=COLOURS[role])
            continue
        size = max(9.0, 2.4 * scale)
        tip = (px + size * math.cos(heading), py - size * math.sin(heading))
        back = [(px - size * 0.6 * math.cos(heading) + side * size * 0.55 * math.sin(heading),
                 py + size * 0.6 * math.sin(heading) + side * size * 0.55 * math.cos(heading)) for side in (1, -1)]
        canvas.polygon([tip, *back], fill=COLOURS[role], outline=(20, 22, 26))
    output = io.BytesIO()
    image.save(output, "PNG", optimize=True)
    return output.getvalue()


def drawing_path(store: AssetStore, version: AssetVersion) -> Path:
    identity = json.dumps([version.asset_id, version.version_id, version.content_sha256, DRAWING])
    return store.root / "road_drawings" / (hashlib.sha256(identity.encode()).hexdigest() + ".png")


def road_drawing(store: AssetStore, version: AssetVersion) -> bytes | None:
    """The saved drawing of the version's road, drawn and saved first when there is none yet."""
    if version.road_missing:
        return None
    path = drawing_path(store, version)
    if path.is_file():
        return path.read_bytes()
    data = draw_road(store.load_asset(version).bundle)
    if data is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_bytes(path, data, prefix="drawing-", suffix=".tmp")
    return data


# ---------- esmini frames for the whole library ----------

def capture(store: AssetStore, version: AssetVersion, executable: Path, cancel: Event) -> str:
    """Run esmini briefly for one version, save its still frame and record the outcome on the version."""
    try:
        preview = start_preview(store, version, executable, duration=CAPTURE_SECONDS)
    except Exception as error:  # noqa: BLE001 - every start failure is the version's preview outcome
        store.set_compatibility(version, "failed", str(error))
        return "failed"
    try:
        deadline = time.monotonic() + CAPTURE_TIMEOUT
        while (status := preview.status())["state"] not in {"finished", "failed", "stopped"}:
            if time.monotonic() > deadline:
                store.set_compatibility(version, "timeout", "esmini did not finish a short capture in time.")
                return "timeout"
            if cancel.wait(0.3):
                raise InterruptedError()
        return record_outcome(store, version, status)
    finally:
        preview.stop()


def _work(store: AssetStore, retry_failed: bool):
    def work(job: jobs.Job) -> dict[str, Any]:
        versions = sorted(store.latest(), key=lambda item: (item.source_name, item.title))
        executable = find_esmini(str(read_preferences().get("esmini_path", "")))
        if executable is None:
            job.note("尚未找到 esmini：只画道路图 / esmini not found: drawing roads only")
        counts = {"frames": 0, "failed": 0, "kept": 0, "road_missing": 0, "drawings": 0}
        job.update(stage="previewing", total=len(versions))
        for index, version in enumerate(versions):
            job.check()
            job.update(done=index, current=version.title or version.xosc_name)
            if version.road_missing:
                counts["road_missing"] += 1
                continue
            if road_drawing(store, version) is not None:
                counts["drawings"] += 1
            if executable is None:
                continue
            if read_frame(store, version) or (version.compatibility in {"failed", "timeout"} and not retry_failed):
                counts["kept"] += 1
                continue
            outcome = capture(store, version, executable, job.cancel)
            counts["frames" if outcome == "playable" else "failed"] += 1
            job.update(done=index + 1, result=dict(counts))
        job.update(done=len(versions))
        return counts
    return work


def _scope(store: AssetStore) -> str:
    return str(store.root.resolve())


def start(store: AssetStore, *, retry_failed: bool = False) -> jobs.Job:
    """One preview run per data folder; a second request while one runs is refused."""
    if jobs.running(KIND, _scope(store)):
        raise ValueError("预览已在生成中 / Previews are already being made.")
    return jobs.start(jobs.Job(KIND, _scope(store)), _work(store, retry_failed))


def latest(store: AssetStore) -> jobs.Job | None:
    return jobs.latest(KIND, _scope(store))
