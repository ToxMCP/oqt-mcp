"""
Test package initialization.

Ensures the project root is importable so test modules can resolve the
`src.*` modules without requiring an editable install.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
