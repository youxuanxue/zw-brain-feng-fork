# Wave: 1
# Journey: J1
# Pages: P2 资源详情（按类型分型）/ 目录详情（编制规范字段）
# Consumer-faces: API (brain.invoke_skill catalog.resource_view) → WebUI (P2ResourceDetail)
# Roles: ROLE_ORGAN_MANAGER
# Trace:
#   zw_brain/domain/serializers/typed_resource_detail.py
#   zw_brain/domain/services/catalog_service.py enrich_detail (typedDetail / catalogMeta)
#   zw-brain-web/src/pages/P2ResourceDetail.vue
"""分型资源详情 + 目录编制规范字段真数据回归（反馈 5/6，D11 禁 Mock）。

反馈 6：不同资源类型（库表 / 文件 / 文件夹 / 接口）展示的详情应分型区分。本测试用
真实 seed 库断言 catalog.resource_view 给四类资源各自投影出 typedDetail（文件→文件信息、
库表→库表信息、链接→链接信息、接口→接口信息），且文件/库表/链接类至少一条真实记录
其分型字段非空（用真实导入有值的资源做锚）。

反馈 5：目录详情不能少于旧平台编制规范字段。断言 catalogMeta 投影出编制规范字段全集
（目录名称 / 代码 / 来源 / 提供方 / 信息资源格式 / 更新周期 / 摘要 …），关键字段真值非空。
"""
from __future__ import annotations

import contextlib

import psycopg
import pytest
from sqlalchemy.engine import make_url

from tests._pg_realistic import realistic_pg_module  # noqa: F401  (module fixture)
from tests._trusted_payload import invoke_trusted
from zw_brain.domain.serializers.typed_resource_detail import typed_resource_detail
from zw_brain.shared import db as _db

TENANT = "sd-default"

# 真实数据回归：克隆 zw_realistic_tmpl；模板缺位整模块 skip（CI 无 dump），承接旧
# require_real_seed({"resource_asset": 50, "resource_channel_binding": 20}) 跳过语义。
pytestmark = pytest.mark.usefixtures("realistic_pg_module")


@contextlib.contextmanager
def _read_conn() -> psycopg.Connection:
    """只读 psycopg 连接，连当前测试库（realistic 克隆）。绝不开文件。"""
    url = make_url(_db.get_database_url())
    conn = psycopg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        dbname=url.database,
    )
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def brain():
    # function-scoped：realistic_pg_module 模块级钉住真灌库克隆，但根 conftest 的 hands-off
    # 分支仍每测试重置 audit 全局（清 sink）；故 store + 审计 sink 必须每测试对同一克隆重挂。
    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=StateStore(database_store=ds))


def _result(out: object) -> dict:
    if isinstance(out, dict) and "result" in out and "audit_id" in out:
        return out["result"]
    assert isinstance(out, dict)
    return out


def _resource_with_binding(kind: str, channel_kind: str) -> str | None:
    """挑一个指定 resource_kind 且确有对应 channel binding 的真实资源（分型字段有值的锚）。"""
    with _read_conn() as conn:
        row = conn.execute(
            "select a.resource_code from resource_asset a "
            "join resource_channel_binding b "
            "  on a.resource_code = b.resource_code and a.tenant_id = b.tenant_id "
            "where a.tenant_id = %s and a.resource_kind = %s and b.channel_kind = %s "
            "order by a.resource_code limit 1",
            (TENANT, kind, channel_kind),
        ).fetchone()
    return row[0] if row else None


def _view(brain, resource_code: str) -> dict:
    out = invoke_trusted(
        brain,
        "catalog.resource_view",
        {"resource_id": resource_code},
        role="ROLE_ORGAN_MANAGER",
    )
    return _result(out)


# ── 反馈 6：四类型分型 ──────────────────────────────────────────────────────

def test_file_resource_renders_file_info(brain) -> None:
    code = _resource_with_binding("file", "file")
    if not code:
        pytest.skip("seed 库无带 file binding 的文件资源")
    detail = _view(brain, code)
    assert detail.get("resourceKind") == "file"
    typed = detail.get("typedDetail")
    assert typed and typed["kind"] == "file"
    assert typed["kindLabel"] == "文件"
    section = typed["sections"][0]
    assert section["title"] == "文件信息"
    rows = {r["label"]: r["value"] for r in section["rows"]}
    assert set(rows) >= {"文件名称", "文件类型", "文件大小", "存储类型"}
    # 真实文件资源至少文件名 + 文件类型非空（用真实导入有值的资源做锚）
    assert rows["文件名称"], "真实文件资源应有文件名"
    assert rows["文件类型"], "真实文件资源应有文件类型"


def test_table_resource_renders_table_info(brain) -> None:
    code = _resource_with_binding("table", "table")
    if not code:
        pytest.skip("seed 库无带 table binding 的库表资源")
    detail = _view(brain, code)
    assert detail.get("resourceKind") == "table"
    typed = detail.get("typedDetail")
    assert typed and typed["kind"] == "table"
    assert typed["kindLabel"] == "库表"
    section = typed["sections"][0]
    assert section["title"] == "库表信息"
    rows = {r["label"]: r["value"] for r in section["rows"]}
    assert "物理表名" in rows
    assert rows["物理表名"], "真实库表资源应有物理表名"


def test_url_kind_folds_into_file(brain) -> None:
    """资源类型收敛为 库表/文件/API（D53）：链接/文件夹退役，归一化折叠为 file。
    任何残留 url/folder kind 在分型层防御性归入文件分型，不再单列「链接信息」块。"""
    detail = typed_resource_detail(resource_kind="url", bindings=[])
    assert detail["kind"] == "file"
    assert detail["kindLabel"] == "文件"
    assert detail["sections"][0]["title"] == "文件信息"
    folder = typed_resource_detail(resource_kind="folder", bindings=[])
    assert folder["kind"] == "file"


