"""infra：平台文档只读检索，供内置平台指南 Agent 使用。"""

from __future__ import annotations

from typing import Any

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.shared import platform_docs


def handler_search(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    _ = deps, ctx
    query = str(payload.get("query") or "").strip()
    limit = payload.get("limit")
    return platform_docs.search_docs(query=query, limit=int(limit) if limit is not None else None)


def handler_read(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    _ = deps, ctx
    rel_path = str(payload.get("path") or payload.get("rel_path") or "").strip()
    max_chars = payload.get("max_chars")
    return platform_docs.read_doc(
        rel_path=rel_path,
        max_chars=int(max_chars) if max_chars is not None else None,
    )
