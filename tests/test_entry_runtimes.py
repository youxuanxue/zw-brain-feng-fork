from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import zw_brain.command.runtime as runtime

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def rest_policy_eval(capability_id: str, surface: str) -> str:
    return (
        "import json; "
        "from zw_brain.entry.rest.server import require_surface, get_service; "
        "require_surface('tenant.policy.evaluate', 'api'); "
        "print(json.dumps(get_service().invoke_skill('tenant.policy.evaluate', "
        f"{{'capability_id':{capability_id!r},'surface':{surface!r},'role':'ROLE_BUSIAUDIT'}}), ensure_ascii=False))"
    )


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

        cli = run_module("-m", "zw_brain.entry.cli.main", "data.search", "--payload", '{"query":"法人","role":"ROLE_ORGAN_OPERATER"}', env=env)
        cli_data = json.loads(cli.stdout)
        assert cli_data["results"]

        mcp_list = run_module("-m", "zw_brain.entry.mcp.server", "list-tools", env=env)
        mcp_tools = json.loads(mcp_list.stdout)
        assert any(item["name"] == "data.search" for item in mcp_tools)
        assert any(item["name"] == "audit.replay_evidence_chain" for item in mcp_tools)
        assert not any(item["name"] == "request.create" for item in mcp_tools)

        mcp_call = run_module(
            "-m",
            "zw_brain.entry.mcp.server",
            "call-tool",
            "request.view",
            "--payload",
            '{"request_id":"REQ-2026-04-25-0011","role":"ROLE_ORGAN_OPERATER"}',
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
            '{"role":"ROLE_SECURITY_AUDIT"}',
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
            '{"request_id":"REQ-2026-04-25-0011","decision":"approve","role":"ROLE_ORGAN_OPERATER","confirmed":true}',
            env=env,
            check=False,
        )
        assert denied_cli.returncode != 0
        assert "AccessDeniedError" in denied_cli.stderr

        denied_mcp_surface = run_module(
            "-m",
            "zw_brain.entry.mcp.server",
            "call-tool",
            "request.create",
            "--payload",
            '{"resource_id":"res-market-activity","role":"ROLE_ORGAN_OPERATER","confirmed":true}',
            env=env,
            check=False,
        )
        assert denied_mcp_surface.returncode != 0
        assert "SurfaceNotEnabledError" in denied_mcp_surface.stderr

        denied_mcp = run_module(
            "-m",
            "zw_brain.entry.mcp.server",
            "call-tool",
            "approval.review_decide",
            "--payload",
            '{"request_id":"REQ-2026-04-25-0011","decision":"approve","role":"ROLE_ORGAN_OPERATER","confirmed":true}',
            env=env,
            check=False,
        )
        assert denied_mcp.returncode != 0
        assert "SurfaceNotEnabledError" in denied_mcp.stderr

        denied_a2a = run_module(
            "-m",
            "zw_brain.entry.a2a.server",
            "invoke",
            "approval.review_decide",
            "--payload",
            '{"request_id":"REQ-2026-04-25-0011","decision":"approve","role":"ROLE_ORGAN_OPERATER","confirmed":true}',
            env=env,
            check=False,
        )
        assert denied_a2a.returncode != 0
        assert "AccessDeniedError" in denied_a2a.stderr

        runtime._service = None


def test_governance_iam_overview_shared_across_cli_mcp_a2a() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        env = os.environ.copy()
        env["ZW_BRAIN_DB_PATH"] = str(db_path)
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        runtime._service = None

        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()
        cli = json.loads(run_module("-m", "zw_brain.entry.cli.main", "governance.iam_overview", "--payload", '{"role":"ROLE_BUSIAUDIT"}', env=env).stdout)
        mcp = json.loads(run_module("-m", "zw_brain.entry.mcp.server", "call-tool", "governance.iam_overview", "--payload", '{"role":"ROLE_BUSIAUDIT"}', env=env).stdout)["result"]
        a2a = json.loads(run_module("-m", "zw_brain.entry.a2a.server", "invoke", "governance.iam_overview", "--payload", '{"role":"ROLE_BUSIAUDIT"}', env=env).stdout)["result"]
        for payload in [cli, mcp, a2a]:
            assert payload["tenant_id"] == "sd-default"
            assert "summary" in payload
            assert "actors" in payload
            assert "tenant_policies" in payload
            assert "import_issues" in payload
        runtime._service = None


