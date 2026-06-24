from __future__ import annotations

import json
from pathlib import Path

from scripts.export_agent_contract import discover_skills, is_live

REPO_ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = REPO_ROOT / "zw_brain" / "entry" / "rest" / "openapi.json"
AGENT_CARD_PATH = REPO_ROOT / "zw_brain" / "entry" / "a2a" / "agent_card.json"
RUNTIME_BINDINGS_PATH = REPO_ROOT / "zw_brain" / "entry" / "a2a" / "tools" / "runtime_bindings.json"
MCP_TOOLS_DIR = REPO_ROOT / "zw_brain" / "entry" / "mcp" / "tools"
DOC_PATH = REPO_ROOT / "docs" / "agent_integration.md"


def _non_live_skill_ids() -> set[str]:
    return {item["skill_id"] for item in discover_skills() if "error" not in item and not is_live(item)}


def test_non_live_skills_absent_from_openapi_paths() -> None:
    openapi = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    paths = openapi.get("paths", {})
    leaked = [sid for sid in _non_live_skill_ids() if f"/api/skills/{sid}" in paths]
    assert leaked == [], f"non-live skills leaked into openapi.json paths: {leaked}"


def test_non_live_skills_absent_from_a2a_agent_card() -> None:
    card = json.loads(AGENT_CARD_PATH.read_text(encoding="utf-8"))
    card_ids = {item["id"] for item in card.get("skills", [])}
    leaked = sorted(_non_live_skill_ids() & card_ids)
    assert leaked == [], f"non-live skills leaked into a2a/agent_card.json: {leaked}"


def test_non_live_skills_absent_from_a2a_runtime_bindings() -> None:
    bindings = json.loads(RUNTIME_BINDINGS_PATH.read_text(encoding="utf-8"))
    binding_names = {item["tool_name"] for item in bindings}
    leaked = sorted(_non_live_skill_ids() & binding_names)
    assert leaked == [], f"non-live skills leaked into a2a/tools/runtime_bindings.json: {leaked}"


def test_non_live_skills_absent_from_mcp_tool_descriptors() -> None:
    on_disk = {p.stem for p in MCP_TOOLS_DIR.glob("*.json")}
    leaked = sorted(_non_live_skill_ids() & on_disk)
    assert leaked == [], f"non-live skills leaked into mcp/tools/*.json: {leaked}"


def test_agent_integration_doc_canonical_table_only_lists_live_skills() -> None:
    doc = DOC_PATH.read_text(encoding="utf-8")
    leaked = sorted({sid for sid in _non_live_skill_ids() if f"`{sid}`" in doc})
    assert leaked == [], f"non-live skills leaked into docs/agent_integration.md: {leaked}"


def test_known_deferred_and_external_samples_are_filtered() -> None:
    samples = {
        "standard.asset.sync",
        "standard.asset.recommend",
        "adapter.national.application.submit",
        "adapter.national.catalog.pull",
        "direct_access.catalog.query",
        "ops.exchange.diagnose",
        "ops.gateway.heartbeat.ingest",
        "metadata.lineage.query",
        "external.quality.scan.execute",
    }
    openapi = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    paths = openapi.get("paths", {})
    card_ids = {item["id"] for item in json.loads(AGENT_CARD_PATH.read_text(encoding="utf-8")).get("skills", [])}
    binding_names = {item["tool_name"] for item in json.loads(RUNTIME_BINDINGS_PATH.read_text(encoding="utf-8"))}
    mcp_files = {p.stem for p in MCP_TOOLS_DIR.glob("*.json")}

    for sid in samples:
        assert f"/api/skills/{sid}" not in paths, f"openapi must not project {sid}"
        assert sid not in card_ids, f"agent_card must not list {sid}"
        assert sid not in binding_names, f"runtime_bindings must not list {sid}"
        assert sid not in mcp_files, f"mcp tool descriptor must not exist for {sid}"
