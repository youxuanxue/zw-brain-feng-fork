from __future__ import annotations

import json
from pathlib import Path

from scripts.export_agent_contract import (
    build_a2a_card,
    build_mcp_tool_descriptor,
    build_rest_openapi,
    build_runtime_bindings,
    discover_skills,
    is_live,
)
from zw_brain.command.brain import BrainService, UnknownSkillError
from zw_brain.skill_registration.runtime import SURFACES, is_surface_enabled

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_generated_a2a_card_and_runtime_bindings_cover_registered_skills(monkeypatch) -> None:
    monkeypatch.delenv("ZW_BRAIN_REST_BASE_URL", raising=False)
    monkeypatch.delenv("ZW_BRAIN_REST_PORT", raising=False)

    skills = [
        item
        for item in discover_skills()
        if "error" not in item and is_surface_enabled(item, "a2a") and is_live(item)
    ]
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

    skills = [
        item
        for item in discover_skills()
        if "error" not in item and is_surface_enabled(item, "a2a") and is_live(item)
    ]
    card = build_a2a_card(skills)
    bindings = build_runtime_bindings(skills)

    assert card["endpoint"] == "https://brain.example.internal:9443/api/skills"
    assert any(item["endpoint"] == "https://brain.example.internal:9443/api/skills/request.create" for item in bindings)


def test_tenant_policy_evaluate_contract_is_shared_across_five_surfaces() -> None:
    skills = {item["skill_id"]: item for item in discover_skills() if "error" not in item}
    skill = skills["tenant.policy.evaluate"]

    assert set(skill["compatibility"]) == {"webui", "api", "cli", "mcp", "a2a"}
    props = skill["input_schema"]["properties"]
    for name in ["actor_snapshot", "org_snapshot", "role_codes", "capability_slug", "surface", "target_ref", "risk_context"]:
        assert name in props
    result_props = skill["output_schema"]["properties"]["result"]["properties"]
    for name in ["allowed", "decision_reason", "human_confirmation_required", "audit_class", "policy_version", "actor_snapshot"]:
        assert name in result_props


def test_governance_iam_overview_contract_is_shared_across_five_surfaces() -> None:
    skills = {item["skill_id"]: item for item in discover_skills() if "error" not in item}
    skill = skills["governance.iam_overview"]

    assert set(skill["compatibility"]) == {"webui", "api", "cli", "mcp", "a2a"}
    props = skill["input_schema"]["properties"]
    for name in ["tenant_id", "binding_status", "role_code", "actor_id", "capability_id", "issue_type"]:
        assert name in props
    output_props = skill["output_schema"]["properties"]
    for name in ["actors", "roles", "tenant_policies", "import_issues", "audit_events", "policy_probe"]:
        assert name in output_props


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


