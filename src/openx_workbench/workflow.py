from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath

from .models import ParseBundle
from .parser import parse_bundle


@dataclass(frozen=True, slots=True)
class InputFile:
    name: str
    data: bytes


class InputValidationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def inspect_pair(xosc: InputFile, xodr: InputFile) -> ParseBundle:
    """Validate filenames and parse one OpenSCENARIO/OpenDRIVE pair."""

    if PurePath(xosc.name).suffix.casefold() != ".xosc":
        raise InputValidationError("invalid_xosc_extension")
    if PurePath(xodr.name).suffix.casefold() != ".xodr":
        raise InputValidationError("invalid_xodr_extension")
    if not xosc.data:
        raise InputValidationError("empty_xosc")
    if not xodr.data:
        raise InputValidationError("empty_xodr")
    return parse_bundle(xosc.data, xodr.data, xodr.name)
