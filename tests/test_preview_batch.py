"""Previews for the whole library: road drawings from the OpenDRIVE geometry, and one esmini capture per
version (a stand-in here, no simulator)."""
import io
from dataclasses import replace
import threading
import time
from pathlib import Path

import pytest

from openx_workbench import import_jobs, jobs, preview_batch
from openx_workbench.asset_store import AssetStore
from openx_workbench.catalog import AssetFile, build_catalog
from openx_workbench.preferences import save_preferences
from openx_workbench.preview_frames import frame_path, save_frame

FIXTURES = Path(__file__).parent / "fixtures"
JPEG = b"\xff\xd8 frame \xff\xd9"


def two_lane_road() -> bytes:
    """The fixture road with a 3.5 m lane each way."""
    road = (FIXTURES / "minimal.xodr").read_text(encoding="utf-8")
    for lane in ("1", "-1"):
        road = road.replace(f'<lane id="{lane}" type="driving" level="false"/>',
                            f'<lane id="{lane}" type="driving" level="false"><width sOffset="0" a="3.5" b="0" c="0" d="0"/></lane>')
    return road.encode("utf-8")


def files(name="minimal.xosc"):
    return [AssetFile(name, (FIXTURES / "minimal.xosc").read_bytes()), AssetFile("minimal.xodr", two_lane_road())]


def finished(job):
    for _ in range(500):
        if job.snapshot()["status"] != "running":
            return job.snapshot()
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_the_road_is_drawn_from_above_with_the_ego_where_it_starts():
    from PIL import Image

    bundle = build_catalog(files())[0].bundle
    image = Image.open(io.BytesIO(preview_batch.draw_road(bundle)))
    assert image.size == preview_batch.SIZE
    colours = {colour for _, colour in image.getcolors(1 << 16)}
    assert preview_batch.ASPHALT in colours and preview_batch.CENTRE in colours  # a lane each way
    assert preview_batch.COLOURS["ego"] in colours
    assert preview_batch.draw_road(replace(bundle, road_geometry={})) is None


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    store = AssetStore()
    versions = [store.import_files(files(f"case{number}.xosc"))[0] for number in range(3)]
    return store, versions


def test_a_drawing_is_kept_and_a_version_without_a_road_has_none(library):
    store, versions = library
    data = preview_batch.road_drawing(store, versions[0])
    assert data.startswith(b"\x89PNG") and preview_batch.drawing_path(store, versions[0]).read_bytes() == data
    assert preview_batch.road_drawing(store, replace(versions[0], files=())) is None


def test_one_run_captures_what_has_no_frame_and_keeps_the_rest(library, monkeypatch):
    store, versions = library
    save_frame(frame_path(store, versions[0]), JPEG, 10)  # already has a frame
    store.set_compatibility(versions[1], "failed", "esmini rejected the scenario.")
    captured = []

    def capture(store, version, executable, cancel):
        captured.append(version.asset_id)
        return "playable"
    monkeypatch.setattr(preview_batch, "find_esmini", lambda value: Path("esmini.exe"))
    monkeypatch.setattr(preview_batch, "capture", capture)
    result = finished(preview_batch.start(store))
    assert result["status"] == "completed" and captured == [versions[2].asset_id]
    assert result["result"] == {"frames": 1, "failed": 0, "kept": 2, "road_missing": 0, "drawings": 3}

    captured.clear()
    again = finished(preview_batch.start(store, retry_failed=True))
    assert sorted(captured) == sorted([versions[1].asset_id, versions[2].asset_id]) and again["result"]["frames"] == 2


@pytest.fixture
def larger_library(tmp_path, monkeypatch):
    """Twice as many versions without a frame as captures run at once."""
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(preview_batch, "find_esmini", lambda value: Path("esmini.exe"))
    store = AssetStore()
    for number in range(2 * preview_batch.CAPTURES_AT_ONCE):
        store.import_files(files(f"case{number}.xosc"))
    return store


