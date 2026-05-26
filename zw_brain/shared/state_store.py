from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from zw_brain.domain.seed import clone_seed_snapshot
from zw_brain.shared.database_store import DEFAULT_PERSISTABLE_UI_STATE, DatabaseStore

DEFAULT_DATA_DIR = Path(os.environ.get("ZW_BRAIN_DATA_DIR", Path(__file__).resolve().parents[2] / ".data"))
DEFAULT_STATE_PATH = DEFAULT_DATA_DIR / "brain_state.json"


class StateStore:
    def __init__(self, path: Path | None = None, database_store: DatabaseStore | None = None) -> None:
        self._path = path or DEFAULT_STATE_PATH
        self._database_store = database_store

    @property
    def path(self) -> Path:
        return self._path

    @property
    def database_store(self) -> DatabaseStore | None:
        return self._database_store

    def exists(self) -> bool:
        if self._database_store is not None:
            return True
        return self._path.exists()

    def load(self) -> dict[str, Any]:
        if self._database_store is not None:
            snapshot, _ = self._database_store.load_runtime_state()
            return snapshot
        if not self._path.exists():
            return clone_seed_snapshot()
        return json.loads(self._path.read_text(encoding="utf-8"))

    def save(self, snapshot: dict[str, Any], ui_state: dict[str, Any] | None = None) -> None:
        if self._database_store is not None:
            self._database_store.save_runtime_state(
                snapshot,
                ui_state or dict(DEFAULT_PERSISTABLE_UI_STATE),
            )
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    def reset(self) -> dict[str, Any]:
        snapshot = clone_seed_snapshot()
        self.save(snapshot)
        return copy.deepcopy(snapshot)
