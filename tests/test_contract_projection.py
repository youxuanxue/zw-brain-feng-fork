from __future__ import annotations

import json
from pathlib import Path

from scripts.export_agent_contract import (
    build_a2a_card,
    build_mcp_tool_descriptor,
    build_runtime_bindings,
    discover_skills,
)
from zw_brain.command.brain import BrainService, UnknownSkillError
from zw_brain.skill_registration.runtime import is_surface_enabled

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_generated_a2a_card_and_runtime_bindings_cover_registered_skills(monkeypatch) -> None:
    monkeypatch.delenv("ZW_BRAIN_REST_BASE_URL", raising=False)
    monkeypatch.delenv("ZW_BRAIN_REST_PORT", raising=False)

    skills = [item for item in discover_skills() if "error" not in item and is_surface_enabled(item, "a2a")]
    card = build_a2a_card(skills)
    bindings = build_runtime_bindings(skills)

    skill_ids = {item["skill_id"] for item in skills}
    card_ids = {item["id"] for item in card["skills"]}
    binding_names = {item["tool_name"] for item in bindings}

    assert card_ids == skill_ids
    assert binding_names == skill_ids
    assert card["endpoint"] == "http://127.0.0.1:8800/api/skills"
    assert any(item["id"] == "request.create" and item["mode"] == "write" for item in card["skills"])
    assert any(item["tool_name"] == "request.create" and item["auth_strategy"] == "human_confirmation" for item in bindings)
    assert all(item["endpoint"].startswith("http://127.0.0.1:8800/api/skills/") for item in bindings)


def test_generated_a2a_endpoint_follows_rest_base_url_override(monkeypatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_REST_BASE_URL", "https://brain.example.internal:9443/")

    skills = [item for item in discover_skills() if "error" not in item and is_surface_enabled(item, "a2a")]
    card = build_a2a_card(skills)
    bindings = build_runtime_bindings(skills)

    assert card["endpoint"] == "https://brain.example.internal:9443/api/skills"
    assert any(item["endpoint"] == "https://brain.example.internal:9443/api/skills/request.create" for item in bindings)


def test_generated_mcp_descriptors_cover_mcp_compatible_skills() -> None:
    skills = [item for item in discover_skills() if "error" not in item]
    mcp_skills = [item for item in skills if is_surface_enabled(item, "mcp")]
    descriptors = {item["skill_id"]: build_mcp_tool_descriptor(item) for item in mcp_skills}

    assert set(descriptors) == {item["skill_id"] for item in mcp_skills}
    assert descriptors["data.search"]["annotations"]["mode"] == "read"
    assert "request.create" not in descriptors
    assert "approval.review_decide" not in descriptors


def test_generated_runtime_bindings_file_is_valid_json() -> None:
    path = REPO_ROOT / "zw_brain" / "entry" / "a2a" / "tools" / "runtime_bindings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert any(item["tool_name"] == "request.create" for item in data)




def test_external_capability_contracts_are_registered_but_not_direct_surfaces() -> None:
    skills = [item for item in discover_skills() if "error" not in item]
    external_skills = [item for item in skills if item.get("execution_binding") == "external_capability"]

    expected = {
        "external.metadata.gather.execute",
        "external.datasource.connectivity.test",
        "external.datasource.connectivity.probe",
        "external.schema.structure.apply",
        "external.catalog.materialize.execute",
        "external.catalog.reverse_compile.execute",
        "external.quality.scan.execute",
        "external.lineage.graph.build",
        "external.exchange.executor.execute",
        "external.cascade.sync.execute",
        "external.share.governance.configure",
        "external.notification.workorder.dispatch",
        "external.tenant.field_projection.configure",
        "external.security.remediation.dispatch",
    }
    assert {item["skill_id"] for item in external_skills} == expected

    for skill in external_skills:
        assert skill["compatibility"] == []
        assert skill["tenant_scope"] == "tenant"
        assert skill["auth_policy"] == "service"
        assert skill["audit_required"] is True
        assert skill["runtime_binding"]["kind"] == "external_capability"
        assert skill["runtime_binding"]["canonical_write_policy"] == "callback_only"
        assert skill["runtime_binding"]["failure_callback_required"] is True
        assert skill["runtime_binding"]["callback_skill_id"]
        assert "failure_callback_json" in skill["output_schema"]["properties"]
        assert "external_execution" in skill["side_effects"]
        assert not any(is_surface_enabled(skill, surface) for surface in ["webui", "api", "cli", "mcp", "a2a"])



def test_registered_builtin_contracts_are_brain_service_routed() -> None:
    from zw_brain.domain.policy import ACTOR_NAMES, permissions_for_role

    service = BrainService()
    missing: list[str] = []

    for skill in discover_skills():
        if "error" in skill or skill.get("execution_binding") != "builtin":
            continue
        required_permissions = set(skill.get("permissions") or [])
        role = next(
            (candidate for candidate in ACTOR_NAMES if required_permissions.issubset(permissions_for_role(candidate))),
            "r8",
        )
        payload = {name: _sample_value(name, schema) for name, schema in skill.get("input_schema", {}).get("properties", {}).items()}
        for name in skill.get("input_schema", {}).get("required", []):
            payload.setdefault(name, _sample_value(name, {}))
        payload["role"] = role
        if skill.get("human_confirmation_required"):
            payload["confirmed"] = True
        try:
            service.invoke_skill(skill["skill_id"], payload)
        except UnknownSkillError:
            missing.append(skill["skill_id"])
        except Exception:
            pass

    assert missing == []


def test_registered_skill_permissions_are_assigned_to_roles() -> None:
    from zw_brain.domain.policy import ACTOR_NAMES, permissions_for_role

    permissions_by_role = {role: permissions_for_role(role) for role in ACTOR_NAMES}
    unassigned: list[tuple[str, str]] = []

    for skill in discover_skills():
        if "error" in skill:
            continue
        for permission in skill.get("permissions") or []:
            if not any(permission in permissions for permissions in permissions_by_role.values()):
                unassigned.append((skill["skill_id"], permission))

    assert unassigned == []


def _sample_value(name: str, schema: dict) -> object:
    if name == "role":
        return "r8"
    if name == "confirmed":
        return True
    if name == "decision":
        return "approve"
    if name == "action":
        return "publish"
    if name == "mode":
        return "expand"
    if name == "task_id":
        return "DLV-2026-04-25-0011"
    if name == "request_id":
        return "REQ-2026-04-25-0011"
    if name == "resource_id":
        return "res-jbxx-ledger"
    if name.endswith("_json") or schema.get("type") == "object":
        return {}
    if schema.get("type") == "array":
        return []
    if schema.get("type") == "integer":
        return 1
    return f"sample-{name}"


def test_external_capability_contracts_are_not_brain_service_invokable() -> None:
    service = BrainService()

    try:
        service.invoke_skill(
            "external.quality.scan.execute",
            {
                "quality_ref": "quality-demo",
                "target_type": "catalog",
                "target_ref": "cat-demo",
                "tenant_id": "sd-default",
                "role": "r7",
            },
        )
    except UnknownSkillError:
        pass
    else:
        raise AssertionError("external capability contracts must not be direct BrainService writes")
