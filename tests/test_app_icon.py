from PIL import Image

from openx_workbench.app_icon import ICO_SIZES, app_icon, save_icon


def test_icon_files_carry_every_size(tmp_path):
    for name, stop in (("openx.ico", False), ("openx-stop.ico", True)):
        save_icon(tmp_path / name, stop=stop)
        with Image.open(tmp_path / name) as icon:
            assert icon.info["sizes"] == {(size, size) for size in ICO_SIZES}


def test_stop_icon_differs_and_corners_stay_transparent():
    start, stop = app_icon(64), app_icon(64, stop=True)
    assert start.mode == "RGBA" and start.getpixel((0, 0))[3] == 0
    assert start.tobytes() != stop.tobytes()
