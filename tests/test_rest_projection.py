from __future__ import annotations

import json
from pathlib import Path

from scripts.export_agent_contract import build_rest_openapi, discover_skills

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_generated_openapi_covers_registered_skills() -> None:
    skills = [item for item in discover_skills() if "error" not in item]
    openapi = build_rest_openapi(skills)
    paths = openapi["paths"]

    assert "/openapi.json" in paths
    assert "/api/skills/request.create" in paths
    assert "post" in paths["/api/skills/request.create"]
    assert "/api/skills/data.search" in paths
    assert "get" in paths["/api/skills/data.search"]
    assert "/auth/iaf/config" in paths

    auth_config_schema = paths["/auth/iaf/config"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert "development_iam_bypass_enabled" in auth_config_schema["properties"]
    assert "development_iam_bypass_enabled" in auth_config_schema["required"]

    request_create = paths["/api/skills/request.create"]["post"]
    # Cookie + CSRF is the primary browser surface; Bearer is the fallback for CLI / direct API.
    # Both must be advertised so OpenAPI clients can pick the right auth flow.
    assert request_create["security"] == [
        {"cookieAuth": [], "csrfToken": []},
        {"BearerAuth": []},
    ]
    assert "401" in request_create["responses"]
    assert "503" in request_create["responses"]
    assert request_create["x-zwbrain-skill-id"] == "request.create"
    assert request_create["x-zwbrain-human-confirmation-required"] is True
    assert request_create["x-zwbrain-auth-policy"] == "user"
    assert request_create["x-zwbrain-tenant-scope"] == "tenant"
    assert "403" in request_create["responses"]
    assert request_create["requestBody"]["content"]["application/json"]["schema"]["required"] == ["resource_id", "confirmed"]


def test_generated_openapi_file_is_valid_json() -> None:
    path = REPO_ROOT / "zw_brain" / "entry" / "rest" / "openapi.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["openapi"] == "3.1.0"
    assert "/api/skills/request.create" in data["paths"]
    assert "/api/skills/compliance.metric.query" in data["paths"]
