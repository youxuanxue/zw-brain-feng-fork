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
SEED_DB = Path(__file__).resolve().parent.parent / ".data" / "zw_brain.db"


@pytest.fixture()
def seed_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    """显式钉到真实 seed DB + 隔离 engine cache。

    这两条 enrich 断言依赖真实库的已发布专题包/反向草稿字段。它们原先靠"环境里
    ZW_BRAIN_DB_PATH 默认指向 .data/zw_brain.db"的隐式约定——但仓内约 30 个 fixture
    用裸 os.environ 改 ZW_BRAIN_DB_PATH 且无 teardown（见 .testing/debt 登记），上游某条
    real-data 测试泄漏后会把这里指向空库 → "no such table"。pin + monkeypatch 自动还原
    使其对上游泄漏免疫，并声明真实依赖（与同模块 temp_db / 邻居 _shadow_db 同模式）。
    """
    if not SEED_DB.is_file():
        pytest.skip("seed db missing — 跑 scripts/customer_acceptance_up.sh 重建")
    monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(SEED_DB))
    monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
    with db_module._CACHE_LOCK:
        db_module._ENGINE_CACHE.clear()
    yield SEED_DB
    with db_module._CACHE_LOCK:
        db_module._ENGINE_CACHE.clear()


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
            # G4 分流后 kind 有语义：挂接收件箱=非 API 类；upsert_asset 缺省 kind 默认 "api"
            # （仓库历史默认）会把本行误归 API 注册审核侧，故 fixture 显式声明库表资产。
            "resource_kind": "table",
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


