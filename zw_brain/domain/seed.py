from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

SEED_PATH = Path(__file__).with_name("seed_snapshot.json")


def load_seed_snapshot() -> dict[str, Any]:
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def clone_seed_snapshot() -> dict[str, Any]:
    return copy.deepcopy(load_seed_snapshot())
