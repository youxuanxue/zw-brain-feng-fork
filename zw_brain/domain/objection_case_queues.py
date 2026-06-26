"""Objection queue predicates shared by workbench and provider inbox projections."""

from __future__ import annotations

from typing import Any

from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

PENDING_ACCEPTANCE_STATUS = "submitted"


def project_pending_objection_cases(*, tenant_id: str | None = None) -> list[Any]:
    """待受理异议队列单一事实源：submitted case.

    该队列同时供工作台「待受理异议」计数/行内受理、以及异议收件箱的待受理筛选视图消费。
    不在前端或其它投影处再手写一份状态集合，避免 count 与列表口径漂移。
    """
    tenant_id = tenant_id or get_runtime_tenant_id()
    return ObjectionRepository().list_cases(tenant_id=tenant_id, status=PENDING_ACCEPTANCE_STATUS)