def test_tenant_policy_evaluate_consistent_across_cli_mcp_a2a() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        env = os.environ.copy()
        env["ZW_BRAIN_DB_PATH"] = str(db_path)
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        runtime._service = None

        from zw_brain.shared.migrate import ensure_runtime_schema

        ensure_runtime_schema()

        run_module(
            "-m",
            "zw_brain.entry.cli.main",
            "package.review_decide",
            "--payload",
            '{"package_id":"PKG-2026-04-25-001","decision":"approve","role":"ROLE_BUSIAUDIT","confirmed":true}',
            env=env,
        )
        run_module(
            "-m",
            "zw_brain.entry.cli.main",
            "package.register_version",
            "--payload",
            '{"package_id":"PKG-2026-04-25-001","role":"ROLE_BUSIAUDIT","confirmed":true}',
            env=env,
        )
        run_module(
            "-m",
            "zw_brain.entry.cli.main",
            "package.apply_tenant_policy",
            "--payload",
            '{"package_id":"PKG-2026-04-25-001","role":"ROLE_BUSIAUDIT","confirmed":true}',
            env=env,
        )

        cli_allowed = run_module(
            "-m",
            "zw_brain.entry.cli.main",
            "tenant.policy.evaluate",
            "--payload",
            '{"capability_id":"ledger.entity.base.read","surface":"api","role":"ROLE_BUSIAUDIT"}',
            env=env,
        )
        cli_surface_blocked = run_module(
            "-m",
            "zw_brain.entry.cli.main",
            "tenant.policy.evaluate",
            "--payload",
            '{"capability_id":"ledger.entity.base.read","surface":"cli","role":"ROLE_BUSIAUDIT"}',
            env=env,
        )
        cli_allowed_data = json.loads(cli_allowed.stdout)
        cli_surface_blocked_data = json.loads(cli_surface_blocked.stdout)
        assert cli_allowed_data["allowed"] is True
        assert cli_allowed_data["source"] == "tenant_capability_policy"
        assert cli_allowed_data["decision_reason"] == "allowed_by_tenant_policy"
        assert cli_surface_blocked_data["allowed"] is False
        assert cli_surface_blocked_data["source"] == "tenant_capability_policy"
        assert cli_surface_blocked_data["decision_reason"] == "surface_not_exposed"

        rest_allowed = run_module(
            "-c",
            rest_policy_eval('ledger.entity.base.read', 'api'),
            env=env,
        )
        rest_surface_blocked = run_module(
            "-c",
            rest_policy_eval('ledger.entity.base.read', 'webui'),
            env=env,
        )
        rest_allowed_data = json.loads(rest_allowed.stdout)
        rest_surface_blocked_data = json.loads(rest_surface_blocked.stdout)
        assert rest_allowed_data["allowed"] is True
        assert rest_allowed_data["source"] == "tenant_capability_policy"
        assert rest_allowed_data["decision_reason"] == "allowed_by_tenant_policy"
        assert rest_surface_blocked_data["allowed"] is False
        assert rest_surface_blocked_data["source"] == "tenant_capability_policy"
        assert rest_surface_blocked_data["decision_reason"] == "surface_not_exposed"

        webui_surface_blocked = run_module(
            "-c",
            rest_policy_eval('ledger.entity.base.read', 'webui'),
            env=env,
        )
        webui_surface_blocked_data = json.loads(webui_surface_blocked.stdout)
        assert webui_surface_blocked_data["allowed"] is False
        assert webui_surface_blocked_data["source"] == "tenant_capability_policy"
        assert webui_surface_blocked_data["decision_reason"] == "surface_not_exposed"

        mcp_allowed = run_module(
            "-m",
            "zw_brain.entry.mcp.server",
            "call-tool",
            "tenant.policy.evaluate",
            "--payload",
            '{"capability_id":"ledger.entity.base.read","surface":"api","role":"ROLE_BUSIAUDIT"}',
            env=env,
        )
        mcp_surface_blocked = run_module(
            "-m",
            "zw_brain.entry.mcp.server",
            "call-tool",
            "tenant.policy.evaluate",
            "--payload",
            '{"capability_id":"ledger.entity.base.read","surface":"mcp","role":"ROLE_BUSIAUDIT"}',
            env=env,
        )
        mcp_allowed_data = json.loads(mcp_allowed.stdout)["result"]
        mcp_surface_blocked_data = json.loads(mcp_surface_blocked.stdout)["result"]
        assert mcp_allowed_data["allowed"] is True
        assert mcp_allowed_data["source"] == "tenant_capability_policy"
        assert mcp_allowed_data["decision_reason"] == "allowed_by_tenant_policy"
        assert mcp_surface_blocked_data["allowed"] is False
        assert mcp_surface_blocked_data["source"] == "tenant_capability_policy"
        assert mcp_surface_blocked_data["decision_reason"] == "surface_not_exposed"

        a2a_allowed = run_module(
            "-m",
            "zw_brain.entry.a2a.server",
            "invoke",
            "tenant.policy.evaluate",
            "--payload",
            '{"capability_id":"ledger.entity.base.read","surface":"api","role":"ROLE_BUSIAUDIT"}',
            env=env,
        )
        a2a_surface_blocked = run_module(
            "-m",
            "zw_brain.entry.a2a.server",
            "invoke",
            "tenant.policy.evaluate",
            "--payload",
            '{"capability_id":"ledger.entity.base.read","surface":"a2a","role":"ROLE_BUSIAUDIT"}',
            env=env,
        )
        a2a_allowed_data = json.loads(a2a_allowed.stdout)["result"]
        a2a_surface_blocked_data = json.loads(a2a_surface_blocked.stdout)["result"]
        assert a2a_allowed_data["allowed"] is True
        assert a2a_allowed_data["source"] == "tenant_capability_policy"
        assert a2a_allowed_data["decision_reason"] == "allowed_by_tenant_policy"
        assert a2a_surface_blocked_data["allowed"] is False
        assert a2a_surface_blocked_data["source"] == "tenant_capability_policy"
        assert a2a_surface_blocked_data["decision_reason"] == "surface_not_exposed"

        run_module(
            "-m",
            "zw_brain.entry.cli.main",
            "tenant.capability.disable",
            "--payload",
            '{"package_id":"PKG-2026-04-25-001","role":"ROLE_BUSIAUDIT","confirmed":true}',
            env=env,
        )
        disabled_results = {
            "webui": json.loads(run_module("-c", rest_policy_eval('ledger.entity.base.read', 'webui'), env=env).stdout),
            "api": json.loads(run_module("-m", "zw_brain.entry.cli.main", "tenant.policy.evaluate", "--payload", '{"capability_id":"ledger.entity.base.read","surface":"api","role":"ROLE_BUSIAUDIT"}', env=env).stdout),
            "cli": json.loads(run_module("-m", "zw_brain.entry.cli.main", "tenant.policy.evaluate", "--payload", '{"capability_id":"ledger.entity.base.read","surface":"cli","role":"ROLE_BUSIAUDIT"}', env=env).stdout),
            "mcp": json.loads(run_module("-m", "zw_brain.entry.mcp.server", "call-tool", "tenant.policy.evaluate", "--payload", '{"capability_id":"ledger.entity.base.read","surface":"mcp","role":"ROLE_BUSIAUDIT"}', env=env).stdout)["result"],
            "a2a": json.loads(run_module("-m", "zw_brain.entry.a2a.server", "invoke", "tenant.policy.evaluate", "--payload", '{"capability_id":"ledger.entity.base.read","surface":"a2a","role":"ROLE_BUSIAUDIT"}', env=env).stdout)["result"],
        }
        assert set(disabled_results) == {"webui", "api", "cli", "mcp", "a2a"}
        for decision in disabled_results.values():
            assert decision["allowed"] is False
            assert decision["source"] == "tenant_capability_policy"
            assert decision["decision_reason"] == "tenant_policy_disabled"

        runtime._service = None


