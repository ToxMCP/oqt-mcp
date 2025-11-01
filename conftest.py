"""
Project-wide pytest configuration.

Adds the repository root to sys.path so tests can import the `src` package
without requiring `PYTHONPATH` tweaks or editable installs.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

for path in (ROOT, SRC):
    str_path = str(path)
    if str_path not in sys.path:
        sys.path.insert(0, str_path)
