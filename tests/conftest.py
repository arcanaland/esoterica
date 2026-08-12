from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# tools/ holds standalone scripts rather than a package, so a test that exercises
# one puts it on the path the same way build.py does.
sys.path.insert(0, str(REPO_ROOT / "tools"))