def test_registry_projection_metadata_matches_openapi_mcp_and_a2a() -> None:
    skills = {item["skill_id"]: item for item in discover_skills() if "error" not in item}
    openapi = build_rest_openapi(list(skills.values()))
    mcp_tools_dir = REPO_ROOT / "zw_brain" / "entry" / "mcp" / "tools"
    a2a_bindings = {
        item["tool_name"]: item
        for item in json.loads((REPO_ROOT / "zw_brain" / "entry" / "a2a" / "tools" / "runtime_bindings.json").read_text(encoding="utf-8"))
    }
    a2a_card = {item["id"]: item for item in json.loads((REPO_ROOT / "zw_brain" / "entry" / "a2a" / "agent_card.json").read_text(encoding="utf-8"))["skills"]}

    for skill_id, skill in skills.items():
        surfaces = set(skill.get("compatibility") or [])
        assert surfaces <= SURFACES
        for surface in SURFACES - surfaces:
            if skill.get("execution_binding") != "external_capability":
                assert not is_surface_enabled(skill, surface)

        live = is_live(skill)

        if "api" in surfaces and live:
            path = f"/api/skills/{skill_id}"
            if skill_id == "system.snapshot":
                assert openapi["paths"]["/api/snapshot"]["get"]["x-zwbrain-skill-id"] == skill_id
            else:
                assert path in openapi["paths"], skill_id
                method = "post" if skill.get("side_effects") else "get"
                operation = openapi["paths"][path][method]
                assert operation["x-zwbrain-skill-id"] == skill_id
                assert operation["x-zwbrain-human-confirmation-required"] == skill["human_confirmation_required"]
                assert operation["x-zwbrain-audit-class"] == skill.get("audit_class", "")
                assert set(operation["x-zwbrain-surfaces"]) == surfaces
                assert operation["x-zwbrain-side-effects"] == skill.get("side_effects", [])
        else:
            assert f"/api/skills/{skill_id}" not in openapi["paths"], skill_id

        mcp_path = mcp_tools_dir / f"{skill_id}.json"
        if "mcp" in surfaces and live:
            descriptor = json.loads(mcp_path.read_text(encoding="utf-8"))
            assert descriptor["annotations"]["humanConfirmationRequired"] == skill["human_confirmation_required"]
            assert descriptor["annotations"]["readOnlyHint"] is (not bool(skill.get("side_effects")))
            assert descriptor["x-zwbrain-audit-class"] == skill.get("audit_class", "")
            assert set(descriptor["x-zwbrain-surfaces"]) == surfaces
        else:
            assert not mcp_path.exists(), skill_id

        if "a2a" in surfaces and live:
            assert skill_id in a2a_card
            assert skill_id in a2a_bindings
            assert a2a_card[skill_id]["humanConfirmationRequired"] == skill["human_confirmation_required"]
            assert a2a_card[skill_id]["auditClass"] == skill.get("audit_class", "")
            assert set(a2a_card[skill_id]["surfaces"]) == surfaces
            assert a2a_bindings[skill_id]["config_json"]["human_confirmation_required"] == skill["human_confirmation_required"]
            assert a2a_bindings[skill_id]["config_json"]["audit_class"] == skill.get("audit_class", "")
            assert set(a2a_bindings[skill_id]["config_json"]["surfaces"]) == surfaces
        else:
            assert skill_id not in a2a_card, skill_id
            assert skill_id not in a2a_bindings, skill_id


def test_webui_uses_registry_gateways_only() -> None:
    # K12 dashboard BFF 退役（详见 D15 二次反转）；本测试仅校验 WebUI 通过 registry gateway 调能力
    app_js = (REPO_ROOT / "zw-brain-web" / "js" / "app.js").read_text(encoding="utf-8")

    assert "window.ZW_AUTH.authFetch(`/api/skills/${skillId}${encodeParams(payload)}`" in app_js
    assert "window.ZW_AUTH.authFetch(`/api/skills/${skillId}`" in app_js
    assert "Object.assign({ role: currentRole, confirmed: true }, payload)" in app_js
    assert "get_service" not in app_js
    assert "invoke_skill" not in app_js


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
            "ROLE_SECURITY_AUDIT",
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
    """live skill 的 permissions 必须被至少一个 role 持有；
    deferred:wave-N / external 状态不进任何 surface 投影，无 role 绑定刚性需求。"""
    from zw_brain.domain.policy import ACTOR_NAMES, permissions_for_role

    permissions_by_role = {role: permissions_for_role(role) for role in ACTOR_NAMES}
    unassigned: list[tuple[str, str]] = []

    for skill in discover_skills():
        if "error" in skill:
            continue
        scope = skill.get("product_scope") or {}
        if scope.get("status") != "live":
            continue
        for permission in skill.get("permissions") or []:
            if not any(permission in permissions for permissions in permissions_by_role.values()):
                unassigned.append((skill["skill_id"], permission))

    assert unassigned == []


def _sample_value(name: str, schema: dict) -> object:
    if name == "role":
        return "ROLE_SECURITY_AUDIT"
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
                "role": "ROLE_BUSIAUDIT",
            },
        )
    except UnknownSkillError:
        pass
    else:
        raise AssertionError("external capability contracts must not be direct BrainService writes")
