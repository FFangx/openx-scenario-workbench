"""Asset management page."""

from __future__ import annotations

from openx_workbench.ui_shell import source_files
from openx_workbench.ui.assets import preview_controls
from openx_workbench.ui.imports import import_progress, library_controls


def management_page(language: str) -> None:
    from openx_workbench.asset_management import render
    render(language, import_controls=library_controls, import_progress=import_progress,
           preview_controls=preview_controls, source_files=source_files)