def test_several_captures_run_at_once_and_no_more(larger_library, monkeypatch):
    # The run only completes when CAPTURES_AT_ONCE captures are under way together.
    together = threading.Barrier(preview_batch.CAPTURES_AT_ONCE, timeout=5)
    lock = threading.Lock()
    under_way, most = [0], [0]

    def capture(store, version, executable, cancel):
        with lock:
            under_way[0] += 1
            most[0] = max(most[0], under_way[0])
        together.wait()
        with lock:
            under_way[0] -= 1
        store.set_compatibility(version, "playable")
        return "playable"
    monkeypatch.setattr(preview_batch, "capture", capture)
    result = finished(preview_batch.start(larger_library))
    count = 2 * preview_batch.CAPTURES_AT_ONCE
    assert result["status"] == "completed", result["error"]
    assert result["done"] == result["total"] == count and result["result"]["frames"] == count
    assert most[0] == preview_batch.CAPTURES_AT_ONCE
    assert {version.compatibility for version in larger_library.latest()} == {"playable"}


def test_a_stopped_run_starts_no_further_capture(larger_library, monkeypatch):
    started = []
    lock = threading.Lock()

    def capture(store, version, executable, cancel):
        with lock:
            started.append(version.asset_id)
        if cancel.wait(5):  # as the real capture: stop the esmini under way
            raise InterruptedError()
        return "playable"
    monkeypatch.setattr(preview_batch, "capture", capture)
    job = preview_batch.start(larger_library)
    for _ in range(500):
        if len(started) == preview_batch.CAPTURES_AT_ONCE:
            break
        time.sleep(0.01)
    assert len(started) == preview_batch.CAPTURES_AT_ONCE
    job.cancel.set()
    result = finished(job)
    time.sleep(0.2)
    assert result["status"] == "stopped" and len(started) == preview_batch.CAPTURES_AT_ONCE
    assert result["result"].get("frames", 0) == 0


def test_without_esmini_only_the_roads_are_drawn(library, monkeypatch):
    store, _ = library
    monkeypatch.setattr(preview_batch, "find_esmini", lambda value: None)
    result = finished(preview_batch.start(store))
    assert result["result"]["drawings"] == 3 and result["result"]["frames"] == 0
    assert "esmini" in result["messages"][0]


def test_an_import_makes_previews_when_the_setting_asks(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    store = AssetStore()
    started = []
    monkeypatch.setattr(preview_batch, "start", lambda store: started.append(store))
    finished(import_jobs.start_import(store, files()))
    assert started == []
    save_preferences(auto_preview=True)
    finished(import_jobs.start_import(store, files("other.xosc")))
    assert len(started) == 1


def test_the_api_starts_a_run_and_serves_drawings(library, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from openx_workbench import api

    store, versions = library
    monkeypatch.setattr(preview_batch, "find_esmini", lambda value: None)
    client = TestClient(api.app, base_url="http://127.0.0.1")
    job = client.post("/api/previews", json={}).json()
    assert job["kind"] == preview_batch.KIND
    finished(jobs.get(job["id"]))
    assert client.get("/api/jobs", params={"kind": "preview_batch"}).json()[0]["id"] == job["id"]
    version = versions[0]
    drawing = client.get(f"/api/assets/{version.asset_id}/versions/{version.version_id}/road-drawing")
    assert drawing.headers["content-type"] == "image/png" and drawing.content.startswith(b"\x89PNG")


def test_a_capture_records_whether_the_version_played(library, monkeypatch):
    from threading import Event

    store, versions = library

    class Worker:
        stopped = False

        def __init__(self, states):
            self.states = iter(states)

        def status(self):
            return next(self.states)

        def stop(self):
            Worker.stopped = True

    states = [{"state": "running", "frames": 3}, {"state": "finished", "frames": 20}]
    monkeypatch.setattr(preview_batch, "start_preview", lambda *args, **kwargs: Worker(states))
    assert preview_batch.capture(store, versions[0], Path("esmini.exe"), Event()) == "playable" and Worker.stopped
    played = next(item for item in store.versions() if item.asset_id == versions[0].asset_id)
    assert played.compatibility == "playable"

    def refuse(*args, **kwargs):
        raise RuntimeError("esmini rejected the scenario.")
    monkeypatch.setattr(preview_batch, "start_preview", refuse)
    assert preview_batch.capture(store, versions[1], Path("esmini.exe"), Event()) == "failed"
    failed = next(item for item in store.versions() if item.asset_id == versions[1].asset_id)
    assert (failed.compatibility, failed.compatibility_detail) == ("failed", "esmini rejected the scenario.")
