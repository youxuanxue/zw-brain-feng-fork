from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from zw_brain.entry.dashboard_bff import DashboardBffHandler, main

__all__ = ["DashboardBffHandler", "main"]


if __name__ == "__main__":
    main()
