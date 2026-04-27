"""Skill: data.search.

The canonical runtime implementation is exposed through `BrainService.search_resources`
and the registered manifest under `zw_brain/skill_registration/registered/data.search.json`.
This module remains a lightweight compatibility shim for direct imports.
"""
from __future__ import annotations

from zw_brain.command.brain import BrainService
from zw_brain.shared.state_store import StateStore


def run(query: str, page: int = 1) -> dict:
    service = BrainService(state_store=StateStore())
    return service.search_resources(query=query, page=page)
