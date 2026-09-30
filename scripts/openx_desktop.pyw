"""Shortcut entry point; keep source imports independent of the working directory."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from openx_workbench.launcher import main

main()
