"""Install a dedicated local OCR environment without changing BGE's runtime."""
from __future__ import annotations

import os
import subprocess
import venv

from .atomic_write import write_json
from .asset_store import default_store_root


def main():
    root = default_store_root()
    environment = root / "ocr_runtime"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(environment)
    subprocess.run([str(python), "-m", "pip", "install", "paddleocr[doc-parser]==3.7.0", "paddlex==3.7.2", "paddlepaddle==3.2.2"], check=True)
    config = {"python": str(python), "runtime": {"paddleocr": "3.7.0", "paddlex": "3.7.2", "paddlepaddle": "3.2.2"}}
    write_json(root / "ocr_settings.json", config, indent=2)
    print("Local OCR environment configured.")


if __name__ == "__main__":
    main()
