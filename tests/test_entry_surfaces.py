"""R-005: 自动化覆盖 F5 CLI + F6 MCP/A2A entry surfaces.

之前只有 scripts/headless_j1_demo.sh + scripts/mcp_client_smoke.py manual sample，
CI 不跑。本测试把三类入口的核心契约（list/describe/invoke + 错误路径）变成 pytest，
回归任何一项立即失败。

设计：
- in-process invoke 优先（无须起 server），跑得快、不依赖端口。
- 至少 1 个 read-only skill 真跑通（workbench.view），1 个未注册 skill 返 404/UnknownSkill。
- 不打 sample.txt 等存储产物；只校验调用契约。
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# ─── CLI (zw_brain.entry.cli.main) ──────────────────────────────────────────


def _ensure_dev_iam_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    """dev-iam-bypass 是 brain.invoke_skill 在测试进程里走通的最小授权前提。"""
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", "1")
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "development-only")


def _run_cli(args: list[str]) -> tuple[int, str, str]:
    from zw_brain.entry.cli import main as cli_main

    out, err = io.StringIO(), io.StringIO()
    parser = cli_main.build_parser()
    parsed = parser.parse_args(args)
    data = cli_main._load_commands()
    with redirect_stdout(out), redirect_stderr(err):
        if parsed.list is not None:
            code = cli_main.cmd_list(parsed.list or None, data)
        elif parsed.describe:
            code = cli_main.cmd_describe(parsed.describe, data)
        elif not parsed.skill_id:
            code = cli_main.EXIT_USAGE
        else:
            role = parsed.role or cli_main._resolve_default_role()
            code = cli_main.cmd_invoke(parsed.skill_id, parsed.payload, role, parsed.endpoint, data)
    return code, out.getvalue(), err.getvalue()


def test_cli_list_returns_many_skills() -> None:
    code, out, err = _run_cli(["--list"])
    assert code == 0
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) > 50, f"expected many skills, got {len(lines)}"
    assert "(source: commands.generated.json)" in err


def test_cli_list_prefix_filter() -> None:
    code, out, _ = _run_cli(["--list", "workbench"])
    assert code == 0
    skill_ids = [ln.split()[0] for ln in out.splitlines() if ln.strip()]
    assert skill_ids, "expected at least one workbench.* skill"
    assert all(sid.startswith("workbench") for sid in skill_ids)


def test_cli_describe_known_skill() -> None:
    code, out, _ = _run_cli(["--describe", "workbench.view"])
    assert code == 0
    assert "skill_id:    workbench.view" in out
    assert "invoke example:" in out


def test_cli_unknown_skill_exits_2() -> None:
    code, _, err = _run_cli(["bogus.skill.id"])
    from zw_brain.entry.cli.main import EXIT_UNKNOWN_SKILL

    assert code == EXIT_UNKNOWN_SKILL
    assert "unknown skill_id" in err


def test_cli_bad_payload_exits_3() -> None:
    code, _, err = _run_cli(["workbench.view", "--payload", "not json"])
    from zw_brain.entry.cli.main import EXIT_BAD_PAYLOAD

    assert code == EXIT_BAD_PAYLOAD
    assert "bad --payload JSON" in err


def test_cli_invoke_workbench_view_real_data(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_dev_iam_bypass(monkeypatch)
    code, out, _ = _run_cli(["workbench.view", "--role", "ROLE_ORGAN_OPERATER"])
    assert code == 0, out
    payload = json.loads(out)
    assert "greeting" in payload
    assert "todos" in payload


def test_cli_invoke_injects_sticky_confirmed(monkeypatch: pytest.MonkeyPatch) -> None:
    """R-002 regression guard: CLI must inject `confirmed: true` so write skills
    aren't rejected by policy.py:386 human_confirmation_required gate."""
    captured: dict[str, Any] = {}

    def fake_get_service() -> Any:
        class _Svc:
            def invoke_skill(self, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
                captured["skill_id"] = skill_id
                captured["payload"] = dict(payload)
                return {"ok": True}

        return _Svc()

    from zw_brain.command import runtime as cmd_runtime
    from zw_brain.skill_registration import runtime as reg_runtime

    monkeypatch.setattr(cmd_runtime, "get_service", fake_get_service)
    monkeypatch.setattr(reg_runtime, "require_surface", lambda *_a, **_kw: None)
    _ensure_dev_iam_bypass(monkeypatch)
    code, _, _ = _run_cli(["workbench.view"])
    assert code == 0
    assert captured["payload"].get("confirmed") is True, captured


# ─── MCP (zw_brain.entry.mcp.server) ────────────────────────────────────────


def test_mcp_list_tools_returns_descriptors() -> None:
    from zw_brain.entry.mcp.server import list_tools

    tools = list_tools()
    assert len(tools) > 20, f"expected >20 MCP tool descriptors, got {len(tools)}"
    for tool in tools[:3]:
        assert "name" in tool


def test_mcp_call_tool_real_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_dev_iam_bypass(monkeypatch)
    from zw_brain.entry.mcp.server import call_tool

    result = call_tool("workbench.view", {"role": "ROLE_ORGAN_OPERATER"})
    assert result["tool"] == "workbench.view"
    assert "greeting" in result["result"]


def test_mcp_client_smoke_stdio_subprocess() -> None:
    """F6: MCP stdio JSON-RPC 子进程 smoke（与 Cursor 接入同协议路径）。"""
    import os
    import subprocess
    import sys

    env = {
        **os.environ,
        "ZW_BRAIN_DEV_IAM_BYPASS": "1",
        "ZW_BRAIN_DEV_IAM_BYPASS_ACK": "development-only",
    }
    script = REPO_ROOT / "scripts" / "mcp_client_smoke.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "5 capability calls succeeded" in proc.stdout or "→ 200" in proc.stdout


def test_mcp_handle_tools_list_jsonrpc() -> None:
    from zw_brain.entry.mcp.server import _handle_tools_list

    resp = _handle_tools_list(id_=42)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 42
    assert "tools" in resp["result"]
    assert len(resp["result"]["tools"]) > 20


def test_mcp_handle_tools_call_unknown_returns_error() -> None:
    from zw_brain.entry.mcp.server import _handle_tools_call

    resp = _handle_tools_call(id_=99, params={"name": "bogus.skill.id", "arguments": {}})
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 99
    assert resp["error"]["code"] in (-32601, -32000), resp


# ─── A2A (zw_brain.entry.a2a.server) ────────────────────────────────────────


def test_a2a_agent_card_loadable() -> None:
    from zw_brain.entry.a2a.server import get_agent_card

    card = get_agent_card()
    assert card.get("name") == "zw-brain"
    assert "skills" in card


def test_a2a_runtime_bindings_loadable() -> None:
    from zw_brain.entry.a2a.server import get_runtime_bindings

    bindings = get_runtime_bindings()
    assert len(bindings) > 50
    sample = bindings[0]
    assert "tool_name" in sample


def test_a2a_invoke_real_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_dev_iam_bypass(monkeypatch)
    from zw_brain.entry.a2a.server import invoke

    result = invoke("workbench.view", {"role": "ROLE_ORGAN_OPERATER"})
    assert result["skill_id"] == "workbench.view"
    assert "greeting" in result["result"]


def test_a2a_serve_refuses_without_dev_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    """R-001 regression guard: A2A daemon must refuse to start without dev IAM bypass +
    ACK, since it has no per-request auth check."""
    monkeypatch.delenv("ZW_BRAIN_DEV_IAM_BYPASS", raising=False)
    monkeypatch.delenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", raising=False)
    from zw_brain.entry.a2a.server import serve_http

    err = io.StringIO()
    with redirect_stderr(err):
        code = serve_http(host="127.0.0.1", port=0)
    assert code == 2
    assert "refusing to start" in err.getvalue()
    assert "ZW_BRAIN_DEV_IAM_BYPASS_ACK" in err.getvalue()
