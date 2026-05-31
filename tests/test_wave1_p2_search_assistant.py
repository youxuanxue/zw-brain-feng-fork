# Wave: 1
# Journey: J1
# Pages: P2 资源发现（减摩组件）
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_OPERATER
# Trace:
#   zw_brain/command/handlers/j1/search_assistant.py
#   zw_brain/capability_registry/registered/search.intent.parse.json
#   docs/approved/zw-brain-architecture.md §5.4.4 (减摩组件反约束)
"""F6: P2 搜索上下文助手 — 意图解析 + 缺口追问 + 推荐理由 + 推理失败降级.

测试覆盖：
- 5 种典型一句话查询的 fallback_rule 路径（不依赖推理平台）
- inference 路径（monkeypatch chat 返回 JSON）
- 推理失败降级路径（monkeypatch chat 抛 InferenceError）
- enabled=false 关闭路径
- audit chain：search.intent.parse 写入 audit feed
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from tests._seed_guard import require_real_seed
from tests._trusted_payload import invoke_trusted

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB = REPO_ROOT / ".data" / "test_wave1_p2_search_shadow.db"

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
# inference 路径 — monkeypatch chat 返回结构化 JSON
# ──────────────────────────────────────────────────────────────────────


def test_inference_path_returns_structured_fields(brain, monkeypatch):
    from zw_brain.command.handlers.j1 import search_assistant as sa
    from zw_brain.shared.inference.client import ChatResult

    mocked_payload = (
        '{"intent":"discover_resource","keywords":["医保码","跨省"],'
        '"dimension":{"keyword":["医保码"],"target_resource_hint":"医保码信息","region":"跨省"},'
        '"missing_fields":["数据更新频率"],'
        '"recommendation_reason":"基于关键词医保码+跨省，推断为资源发现。",'
        '"follow_up_questions":["需要原始库表还是接口？","限定哪些省份？"]}'
    )
    calls: list[dict] = []

    def _mock_chat(messages, *, model, request_id, temperature=0.0, **kwargs):
        calls.append({"model": model, "request_id": request_id, "messages": [(m.role, m.content) for m in messages]})
        return ChatResult(text=mocked_payload, model=model or "demo", usage={"total_tokens": 64})

    monkeypatch.setattr(sa, "_inference_chat", _mock_chat)
    out = _invoke(brain, {"query": "跨省医保码相关", "role": "ROLE_ORGAN_OPERATER", "enabled": True})
    assert out["source"] == "inference"
    assert out["intent"] == "discover_resource"
    assert "医保码" in out["keywords"]
    assert out["dimension"]["region"] == "跨省"
    assert out["dimension"]["target_resource_hint"] == "医保码信息"
    assert out["follow_up_questions"]
    assert calls, "inference chat must be called"
    assert calls[0]["request_id"].startswith("search-intent-")


def test_inference_path_strips_markdown_fence(brain, monkeypatch):
    """推理返回带 ```json``` 围栏的 JSON 时仍可解析."""
    from zw_brain.command.handlers.j1 import search_assistant as sa
    from zw_brain.shared.inference.client import ChatResult

    fenced = (
        "```json\n"
        '{"intent":"discover_resource","keywords":["户籍"],'
        '"dimension":{"keyword":["户籍"],"target_resource_hint":null,"region":null},'
        '"missing_fields":[],"recommendation_reason":"测试","follow_up_questions":[]}'
        "\n```"
    )
    monkeypatch.setattr(sa, "_inference_chat",
                        lambda *a, **kw: ChatResult(text=fenced, model="demo"))
    out = _invoke(brain, {"query": "户籍数据", "role": "ROLE_ORGAN_OPERATER", "enabled": True})
    assert out["source"] == "inference"
    assert out["keywords"] == ["户籍"]


def test_inference_invalid_json_degrades_to_fallback(brain, monkeypatch):
    """推理返回不可解析的非 JSON 字符串 → 降级到本地规则."""
    from zw_brain.command.handlers.j1 import search_assistant as sa
    from zw_brain.shared.inference.client import ChatResult

    monkeypatch.setattr(sa, "_inference_chat",
                        lambda *a, **kw: ChatResult(text="抱歉我没听懂", model="demo"))
    out = _invoke(brain, {"query": "找不到工业能耗数据", "role": "ROLE_ORGAN_OPERATER"})
    assert out["source"] == "fallback_rule"
    assert out["degraded"] is True
    # fallback 仍能识别 register_demand intent
    assert out["intent"] == "register_demand"


def test_inference_error_degrades_to_fallback(brain, monkeypatch):
    """推理平台 InferenceError → 降级到本地规则，不抛错给调用方."""
    from zw_brain.command.handlers.j1 import search_assistant as sa
    from zw_brain.shared.inference.client import InferenceError

    def _raise(*a, **kw):
        raise InferenceError("inference base_url is required")

    monkeypatch.setattr(sa, "_inference_chat", _raise)
    out = _invoke(brain, {"query": "查房地产数据", "role": "ROLE_ORGAN_OPERATER"})
    assert out["source"] == "fallback_rule"
    assert out["degraded"] is True
    assert out["intent"] == "discover_resource"


# ──────────────────────────────────────────────────────────────────────
# 可关闭 + audit chain
# ──────────────────────────────────────────────────────────────────────


def test_disabled_skips_inference_no_call(brain, monkeypatch):
    from zw_brain.command.handlers.j1 import search_assistant as sa

    def _should_not_be_called(*a, **kw):
        raise AssertionError("inference must NOT be called when enabled=false")

    monkeypatch.setattr(sa, "_inference_chat", _should_not_be_called)
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
