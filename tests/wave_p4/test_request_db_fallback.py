# Wave: 1
# Journey: J1
# Pages: P3 申请 / P4 凭据领取
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_OPERATER (申请人) | ROLE_ORGAN_MANAGER (审批人)
# Trace:
#   zw_brain/domain/services/request_service.py
#   zw_brain/domain/repositories/application.py
"""request_service.by_id DB 回源（Fix B，request 侧）回归.

真 bug：M0 dump 导入的申请不在内存快照基底里。by_id 旧实现只读 brain._snapshot
→ credential.issue 路径取不到 request → NotFoundError → P3 凭据签发 422。
Fix B（request 侧）：内存未命中 → 回源 DB（application_repo.get_record →
record_to_request）。与 delivery_service.by_request_id 同范式。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from tests._seed_guard import require_real_seed

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB = REPO_ROOT / ".data" / "test_request_db_fallback_shadow.db"
TENANT = "sd-default"

require_real_seed({"catalog_entry": 100})


@pytest.fixture(scope="module", autouse=True)
def _shadow_db() -> None:
    if SHADOW_DB.exists():
        SHADOW_DB.unlink()
    shutil.copy(SEED_DB, SHADOW_DB)
    os.environ["ZW_BRAIN_DB_PATH"] = str(SHADOW_DB)
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
    from zw_brain.shared import db as _db
    with _db._CACHE_LOCK:
        _db._ENGINE_CACHE.clear()
    yield


@pytest.fixture(scope="module")
def brain():
    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore
    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    ss = StateStore(database_store=ds)
    return BrainService(state_store=ss)


def _db_only_request(brain, request_id: str) -> None:
    """写一条 DB-only 申请（不进内存快照）+ 一条 granted delivery，模拟 M0 dump 导入态。"""
    store = brain._state_store.database_store
    # 取一条真实 catalog 作 resource 锚
    catalog = store.catalog_repo.list_entries(tenant_id=TENANT, limit=1)
    catalog_code = catalog[0].catalog_code if catalog else "CAT-FALLBACK"
    store.application_repo.upsert_from_request(
        {
            "id": request_id,
            "status": "granted",
            "applicant": "U_DBONLY",
            "applicantDept": "部门A_公安",
            "resourceId": catalog_code,
            "resource_name": "DB-only 申请回归资源",
        },
        tenant_id=TENANT,
    )
    store.delivery_repo.upsert_from_delivery(
        {
            "id": request_id.replace("REQ-", "DLV-", 1),
            "requestId": request_id,
            "status": "granted",
            "channel": "api",
            "resourceId": catalog_code,
            "accessGrantSnapshot": {},
            "history": [],
        },
        tenant_id=TENANT,
    )
    # 确保内存快照里没有它
    brain._snapshot.setdefault("requests", [])
    brain._snapshot["requests"] = [r for r in brain._snapshot["requests"] if r.get("id") != request_id]


def test_by_id_falls_back_to_db_when_snapshot_misses(brain):
    """内存快照无、DB 有 → by_id 回源 DB 命中（旧实现会 NotFoundError）。"""
    request_id = "REQ-DBONLY-001"
    _db_only_request(brain, request_id)
    request = brain._get_handler_deps().services.request.by_id(request_id)
    assert request is not None
    assert request["id"] == request_id


def test_maybe_by_id_benefits_from_fallback(brain):
    """maybe_by_id 复用 by_id，自动受益。"""
    request_id = "REQ-DBONLY-002"
    _db_only_request(brain, request_id)
    assert brain._get_handler_deps().services.request.maybe_by_id(request_id) is not None


def test_by_id_still_raises_when_truly_absent(brain):
    """DB 也无 → NotFoundError（行为不变，不吞错）。"""
    from zw_brain.domain.errors import NotFoundError
    with pytest.raises(NotFoundError):
        brain._get_handler_deps().services.request.by_id("REQ-DOES-NOT-EXIST-XYZ")


def test_credential_issue_no_longer_422_for_db_only_request(brain):
    """回归根因：DB-only 申请走 credential.issue 不再 NotFoundError（422）。"""
    from tests._trusted_payload import invoke_trusted
    request_id = "REQ-DBONLY-CRED"
    _db_only_request(brain, request_id)
    out = invoke_trusted(
        brain,
        "credential.issue",
        {"request_id": request_id, "confirmed": True},
        role="ROLE_ORGAN_MANAGER",
    )
    result = out["result"] if isinstance(out, dict) and "result" in out and "audit_id" in out else out
    assert result is not None
    assert result["credential"]["app_key"].startswith("AK-SELF-")
