"""Snapshot delivery_tasks enrichment for Web UI (E5 F15)."""

from __future__ import annotations

import pytest

from tests._pg_realistic import realistic_pg_module  # noqa: F401  (fixture)

# 需真实旧平台数据（交付任务 ≥1）：克隆 realistic 模板库；无模板（CI 无 dump）则 skip，
# 承接旧 SEED_DB-missing → require_real_seed 跳过语义。
pytestmark = pytest.mark.usefixtures("realistic_pg_module")


def test_system_snapshot_delivery_tasks_dept_scoped_fail_closed() -> None:
    """#294 集成期遗漏补口：交付任务按调用者机构收口，缺机构上下文 → fail-closed 空。

    交付面唯一消费者是部门角色（redaction `_DELIVERY`={操作员,管理员}）。部门角色无机构
    上下文（payload 不带 org_code，bearer/裸 role 入口）→ visible_org_codes=空集 → 上游
    requests fail-closed 空 → request_map 空 → 交付一并清空。此前 delivery_tasks 未收口、
    把**全部门**交付任务（listed ≥ 1）泄漏给该调用，本断言锁定泄漏已闭合。
    带机构上下文的正向部门隔离见 test_dept_isolation_snapshot_two_actor。
    """
    from tests._handler_call import call_handler
    from zw_brain.command.brain import BrainService
    from zw_brain.command.handlers.b1.system_ops import handler_system_snapshot
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    # Action D：交付单一事实源在 DB——本测试须 DB-backed brain（file-mode 无库即诚实空列表，
    # 比较失去意义）。真实库须有交付任务，泄漏闭合断言才有意义。
    brain = BrainService(state_store=StateStore(database_store=DatabaseStore()))
    listed = brain.list_delivery_tasks()
    assert len(listed) >= 1, "真实库须有交付任务，泄漏闭合断言才非空言"
    snap = call_handler(handler_system_snapshot, brain=brain, skill_id="system.snapshot", payload={"role": "ROLE_ORGAN_OPERATER"})
    snap_tasks = snap.get("delivery_tasks") or []
    assert snap_tasks == [], "部门角色无机构上下文 → 交付任务 fail-closed 空（不泄漏全部门交付）"
