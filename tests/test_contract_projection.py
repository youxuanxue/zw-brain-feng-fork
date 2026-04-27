from __future__ import annotations

import json
from pathlib import Path

from scripts.export_agent_contract import build_a2a_card, build_mcp_tool_descriptor, build_runtime_bindings, discover_skills


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_generated_a2a_card_and_runtime_bindings_cover_registered_skills(monkeypatch) -> None:
    monkeypatch.delenv("ZW_BRAIN_REST_BASE_URL", raising=False)
    monkeypatch.delenv("ZW_BRAIN_REST_PORT", raising=False)

    skills = [item for item in discover_skills() if "error" not in item]
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

    skills = [item for item in discover_skills() if "error" not in item]
    card = build_a2a_card(skills)
    bindings = build_runtime_bindings(skills)

    assert card["endpoint"] == "https://brain.example.internal:9443/api/skills"
    assert any(item["endpoint"] == "https://brain.example.internal:9443/api/skills/request.create" for item in bindings)


def test_generated_mcp_descriptors_cover_registered_skills() -> None:
    skills = [item for item in discover_skills() if "error" not in item]
    descriptors = {item["skill_id"]: build_mcp_tool_descriptor(item) for item in skills}

    assert set(descriptors) == {item["skill_id"] for item in skills}
    assert descriptors["data.search"]["annotations"]["mode"] == "read"
    assert descriptors["request.create"]["annotations"]["mode"] == "write"
    assert descriptors["request.create"]["annotations"]["humanConfirmationRequired"] is True


def test_generated_runtime_bindings_file_is_valid_json() -> None:
    path = REPO_ROOT / "zw_brain" / "entry" / "a2a" / "tools" / "runtime_bindings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert any(item["tool_name"] == "request.create" for item in data)


def test_generated_mcp_tool_file_is_valid_json() -> None:
    path = REPO_ROOT / "zw_brain" / "entry" / "mcp" / "tools" / "request.create.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["name"] == "request.create"
    assert data["annotations"]["mode"] == "write"
