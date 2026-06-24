from __future__ import annotations

import sys
import types
from pathlib import Path

import yaml


def _install_psycopg_stub() -> None:
    if "psycopg" in sys.modules:
        return
    psycopg = types.ModuleType("psycopg")
    conninfo = types.ModuleType("psycopg.conninfo")
    conninfo.make_conninfo = lambda **_kw: ""
    psycopg.conninfo = conninfo
    sys.modules["psycopg"] = psycopg
    sys.modules["psycopg.conninfo"] = conninfo


class _FakeStateRepo:
    saved: dict | None = None

    def list_states(self, *, tenant_id: str = "sd-default") -> dict:
        if not self.saved:
            return {}
        record = types.SimpleNamespace(
            enabled=self.saved["enabled"],
            allowed_roles_json=self.saved["allowed_roles"],
            updated_by=self.saved["updated_by"],
            reason=self.saved["reason"],
            updated_at=None,
        )
        return {self.saved["agent_id"]: record}

    def to_dict(self, record, *, default_roles: list[str]) -> dict:
        if record is not None:
            return {
                "enabled": bool(record.enabled),
                "allowed_roles": list(record.allowed_roles_json),
                "updated_by": record.updated_by,
                "reason": record.reason,
                "updated_at": None,
            }
        return {
            "enabled": True,
            "allowed_roles": list(default_roles),
            "updated_by": None,
            "reason": None,
            "updated_at": None,
        }

    def set_state(
        self,
        agent_id: str,
        *,
        tenant_id: str = "sd-default",
        enabled: bool,
        allowed_roles: list[str],
        updated_by: str | None,
        reason: str | None,
    ):
        self.saved = {
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "enabled": enabled,
            "allowed_roles": allowed_roles,
            "updated_by": updated_by,
            "reason": reason,
        }

        record = types.SimpleNamespace(
            enabled=enabled,
            allowed_roles_json=allowed_roles,
            updated_by=updated_by,
            reason=reason,
            updated_at=None,
        )
        return record


def _stub_agent_state(monkeypatch) -> None:
    from zw_brain.command import agent_runtime_bridge as bridge

    monkeypatch.setattr(bridge, "AgentRuntimeStateRepository", lambda: _FakeStateRepo())


def test_scenario_agent_catalog_exposes_ab_runtime_ready(monkeypatch) -> None:
    _install_psycopg_stub()
    from zw_brain.command import agent_runtime_bridge as bridge

    _stub_agent_state(monkeypatch)
    monkeypatch.setattr(
        bridge.policy,
        "enforce_manifest_policy",
        lambda _skill_id, _manifest, _role, _ctx: None,
    )

    items = bridge.list_builtin_agents()
    by_id = {item["agent_id"]: item for item in items}

    assert len(items) >= 25
    assert by_id["a-zw-search-helper"]["category"] == "agent"
    assert by_id["a-zw-search-helper"]["agent_class"] == "A"
    assert by_id["a-zw-search-helper"]["agent_type_label"] == "A 类 · 平台办事助手"
    assert by_id["a-zw-search-helper"]["runtime_ready"] is True
    assert by_id["a-zw-search-helper"]["net_new"] == "none"
    assert len(by_id["a-zw-search-helper"]["quick_questions"]) == 3

    assert by_id["b-legal-person-credit-profiler"]["agent_class"] == "B"
    assert by_id["b-legal-person-credit-profiler"]["agent_type_label"] == "B 类 · 场景用数助手"
    assert by_id["b-legal-person-credit-profiler"]["category"] == "agent"
    assert by_id["b-legal-person-credit-profiler"]["tool_count"] == 3


