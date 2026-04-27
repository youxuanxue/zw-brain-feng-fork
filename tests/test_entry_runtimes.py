from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import zw_brain.shared.runtime as runtime

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run_module(*args: str, env: dict[str, str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


def test_cli_mcp_and_a2a_share_runtime_contract() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        env = os.environ.copy()
        env["ZW_BRAIN_DB_PATH"] = str(db_path)
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        runtime._service = None

        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()

        cli = run_module("-m", "zw_brain.entry.cli.main", "data.search", "--payload", '{"query":"法人","role":"r1"}', env=env)
        cli_data = json.loads(cli.stdout)
        assert cli_data["results"]

        mcp_list = run_module("-m", "zw_brain.entry.mcp.server", "list-tools", env=env)
        mcp_tools = json.loads(mcp_list.stdout)
        assert any(item["name"] == "data.search" for item in mcp_tools)
        assert any(item["name"] == "audit.replay_evidence_chain" for item in mcp_tools)
        assert any(item["name"] == "request.create" and item["annotations"]["mode"] == "write" for item in mcp_tools)

        mcp_call = run_module(
            "-m",
            "zw_brain.entry.mcp.server",
            "call-tool",
            "request.view",
            "--payload",
            '{"request_id":"REQ-2026-04-25-0011","role":"r1"}',
            env=env,
        )
        mcp_data = json.loads(mcp_call.stdout)
        assert mcp_data["tool"] == "request.view"
        assert mcp_data["result"]["id"] == "REQ-2026-04-25-0011"

        a2a_card = run_module("-m", "zw_brain.entry.a2a.server", "agent-card", env=env)
        card = json.loads(a2a_card.stdout)
        assert any(item["id"] == "request.create" and item["mode"] == "write" for item in card["skills"])
        assert any(item["id"] == "data.search" and item["mode"] == "read" for item in card["skills"])

        a2a_invoke = run_module(
            "-m",
            "zw_brain.entry.a2a.server",
            "invoke",
            "dashboard.render_command_center",
            "--payload",
            '{"role":"r8"}',
            env=env,
        )
        a2a_data = json.loads(a2a_invoke.stdout)
        assert a2a_data["skill_id"] == "dashboard.render_command_center"
        assert a2a_data["result"]["mode"] in {"live-readonly", "snapshot"}

        denied_cli = run_module(
            "-m",
            "zw_brain.entry.cli.main",
            "approval.review_decide",
            "--payload",
            '{"request_id":"REQ-2026-04-25-0011","decision":"approve","role":"r1","confirmed":true}',
            env=env,
            check=False,
        )
        assert denied_cli.returncode != 0
        assert "AccessDeniedError" in denied_cli.stderr

        denied_mcp = run_module(
            "-m",
            "zw_brain.entry.mcp.server",
            "call-tool",
            "approval.review_decide",
            "--payload",
            '{"request_id":"REQ-2026-04-25-0011","decision":"approve","role":"r1","confirmed":true}',
            env=env,
            check=False,
        )
        assert denied_mcp.returncode != 0
        assert "AccessDeniedError" in denied_mcp.stderr

        denied_a2a = run_module(
            "-m",
            "zw_brain.entry.a2a.server",
            "invoke",
            "approval.review_decide",
            "--payload",
            '{"request_id":"REQ-2026-04-25-0011","decision":"approve","role":"r1","confirmed":true}',
            env=env,
            check=False,
        )
        assert denied_a2a.returncode != 0
        assert "AccessDeniedError" in denied_a2a.stderr

        runtime._service = None
