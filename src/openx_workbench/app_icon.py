"""The OpenX desktop icon: a requirement page whose figure is a road with a car on it."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

CANVAS = 1024  # drawn large, then scaled down so every size is smooth
TILE_TOP, TILE_BOTTOM = (29, 64, 96), (16, 36, 56)
NAVY = "#142e46"  # the header colour
BLUE = "#3d8bff"  # the X of the header brand
PAPER_FOLD = "#b9c8d8"
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def _tile():
    shade = Image.linear_gradient("L").resize((CANVAS, CANVAS))
    fill = Image.composite(Image.new("RGBA", (CANVAS, CANVAS), TILE_BOTTOM),
                           Image.new("RGBA", (CANVAS, CANVAS), TILE_TOP), shade)
    mask = Image.new("L", (CANVAS, CANVAS), 0)
    ImageDraw.Draw(mask).rounded_rectangle((40, 40, CANVAS - 40, CANVAS - 40), 230, fill=255)
    tile = Image.new("RGBA", (CANVAS, CANVAS))
    tile.paste(fill, mask=mask)
    return tile


def _page(image, draw):
    left, top, right, bottom, fold = 255, 165, 769, 865, 150
    mask = Image.new("L", image.size, 0)
    shape = ImageDraw.Draw(mask)
    shape.rounded_rectangle((left, top, right, bottom), 44, fill=255)
    shape.polygon(((right - fold, top - 5), (right + 5, top - 5), (right + 5, top + fold)), fill=0)
    image.paste("#ffffff", mask=mask)
    draw.polygon(((right - fold, top), (right - fold, top + fold), (right, top + fold)), fill=PAPER_FOLD)
    for y, width in ((265, 270), (335, 370)):
        draw.rounded_rectangle((left + 65, y, left + 65 + width, y + 36), 18, fill=PAPER_FOLD)


def _road(draw):
    """Perspective road from the bottom of the page to its horizon."""
    near, horizon = 800, 445
    draw.polygon(((310, near), (714, near), (546, horizon), (478, horizon)), fill=NAVY)
    for low, high, width in ((785, 700, 28), (655, 590, 21), (555, 510, 15), (482, 455, 10)):
        draw.rectangle((512 - width // 2, high, 512 + width // 2, low), fill="#ffffff")


def _rear_car(draw, cx, bottom, width):
    """A car seen from behind, in the same perspective as the road."""
    u = width / 120

    def box(x0, y0, x1, y1):
        return cx + x0 * u, bottom + y0 * u, cx + x1 * u, bottom + y1 * u

    def trapezoid(y_top, y_low, half_top, half_low):
        return ((cx - half_top * u, bottom + y_top * u), (cx + half_top * u, bottom + y_top * u),
                (cx + half_low * u, bottom + y_low * u), (cx - half_low * u, bottom + y_low * u))

    draw.rounded_rectangle(box(-55, -14, -33, 4), 5 * u, fill="#08131d")  # wheels
    draw.rounded_rectangle(box(33, -14, 55, 4), 5 * u, fill="#08131d")
    draw.polygon(trapezoid(-92, -52, 40, 54), fill=BLUE)  # cabin
    draw.polygon(trapezoid(-84, -58, 32, 43), fill="#123c73")  # rear window
    draw.rounded_rectangle(box(-60, -58, 60, -10), 12 * u, fill=BLUE)  # body
    draw.rounded_rectangle(box(-52, -48, -32, -38), 4 * u, fill="#ff5d5d")  # tail lights
    draw.rounded_rectangle(box(32, -48, 52, -38), 4 * u, fill="#ff5d5d")
    draw.rounded_rectangle(box(-20, -32, 20, -20), 3 * u, fill="#d5e6ff")  # number plate


def _stop_badge(image, draw):
    cx = cy = 820
    radius, gap = 150, 30
    clear = Image.new("L", image.size, 0)
    ImageDraw.Draw(clear).ellipse((cx - radius - gap, cy - radius - gap, cx + radius + gap, cy + radius + gap), fill=255)
    image.paste((0, 0, 0, 0), mask=clear)
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill="#e5484d")
    draw.rounded_rectangle((cx - 60, cy - 60, cx + 60, cy + 60), 16, fill="#ffffff")


def _master(stop):
    image = _tile()
    draw = ImageDraw.Draw(image)
    _page(image, draw)
    _road(draw)
    _rear_car(draw, 600, 776, 140)
    if stop:
        _stop_badge(image, draw)
    return image


def app_icon(size=256, *, stop=False):
    """The start icon, or with a red stop badge for the stop shortcut."""
    return _master(stop).resize((size, size), Image.Resampling.LANCZOS)


def save_icon(path, *, stop=False):
    """Write a Windows .ico with every size Explorer and the taskbar ask for."""
    master = _master(stop)
    frames = [master.resize((size, size), Image.Resampling.LANCZOS) for size in ICO_SIZES]
    frames[-1].save(Path(path), format="ICO", sizes=[(size, size) for size in ICO_SIZES], append_images=frames[:-1])
