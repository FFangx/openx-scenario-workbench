"""Attribute readers shared by the OpenSCENARIO and OpenDRIVE parsers."""

from __future__ import annotations

from xml.etree import ElementTree as ET


def local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def parse_local(data: bytes | str) -> ET.Element:
    """The document with every tag reduced to its local name, so a search by tag (`iter(name)`) runs in C
    instead of comparing every element's name in Python."""
    root = ET.fromstring(data)
    for element in root.iter():
        if element.tag[:1] == "{":
            element.tag = local_name(element)
    return root


def number(value: str | None, default: float | None = None) -> float | None:
    """`value` as a float, or `default` when it is missing or not numeric. Infinities and NaN pass through."""
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default