def test_operater_snapshot_includes_registered_api_services(brain: BrainService) -> None:
    """D54 GATE-1：代理服务注册 = 部门操作员 + 部门管理员。操作员注册 API 服务后，必须能在
    快照 provider.services 看到自己的服务（含原始 lifecycle_status）以行内提交审核/管理——
    故 provider.services 不再对 OPERATER redact（_PROVIDER_PARTIAL_KEYS 加 services）。"""
    resources = ResourceApiRepository()
    resources.upsert_asset(
        {
            "resource_code": "res-api-op-001",
            "title": "操作员注册的代理服务",
            "resource_kind": "api",
            "lifecycle_status": "draft",
            "owner_org_id": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )
    snap = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_ORGAN_OPERATER"}, role="ROLE_ORGAN_OPERATER")
    services = snap["provider"]["services"]
    svc = next((s for s in services if s["id"] == "res-api-op-001"), None)
    assert svc is not None, "操作员应能看到自己注册的 API 服务（services 未被 redact）"
    # 行内操作（提交审核/发布/下线）按原始生命周期码分流，故 lifecycle_status 必须透传。
    assert svc["lifecycle_status"] == "draft"


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

    # 安全审计员不属于「数据供给维护」三角色（OPERATER/MANAGER/BUSIAUDIT），
    # provider snapshot 应被 redact 为 _EMPTY_PROVIDER。
    # （原用 ROLE_SECURITY_ADMIN，该角色本期退役 D55/P16，改用同样非供给角色 ROLE_SECURITY_AUDIT。）
    redacted = redact_webui_snapshot({"provider": {}}, "ROLE_SECURITY_AUDIT")
    assert redacted["provider"] == _EMPTY_PROVIDER


def test_enrich_zones_snapshot_attaches_package_code(seed_db: Path) -> None:
    from zw_brain.domain.provider_snapshot_projection import enrich_zones_snapshot

    snap = enrich_zones_snapshot(
        {"zones": [{"id": "business", "name": "城市运行专区"}]},
        tenant_id=TENANT,
    )
    zone = snap["zones"][0]
    assert zone.get("package_code"), "P7 订阅应拿到 DB 中已发布专题包的 package_code"


def test_enrich_provider_catalogs_attach_reverse_draft_fields(temp_db: Path) -> None:
    """seed 回落路径（DB 无 catalog_entry 行时保留传入 catalogs 并补反向编目字段）。

    T9 诚实化后 DB 非空即整体替换为 live 投影（见下两条测试），本断言只覆盖空库回落。"""
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


def test_provider_catalogs_replaced_with_live_rows_when_db_nonempty(temp_db: Path) -> None:
    """T9 诚实化（承 #191 读路径单源）：DB 有目录行时，provider.catalogs 整体替换为真实库
    现算行——新编目录即时可见；api-group:*（API 分组）、basic-elem:*（国家基本要素）、
    retired（历史版本尾巴）不进目录管理清单。owner 经 ReferenceService 解析机构中文名。"""
    from zw_brain.domain.provider_snapshot_projection import enrich_provider_snapshot
    from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository

    GovernanceProjectionRepository().upsert_org(
        {"org_code": "11370000MB284651XL", "org_name": "省大数据局"}, tenant_id=TENANT
    )
    catalog = CatalogRepository()
    catalog.upsert_from_resource(
        {
            "id": "j2-inline-live-001",
            "name": "新编医疗救助目录",
            "status": "draft",
            "provider": "11370000MB284651XL",
            "data_catalog_code": "DRC-37-000001",
        },
        tenant_id=TENANT,
    )
    catalog.upsert_from_resource(
        {"id": "api-group:legacy-1", "name": "API 分组（不进清单）", "status": "active", "provider": "platform"},
        tenant_id=TENANT,
    )
    catalog.upsert_from_resource(
        {"id": "basic-elem:nat-1", "name": "国家基本要素（不进清单）", "status": "active", "provider": "platform"},
        tenant_id=TENANT,
    )
    catalog.upsert_from_resource(
        {"id": "cat-old-version", "name": "退役历史版本", "status": "retired", "provider": "11370000MB284651XL"},
        tenant_id=TENANT,
    )

    snap = enrich_provider_snapshot(
        {"provider": {"catalogs": [{"id": "seed-demo", "name": "seed 演示目录"}]}},
        tenant_id=TENANT,
    )
    catalogs = snap["provider"]["catalogs"]
    codes = {c["catalog_code"] for c in catalogs}
    assert "j2-inline-live-001" in codes, "新编目录必须即时进入目录管理清单"
    assert "seed-demo" not in codes, "DB 非空时不得再展示 seed 演示行"
    assert not any(code.startswith(("api-group:", "basic-elem:")) for code in codes)
    assert "cat-old-version" not in codes, "retired 行不进管理清单"
    row = next(c for c in catalogs if c["catalog_code"] == "j2-inline-live-001")
    assert row["owner"] == "省大数据局", "owner 应解析为机构中文名（ReferenceService）"
    assert row["data_catalog_code"] == "DRC-37-000001"
    assert row["status"] == "draft"


def test_provider_resources_replaced_with_live_rows_when_db_nonempty(temp_db: Path) -> None:
    """T9 诚实化：DB 有资源行时 provider.resources 整体替换为真实库现算行（排除 retired）。"""
    from zw_brain.domain.provider_snapshot_projection import enrich_provider_snapshot

    resources = ResourceApiRepository()
    resources.upsert_asset(
        {
            "resource_code": "res-live-table-001",
            "title": "新挂接库表资源",
            "resource_kind": "table",
            "lifecycle_status": "pending_review",
            "owner_org_id": "11370000MB284651XL",
            "catalog_code": "j2-inline-live-001",
        },
        tenant_id=TENANT,
    )
    resources.upsert_asset(
        {
            "resource_code": "res-live-retired-001",
            "title": "已退役资源（不进清单）",
            "resource_kind": "file",
            "lifecycle_status": "retired",
            "owner_org_id": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )

    snap = enrich_provider_snapshot(
        {"provider": {"resources": [{"id": "seed-res-demo", "name": "seed 演示资源"}]}},
        tenant_id=TENANT,
    )
    rows = snap["provider"]["resources"]
    ids = {r["id"] for r in rows}
    assert "res-live-table-001" in ids
    assert "seed-res-demo" not in ids
    assert "res-live-retired-001" not in ids
    row = next(r for r in rows if r["id"] == "res-live-table-001")
    assert row["resource_kind"] == "table"
    assert row["catalog_code"] == "j2-inline-live-001"
