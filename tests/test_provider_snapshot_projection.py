"""Provider snapshot inbox projection — P5 todo counts from live DB."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy.engine import make_url

from tests._pg_admin import drop_database
from tests._pg_realistic import realistic_pg_module  # noqa: F401  (module fixture)
from tests._trusted_payload import actor_snapshot, invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.domain.repositories.supply_demand import SupplyDemandRepository
from zw_brain.domain.supply_demand_phase import PHASE_REGISTERED
from zw_brain.domain.web_snapshot_redaction import redact_webui_snapshot
from zw_brain.shared import audit as audit_bus
from zw_brain.shared import db as db_module
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.state_store import StateStore

TENANT = "sd-default"

# 供数面 fixture 全用此机构作 owner_org_id（省大数据局）。M4 部门数据可见域收口后，
# 部门角色（MANAGER/OPERATER）snapshot 只见本机构(+下级) provider 行——故 system.snapshot
# 调用须携带与 seed 同机构的会话上下文（invoke_trusted 默认 ORG-A 与 seed 不符会被收口为空）。
# 全局角色（BUSIAUDIT）visible_org_codes=None 放行全量，无需带机构。
SEED_ORG = "11370000MB284651XL"


def _dept_snapshot(brain: BrainService, role: str) -> dict:
    """部门角色 system.snapshot：携带与 fixture 同机构的会话（M4 收口后才看得到自家 provider 行）。"""
    return invoke_trusted(
        brain, "system.snapshot", {"role": role}, role=role,
        snapshot=actor_snapshot(role, org_code=SEED_ORG),
    )


@pytest.fixture()
def seed_db(realistic_pg_module: str) -> str:  # noqa: F811  (pytest fixture request, not a redef)
    """真灌库（含已发布专题包/反向草稿字段）依赖声明。

    这几条 enrich 断言依赖真实库数据。PG 迁移后真灌库由 realistic_pg_module 克隆
    zw_realistic_tmpl 注入 ZW_BRAIN_DATABASE_URL；模板缺位（CI 无 dump）整模块 skip，
    承接旧真灌库缺位跳过语义。无需手开文件 / 拷贝 / 旧文件路径环境变量。
    """
    return realistic_pg_module


@pytest.fixture()
def temp_db(_pg_template) -> str:
    """纯 schema 测试：显式克隆会话级空模板（已 alembic upgrade head 建全表）为一个
    一次性空库并指向它，测试体自行灌入所需行。

    不直接复用根 conftest 的 function-scoped 空克隆，是因为本模块还有 seed_db 测试经
    module-scoped realistic_pg_module 设了 ZW_BRAIN_TEST_REALISTIC_DB——一旦该 env 在位，
    conftest 的 _isolate_db_env 会整模块「让位、不克隆」。故 temp_db 自建空克隆，与
    realistic 数据彻底隔离、不受测试执行顺序影响。无真灌库文件 / 临时文件 / 单机文件库。
    """
    template, server_url, maint = _pg_template
    clone = f"zw_provproj_{uuid.uuid4().hex}"
    drop_database(maint, clone)
    maint.execute(f'CREATE DATABASE "{clone}" TEMPLATE "{template}"')
    saved_url = os.environ.get("ZW_BRAIN_DATABASE_URL")
    saved_realistic = os.environ.get("ZW_BRAIN_TEST_REALISTIC_DB")
    saved_default = db_module.DEFAULT_PG_URL
    clone_url = make_url(
        server_url.set(database=clone).render_as_string(hide_password=False)
    ).render_as_string(hide_password=False)
    # 关键：本测试期间临时撤掉 realistic 标记，否则 _isolate_db_env 已让位、且其它路径
    # 可能据该标记回落 realistic 库；此处明确钉到空克隆。
    os.environ.pop("ZW_BRAIN_TEST_REALISTIC_DB", None)
    os.environ["ZW_BRAIN_DATABASE_URL"] = clone_url
    db_module.DEFAULT_PG_URL = clone_url
    db_module.reset_engine_cache()
    try:
        yield clone
    finally:
        db_module.DEFAULT_PG_URL = saved_default
        db_module.reset_engine_cache()
        # 关闭进程级 audit store（D4：独立 psycopg 连接，不在 ORM 引擎缓存里），否则其
        # 连接会钉住即将 DROP 的克隆库。set_default_store(None) 关旧 store。
        from zw_brain.shared.audit import store as _audit_store

        closer = getattr(_audit_store, "set_default_store", None)
        if callable(closer):
            try:
                closer(None)
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass
        if saved_url is None:
            os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
        else:
            os.environ["ZW_BRAIN_DATABASE_URL"] = saved_url
        if saved_realistic is not None:
            os.environ["ZW_BRAIN_TEST_REALISTIC_DB"] = saved_realistic
        drop_database(maint, clone)


@pytest.fixture()
def brain(temp_db: str) -> BrainService:
    ds = DatabaseStore()
    ds.initialize()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=StateStore(database_store=ds))


def _seed_inbox_rows() -> None:
    GovernanceProjectionRepository().upsert_org(
        {"org_code": SEED_ORG, "org_name": "省大数据局"}, tenant_id=TENANT
    )
    catalog = CatalogRepository()
    # 反向编目审核收件箱口径（0611 修复项 R-4）= source=reverse ∧ lifecycle=draft（与 confirm/reject
    # handler 可办前置一致）；正向编制在审单（pending_review、无 source）不得混入。
    catalog.upsert_from_resource(
        {
            "id": "cat-proj-field-001",
            "name": "反向编目待审核草稿",
            "status": "draft",
            "source": "reverse",
            "schema_ref": "schema:cat-proj-field-001",
            "provider": "11370000MB284651XL",
            "draft_field_suggestions": [{"field": "xm"}, {"field": "sfzh"}],
        },
        tenant_id=TENANT,
    )
    catalog.upsert_from_resource(
        {
            "id": "cat-proj-forward-001",
            "name": "正向编制在审目录（不进反向编目审核收件箱）",
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
        target_resource_hint="低保对象",
    )


def test_manager_snapshot_includes_provider_inbox_arrays(brain: BrainService) -> None:
    _seed_inbox_rows()
    snap = _dept_snapshot(brain, "ROLE_ORGAN_MANAGER")
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
    snap = _dept_snapshot(brain, "ROLE_ORGAN_OPERATER")
    services = snap["provider"]["services"]
    svc = next((s for s in services if s["id"] == "res-api-op-001"), None)
    assert svc is not None, "操作员应能看到自己注册的 API 服务（services 未被 redact）"
    # 行内操作（提交审核/发布/下线）按原始生命周期码分流，故 lifecycle_status 必须透传。
    assert svc["lifecycle_status"] == "draft"


def test_operater_snapshot_includes_datasource_endpoints(temp_db: str) -> None:
    """PR #340：数据源管理/反向编目/挂接 = 操作员供数主线，snapshot 须带 datasource_endpoints。"""
    from zw_brain.domain.repositories.datasource_endpoint import DatasourceEndpointRepository

    DatasourceEndpointRepository().upsert_endpoint(
        {
            "endpoint_id": "ep-operater-snap-001",
            "display_name": "操作员可见数据源",
            "db_name": "op_db",
            "db_type": "mysql",
            "org_code": SEED_ORG,
            "data_partition": "front",
            "connectivity_status": "connected",
            "connection_ref": "manual:datasource:ep-operater-snap-001",
        },
        tenant_id=TENANT,
    )
    brain = BrainService(state_store=StateStore(database_store=DatabaseStore()))
    DatabaseStore().initialize()
    snap = _dept_snapshot(brain, "ROLE_ORGAN_OPERATER")
    endpoints = snap["provider"].get("datasource_endpoints")
    assert isinstance(endpoints, list)
    assert any(e.get("endpoint_id") == "ep-operater-snap-001" for e in endpoints)


