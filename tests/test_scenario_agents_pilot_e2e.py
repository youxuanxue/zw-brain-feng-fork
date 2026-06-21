# Wave: 1
# Journey: J1 (A① 数据发现副驾) + B 试点 (法人信用画像研判, embedded)
# Pages: P2 资源发现 / 用数方研判
# Consumer-faces: AgentRuntime embedded (ZwBrainCapabilityProvider.call_tool)
# Roles: ROLE_ORGAN_OPERATER (A①), ROLE_ORGAN_MANAGER (B 试点字段映射)
# Trace:
#   docs/scenario-agents/scenario-agents-design-v1.md §4 A① / §5.1 B 试点
#   agents/zw_search_helper/{AGENT.yaml,capabilities.json}
#   agents/legal_person_credit_profiler/{AGENT.yaml,capabilities.json}
#   zw_brain/shared/agent_runtime/capability_provider.py (call_tool → invoke_skill)
"""端到端试点验收：两个场景智能体经真实 ``ZwBrainCapabilityProvider.call_tool``
→ ``BrainService.invoke_skill`` 路径调用其声明的能力，证明承载链端到端通、只读、
§8.5 安全，且权限边界正确（最小权限）。

覆盖口径（诚实边界）：
- ``data_search`` 经 ``_seed`` 注入的内存快照覆盖**真实读路径**（命中 active、过滤
  draft），断言强（命中/缺席具体 id）。
- ``catalog_browse`` / ``catalog_entry_query`` / ``catalog_item_query`` 读 DB 仓；
  本文件跑 seed-light 空库克隆（未挂 realistic_pg_module），故目录/元数据表为空——
  此处只断言**只读信封形状 + 权限边界**（manager 授权可调、operator 被拒），**不**
  断言目录数据深度（非空命中由 realistic_pg_module 套件 / live 演示覆盖）。

不依赖 445MB 真实模板（无构建器，CI 同 skip）、不依赖 live 推理（intent.parse 走
规则回落）。这是 scenario-agents 试点的「承载形态端到端可交付」证据。
"""
from __future__ import annotations

import types

import pytest

from zw_brain.command.brain import BrainService
from zw_brain.shared.agent_runtime import service as S
from zw_brain.shared.agent_runtime.capability_provider import ZwBrainCapabilityProvider

_TOKEN = "法人信用画像XZ9"


def _seed(brain: BrainService) -> None:
    """注入真实形状的资源快照：一条 active（应可发现）+ 一条 draft（应被过滤）。"""
    brain._snapshot["api_resources"] = [
        {
            "resource_code": "test-api-active",
            "title": f"{_TOKEN}_企业登记基本信息",
            "owner_org_id": "11370000TEST00000A",
            "lifecycle_status": "active",
            "resource_kind": "api",
            "summary_json": {"domain": "法人", "desc": f"{_TOKEN} 法人库群体画像"},
        },
        {
            "resource_code": "test-api-draft",
            "title": f"{_TOKEN}_草稿态",
            "owner_org_id": "11370000TEST00000A",
            "lifecycle_status": "draft",
            "resource_kind": "api",
            "summary_json": {"domain": "法人", "desc": "草稿，不应被发现"},
        },
    ]


def _provider(agent_folder: str) -> tuple[ZwBrainCapabilityProvider, BrainService]:
    brain = BrainService()
    _seed(brain)
    prov = ZwBrainCapabilityProvider(brain, agent_dir=S.agents_dir() / agent_folder)
    return prov, brain


def _ctx(role: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        task_metadata={"caller_role": role, "request_id": "pilot-e2e"}
    )


# --------------------------------------------------------------------------- #
# A① data-discovery-copilot（升级 zw-search-helper）
# --------------------------------------------------------------------------- #
def test_a1_injects_exactly_four_readonly_tools() -> None:
    prov, _ = _provider("zw_search_helper")
    names = [t["name"] for t in prov.list_tools(_ctx("ROLE_ORGAN_OPERATER"))]
    assert names == ["search_intent_parse", "data_search", "catalog_browse", "catalog_entry_query"]


def test_a1_data_search_through_provider_returns_only_active() -> None:
    """经 provider→invoke_skill 真实路径检索：只命中 active，draft 被过滤（D53① 口径）。"""
    prov, _ = _provider("zw_search_helper")
    out = prov.call_tool("data_search", {"query": _TOKEN}, _ctx("ROLE_ORGAN_OPERATER"))
    codes = {str(r.get("id")) for r in out["results"]}
    assert "test-api-active" in codes
    assert "test-api-draft" not in codes


