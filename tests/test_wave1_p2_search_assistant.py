# Wave: 1
# Journey: J1
# Pages: P2 资源发现（减摩组件）
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_OPERATER
# Trace:
#   zw_brain/command/handlers/j1/search_assistant.py
#   zw_brain/capability_registry/registered/search.intent.parse.json
#   docs/approved/zw-brain-architecture.md §5.4.4 (减摩组件反约束)
"""F6: P2 搜索上下文助手 — 意图解析 + 缺口追问 + 推荐理由.

测试覆盖：
- 5 种典型一句话查询的 fallback_rule 路径（不依赖推理平台）
- enabled=true 同样走本地规则（zw-brain 不持有推理 SDK/env）
- enabled=false 关闭路径
- audit chain：search.intent.parse 写入 audit feed

数据隔离：realistic_pg_module 克隆 zw_realistic_tmpl（含真实旧平台数据），
模板缺位时整模块 skip（承接旧 require_real_seed 数据量门槛语义），writes 落克隆库、
不污染真实模板。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._pg_realistic import realistic_pg_module  # noqa: F401  (fixture)
from tests._trusted_payload import invoke_trusted

REPO_ROOT = Path(__file__).resolve().parent.parent

# 门槛语义（catalog_entry≥100）由 realistic_pg_module 的 skip-when-absent 承接。
pytestmark = pytest.mark.usefixtures("realistic_pg_module")


@pytest.fixture
def brain():
    # Function-scoped: conftest._isolate_db_env clears the audit-bus sink before
    # every test, so the sink must be (re)configured per test.
    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore
    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    ss = StateStore(database_store=ds)
    return BrainService(state_store=ss)


def _invoke(brain, payload: dict) -> dict:
    role = payload.pop("role", "ROLE_ORGAN_MANAGER")
    out = invoke_trusted(brain, "search.intent.parse", payload, role=role)
    if isinstance(out, dict) and "result" in out and "audit_id" in out:
        return out["result"]
    return out


# ──────────────────────────────────────────────────────────────────────
# 5 种典型一句话查询的 fallback_rule 解析（不依赖推理平台）
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "query,expected_intent,must_contain_keyword",
    [
        ("医保码相关", "discover_resource", "医保码"),
        ("跨省医保结算数据", "discover_resource", "跨省"),
        ("我要房地产数据", "discover_resource", "房地产"),
        ("我提交的申请单审批进度", "query_application", "申请单"),
        ("找不到医疗救助信息，需要登记需求", "register_demand", "医疗救助"),
    ],
)
def test_fallback_rule_typical_queries(brain, query, expected_intent, must_contain_keyword):
    """关闭推理 → fallback_rule 解析 5 种典型查询."""
    out = _invoke(brain, {"query": query, "role": "ROLE_ORGAN_OPERATER", "enabled": False})
    assert out["intent"] == expected_intent
    assert out["source"] == "fallback_rule"
    assert any(must_contain_keyword in k for k in out["keywords"]), (
        f"expected `{must_contain_keyword}` in keywords {out['keywords']}"
    )
    assert isinstance(out["follow_up_questions"], list)
    assert isinstance(out["missing_fields"], list)
    assert out["recommendation_reason"]


def test_fallback_rule_business_environment_query(brain):
    out = _invoke(
        brain,
        {"query": "查省营商环境相关数据", "role": "ROLE_ORGAN_OPERATER", "enabled": False},
    )
    assert out["intent"] == "discover_resource"
    assert any("营商环境" in k for k in out["keywords"]), out["keywords"]


def test_fallback_rule_empty_query_marks_unknown(brain):
    out = _invoke(brain, {"query": "", "role": "ROLE_ORGAN_OPERATER", "enabled": False})
    assert out["intent"] == "unknown"
    assert "query" in out["missing_fields"]


def test_fallback_rule_region_detection(brain):
    """region 词汇命中 _REGION_PATTERN."""
    out = _invoke(brain, {"query": "全省户籍数据", "role": "ROLE_ORGAN_OPERATER", "enabled": False})
    assert out["dimension"]["region"] == "全省"


# ──────────────────────────────────────────────────────────────────────
# enabled=true — 仍走本地确定性规则
# ──────────────────────────────────────────────────────────────────────


def test_enabled_true_uses_local_rule_fields(brain):
    out = _invoke(brain, {"query": "跨省医保码相关", "role": "ROLE_ORGAN_OPERATER", "enabled": True})
    assert out["source"] == "fallback_rule"
    assert out["intent"] == "discover_resource"
    assert "医保码" in out["keywords"]
    assert out["dimension"]["region"] == "跨省"
    assert out["dimension"]["target_resource_hint"]
    assert out["follow_up_questions"]


# ──────────────────────────────────────────────────────────────────────
# 可关闭 + audit chain
# ──────────────────────────────────────────────────────────────────────


def test_disabled_marks_enabled_false(brain):
    out = _invoke(brain, {"query": "户籍数据", "role": "ROLE_ORGAN_OPERATER", "enabled": False})
    assert out["enabled"] is False
    assert out["source"] == "fallback_rule"


def test_audit_chain_records_intent_parse(brain):
    _invoke(brain, {"query": "audit-test-医保码", "role": "ROLE_ORGAN_OPERATER", "enabled": False})
    events = [
        e
        for e in brain.snapshot()["audit_events"]
        if "audit-test-医保码" in e.get("target", "") and e["type"] == "search.intent.parse"
    ]
    assert events, "search.intent.parse not written to audit feed"
    # Action F lock: handler must attribute the audit feed to the per-request
    # role-derived actor (ctx.actor), never the dead `_ui_state["actor"]` constant
    # "system" — guards against a silent regression of audit attribution.
    actor = events[-1]["actor"]
    assert actor != "system"
    assert actor.startswith("user:gov:ROLE_ORGAN_OPERATER:"), actor


# ──────────────────────────────────────────────────────────────────────
# §5.4.4 反约束守卫 — 减摩组件不应替代目录树/筛选器/资源详情
# ──────────────────────────────────────────────────────────────────────


def test_output_does_not_include_resource_list_substitute(brain):
    """cap 输出只含辅助字段，绝不带 'resources' / 'catalog_entries' 之类列表
    （那是 data.search 的职责，不是减摩组件）."""
    out = _invoke(brain, {"query": "户籍数据", "role": "ROLE_ORGAN_OPERATER", "enabled": False})
    for forbidden in ("resources", "catalog_entries", "resource_assets", "items"):
        assert forbidden not in out, (
            f"减摩组件 cap 不应返回 {forbidden} 列表（§5.4.4 反约束）"
        )
