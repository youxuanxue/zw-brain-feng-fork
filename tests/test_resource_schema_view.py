# Wave: 1
# Journey: J1
# Pages: P2 资源详情（字段数据模型只读块）
# Consumer-faces: API (brain.invoke_skill) → WebUI (P2ResourceDetail)
# Roles: ROLE_ORGAN_MANAGER | ROLE_BUSIAUDIT | ROLE_SECURITY_AUDIT
# Trace:
#   zw_brain/command/handlers/j2/metadata.py handler_metadata_schema_query
#   zw-brain-web/src/composables/useResourceSchema.ts
#   scripts/webui_capability_rendered_exemptions.txt（metadata.schema.query 还债出表）
"""字段数据模型只读链路（metadata.schema.query）真数据回归（D11 禁 Mock）。

把此前在 zw-brain-web 无任何渲染消费者的 live+webui 能力 metadata.schema.query
端到端铺到 P2 资源详情页。本测试用真实 seed 库断言：
  1. 授权岗位（MANAGER）能查到某真实资源的逐列 schema 快照（非空、字段齐全）；
  2. 无权岗位（OPERATER）被后端 policy 拒绝（无权=后端兜底，前端再不可见）。
"""
from __future__ import annotations

import contextlib

import psycopg
import pytest
from sqlalchemy.engine import make_url

from tests._pg_realistic import realistic_pg_module  # noqa: F401  (module fixture)
from tests._trusted_payload import invoke_trusted
from zw_brain.shared import db as _db

# 真实数据回归：克隆 zw_realistic_tmpl（含真实旧平台数据）；模板缺位时整模块 skip
# （CI 无 dump），承接旧 require_real_seed({"resource_schema_snapshot": 100}) 跳过语义。
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


@pytest.fixture(scope="module")
def resource_code_with_schema() -> str:
    """真实库里挑一个列数最多、且确实是 resource_asset 的资源（即 P2 详情页可达的 id）。"""
    with _read_conn() as conn:
        row = conn.execute(
            "select s.resource_code, count(*) c "
            "from resource_schema_snapshot s "
            "join resource_asset ra on ra.resource_code = s.resource_code "
            "group by s.resource_code order by c desc limit 1"
        ).fetchone()
    assert row is not None, "seed 库缺少带 schema 快照的 resource_asset，无法做真数据回归"
    return row[0]


@pytest.fixture(scope="module")
def resource_code_bridged_only() -> str:
    """挑一个「resource_code 直查 schema_snapshot 命中=0、但有 active schema_mapping」的 resource_asset。

    这正是键对齐 bridge 要救的多数资源：snapshot 按 db_meta_table.meta_id 入库、与
    resource_asset.resource_code 不同键，只能经 resource_schema_mapping.binding_code 桥接到
    resource_schema_snapshot.binding_code。无此类资源则跳过（seed 形态变化时不误失败）。
    """
    with _read_conn() as conn:
        row = conn.execute(
            "select ra.resource_code, count(*) c "
            "from resource_asset ra "
            "join resource_schema_mapping m on m.resource_code = ra.resource_code and m.status = 'active' "
            "join resource_schema_snapshot s on s.binding_code = m.binding_code "
            "where ra.resource_code not in (select distinct resource_code from resource_schema_snapshot) "
            "group by ra.resource_code order by c desc limit 1"
        ).fetchone()
    if row is None:
        pytest.skip("seed 库无「直查空但可经 binding 桥接」的资源（数据形态变化）")
    return row[0]


def _result(out: object) -> dict:
    if isinstance(out, dict) and "result" in out:
        return out["result"]
    assert isinstance(out, dict)
    return out


def test_manager_reads_real_field_schema(brain, resource_code_with_schema) -> None:
    out = invoke_trusted(
        brain,
        "metadata.schema.query",
        {"resource_code": resource_code_with_schema},
        role="ROLE_ORGAN_MANAGER",
    )
    res = _result(out)
    items = res.get("items", [])
    assert res.get("total", 0) > 0, "授权岗位应查到真实字段 schema"
    assert len(items) == res["total"]
    # schema 快照含表级 + 列级两类行；前端只渲染列级（带 column_name），此处同样断言列级子集。
    column_rows = [
        it.get("schema_json")
        for it in items
        if isinstance(it.get("schema_json"), dict) and (it.get("schema_json") or {}).get("column_name")
    ]
    assert column_rows, "应至少有一列携带 column_name 的真实数据模型字段"
    # 至少一列带中文注释或格式（真实元数据，非占位）。
    assert any(c.get("comment") or c.get("format") for c in column_rows), (
        "真实 schema 快照应携带注释/格式元数据"
    )


def test_bridge_resolves_schema_via_mapping_binding_code(brain, resource_code_bridged_only) -> None:
    """键对齐 bridge：resource_code 直查 schema_snapshot 命中=0 的资源，经 schema_mapping
    的 binding_code 桥接后应能查到真实列级 schema（2%→27% 覆盖率提升的核心路径）。"""
    # 前提：该资源直查确实为空（否则测的不是 bridge 路径）。
    with _read_conn() as conn:
        direct = conn.execute(
            "select count(*) from resource_schema_snapshot where resource_code = %s",
            (resource_code_bridged_only,),
        ).fetchone()[0]
    assert direct == 0, "fixture 应挑选直查为空的资源，才能验证 bridge"

    out = invoke_trusted(
        brain,
        "metadata.schema.query",
        {"resource_code": resource_code_bridged_only},
        role="ROLE_ORGAN_MANAGER",
    )
    res = _result(out)
    items = res.get("items", [])
    assert res.get("total", 0) > 0, "经 binding_code 桥接应查到 schema（bridge 失效则回归 2% 覆盖率）"
    column_rows = [
        it.get("schema_json")
        for it in items
        if isinstance(it.get("schema_json"), dict) and (it.get("schema_json") or {}).get("column_name")
    ]
    assert column_rows, "桥接结果应含至少一列携带 column_name 的真实字段"


def test_operater_denied_field_schema(brain, resource_code_with_schema) -> None:
    from zw_brain.domain.errors import AccessDeniedError

    with pytest.raises(AccessDeniedError):
        invoke_trusted(
            brain,
            "metadata.schema.query",
            {"resource_code": resource_code_with_schema},
            role="ROLE_ORGAN_OPERATER",
        )