def test_api_resource_template_present_even_when_data_thin(brain) -> None:
    """接口资源：真实库 service-kind 有资源、但 api 服务化 binding 未随本批导入。

    分型模板仍渲染「接口信息」块，缺值诚实空态（None），绝不造假（D11）。
    """
    # 取一个 api/service 类资源，且其挂接目录在 catalog_entry 主表可达——这正是 P2 资源详情页
    # 可达（catalog.resource_view 经 asset.catalog_code 解析）的接口资源；PG 下 limit 无序，
    # 故显式 join + order_by 钉死，避免取到 catalog_code 悬空、resource_view 必 404 的孤儿行。
    with _read_conn() as conn:
        row = conn.execute(
            "select a.resource_code from resource_asset a "
            "join catalog_entry c on c.catalog_code = a.catalog_code and c.tenant_id = a.tenant_id "
            "where a.tenant_id = %s and a.resource_kind in ('service', 'api') "
            "order by a.resource_code limit 1",
            (TENANT,),
        ).fetchone()
    if not row:
        pytest.skip("seed 库无可达（挂接目录主表可解析）的接口类资源")
    detail = _view(brain, row[0])
    typed = detail.get("typedDetail")
    assert typed and typed["kind"] == "api"
    assert typed["kindLabel"] == "接口"
    assert typed["sections"][0]["title"] == "接口信息"


# ── 反馈 5：目录详情编制规范字段 ────────────────────────────────────────────

def test_catalog_meta_carries_compilation_spec_fields(brain) -> None:
    """目录详情 catalogMeta 投影出旧平台编制规范字段全集，关键字段真值非空。"""
    # 挑一个真实业务目录（含中文标题 + 有 summary 描述），其下挂资源
    with _read_conn() as conn:
        row = conn.execute(
            "select a.resource_code from resource_asset a "
            "join catalog_entry c on c.catalog_code = a.catalog_code and c.tenant_id = a.tenant_id "
            "where a.tenant_id = %s and c.title is not null and length(c.title) >= 4 "
            "and c.summary_json::text like '%%description%%' "
            "order by a.resource_code limit 1",
            (TENANT,),
        ).fetchone()
    assert row, "seed 库应有挂资源且带描述的真实目录"
    detail = _view(brain, row[0])
    meta = detail.get("catalogMeta")
    assert meta, "目录详情应投影 catalogMeta（编制规范字段）"
    # 编制规范字段键全集（一个不漏，缺值由前端诚实空态承载）
    assert set(meta) >= {
        "catalogName",
        "catalogCode",
        "catalogType",
        "provider",
        "internalDept",
        "domain",
        "sourceSystem",
        "resourceFormat",
        "updateCycle",
        "catalogVersion",
        "summary",
        # B3（反馈 6.4#5）：补「应用场景 / 业务更新周期 / 数据更新周期」三键。
        "applicationScenario",
        "businessUpdateCycle",
        "dataUpdateCycle",
    }
    # B3：旧导入只有单 update_cycle 时，业务/数据周期回落到它（一个不漏、老数据不空态）。
    assert meta["businessUpdateCycle"] == meta["updateCycle"] or meta["businessUpdateCycle"] is not None
    assert meta["dataUpdateCycle"] == meta["updateCycle"] or meta["dataUpdateCycle"] is not None
    # 关键字段真值非空（用真实有值目录做锚）
    assert meta["catalogName"], "目录名称应非空"
    assert meta["catalogCode"], "目录代码应非空"
    assert meta["summary"], "数据资源摘要应非空"


def test_discovery_card_carries_materialization_kind(brain) -> None:
    """反馈 7 资源类型筛选维度：data.search 卡片携带 materializationKind（从 resource_format 派生）。"""
    out = invoke_trusted(
        brain, "data.search", {"query": "信息", "page": 1}, role="ROLE_ORGAN_OPERATER"
    )
    res = _result(out)
    cards = res.get("results", [])
    if not cards:
        pytest.skip("检索「信息」无命中（数据形态变化）")
    # 至少一张卡片带 materializationKind（真实库 resource_format 已填充档位）
    kinds = {str(c.get("materializationKind")) for c in cards if c.get("materializationKind")}
    assert kinds, "发现页卡片应至少有一类携带物化形态（资源类型筛选维度）"
    # 物化形态取值落在收敛后的合法集合内：库表/文件/API（D53；folder/url 已退役折叠为 file）
    assert kinds <= {"table", "file", "api", "service"}


def test_catalog_access_policy_share_open_semantics(brain) -> None:
    """共享方式 / 共享类型 / 开放类型为首屏决策字段，真实目录应携带（accessPolicy）。"""
    with _read_conn() as conn:
        row = conn.execute(
            "select a.resource_code from resource_asset a "
            "join catalog_entry c on c.catalog_code = a.catalog_code and c.tenant_id = a.tenant_id "
            "where a.tenant_id = %s and c.summary_json::text like '%%shared_type%%' "
            "order by a.resource_code limit 1",
            (TENANT,),
        ).fetchone()
    if not row:
        pytest.skip("seed 库无带 shared_type 的目录")
    detail = _view(brain, row[0])
    policy = detail.get("accessPolicy") or {}
    assert "shareType" in policy
    assert policy.get("shareType"), "真实目录应有共享类型"
