"""Retrobox: launcher, configuration generators and frontend glue."""

import sys
from pathlib import Path

# Bundled pure-Python dependencies (PySDL2, see _vendor/COPYING-pysdl2.txt).
# Appended, not prepended: a copy installed by the distribution or in a venv
# still wins, the bundled one only fills in where the distribution has none
# (Fedora 45 dropped python3-pysdl2).
_VENDOR_DIR = str(Path(__file__).resolve().parent / "_vendor")
if _VENDOR_DIR not in sys.path:
    sys.path.append(_VENDOR_DIR)
