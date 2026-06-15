"""infra：平台文档只读检索，供内置平台指南 Agent 使用。"""

from __future__ import annotations

import logging
from typing import Any

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.shared import platform_docs

logger = logging.getLogger(__name__)


def handler_search(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    _ = deps, ctx
    query = str(payload.get("query") or "").strip()
    limit = payload.get("limit")
    try:
        return platform_docs.search_docs(query=query, limit=int(limit) if limit is not None else None)
    except Exception:
        logger.exception(
            "平台指南搜索失败 | query=%s limit=%s payload=%s",
            query, limit, payload,
        )
        raise


def handler_read(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    _ = deps, ctx
    rel_path = str(payload.get("path") or payload.get("rel_path") or "").strip()
    max_chars = payload.get("max_chars")
    try:
        result = platform_docs.read_doc(
            rel_path=rel_path,
            max_chars=int(max_chars) if max_chars is not None else None,
        )
        # read_doc 内部已处理 FileNotFoundError，返回包含 error 字段的友好提示
        if isinstance(result, dict) and result.get("error") == "document_not_found":
            did_you_mean = result.get("did_you_mean", [])
            logger.warning(
                "平台指南读取文档不存在 | rel_path=%s max_chars=%s did_you_mean=%s payload=%s",
                rel_path, max_chars, did_you_mean, payload,
            )
        return result
    except Exception:
        logger.exception(
            "平台指南读取文档异常 | rel_path=%s max_chars=%s payload=%s",
            rel_path, max_chars, payload,
        )
        raise