def test_a1_data_search_tolerates_llm_null_page() -> None:
    """LLM 工具编排常把可选字段显式填 null（page: null）。live 推理（GLM-4）实测暴露
    data_search.py `int(payload.get("page", 1))` 在 page=None 时崩（int(None)）。
    修为 `or 1` 后必须容忍不崩并正常返回——本测试钉死回归。"""
    prov, _ = _provider("zw_search_helper")
    out = prov.call_tool("data_search", {"query": _TOKEN, "page": None}, _ctx("ROLE_ORGAN_OPERATER"))
    assert "test-api-active" in {str(r.get("id")) for r in out["results"]}


def test_a1_catalog_and_intent_tools_return_structured() -> None:
    prov, _ = _provider("zw_search_helper")
    ctx = _ctx("ROLE_ORGAN_OPERATER")
    intent = prov.call_tool("search_intent_parse", {"query": "我要法人信用数据"}, ctx)
    assert isinstance(intent, dict) and "keywords" in intent  # rule fallback ok, no LLM needed
    # catalog 工具读 DB 仓（seed-light 空库 → items 为空）：此处断言只读信封形状（不崩、
    # 返回 items 列表）；非空目录数据深度由 realistic_pg_module 套件 / live 演示覆盖。
    browse = prov.call_tool("catalog_browse", {"query": _TOKEN, "lifecycle": "active"}, ctx)
    assert isinstance(browse.get("items"), list)
    entry = prov.call_tool("catalog_entry_query", {"query": _TOKEN}, ctx)
    assert isinstance(entry.get("items"), list)


def test_a1_is_readonly_no_state_mutation() -> None:
    prov, brain = _provider("zw_search_helper")
    ctx = _ctx("ROLE_ORGAN_OPERATER")
    before = list(brain._snapshot.get("api_resources", []))
    for name, args in [
        ("search_intent_parse", {"query": "x"}),
        ("data_search", {"query": _TOKEN}),
        ("catalog_browse", {"lifecycle": "active"}),
        ("catalog_entry_query", {"query": _TOKEN}),
    ]:
        prov.call_tool(name, args, ctx)
    assert brain._snapshot.get("api_resources", []) == before


# --------------------------------------------------------------------------- #
# B 试点 legal-person-credit-profiler（embedded internal，不触发 T1）
# --------------------------------------------------------------------------- #
def test_bpilot_injects_exactly_three_readonly_tools() -> None:
    prov, _ = _provider("legal_person_credit_profiler")
    names = [t["name"] for t in prov.list_tools(_ctx("ROLE_ORGAN_MANAGER"))]
    assert names == ["data_search", "catalog_entry_query", "catalog_item_query"]


def test_bpilot_consumes_shared_data_for_authorized_manager() -> None:
    """用数方 manager 角色经授权调用 B 试点全部 3 个工具：承载链通、信封正确、不被拒。

    data_search 经内存快照覆盖真实读路径（命中 seeded active id，断言强）；
    catalog_entry_query / catalog_item_query 读 DB 仓（seed-light 空库），此处断言 manager
    **授权可调**（返回只读信封、不抛 AccessDenied），与 operator 被拒（见
    test_bpilot_field_mapping_denied_for_basic_operator）一同钉死 §8.5 最小权限边界。
    目录/字段映射的非空数据深度由 realistic_pg_module 套件 / live 覆盖。
    """
    prov, _ = _provider("legal_person_credit_profiler")
    ctx = _ctx("ROLE_ORGAN_MANAGER")
    assert "test-api-active" in {str(r.get("id")) for r in prov.call_tool("data_search", {"query": _TOKEN}, ctx)["results"]}
    assert isinstance(prov.call_tool("catalog_entry_query", {"query": _TOKEN}, ctx).get("items"), list)
    # 字段映射工具对授权 manager 可调用并返回只读信封（不抛 AccessDenied）；空库下不断言具体
    # 标签，敏感标签数据深度见 realistic 套件 / live。operator 被拒在下方专测钉死。
    item = prov.call_tool("catalog_item_query", {"catalog_code": "GG-1"}, ctx)
    assert isinstance(item, dict)


def test_bpilot_field_mapping_denied_for_basic_operator() -> None:
    """§8.5 最小权限边界：敏感字段映射 metadata.catalog_item.query 对基础操作员拒绝，
    仅 manager/运营/审计可读（policy.py:242）。这条治理边界是试点的安全前提，钉死防回归。"""
    prov, _ = _provider("legal_person_credit_profiler")
    with pytest.raises(Exception, match="lacks permissions"):
        prov.call_tool("catalog_item_query", {"catalog_code": "GG-1"}, _ctx("ROLE_ORGAN_OPERATER"))


def test_bpilot_is_readonly_no_state_mutation() -> None:
    prov, brain = _provider("legal_person_credit_profiler")
    ctx = _ctx("ROLE_ORGAN_MANAGER")
    before = list(brain._snapshot.get("api_resources", []))
    prov.call_tool("data_search", {"query": _TOKEN}, ctx)
    prov.call_tool("catalog_entry_query", {"query": _TOKEN}, ctx)
    assert brain._snapshot.get("api_resources", []) == before
