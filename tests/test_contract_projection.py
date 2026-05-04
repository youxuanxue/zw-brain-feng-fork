from __future__ import annotations

import json
from pathlib import Path

from scripts.export_agent_contract import build_a2a_card, build_mcp_tool_descriptor, build_runtime_bindings, discover_skills
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
        "external.schema.structure.apply",
        "external.catalog.materialize.execute",
        "external.catalog.reverse_compile.execute",
        "external.quality.scan.execute",
        "external.lineage.graph.build",
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


def test_external_capability_contracts_are_not_brain_service_invokable() -> None:
    service = BrainService()

    try:
        service.invoke_skill(
            "external.quality.scan.execute",
            {
                "quality_ref": "quality-demo",
                "target_type": "catalog",
                "target_ref": "cat-demo",
                "tenant_id": "default",
                "role": "r7",
            },
        )
    except UnknownSkillError:
        pass
    else:
        raise AssertionError("external capability contracts must not be direct BrainService writes")
