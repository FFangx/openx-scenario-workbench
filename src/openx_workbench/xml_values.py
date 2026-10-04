"""Attribute readers shared by the OpenSCENARIO and OpenDRIVE parsers."""

from __future__ import annotations

from xml.etree import ElementTree as ET


def local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def number(value: str | None, default: float | None = None) -> float | None:
    """`value` as a float, or `default` when it is missing or not numeric. Infinities and NaN pass through."""
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default