def test_agent_with_no_allowed_policy_roles_hidden_from_business_visible_to_ops(monkeypatch) -> None:
    _install_psycopg_stub()
    from zw_brain.command import agent_runtime_bridge as bridge

    _stub_agent_state(monkeypatch)
    operator_items = bridge.list_builtin_agents(role="ROLE_ORGAN_OPERATER")
    operator_ids = {item["agent_id"] for item in operator_items}
    assert "a-compliance-permission-checker" not in operator_ids

    ops_items = bridge.list_builtin_agents(role="ROLE_SYSTEM")
    by_id = {item["agent_id"]: item for item in ops_items}
    assert "a-compliance-permission-checker" in by_id
    assert by_id["a-compliance-permission-checker"]["policy_allowed_roles"] == []
    assert by_id["a-compliance-permission-checker"]["callable"] is True


def test_platform_operator_can_debug_agent_without_business_authorization(monkeypatch) -> None:
    _install_psycopg_stub()
    from zw_brain.command import agent_runtime_bridge as bridge

    _stub_agent_state(monkeypatch)
    ops_items = bridge.list_builtin_agents(role="ROLE_SYSTEM")
    by_id = {item["agent_id"]: item for item in ops_items}

    assert by_id["a-compliance-permission-checker"]["policy_allowed_roles"] == []
    assert by_id["a-compliance-permission-checker"]["allowed_roles"] == []
    assert by_id["a-compliance-permission-checker"]["callable"] is True

    monkeypatch.setattr(bridge, "is_agent_runtime_enabled", lambda: True)
    bridge._verify_agent_and_policy(agent_id="a-compliance-permission-checker", role="ROLE_SYSTEM")


def test_update_agent_state_accepts_ops_added_business_role(monkeypatch) -> None:
    _install_psycopg_stub()
    from zw_brain.command import agent_runtime_bridge as bridge

    repo = _FakeStateRepo()
    monkeypatch.setattr(bridge, "AgentRuntimeStateRepository", lambda: repo)

    result = bridge.update_agent_state(
        agent_id="b-legal-person-credit-profiler",
        enabled=True,
        allowed_roles=["ROLE_ORGAN_OPERATER"],
        updated_by="tester",
        reason="test",
    )

    assert repo.saved is not None
    assert repo.saved["allowed_roles"] == ["ROLE_ORGAN_OPERATER"]
    assert result["allowed_roles"] == ["ROLE_ORGAN_OPERATER"]


def test_update_agent_state_rejects_platform_operator_as_business_authorization(monkeypatch) -> None:
    _install_psycopg_stub()
    from zw_brain.command import agent_runtime_bridge as bridge
    from zw_brain.command.brain import AccessDeniedError

    _stub_agent_state(monkeypatch)

    try:
        bridge.update_agent_state(
            agent_id="b-legal-person-credit-profiler",
            enabled=True,
            allowed_roles=["ROLE_SYSTEM"],
            updated_by="tester",
            reason="test",
        )
    except AccessDeniedError as exc:
        assert "ROLE_SYSTEM" in str(exc)
    else:
        raise AssertionError("expected AccessDeniedError")


def test_generated_scenario_agent_bundles_are_complete() -> None:
    agent_dirs = [p for p in (Path(__file__).resolve().parents[1] / "agents").iterdir() if p.is_dir()]
    complete = [
        p
        for p in agent_dirs
        if (p / "AGENT.yaml").is_file()
        and (p / "capabilities.json").is_file()
        and (p / "zw-brain-capabilities.openapi.yaml").is_file()
    ]

    assert len(complete) >= 25


def test_generated_agent_manifests_do_not_leak_ui_sidecar_fields() -> None:
    for manifest_path in (Path(__file__).resolve().parents[1] / "agents").glob("*/AGENT.yaml"):
        doc = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        metadata = doc.get("metadata") if isinstance(doc, dict) else {}
        assert "quick_questions" not in metadata, manifest_path


def test_generated_scenario_agents_are_chat_visible_to_runtime() -> None:
    for manifest_path in (Path(__file__).resolve().parents[1] / "agents").glob("*/AGENT.yaml"):
        doc = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        metadata = doc.get("metadata") if isinstance(doc, dict) else {}
        assert metadata.get("exposes_chat") is True, manifest_path
