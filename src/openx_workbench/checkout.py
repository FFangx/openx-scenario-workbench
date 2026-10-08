"""Locate the repository checkout that holds the web build and the authored examples.

Neither is part of the wheel. Used from the checkout, they sit next to the sources.
After a normal install the package lives in site-packages, so also accept the
working directory: the documented commands run from the repository root.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def checkout_root() -> Path:
    candidates = (Path(__file__).resolve().parents[2], Path.cwd())
    for root in candidates:
        if (root / "pyproject.toml").is_file() and (root / "src" / "openx_workbench").is_dir():
            return root
    return candidates[0]


def package_revision(package: Path) -> str:
    """Digest of the Python sources under `package`; logs and other runtime files do not count."""
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        digest.update(path.relative_to(package).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
