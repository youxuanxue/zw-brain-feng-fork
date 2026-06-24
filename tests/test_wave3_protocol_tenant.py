"""F7 turn 2: wave-3 mcp-hardening + multi-tenant-policy 行为 pytest 映射."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import zw_brain.shared.audit as audit_bus
from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_TOOLS_DIR = REPO_ROOT / "zw_brain" / "entry" / "mcp" / "tools"


@pytest.mark.no_db
def test_wave3_mcp_hardening_live_skills_match_openapi_and_tool_files() -> None:
    """mcp-hardening.feature: MCP tool 列表与 OpenAPI capability 一致（live skills）。"""
    from scripts.export_agent_contract import build_rest_openapi, discover_skills
    from zw_brain.capability_registry.runtime import is_surface_enabled

    skills = {s["skill_id"]: s for s in discover_skills() if "error" not in s}
    live_mcp = {
        sid
        for sid, s in skills.items()
        if is_surface_enabled(s, "mcp") and s.get("product_scope", {}).get("status") == "live"
    }
    openapi = build_rest_openapi(list(skills.values()))
    for skill_id in sorted(live_mcp):
        if skill_id == "system.snapshot":
            op = openapi["paths"]["/api/snapshot"]["get"]
        else:
            path = f"/api/skills/{skill_id}"
            assert path in openapi["paths"], skill_id
            method = "post" if skills[skill_id].get("side_effects") else "get"
            op = openapi["paths"][path][method]
        assert op["x-zwbrain-skill-id"] == skill_id

        desc = json.loads((MCP_TOOLS_DIR / f"{skill_id}.json").read_text(encoding="utf-8"))
        assert desc.get("name") == skill_id
        assert desc.get("inputSchema")


def test_wave3_multi_tenant_policy_catalog_entries_isolated() -> None:
    """multi-tenant-policy.feature: 两 tenant catalog 完全隔离（repo 层）。"""
    ensure_runtime_schema()

    repo = CatalogRepository()
    repo.upsert_from_resource(
        {"id": "CAT-SD-ONLY", "name": "山东专属目录", "status": "published", "provider": "ORG-SD"},
        tenant_id="sd-default",
    )
    repo.upsert_from_resource(
        {"id": "CAT-YN-ONLY", "name": "云南专属目录", "status": "published", "provider": "ORG-YN"},
        tenant_id="yn-default",
    )

    sd_codes = {e.catalog_code for e in repo.list_entries(tenant_id="sd-default")}
    yn_codes = {e.catalog_code for e in repo.list_entries(tenant_id="yn-default")}

    assert "CAT-SD-ONLY" in sd_codes
    assert "CAT-YN-ONLY" not in sd_codes
    assert "CAT-YN-ONLY" in yn_codes
    assert "CAT-SD-ONLY" not in yn_codes

    sd_hits = repo.search_entries("专属", tenant_id="sd-default")
    yn_hits = repo.search_entries("专属", tenant_id="yn-default")
    assert len(sd_hits) == 1 and sd_hits[0].catalog_code == "CAT-SD-ONLY"
    assert len(yn_hits) == 1 and yn_hits[0].catalog_code == "CAT-YN-ONLY"


@pytest.mark.no_db
def test_wave3_observability_cost_quota_no_in_repo_alerting() -> None:
    """observability-cost-quota.feature 负向：zw-brain 不内嵌 alertmanager/告警规则（监控外置）。"""
    for rel_dir in ("zw_brain", "scripts"):
        root = REPO_ROOT / rel_dir
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".sh", ".yaml", ".yml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            assert "alertmanager" not in text, path
            assert "prometheus/alert" not in text, path


def test_wave3_observability_credential_quota_exposed_via_query() -> None:
    """observability-cost-quota.feature：凭据 quota_per_day 在 credential.query 可观测。"""
    ensure_runtime_schema()

    store = DatabaseStore()
    audit_bus.configure_sink(store.append_audit_event)
    brain = BrainService(state_store=StateStore(database_store=store))
    resource = {"resource_id": "res-quota-obs", "resource_name": "quota观测目录"}
    request_id = "REQ-W3-QUOTA-OBS"
    # Action D：申请/交付单一事实源在 DB——直接 upsert 注入。
    store.application_repo.upsert_from_request(
        {
            "id": request_id,
            "status": "approved",
            "applicant": "U_OP_W3",
            "applicantDept": "部门A",
            "resourceId": resource["resource_id"],
            "resourceName": resource["resource_name"],
            "purpose": "wave3 observability",
            "auditId": "AE-W3-test",
        },
        tenant_id="sd-default",
    )
    store.delivery_repo.upsert_from_delivery(
        {
            "id": f"DT-{request_id}",
            "requestId": request_id,
            "resourceId": resource["resource_id"],
            "resourceName": resource["resource_name"],
            "status": "granted",
            "state": "granted",
            "channel": "api",
            "accessGrantSnapshot": {},
            "history": [],
        },
        tenant_id="sd-default",
    )
    invoke_trusted(
        brain,
        "credential.issue",
        {"request_id": request_id, "confirmed": True},
        role="ROLE_ORGAN_MANAGER",
    )
    out = invoke_trusted(
        brain,
        "credential.query",
        {"request_id": request_id},
        role="ROLE_ORGAN_OPERATER",
    )
    result = out.get("result", out) if isinstance(out, dict) else out
    assert result["credential"]["quota_per_day"] == 1000
