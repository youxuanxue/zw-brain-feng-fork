# Journey: J1
# Pages: P3 application / P4 delivery / P1 workbench
# Consumer-faces: API (brain.invoke_skill write path)
# Roles: ROLE_BUSIAUDIT | ROLE_ORGAN_MANAGER | ROLE_ORGAN_OPERATER
# Trace:
#   zw_brain/command/handlers/j1/requirement_intake.py (_dispatch_require_resource)
#   zw_brain/command/handlers/j1/delivery.py (_replace_or_cancel_delivery)
#   zw_brain/command/handlers/j1/workbench.py (_terminate_subscription)
#   zw_brain/command/card_session.py (Action D 写路径单源化)
#   zw_brain/domain/repositories/delivery.py (update_task_payload / terminate_subscription)
"""R-006 写路径旁路收口 — 三个 D56 旁路 handler 改走 CardSession / domain repo.

历史（R-006）：``require.resource.dispatch`` / ``delivery.replace_or_cancel`` /
``subscription.terminate`` 三个 mutation 在闭包内自开 SQLAlchemy session 直接
``commit``，绕过 CardSession identity map + 指纹脏检。``PersistMiddleware`` 在
mutation 返回后 ``_card_session.flush()``——若同一 dispatch 内该卡已被 ``find_by_id``
登记（陈旧态），flush 会用陈旧卡 upsert 覆盖直写，潜伏 lost-update。

本测试锁定收口后的不变量：
1. dispatch：运行时申请卡 status→'dispatched' 落 application_record，
   dispatch_payload / target_region_codes 进 payload，且 flush 不回退；
2. replace_or_cancel：运行时交付卡 state→'cancelled'/'replaced' 落 delivery_task，
   withdrawal_handling 进 payload；
3. terminate：订阅 status→'terminated' 落 delivery_subscription，
   legacy_status_snapshot.terminations 追加一条；不存在订阅 → NotFoundError。
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.shared import db as db_module
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"


@pytest.fixture()
def brain(monkeypatch: pytest.MonkeyPatch):
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "write_path_no_bypass.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()

        import zw_brain.shared.audit as audit_bus
        from zw_brain.command.brain import BrainService
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.state_store import StateStore

        ds = DatabaseStore()
        audit_bus.configure_sink(ds.append_audit_event)
        ss = StateStore(database_store=ds)
        yield BrainService(state_store=ss)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


# --- direct-seed helpers (runtime cards = payload 无 'kind') -------------------


def _seed_runtime_request(code: str, status: str = "pending") -> None:
    from zw_brain.domain.repositories.application import ApplicationRepository

    ApplicationRepository().upsert_from_request(
        {
            "id": code,
            "status": status,
            "applicant": "张三",
            "applicantDept": "测试单位",
            "resourceName": f"资源-{code}",
        },
        tenant_id=TENANT,
    )


def _seed_runtime_delivery(code: str, request_id: str, status: str = "running") -> None:
    from zw_brain.domain.repositories.delivery import DeliveryRepository

    DeliveryRepository().upsert_from_delivery(
        {
            "id": code,
            "requestId": request_id,  # is_runtime_delivery_payload 判别键
            "status": status,
            "channel": "exchange",
            "note": "运行时交付卡",
            "backflow": {},
            "history": [],
        },
        tenant_id=TENANT,
    )


def _seed_subscription(code: str, delivery_code: str, status: str = "active") -> None:
    from zw_brain.domain.repositories.delivery import DeliveryRepository

    DeliveryRepository().upsert_subscription(
        {"subscription_code": code, "delivery_code": delivery_code, "status": status},
        tenant_id=TENANT,
    )


def _app_record(code: str):
    from zw_brain.domain.repositories.application import ApplicationRepository

    return ApplicationRepository().get_record(code, tenant_id=TENANT)


def _delivery_record(code: str):
    from zw_brain.domain.repositories.delivery import DeliveryRepository

    return DeliveryRepository().get_task(code, tenant_id=TENANT)


def _subscription_record(code: str):
    from zw_brain.domain.repositories.delivery import DeliveryRepository

    for rec in DeliveryRepository().list_subscriptions(tenant_id=TENANT):
        if rec.subscription_code == code:
            return rec
    return None


# --- R-006(1) require.resource.dispatch --------------------------------------


def test_dispatch_lands_status_and_payload_no_bypass(brain: Any) -> None:
    _seed_runtime_request("APP-DISPATCH-1")
    out = invoke_trusted(
        brain,
        "require.resource.dispatch",
        {
            "application_code": "APP-DISPATCH-1",
            "confirmed": True,
            "dispatch_payload_json": {"channel": "exchange"},
            "target_region_codes": ["370100"],
        },
        role="ROLE_BUSIAUDIT",
    )
    res = out.get("result", out)
    assert res["status"] == "dispatched"
    rec = _app_record("APP-DISPATCH-1")
    # status 列权威落库（flush 不回退直写——lost-update 守卫）。
    assert rec.status == "dispatched"
    # payload merge 经 CardSession 卡持久化。
    assert rec.payload_json.get("dispatch_target_region_codes") == ["370100"]
    assert rec.payload_json.get("dispatch_payload") == {"channel": "exchange"}


def test_dispatch_unknown_application_raises(brain: Any) -> None:
    from zw_brain.command.brain import NotFoundError

    with pytest.raises(NotFoundError):
        invoke_trusted(
            brain,
            "require.resource.dispatch",
            {"application_code": "APP-MISSING", "confirmed": True, "dispatch_payload_json": {}},
            role="ROLE_BUSIAUDIT",
        )


# --- R-006(2) delivery.replace_or_cancel -------------------------------------


def test_cancel_lands_state_and_payload_no_bypass(brain: Any) -> None:
    _seed_runtime_request("APP-DLV-1")
    _seed_runtime_delivery("DLV-CANCEL-1", "APP-DLV-1")
    out = invoke_trusted(
        brain,
        "delivery.replace_or_cancel",
        {"delivery_code": "DLV-CANCEL-1", "action": "cancel", "reason": "测试取消", "confirmed": True},
        role="ROLE_ORGAN_MANAGER",
    )
    res = out.get("result", out)
    assert res["state"] == "cancelled"
    rec = _delivery_record("DLV-CANCEL-1")
    assert rec.state == "cancelled"
    assert rec.payload_json.get("withdrawal_handling", {}).get("action") == "cancel"


def test_replace_lands_state_no_bypass(brain: Any) -> None:
    _seed_runtime_request("APP-DLV-2")
    _seed_runtime_delivery("DLV-REPLACE-1", "APP-DLV-2")
    out = invoke_trusted(
        brain,
        "delivery.replace_or_cancel",
        {
            "delivery_code": "DLV-REPLACE-1",
            "action": "replace",
            "replacement_resource_id": "RES-NEW",
            "confirmed": True,
        },
        role="ROLE_ORGAN_MANAGER",
    )
    res = out.get("result", out)
    assert res["state"] == "replaced"
    rec = _delivery_record("DLV-REPLACE-1")
    assert rec.state == "replaced"
    assert rec.payload_json.get("withdrawal_handling", {}).get("replacement_resource_id") == "RES-NEW"


# --- R-006(3) subscription.terminate -----------------------------------------


def test_terminate_lands_status_and_appends_termination(brain: Any) -> None:
    _seed_runtime_request("APP-SUB-1")
    _seed_runtime_delivery("DLV-SUB-1", "APP-SUB-1")
    _seed_subscription("SUB-TERM-1", "DLV-SUB-1")
    out = invoke_trusted(
        brain,
        "subscription.terminate",
        {"subscription_code": "SUB-TERM-1", "reason": "不再需要", "confirmed": True},
        role="ROLE_ORGAN_OPERATER",
    )
    res = out.get("result", out)
    assert res["status"] == "terminated"
    rec = _subscription_record("SUB-TERM-1")
    assert rec.status == "terminated"
    terminations = rec.legacy_status_snapshot_json.get("terminations", [])
    assert len(terminations) == 1
    assert terminations[0]["reason"] == "不再需要"


def test_terminate_unknown_subscription_raises(brain: Any) -> None:
    from zw_brain.domain.errors import NotFoundError

    with pytest.raises(NotFoundError):
        invoke_trusted(
            brain,
            "subscription.terminate",
            {"subscription_code": "SUB-MISSING", "reason": "x", "confirmed": True},
            role="ROLE_ORGAN_OPERATER",
        )