def test_rest_main_reads_host_and_port_from_env(monkeypatch) -> None:
    captured = {}

    class FakeServer:
        def __init__(self, address, handler):
            captured["address"] = address
            captured["handler"] = handler

        def serve_forever(self):
            captured["served"] = True

    monkeypatch.setenv("ZW_BRAIN_REST_HOST", "0.0.0.0")
    monkeypatch.setenv("ZW_BRAIN_REST_PORT", "18800")

    from zw_brain.entry.rest import server

    monkeypatch.setattr(server, "ThreadingRestServer", FakeServer)
    server.main()

    assert captured["address"] == ("0.0.0.0", 18800)
    assert captured["served"] is True


def test_dashboard_main_reads_host_and_port_from_env(monkeypatch) -> None:
    captured = {}

    class FakeServer:
        def __init__(self, address, handler):
            captured["address"] = address
            captured["handler"] = handler

        def serve_forever(self):
            captured["served"] = True

    monkeypatch.setenv("ZW_BRAIN_DASHBOARD_BFF_HOST", "0.0.0.0")
    monkeypatch.setenv("ZW_BRAIN_DASHBOARD_BFF_PORT", "18801")

    from zw_brain.entry import dashboard_bff

    monkeypatch.setattr(dashboard_bff, "HTTPServer", FakeServer)
    dashboard_bff.main()

    assert captured["address"] == ("0.0.0.0", 18801)
    assert captured["served"] is True
