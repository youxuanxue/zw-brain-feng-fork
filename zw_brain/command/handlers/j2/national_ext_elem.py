"""J2 国家扩展要素编制 handler（D50/C5，national-ext-elements 子旅程）。

单能力 ``catalog.national_ext_elem.compile`` 按 ``action`` 驱动编制任务生命周期：
create / submit / review / revise / revoke / list / get。状态机 + 2 级审核全部委托
``national_ext_elem_walker`` + ``NationalExtElemRepository`` —— **与政务目录主线完全独立**，
本 handler 绝不写 catalog_entry/catalog_item（national-ext-elements.feature 场景4）。

诚实纪律（D50）：发布（已发布态）= 「同步国家平台」语义，真实出站经 C4 国家通道 gate；
本能力本期 manifest 仍 deferred（handler 就绪、不 live、不进投影），不接真实出站——
未配置即诚实 pending 由 gate 兜底，绝不在此伪造回流。
"""

from __future__ import annotations

from typing import Any

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain import national_ext_elem_walker as walker
from zw_brain.domain.repositories.national_ext_elem import NationalExtElemRepository

_DEFAULT_TENANT = "sd-default"
_READ_ACTIONS = {"list", "get"}


def handler_national_ext_elem_compile(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    action = str(payload.get("action", "create"))
    tenant_id = str(payload.get("tenant_id", _DEFAULT_TENANT))
    repo = NationalExtElemRepository()

    if action in _READ_ACTIONS:
        if action == "list":
            return {"items": repo.list_tasks(tenant_id=tenant_id, compile_status=payload.get("compile_status"))}
        task = repo.get_task(str(payload.get("task_code", "")), tenant_id=tenant_id)
        return {"task": task}

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        task_code = str(payload.get("task_code", ""))
        if action == "create":
            task = repo.create_task(payload, tenant_id=tenant_id)
        elif action == "submit":
            current = _require_task(repo, task_code, tenant_id)["compile_status"]
            target = walker.submit_target(current)
            step = 1 if target in (walker.PENDING_BUSINESS_REVIEW, walker.PENDING_BUSINESS_REVIEW_REVISION) else None
            task = repo.set_status(task_code, target, tenant_id=tenant_id, current_review_step=step)
        elif action == "review":
            task = repo.review_decision(task_code, approve=bool(payload.get("approve")), tenant_id=tenant_id)
        elif action == "revise":
            task = repo.set_status(task_code, walker.REVISION_DRAFT, tenant_id=tenant_id)
        elif action == "revoke":
            task = repo.set_status(task_code, walker.PENDING_REVOKE_REVIEW, tenant_id=tenant_id)
        else:
            raise ValueError(f"unknown national ext-elem action: {action!r}")
        return {"task": task, "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)


def _require_task(repo: NationalExtElemRepository, task_code: str, tenant_id: str) -> dict[str, Any]:
    task = repo.get_task(task_code, tenant_id=tenant_id)
    if task is None:
        raise KeyError(f"national ext-elem task not found: {task_code}")
    return task
