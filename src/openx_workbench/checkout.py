"""Locate the repository checkout that holds the web build and the authored examples.

Neither is part of the wheel. Used from the checkout, they sit next to the sources.
After a normal install the package lives in site-packages, so also accept the
working directory: the documented commands run from the repository root.
"""

from __future__ import annotations

from pathlib import Path


def checkout_root() -> Path:
    candidates = (Path(__file__).resolve().parents[2], Path.cwd())
    for root in candidates:
        if (root / "pyproject.toml").is_file() and (root / "src" / "openx_workbench").is_dir():
            return root
    return candidates[0]
