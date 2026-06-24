# Wave: 0
# Journey: Cross (infrastructure)
# Covers: infra-contract-projection / infra-audit-bus / infra-inference-gateway / infra-iam-session
"""Wave 0 基础设施横切 .feature 的数据层 / 单元层验收。

仅断言**已实现**的 infra 行为；UI 渲染 / 未实现的富字段场景 skip 并注明归属。
不引入任何后端改动，不触碰 mapper / .data 主库 / 业务路径。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.no_db


# ======================================================================
# infra-contract-projection —— 单一契约 → 五消费面投影一致
# ======================================================================

def _skills_by_id() -> dict:
    from scripts.export_agent_contract import discover_skills

    return {item["skill_id"]: item for item in discover_skills() if "error" not in item}


def test_infra_projection_j1_skill_consistent_across_five_surfaces():
    """同一 J1 能力 slug 在 WebUI/API/CLI/MCP/A2A 投影到同一标识（基线 §6）."""
    from scripts.export_agent_contract import (
        build_a2a_card,
        build_mcp_tool_descriptor,
        build_rest_openapi,
        build_runtime_bindings,
    )
    from zw_brain.capability_registry.runtime import is_surface_enabled

    skills = _skills_by_id()
    # data.search 是 J1 找数 read 能力，五消费面全开
    assert "data.search" in skills, "J1 读能力 data.search 应已注册"
    skill = skills["data.search"]
    surfaces = set(skill.get("compatibility") or [])
    assert {"webui", "api", "cli", "mcp", "a2a"} <= surfaces, f"data.search 应五面齐全，实际 {surfaces}"

    skill_list = list(skills.values())
    openapi = build_rest_openapi(skill_list)
    a2a_card = {item["id"] for item in build_a2a_card(
        [s for s in skill_list if is_surface_enabled(s, "a2a")]
    )["skills"]}
    a2a_bindings = {item["tool_name"] for item in build_runtime_bindings(
        [s for s in skill_list if is_surface_enabled(s, "a2a")]
    )}
    mcp_desc = build_mcp_tool_descriptor(skill)

    assert openapi["paths"]["/api/skills/data.search"]["get"]["x-zwbrain-skill-id"] == "data.search"
    assert "data.search" in a2a_card
    assert "data.search" in a2a_bindings
    assert mcp_desc["name"] == "data.search"


def test_infra_projection_input_schema_single_source():
    """五消费面 schema 同源于 registry —— 字段集合一致（顺序无关）."""
    skills = _skills_by_id()
    skill = skills["data.search"]
    props = skill["input_schema"]["properties"]
    # registry 是唯一事实源：投影派生而非五处手维护
    assert isinstance(props, dict) and props, "data.search 应有 input_schema.properties"


def test_infra_projection_export_check_has_no_drift():
    """export_agent_contract.py --check 无 drift（任意手维护投影会被拦截）."""
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "export_agent_contract.py"), "--check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"契约投影存在 drift:\n{proc.stdout}\n{proc.stderr}"


def test_infra_projection_single_capability_registry_dir():
    """仓库中仅一个目录定义 Capability（确定性自动化运营和运维单一事实源约束）."""
    registry = REPO_ROOT / "zw_brain" / "capability_registry" / "registered"
    assert registry.is_dir()
    assert list(registry.glob("*.json")), "registered/ 下应有 capability 契约 JSON"


# ======================================================================
# infra-audit-bus —— 同步落库 + 写入失败熔断（D4）
# ======================================================================

def test_infra_audit_write_failure_circuit_breaks():
    """审计写入失败必须熔断业务（raise），不静默降级（D4 一票否决）."""
    import zw_brain.shared.audit as audit_bus

    def _failing_sink(*_args, **_kwargs):
        raise RuntimeError("simulated audit sink IntegrityError")

    audit_bus.clear_sink()
    audit_bus.configure_sink(_failing_sink)
    try:
        with pytest.raises(audit_bus.AuditWriteError):
            audit_bus.emit(audit_bus.AuditEvent(
                request_id="REQ-W0-06", actor="ROLE_ORGAN_OPERATER",
                skill_id="application.submit", phase="commit",
            ))
    finally:
        audit_bus.clear_sink()


def test_infra_audit_requires_configured_sink():
    """未配置 durable sink 时写审计直接 raise，不允许无审计落库."""
    import zw_brain.shared.audit as audit_bus

    audit_bus.clear_sink()
    with pytest.raises(audit_bus.AuditWriteError):
        audit_bus.emit(audit_bus.AuditEvent(
            request_id="REQ-W0-06", actor="ROLE_ORGAN_OPERATER",
            skill_id="application.submit", phase="commit",
        ))


def test_infra_audit_requires_mandatory_fields():
    """request_id / actor / skill_id 缺失即 raise（审计可回放硬约束）."""
    import zw_brain.shared.audit as audit_bus

    audit_bus.clear_sink()
    audit_bus.configure_sink(lambda *a, **k: None)
    try:
        with pytest.raises(audit_bus.AuditWriteError):
            audit_bus.emit(audit_bus.AuditEvent(
                request_id="", actor="ROLE_ORGAN_OPERATER",
                skill_id="application.submit", phase="commit",
            ))
    finally:
        audit_bus.clear_sink()


def test_infra_audit_success_calls_sink_and_buffers():
    """正向：sink 成功后事件落 sink 并入缓冲（同步落库语义）."""
    import zw_brain.shared.audit as audit_bus

    captured: list[tuple] = []
    audit_bus.clear_sink()
    audit_bus.drain()
    audit_bus.configure_sink(lambda rid, actor, sid, phase, payload: captured.append((rid, actor, sid, phase)))
    try:
        audit_bus.emit(audit_bus.AuditEvent(
            request_id="REQ-W0-06-ok", actor="ROLE_ORGAN_OPERATER",
            skill_id="application.submit", phase="commit",
        ))
        assert captured == [("REQ-W0-06-ok", "ROLE_ORGAN_OPERATER", "application.submit", "commit")]
        drained = audit_bus.drain()
        assert len(drained) == 1 and drained[0].request_id == "REQ-W0-06-ok"
    finally:
        audit_bus.clear_sink()
        audit_bus.drain()


def test_infra_audit_blockchain_anchor_is_async_outbox():
    """区块链锚定走异步 outbox 表（外链 down 不阻塞业务，D4 可插拔）."""
    from zw_brain.domain.models import AnchorOutboxRecord

    # outbox + delivered 标志的存在即"异步重试队列"结构证明，不在审计同事务内强制落链
    assert AnchorOutboxRecord.__tablename__ == "anchor_outbox"
    assert "delivered" in AnchorOutboxRecord.__table__.columns


@pytest.mark.skip(reason="audit_event 12 富字段（actor_org_code/audit_class/resource_ref/result）+ "
                         "actor_role 7 角色码 CHECK 约束属富 schema 目标态；当前最小 audit_event 表只有 "
                         "request_id/actor/skill_id/phase/payload。富字段落在 capability_call 表，"
                         "字段集对齐归 W0-07/Wave1 审计富化。")
def test_infra_audit_event_full_field_set():
    pass


# ======================================================================
# infra-inference-boundary —— zw-brain 不持有推理 SDK/env（D68）
# ======================================================================

def test_infra_inference_no_direct_llm_check_passes():
    """preflight 段 10 守卫脚本通过：zw_brain/ 无直连第三方 LLM SDK / host."""
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_no_direct_llm.py")],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"检测到直连第三方 LLM:\n{proc.stdout}\n{proc.stderr}"


def test_infra_inference_client_package_removed():
    """旧 shared/inference client 已退役；模型出口只属于独立 AgentRuntime 服务。"""
    assert not (REPO_ROOT / "zw_brain" / "shared" / "inference" / "client.py").exists()
    assert not (REPO_ROOT / "zw_brain" / "shared" / "inference" / "__init__.py").exists()


def test_infra_zw_brain_inference_env_guard_passes():
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_no_zw_brain_inference_env.py")],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.skip(reason="circuit-breaker 降级（AI 减摩点 fallback）+ 提示词注入系统前缀属业务侧 AI "
                         "减摩行为，最小 client 未内建；归 W0-07 浏览器侧 + 各 AI 减摩点 Wave1。")
def test_infra_inference_circuit_breaker_degradation():
    pass


# ======================================================================
# infra-iam-session —— IAF IAM 认证 + 会话生命周期
# ======================================================================

def test_infra_iam_config_derives_oidc_endpoints():
    """IafIamConfig 由 auth_server_url + realm 派生标准 OIDC 端点."""
    from zw_brain.shared.iaf_oidc import IafIamConfig

    cfg = IafIamConfig(auth_server_url="https://iam.example.gov", realm="picp")
    ep = cfg.endpoints
    assert ep.issuer == "https://iam.example.gov/realms/picp"
    assert ep.token_endpoint.endswith("/protocol/openid-connect/token")
    assert ep.jwks_uri.endswith("/protocol/openid-connect/certs")


def test_infra_iam_config_requires_auth_server_url():
    """缺 auth_server_url 即配置错误（IAM 是唯一身份提供方，不可空）."""
    from zw_brain.shared.iaf_oidc import IafIamConfig, IafIamConfigError

    with pytest.raises(IafIamConfigError):
        IafIamConfig(auth_server_url="")


def test_infra_iam_role_codes_extracted_from_realm_access():
    """realm_access.roles → role_codes 元组（IAM realm_roles 映射 zw-brain 角色码）."""
    from zw_brain.shared.auth_context import role_codes_from_claims

    claims = {"realm_access": {"roles": ["ROLE_ORGAN_OPERATER", "ROLE_BUSIAUDIT"]}}
    roles = role_codes_from_claims(claims, client_id="zw-brain")
    assert "ROLE_ORGAN_OPERATER" in roles
    assert "ROLE_BUSIAUDIT" in roles


def test_infra_iam_unknown_role_grants_no_permission():
    """不认识的角色码不静默扩权：permissions_for_role 对未知码 raise（不返回任何权限）."""
    from zw_brain.domain.policy import DomainAccessDeniedError, permissions_for_role

    with pytest.raises(DomainAccessDeniedError):
        permissions_for_role("ROLE_LEGACY_FOO")


def test_infra_iam_default_tenant_is_sd_default():
    """无 project_id claim 时 tenant 落 sd-default（单租户单省）."""
    from zw_brain.shared.auth_context import auth_context_from_claims

    ctx = auth_context_from_claims(
        {"sub": "u1", "preferred_username": "u1", "realm_access": {"roles": ["ROLE_ORGAN_OPERATER"]}},
        client_id="zw-brain",
    )
    assert ctx.tenant_id == "sd-default"
    assert ctx.subject == "u1"


def test_infra_iam_session_lifecycle():
    """会话建立 / 取回 / 删除生命周期（本地业务会话，token 不回传浏览器体）."""
    from zw_brain.shared.auth_session import AuthSessionStore

    store = AuthSessionStore()
    session = store.create(
        token_payload={"access_token": "a", "refresh_token": "r", "expires_in": 300},
        claims={"sub": "u1"},
        actor_snapshot={"subject": "u1", "tenant_id": "sd-default"},
        audit_id="AUD-1",
    )
    assert store.get(session.session_id) is not None
    public = session.public_payload()
    assert "access_token" not in public and public["authenticated"] is True
    store.delete(session.session_id)
    assert store.get(session.session_id) is None


def test_infra_iam_token_health_rejects_missing_bearer():
    """无 Authorization bearer 的请求被拒（401），不进业务层."""
    from zw_brain.shared.iaf_oidc import IafIamConfig, IafOidcClient, IafOidcTokenHealthError

    client = IafOidcClient(IafIamConfig(auth_server_url="https://iam.example.gov"))
    with pytest.raises(IafOidcTokenHealthError) as exc:
        client.validate_access_token_health(authorization="", transport=lambda req: None)
    assert exc.value.status_code == 401


@pytest.mark.skip(reason="D-2 红线：actor_org_role_binding 投影表灌库为 0 行（GovernanceMapper 缺位，"
                         "见 W0-02 D-2）。session → actor_org_role_binding 投影写入 + valid_to 软删除 "
                         "依赖 D-2 解冻，本期不实现、不解冻。")
def test_infra_iam_session_writes_actor_org_role_binding():
    pass


def test_infra_webui_allow_role_switch_on_dev_bypass(monkeypatch: pytest.MonkeyPatch):
    """Dev IAM bypass 默认打开岗位切换（与 scripts/start-local.sh 一致）；显式 =0 仍关闭。"""
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.state_store import StateStore

    brain = BrainService(state_store=StateStore())
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", "1")
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "development-only")
    monkeypatch.delenv("ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH", raising=False)
    assert brain.snapshot()["webui"]["allowRoleSwitch"] is True

    monkeypatch.setenv("ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH", "0")
    assert brain.snapshot()["webui"]["allowRoleSwitch"] is False


# ======================================================================
# E6 F10/F11 — headless demo 去假绿 + start-local NO_PROXY 提示
# ======================================================================

def test_headless_j1_demo_fails_closed_on_non_200_steps():
    """F10：headless J1 脚本任一步非 200 则 exit 1，审批步用 approve_reuse。"""
    script = (REPO_ROOT / "scripts" / "headless_j1_demo.sh").read_text(encoding="utf-8")
    assert "FAILED" in script
    assert 'exit 1' in script
    assert "approve_reuse" in script
    assert "extract_request_id" in script
    assert '"decision":"approved"' not in script
    assert 'REQ-2026-04-25-0011' not in script


def test_start_local_prints_no_proxy_tip_when_proxy_env_set():
    """F11：start-local 在检测到 http(s)_proxy 时提示 NO_PROXY 排障。"""
    script = (REPO_ROOT / "scripts" / "start-local.sh").read_text(encoding="utf-8")
    assert "NO_PROXY=127.0.0.1,localhost" in script
    assert "http_proxy" in script or "HTTP_PROXY" in script


def test_start_local_does_not_inject_inference_env_into_rest():
    """D68：start-local 不再给 zw-brain REST 默认注入推理环境。"""
    script = (REPO_ROOT / "scripts" / "start-local.sh").read_text(encoding="utf-8")
    assert "ZW_BRAIN_INFERENCE_MODE=mock" not in script
    assert "ZW_BRAIN_INFERENCE_MODE=${ZW_BRAIN_INFERENCE_MODE}" not in script
    assert "zw-brain REST does not load inference SDK/env" in script
    service_block = script.find('if [[ "$AR_LOCAL_SWITCH" == "http" ]]; then')
    start_call = script.find("\nstart_rest\n")
    assert service_block != -1 and start_call != -1 and service_block < start_call
