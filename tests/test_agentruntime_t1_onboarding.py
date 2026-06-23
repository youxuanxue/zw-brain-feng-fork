"""T1 外部 Agent onboarding 工具链（D68）：validate/doctor + Registry external-register + 段30.

覆盖（CI-safe，纯结构校验，不连 AR/网关）：
  - validate：平台指南 agent + hello-agent（AR 手册样本）+ 外部用数方参考样本 → OK；
    故意违规样本 → FAIL 且命中具体违规（真命中，防假绿）。
  - Registry validate_manifest：source_type=external-register 强制 4 字段（agent_trust_level
    与 F4 包级 trust_level 区分，GATE D33.d）+ 取值校验；platform/缺字段/旧 spec/非 bool 拒绝。
  - 段30 反污染：非 external-register 的 manifest 不得带这 4 字段。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "fixtures" / "agentruntime"

from zw_brain.capability_registry.runtime import validate_manifest  # noqa: E402
from zw_brain.shared.agent_runtime.manifest_checks import (  # noqa: E402
    diagnose_agent_bundle,
    validate_agent_bundle,
)


# ── validate：用户 Q3 两个测试主体（平台指南 + AR main/hello agent）+ 外部参考样本 ──
@pytest.mark.parametrize(
    "agent_yaml",
    [
        REPO / "agents" / "zw_platform_guide" / "AGENT.yaml",
        FIX / "hello-agent" / "AGENT.yaml",
        FIX / "external-data-consumer" / "AGENT.yaml",
    ],
)
def test_validate_accepts_clean_agents(agent_yaml: Path) -> None:
    valid, violations, _ = validate_agent_bundle(agent_yaml)
    assert valid, f"{agent_yaml.parent.name} 应通过 validate，违规：{violations}"


@pytest.mark.parametrize(
    "agent_yaml",
    [
        REPO / "agents" / "zw_search_helper" / "AGENT.yaml",
        REPO / "agents" / "zw_platform_guide" / "AGENT.yaml",
        REPO / "agents" / "legal_person_credit_profiler" / "AGENT.yaml",
    ],
)
def test_builtin_agents_declare_api_tools_for_sidecar_capabilities(agent_yaml: Path) -> None:
    """#321 后 capabilities.json 不再注入工具；AGENT.yaml 必须显式声明 kind:api。"""
    valid, violations, _ = validate_agent_bundle(agent_yaml)
    assert valid, f"{agent_yaml.parent.name} 应通过 sidecar/tool/OpenAPI 一致性校验：{violations}"


def test_validate_rejects_sidecar_tools_without_declared_api_tools(tmp_path: Path) -> None:
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "AGENT.yaml").write_text(
        """
schema_version: anp-agent/v1.2
kind: Agent
metadata:
  id: bad-builtin
  name: Bad Builtin
  version: 1.0.0
  trust_level: platform
model:
  provider: openai_compatible
  model: ${env:AGENT_RUNTIME_DEFAULT_MODEL}
memory:
  enabled: false
tools: []
""".strip(),
        encoding="utf-8",
    )
    (agent_dir / "capabilities.json").write_text(
        json.dumps(
            {
                "runtime_spec_version": "anp-agent/v1.2",
                "trust_level": "platform",
                "source_type": "builtin",
                "auth_mode": "trusted_gateway",
                "tenant_id": "sd-default",
                "context_policy": "regulated_minimal",
                "capability_tools": [
                    {
                        "skill_id": "data.search",
                        "name": "data_search",
                        "description": "只读检索",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    valid, violations, _ = validate_agent_bundle(agent_dir / "AGENT.yaml")

    assert not valid
    assert any("kind:api" in item and "data_search" in item for item in violations)


def test_validate_rejects_bad_external_with_real_violations() -> None:
    """防假绿：故意违规样本逐条命中（旧 spec / 直连 provider / auth none / 多租户 / kind:skill）。"""
    valid, violations, _ = validate_agent_bundle(FIX / "bad-external" / "AGENT.yaml")
    assert not valid
    blob = " ".join(violations)
    assert "runtime_spec_version" in blob  # 旧 spec
    assert "gateway" in blob               # 直连 provider
    assert "tenant_mode=multi" in blob     # 多租户
    assert any("mcp/skill" in v for v in violations)  # 历史 kind:skill


def test_doctor_emits_diagnoses() -> None:
    diags = diagnose_agent_bundle(FIX / "hello-agent" / "AGENT.yaml", production=False)
    sevs = {sev for sev, _, _ in diags}
    assert diags and sevs <= {"OK", "HINT", "WARN", "FAIL"}


# ── Registry external-register 4 字段（agent_trust_level，GATE D33.d 与 F4 区分）──
_BASE_EXTERNAL = {
    "slug": "external.demo",
    "compatibility": ["api"],
    "product_scope": {"journey": "external", "status": "external"},
    "source_type": "external-register",
    "runtime_spec_version": "anp-agent/v1.2",
    "agent_yaml_ref": "oci://registry.example/agent:1.0.0",
    "agent_trust_level": "untrusted",
    "workspace_required": False,
}


def test_registry_accepts_valid_external_register() -> None:
    validate_manifest(dict(_BASE_EXTERNAL))  # 不抛即通过


@pytest.mark.parametrize(
    "mutate,needle",
    [
        ({"agent_trust_level": "platform"}, "agent_trust_level"),  # 外部不可 platform
        ({"runtime_spec_version": "anp-agent/v1"}, "runtime_spec_version"),  # 旧 spec
        ({"workspace_required": "yes"}, "workspace_required"),  # 非 bool
    ],
)
def test_registry_rejects_invalid_external(mutate: dict, needle: str) -> None:
    bad = {**_BASE_EXTERNAL, **mutate}
    with pytest.raises(ValueError, match=needle):
        validate_manifest(bad)


def test_registry_rejects_missing_required_field() -> None:
    bad = {k: v for k, v in _BASE_EXTERNAL.items() if k != "agent_yaml_ref"}
    with pytest.raises(ValueError, match="agent_yaml_ref"):
        validate_manifest(bad)


# ── 段30 反污染：非 external-register 不得带 4 字段 ──
def _load_guard():
    spec = importlib.util.spec_from_file_location(
        "check_ext_reg", REPO / "scripts" / "check_external_register_metadata.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_seg30_clean_repo_passes() -> None:
    assert _load_guard().main() == 0  # 现仓库无 external-register → 无污染


def test_seg30_detects_pollution(tmp_path: Path, monkeypatch) -> None:
    guard = _load_guard()
    d = tmp_path / "registered"
    d.mkdir()
    import json

    # 非 external-register 却带 external 专属字段 → 污染，应被抓
    (d / "polluted.json").write_text(
        json.dumps({"slug": "x", "source_type": "builtin", "agent_trust_level": "untrusted"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "REGISTRY_DIR", d)
    assert guard.scan(), "应抓到字段污染"
