import io
from dataclasses import replace

from PIL import Image

from openx_workbench.asset_store import AssetStore, AssetVersion
from openx_workbench.preview_frames import frame_path, read_frame, save_frame


def version():
    return AssetVersion("asset", "v1", 1, "Scene", "source", "a.xosc", "a.xodr", "today", "content", "source", ())


def jpeg():
    output = io.BytesIO()
    Image.new("RGB", (64, 36), "navy").save(output, "JPEG")
    return output.getvalue()


def test_frames_cannot_cross_asset_version_or_content_boundaries(tmp_path):
    store = AssetStore(tmp_path)
    original = version()
    assert read_frame(store, original) is None
    save_frame(frame_path(store, original), jpeg(), 10)
    image, metadata = read_frame(store, original)
    assert image == jpeg()
    assert metadata == {"renderer": "esmini", "frame_number": 10, "simulation_seconds": 1.0}
    for changed in (replace(original, version_id="v2"), replace(original, asset_id="other"),
                    replace(original, content_sha256="different")):
        assert read_frame(store, changed) is None
    assert read_frame(AssetStore(tmp_path / "other-store"), original) is None


def test_failed_publication_keeps_last_complete_frame(tmp_path, monkeypatch):
    store = AssetStore(tmp_path)
    path = frame_path(store, version())
    save_frame(path, jpeg(), 1)
    def fail(*args):
        raise PermissionError("authored publication failure")
    monkeypatch.setattr(type(path), "replace", fail)
    import pytest
    with pytest.raises(PermissionError):
        save_frame(path, jpeg(), 10)
    assert read_frame(store, version())[1]["frame_number"] == 1
    assert list(path.parent.iterdir()) == [path]


def test_corrupted_frame_is_a_cache_miss(tmp_path):
    store = AssetStore(tmp_path)
    path = frame_path(store, version())
    path.parent.mkdir(parents=True)
    for value in ('not json', '{}', '{"jpeg":"bad"}', '{"jpeg":"AAAA", "renderer":"esmini"}'):
        path.write_text(value)
        assert read_frame(store, version()) is None