def test_field_decision_projection_item_shape_for_inbox_ui(brain: BrainService) -> None:
    _seed_inbox_rows()
    snap = _dept_snapshot(brain, "ROLE_ORGAN_MANAGER")
    row = snap["provider"]["field_decisions"][0]
    assert row["id"] == "cat-proj-field-001"
    assert row["title"]
    assert row["status"] == "draft"
    # D57⑧ 部门审去盲批：被审内容随行下发——责任单位中文名来自 org_projection，不回落 org id。
    # + 字段建议数（向导 draft_field_suggestions 条数）。
    assert row["owner"] == "省大数据局"
    assert row["field_count"] == 2


def test_field_decision_inbox_lists_only_actionable_reverse_drafts(brain: BrainService) -> None:
    """0611 修复项 R-4（6.9#6）：收件箱口径 = source=reverse ∧ lifecycle=draft，与 confirm/reject
    handler 可办前置一致。此前列 pending_review 全集——正向在审单/已确认反向单混入，
    每行点「通过审核」必 409；待审草稿反而不出现。"""
    _seed_inbox_rows()
    catalog = CatalogRepository()
    # 已确认的反向单（lifecycle=pending_review）：已离开可办态，不得再出现在收件箱。
    catalog.upsert_from_resource(
        {
            "id": "cat-proj-reverse-confirmed-001",
            "name": "已确认反向草稿（已进入正向审核流）",
            "status": "pending_review",
            "source": "reverse",
            "provider": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )
    snap = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_BUSIAUDIT"}, role="ROLE_BUSIAUDIT")
    ids = [row["id"] for row in snap["provider"]["field_decisions"]]
    assert "cat-proj-field-001" in ids  # 待审反向草稿（可办）必须出现
    assert "cat-proj-forward-001" not in ids  # 正向在审单不混入
    assert "cat-proj-reverse-confirmed-001" not in ids  # 已确认反向单不再可办


def test_hookup_and_demand_projection_shapes(brain: BrainService) -> None:
    _seed_inbox_rows()
    snap = _dept_snapshot(brain, "ROLE_ORGAN_MANAGER")
    hookup = snap["provider"]["hookup_reviews"][0]
    demand = snap["provider"]["demand_matches"][0]
    assert hookup["id"] == "res-proj-hookup-001"
    assert hookup["status"] == "pending_review"
    assert demand["id"] == "dem-proj-match-001"
    assert demand["title"]
    assert demand["status"] == "registered"
    assert demand["target_resource_hint"] == "低保对象"


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


@pytest.mark.no_db
def test_redact_empty_provider_includes_inbox_keys() -> None:
    from zw_brain.domain.web_snapshot_redaction import _EMPTY_PROVIDER

    # 安全审计员不属于「数据供给维护」三角色（OPERATER/MANAGER/BUSIAUDIT），
    # provider snapshot 应被 redact 为 _EMPTY_PROVIDER。
    # （原用 ROLE_SECURITY_ADMIN，该角色本期退役 D55/P16，改用同样非供给角色 ROLE_SECURITY_AUDIT。）
    redacted = redact_webui_snapshot({"provider": {}}, "ROLE_SECURITY_AUDIT")
    assert redacted["provider"] == _EMPTY_PROVIDER


def test_enrich_zones_snapshot_attaches_package_code(seed_db: str) -> None:
    from zw_brain.domain.provider_snapshot_projection import enrich_zones_snapshot

    snap = enrich_zones_snapshot(
        {"zones": [{"id": "business", "name": "城市运行专区"}]},
        tenant_id=TENANT,
    )
    zone = snap["zones"][0]
    assert zone.get("package_code"), "P7 订阅应拿到 DB 中已发布专题包的 package_code"


def test_enrich_provider_catalogs_attach_reverse_draft_fields(temp_db: str) -> None:
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


def test_provider_catalogs_replaced_with_live_rows_when_db_nonempty(temp_db: str) -> None:
    """T9 诚实化（承 #191 读路径单源）：DB 有目录行时，provider.catalogs 整体替换为真实库
    现算行——新编目录即时可见；api-group:*（API 分组）、basic-elem:*（国家基本要素）、
    retired（历史版本尾巴）不进目录管理清单。owner 经 ReferenceService 解析机构中文名。"""
    from zw_brain.domain.provider_snapshot_projection import enrich_provider_snapshot

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


def test_provider_resources_replaced_with_live_rows_when_db_nonempty(temp_db: str) -> None:
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


# ──────────────────────────────────────────────────────────────────────
# D57⑨（R10）：挂接审核收件箱去盲批——被审登记信息 + 关联资源/目录名 + 驳回带理由
# ──────────────────────────────────────────────────────────────────────


def test_hookup_review_row_carries_registration_detail(brain: BrainService) -> None:
    """收件箱行带被审内容：resource_name/catalog_name（前端「关联资源/所属目录」列不再恒「—」）
    + 登记信息（形态/提供方/挂接位置/描述/共享类型/字段数），全部真实登记字段。"""
    CatalogRepository().upsert_from_resource(
        {
            "id": "cat-proj-hookup-parent",
            "name": "挂接所属目录甲",
            "status": "active",
            "provider": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )
    ResourceApiRepository().upsert_asset(
        {
            "resource_code": "res-proj-hookup-d57",
            "title": "挂接待审资源（带登记信息）",
            "resource_kind": "table",
            "lifecycle_status": "pending_review",
            "owner_org_id": "11370000MB284651XL",
            "catalog_code": "cat-proj-hookup-parent",
            "source_ref": "db:dsp_meta.t_parking_info",
            "access_policy_json": {"share_type": "2", "share_condition": "仅政务部门"},
            "summary_json": {"desc": "停车场基础信息库表", "fields": ["lot_id", "lot_name", "capacity"]},
        },
        tenant_id=TENANT,
    )
    snap = _dept_snapshot(brain, "ROLE_ORGAN_MANAGER")
    row = next(r for r in snap["provider"]["hookup_reviews"] if r["id"] == "res-proj-hookup-d57")
    assert row["resource_name"] == "挂接待审资源（带登记信息）"
    assert row["catalog_name"] == "挂接所属目录甲"
    assert row["kind_label"] == "库表"
    assert row["source_ref"] == "db:dsp_meta.t_parking_info"
    assert row["desc"] == "停车场基础信息库表"
    assert row["share_type_label"] == "有条件共享"
    assert row["field_count"] == 3


def test_hookup_review_reject_with_reason_returns_to_draft(brain: BrainService) -> None:
    """驳回（decision=return_for_fix）带理由：资产退回 draft、理由落 summary_json
    （提交方整改依据），收件箱行随之消失。"""
    ResourceApiRepository().upsert_asset(
        {
            "resource_code": "res-proj-hookup-reject",
            "title": "将被驳回的挂接资源",
            "resource_kind": "file",
            "lifecycle_status": "pending_review",
            "owner_org_id": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )
    out = invoke_trusted(
        brain,
        "resource.asset.review",
        {
            "resource_code": "res-proj-hookup-reject",
            "decision": "return_for_fix",
            "reason": "登记信息缺少数据来源说明，请补全后重新提交",
            "confirmed": True,
        },
        role="ROLE_ORGAN_MANAGER",
    )["result"]
    assert out["lifecycle_status"] == "draft"

    record = next(
        r
        for r in ResourceApiRepository().list_assets(tenant_id=TENANT)
        if r.resource_code == "res-proj-hookup-reject"
    )
    assert record.summary_json.get("review_return_reason") == "登记信息缺少数据来源说明，请补全后重新提交"

    snap = _dept_snapshot(brain, "ROLE_ORGAN_MANAGER")
    assert all(r["id"] != "res-proj-hookup-reject" for r in snap["provider"]["hookup_reviews"])

    # 驳回理由闭环（写了就必须有读面）：提交方在「资源管理清单」（provider.resources 投影）
    # 看到整改依据——操作员 snapshot 带 resources partial key（_PROVIDER_PARTIAL_KEYS）。
    op_snap = _dept_snapshot(brain, "ROLE_ORGAN_OPERATER")
    row = next(r for r in op_snap["provider"]["resources"] if r["id"] == "res-proj-hookup-reject")
    assert row["review_return_reason"] == "登记信息缺少数据来源说明，请补全后重新提交"
    assert row["lifecycle_status"] == "draft"


def test_hookup_review_reject_requires_reason_fail_closed(brain: BrainService) -> None:
    """D57⑨ 后端 fail-closed：挂接驳回不带/空理由经任何消费面直调一律拦（前端 toast 只是第一道）。"""
    from zw_brain.command.brain import InvalidStateError

    ResourceApiRepository().upsert_asset(
        {
            "resource_code": "res-proj-hookup-no-reason",
            "title": "无理由驳回应被拦",
            "resource_kind": "table",
            "lifecycle_status": "pending_review",
            "owner_org_id": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )
    for payload in (
        {"resource_code": "res-proj-hookup-no-reason", "decision": "return_for_fix", "confirmed": True},
        {"resource_code": "res-proj-hookup-no-reason", "decision": "return_for_fix", "reason": "  ", "confirmed": True},
    ):
        with pytest.raises(InvalidStateError):
            invoke_trusted(brain, "resource.asset.review", payload, role="ROLE_ORGAN_MANAGER")


# ──────────────────────────────────────────────────────────────────────
# S3 万级规模性能：enrich_provider / enrich_zones deepcopy 开关 + assets 预取
# 默认 copy=True 保持纯函数语义（不变异入参）；handler 链路传 copy=False 原地写。
# ──────────────────────────────────────────────────────────────────────


def test_enrich_provider_default_copy_does_not_mutate_input(temp_db: str) -> None:
    """默认 copy=True：拿原 dict 调 enrich，断言原 dict 未被变异（非变异契约）。"""
    import copy as _copy

    from zw_brain.domain.provider_snapshot_projection import enrich_provider_snapshot

    ResourceApiRepository().upsert_asset(
        {
            "resource_code": "res-prov-nm-001",
            "title": "供数资源",
            "resource_kind": "table",
            "lifecycle_status": "pending_review",
            "owner_org_id": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )
    original = {"provider": {"resources": [{"id": "seed-res-demo", "name": "seed"}]}}
    before = _copy.deepcopy(original)
    out = enrich_provider_snapshot(original, tenant_id=TENANT)
    assert out is not original, "copy=True 应返回新 dict"
    assert original == before, "copy=True 不得变异传入快照"
    assert "res-prov-nm-001" in {r["id"] for r in out["provider"]["resources"]}


def test_enrich_provider_copy_false_writes_in_place(temp_db: str) -> None:
    """copy=False：原地写同一 dict（identity 相同）。"""
    from zw_brain.domain.provider_snapshot_projection import enrich_provider_snapshot

    ResourceApiRepository().upsert_asset(
        {
            "resource_code": "res-prov-ip-001",
            "title": "供数资源2",
            "resource_kind": "table",
            "lifecycle_status": "pending_review",
            "owner_org_id": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )
    snap: dict = {"provider": {"resources": [{"id": "seed-res-demo"}]}, "keep": 1}
    out = enrich_provider_snapshot(snap, tenant_id=TENANT, copy=False)
    assert out is snap, "copy=False 应原地写、返回同一对象"
    assert "res-prov-ip-001" in {r["id"] for r in out["provider"]["resources"]}
    assert out["keep"] == 1, "原地写不应破坏其它键"


def test_enrich_provider_uses_prefetched_assets(temp_db: str) -> None:
    """assets 预取：services/resources 投影直接吃传入列表，不回落 DB（万级 4→1 收口可测证据）。

    assets=[] 时应得空 services/resources（不回落 DB 全扫）；assets=None 才回落自查。
    """
    from zw_brain.domain.provider_snapshot_projection import enrich_provider_snapshot

    ResourceApiRepository().upsert_asset(
        {
            "resource_code": "res-prefetch-db",
            "title": "DB 资源",
            "resource_kind": "api",
            "lifecycle_status": "active",
            "owner_org_id": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )
    out_empty = enrich_provider_snapshot({"provider": {}}, tenant_id=TENANT, assets=[], copy=False)
    assert out_empty["provider"]["services"] == [], "assets=[] 应被采用，services 空（不回落 DB）"
    out_db = enrich_provider_snapshot({"provider": {}}, tenant_id=TENANT, assets=None, copy=False)
    assert "res-prefetch-db" in {s["id"] for s in out_db["provider"]["services"]}, (
        "assets=None 回落 DB 自查应看到 DB 资源（区分 [] 与 None 语义）"
    )


def test_enrich_provider_snapshot_includes_datasource_endpoints(temp_db: str) -> None:
    from zw_brain.domain.provider_snapshot_projection import enrich_provider_snapshot
    from zw_brain.domain.repositories.datasource_endpoint import DatasourceEndpointRepository

    DatasourceEndpointRepository().upsert_endpoint(
        {
            "endpoint_id": "ep-enrich-001",
            "display_name": "挂接源",
            "db_name": "hook_db",
            "db_type": "mysql",
            "data_partition": "service",
            "connectivity_status": "connected",
            "connection_ref": "manual:datasource:ep-enrich-001",
        },
        tenant_id=TENANT,
    )
    out = enrich_provider_snapshot({"provider": {}}, tenant_id=TENANT, copy=True)
    endpoints = out["provider"]["datasource_endpoints"]
    assert isinstance(endpoints, list)
    assert any(item.get("endpoint_id") == "ep-enrich-001" for item in endpoints)


def test_enrich_zones_default_copy_does_not_mutate_input(seed_db: str) -> None:
    """默认 copy=True：zones 投影不变异传入快照。"""
    import copy as _copy

    from zw_brain.domain.provider_snapshot_projection import enrich_zones_snapshot

    original = {"zones": [{"id": "business", "name": "城市运行专区"}]}
    before = _copy.deepcopy(original)
    out = enrich_zones_snapshot(original, tenant_id=TENANT)
    assert out is not original
    assert original == before, "copy=True 不得变异传入快照（zone 不应被加 package_code）"
    assert out["zones"][0].get("package_code"), "投影结果仍挂上 package_code"


def test_enrich_zones_copy_false_writes_in_place(seed_db: str) -> None:
    from zw_brain.domain.provider_snapshot_projection import enrich_zones_snapshot

    snap: dict = {"zones": [{"id": "business", "name": "城市运行专区"}]}
    out = enrich_zones_snapshot(snap, tenant_id=TENANT, copy=False)
    assert out is snap, "copy=False 应原地写、返回同一对象"
    assert out["zones"][0].get("package_code")
