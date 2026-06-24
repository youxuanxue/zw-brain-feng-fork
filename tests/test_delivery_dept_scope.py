"""部门数据隔离（#294 集成期遗漏补口）—— 交付任务 delivery_tasks 收口单测。

交付面是 #294 五面收口**漏掉**的第六面：``delivery_tasks`` 仅发给部门角色
（``web_snapshot_redaction._DELIVERY``={操作员,管理员}，全局角色一律清空），却在
``system_ops.handler_system_snapshot`` 装配时未按 ``visible_org_codes`` 收口，部门角色
看到全部门交付任务（与 requests 同类跨部门泄漏）。

收口范式与 approvals R11 一致：交付任务**随其申请单可见性收口**——``request_map`` 已是
上游 ``enrich_requests_snapshot`` 按 applicant_org∨provider_org 收口后的申请卡集合，故
dept_scoped=True 时只保留 requestId 命中域内申请的交付卡，命中不到即 fail-closed drop。

本单测直接锁 ``enrich_delivery_tasks_snapshot`` 的三态（无 DB、纯合成、CI 内恒可跑）；
端到端两 actor 隔离另见 ``test_dept_isolation_snapshot_two_actor``。
"""

from __future__ import annotations

from typing import Any

import pytest

from zw_brain.domain.discovery_snapshot_projection import enrich_delivery_tasks_snapshot

pytestmark = pytest.mark.no_db


class _StubRequestService:
    """status_timeline 桩：命中申请卡即挂可辨识哨兵，验「在域内任务才接 timeline」。"""

    def status_timeline(self, req: dict[str, Any], task: dict[str, Any], *, perspective: str) -> list[str]:
        return [f"tl::{req.get('id')}::{perspective}"]


def _tasks() -> list[dict[str, Any]]:
    # 两张交付卡：APP-A 属 orgA 域内申请、APP-B 属 orgB（域外）。
    return [
        {"id": "DLV-A", "requestId": "APP-A", "status": "completed"},
        {"id": "DLV-B", "requestId": "APP-B", "status": "completed"},
    ]


def _scoped_request_map() -> dict[str, Any]:
    # 上游 requests 已按机构收口后只剩 orgA 域内申请卡（APP-B 已被 dept 过滤掉）。
    return {"APP-A": {"id": "APP-A", "providerOrgCode": "orgA"}}


def test_dept_scoped_drops_out_of_scope_delivery() -> None:
    out = enrich_delivery_tasks_snapshot(
        _tasks(), request_service=_StubRequestService(), request_map=_scoped_request_map(),
        dept_scoped=True,
    )
    ids = {t["id"] for t in out}
    assert ids == {"DLV-A"}, "部门角色只见域内申请对应的交付卡，域外（APP-B）被收口"
    assert out[0]["statusTimeline"] == ["tl::APP-A::reviewer"], "在域内任务仍接权威 timeline"


def test_dept_scoped_empty_request_map_fail_closed() -> None:
    # 部门角色缺机构上下文 → 上游 requests fail-closed 空 → request_map 空 → 交付一并清空。
    out = enrich_delivery_tasks_snapshot(
        _tasks(), request_service=_StubRequestService(), request_map={}, dept_scoped=True,
    )
    assert out == [], "request_map 空（fail-closed）→ 交付卡全 drop，不泄漏"


def test_global_view_keeps_all_delivery() -> None:
    # dept_scoped=False（全局视角/未收口）：保留全量、不丢任务（enrich 不静默吞任务）。
    out = enrich_delivery_tasks_snapshot(
        _tasks(), request_service=_StubRequestService(), request_map=_scoped_request_map(),
        dept_scoped=False,
    )
    assert {t["id"] for t in out} == {"DLV-A", "DLV-B"}, "全局视角保留全量交付卡"
    # 仅命中 request_map 的卡接 timeline，未命中的不接（诚实，不破现渲染）。
    by_id = {t["id"]: t for t in out}
    assert "statusTimeline" in by_id["DLV-A"]
    assert "statusTimeline" not in by_id["DLV-B"]
