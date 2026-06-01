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

import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from tests._seed_guard import require_real_seed
from tests._trusted_payload import invoke_trusted

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB = REPO_ROOT / ".data" / "test_resource_schema_view_shadow.db"

require_real_seed({"resource_schema_snapshot": 100})


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
    return BrainService(state_store=StateStore(database_store=ds))


@pytest.fixture(scope="module")
def resource_code_with_schema() -> str:
    """真实库里挑一个列数最多、且确实是 resource_asset 的资源（即 P2 详情页可达的 id）。"""
    conn = sqlite3.connect(SHADOW_DB)
    try:
        row = conn.execute(
            "select s.resource_code, count(*) c "
            "from resource_schema_snapshot s "
            "join resource_asset ra on ra.resource_code = s.resource_code "
            "group by s.resource_code order by c desc limit 1"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "seed 库缺少带 schema 快照的 resource_asset，无法做真数据回归"
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


def test_operater_denied_field_schema(brain, resource_code_with_schema) -> None:
    from zw_brain.domain.errors import AccessDeniedError

    with pytest.raises(AccessDeniedError):
        invoke_trusted(
            brain,
            "metadata.schema.query",
            {"resource_code": resource_code_with_schema},
            role="ROLE_ORGAN_OPERATER",
        )
