"""Skill: data.search.

The canonical runtime implementation lives in
`zw_brain/command/handlers/j1/data_search.py` (F1 split, turn 2). Registered manifest
under `zw_brain/capability_registry/registered/data.search.json`. This module remains a
lightweight compatibility shim for direct imports.
"""
from __future__ import annotations

from zw_brain.command.brain import BrainService
from zw_brain.command.handlers.j1.data_search import handler as _handler
from zw_brain.shared.state_store import StateStore


def run(query: str, page: int = 1) -> dict:
    service = BrainService(state_store=StateStore())
    return _handler(service, "data.search", {"query": query, "page": page})
