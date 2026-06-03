"""C-1 凭据诚实化：legacy 导入的 granted 授权**不捏造**凭据，诚实标 not_issued。

真实授权表 data_apply_authrization 无 per-grant 凭据列（真凭据在网关域
dsp_service.api_service_app.SECRET、与 apply_id 无绑定供数）。旧实现在 granted 分支
凭据工厂（旧名 derive_demo_credential，今 derive_platform_credential）捏造 AK-DEMO
糊住「granted⟹凭据」——已停止。本测试守住：granted 导入后 access_grant.credential
为 None 且 credential_status="not_issued"，credential.query 因此诚实返回 not_issued
（非任何捏造凭据，含旧 AK-DEMO / 今 AK-SELF 自签前缀）。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from zw_brain.adapters.legacy.mappers.exchange import ExchangeMapper
from zw_brain.domain.repositories.delivery import DeliveryRepository
from zw_brain.shared import db as db_module
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "credential_honesty.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()
        yield db_path
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


def _granted_authz_row(apply_id: str) -> dict[str, object]:
    # apply_status=9 → AUTHZ_APPLY_STATUS_TO_DELIVERY_STATE → "granted"
    return {
        "id": f"authz-{apply_id}",
        "apply_id": apply_id,
        "apply_status": 9,
        "status": 1,
        "limit_day": 180,
        "org_id": "11370000MB284651XL",
        "org_name": "省大数据局",
        "handler_code": "6666666666666666",
        "handler_name": "平台管理员",
        "res_type": "table",
        "create_time": "2024-05-07 15:10:25",
    }


def test_legacy_granted_import_does_not_fabricate_credential(temp_db: Path) -> None:
    mapper = ExchangeMapper(tenant_id=TENANT)
    mapper._map_data_apply_authrization(_granted_authz_row("APPLY-GRANTED-1"), "dsp_catalog")

    task = DeliveryRepository().get_task("APPLY-GRANTED-1", tenant_id=TENANT)
    assert task is not None, "granted 授权应物化交付任务"
    assert task.state == "granted"
    grant = (task.payload_json or {}).get("access_grant") or {}
    # 诚实：无捏造凭据
    assert grant.get("credential") is None, "granted 导入不得捏造凭据（真实授权表无凭据列）"
    assert grant.get("credential_status") == "not_issued", "须显式标 not_issued（不静默缺键）"
    # 反捏造：granted 分支不得出现任何捏造凭据（旧 AK-DEMO / 今 AK-SELF 平台自签前缀皆禁）
    payload_str = str(task.payload_json)
    assert "AK-DEMO" not in payload_str, "不得回潮 AK-DEMO 捏造凭据"
    assert "AK-SELF" not in payload_str, "granted 分支不得自签 AK-SELF 凭据（应诚实 not_issued）"
