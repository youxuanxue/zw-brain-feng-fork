"""Provider snapshot inbox projection — P5 todo counts from live DB."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.domain.repositories.supply_demand import SupplyDemandRepository
from zw_brain.domain.supply_demand_phase import PHASE_REGISTERED
from zw_brain.domain.web_snapshot_redaction import redact_webui_snapshot
from zw_brain.shared import audit as audit_bus
from zw_brain.shared import db as db_module
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

TENANT = "sd-default"


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "provider_projection.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()
        yield db_path
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


@pytest.fixture()
def brain(temp_db: Path) -> BrainService:
    ds = DatabaseStore()
    ds.initialize()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=StateStore(database_store=ds))


def _seed_inbox_rows() -> None:
    catalog = CatalogRepository()
    catalog.upsert_from_resource(
        {
            "id": "cat-proj-field-001",
            "name": "字段裁决待办目录",
            "status": "pending_review",
            "provider": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )
    resources = ResourceApiRepository()
    resources.upsert_asset(
        {
            "resource_code": "res-proj-hookup-001",
            "title": "挂接待审资源",
            "lifecycle_status": "pending_review",
            "owner_org_id": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )
    supply = SupplyDemandRepository()
    supply.register_demand(
        demand_id="dem-proj-match-001",
        title="供需待响应需求",
        applicant="u-demo",
        applicant_dept="市数据局",
        tenant_id=TENANT,
        phase=PHASE_REGISTERED,
    )


def test_manager_snapshot_includes_provider_inbox_arrays(brain: BrainService) -> None:
    _seed_inbox_rows()
    snap = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_ORGAN_MANAGER"}, role="ROLE_ORGAN_MANAGER")
    provider = snap["provider"]
    assert isinstance(provider.get("field_decisions"), list)
    assert isinstance(provider.get("hookup_reviews"), list)
    assert isinstance(provider.get("demand_matches"), list)
    assert len(provider["field_decisions"]) >= 1
    assert len(provider["hookup_reviews"]) >= 1
    assert len(provider["demand_matches"]) >= 1
    assert provider["field_decisions"][0]["id"] == "cat-proj-field-001"


def test_operater_snapshot_includes_provider_for_inline_authoring(brain: BrainService) -> None:
    # roles.md §66 + J2 §166 明确「在线编制目录」属部门操作员职责；
    # /provider shell 必须对 OPERATER 开放（demo customer_demo_j2.sh STEP-1~4 全部 OPERATER 调）。
    # 收件箱待办的可见性由 P5*Inbox.vue 按 canApproveHookup 等岗位 helper 在前端层裁剪。
    _seed_inbox_rows()
    snap = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_ORGAN_OPERATER"}, role="ROLE_ORGAN_OPERATER")
    provider = snap["provider"]
    assert isinstance(provider, dict)
    assert "catalogs" in provider
    assert "field_decisions" in provider


def test_field_decision_projection_item_shape_for_inbox_ui(brain: BrainService) -> None:
    _seed_inbox_rows()
    snap = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_ORGAN_MANAGER"}, role="ROLE_ORGAN_MANAGER")
    row = snap["provider"]["field_decisions"][0]
    assert row["id"] == "cat-proj-field-001"
    assert row["title"]
    assert row["status"] == "pending_review"


def test_hookup_and_demand_projection_shapes(brain: BrainService) -> None:
    _seed_inbox_rows()
    snap = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_ORGAN_MANAGER"}, role="ROLE_ORGAN_MANAGER")
    hookup = snap["provider"]["hookup_reviews"][0]
    demand = snap["provider"]["demand_matches"][0]
    assert hookup["id"] == "res-proj-hookup-001"
    assert hookup["status"] == "pending_review"
    assert demand["id"] == "dem-proj-match-001"
    assert demand["title"]
    assert demand["status"] == "registered"


def test_manager_snapshot_merges_live_disputes(brain: BrainService) -> None:
    repo = ObjectionRepository()
    created = repo.create_case(
        {
            "objection_kind": "catalog_quality",
            "target_type": "catalog",
            "target_id": "cat-proj-dispute-001",
            "title": "提供方待处理异议",
            "complainant_org_id": "ORG-A",
            "provider_org_id": "ORG-B",
            "status": "provider_investigating",
        },
        tenant_id=TENANT,
    )
    snap = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_ORGAN_MANAGER"}, role="ROLE_ORGAN_MANAGER")
    ids = {str(item.get("id")) for item in snap.get("disputes", [])}
    assert created.id in ids
    row = next(item for item in snap["disputes"] if item["id"] == created.id)
    assert row["status"] == "provider_investigating"
    assert row["repository"]["status"] == "provider_investigating"


def test_operater_snapshot_redacts_disputes(brain: BrainService) -> None:
    ObjectionRepository().create_case(
        {
            "objection_kind": "usage",
            "target_type": "delivery",
            "target_id": "del-001",
            "title": "操作员不可见异议",
            "status": "provider_investigating",
        },
        tenant_id=TENANT,
    )
    snap = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_ORGAN_OPERATER"}, role="ROLE_ORGAN_OPERATER")
    assert snap.get("disputes") == []


def test_redact_empty_provider_includes_inbox_keys() -> None:
    from zw_brain.domain.web_snapshot_redaction import _EMPTY_PROVIDER

    # Security admin 不属于「数据供给维护」三角色（OPERATER/MANAGER/BUSIAUDIT），
    # provider snapshot 应被 redact 为 _EMPTY_PROVIDER。
    redacted = redact_webui_snapshot({"provider": {}}, "ROLE_SECURITY_ADMIN")
    assert redacted["provider"] == _EMPTY_PROVIDER


def test_enrich_zones_snapshot_attaches_package_code() -> None:
    from zw_brain.domain.provider_snapshot_projection import enrich_zones_snapshot

    snap = enrich_zones_snapshot(
        {"zones": [{"id": "business", "name": "城市运行专区"}]},
        tenant_id=TENANT,
    )
    zone = snap["zones"][0]
    assert zone.get("package_code"), "P7 订阅应拿到 DB 中已发布专题包的 package_code"


def test_enrich_provider_catalogs_attach_reverse_draft_fields() -> None:
    from zw_brain.domain.provider_snapshot_projection import enrich_provider_snapshot

    snap = enrich_provider_snapshot(
        {
            "provider": {
                "catalogs": [
                    {
                        "id": "cat-parking",
                        "name": "停车场信息目录",
                        "legacy_object_ref": "370000308004000000/000001",
                        "canonical_resource_id": "res-jbxx-ledger",
                    }
                ]
            }
        },
        tenant_id=TENANT,
    )
    cat = snap["provider"]["catalogs"][0]
    assert cat["catalog_code"] == "370000308004000000/000001"
    assert cat["schema_ref"] == "res-jbxx-ledger:legacy:370000308004000000/000001"
