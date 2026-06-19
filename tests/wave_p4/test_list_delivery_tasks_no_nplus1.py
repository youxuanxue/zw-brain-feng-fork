# Wave: 1
# Journey: J1
# Pages: P4 交付
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_MANAGER
# Trace:
#   zw_brain/command/brain.py (list_delivery_tasks)
#   zw_brain/domain/services/delivery_service.py (task_from_record)
"""list_delivery_tasks N+1 消除守卫.

旧实现逐 snapshot task 调 self.get_delivery_task(task_id)（每次重建整张 task dict
+ 重扫内存快照）只为取 receipts；DB-only task 又 next(...list_tasks...) 全表扫。
新实现：复用一次性预取的 records + 直接 list_receipts（索引）；DB-only task 直传
record。本测试锁定 list_tasks 在一次 list_delivery_tasks 内只调一次。
"""
from __future__ import annotations

import pytest

TENANT = "sd-default"

# N+1 守卫只断言 list_tasks 调用次数（与表内行数无关），空 schema 即可证明——故无需真灌库：
# 由根 conftest 的 function-scoped 空 PG 克隆（已 alembic upgrade head）供给，跨测试隔离。


@pytest.fixture()
def brain():
    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore
    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    ss = StateStore(database_store=ds)
    return BrainService(state_store=ss)


def test_list_delivery_tasks_calls_list_tasks_once(brain, monkeypatch):
    store = brain._state_store.database_store
    calls = {"list_tasks": 0}
    real = store.delivery_repo.list_tasks

    def counting(*args, **kwargs):
        calls["list_tasks"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(store.delivery_repo, "list_tasks", counting)
    tasks = brain.list_delivery_tasks()
    assert calls["list_tasks"] == 1, (
        f"list_delivery_tasks 应只调 1 次 list_tasks（N+1 消除），实际 {calls['list_tasks']}"
    )
    assert isinstance(tasks, list)
    for t in tasks:
        assert "receipts" in t
