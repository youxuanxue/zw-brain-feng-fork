"""测试用 trusted-payload helper — 走 build_trusted_skill_payload 模拟 BFF 验证后路径。

集成测试调 `brain.invoke_skill` 时应通过本 helper 构造 payload，避免 bypass
`build_trusted_skill_payload` 的 trust-stamp 路径，让测试与生产 (REST/MCP/CLI BFF
入口) 行为一致。PR #79 修了 3 处哨兵序列化泄漏；本 helper 是 R-001 类点护栏的回归
通道 —— mutate skill 集成测试均改走本 helper，trust-stamp 链路自动生效。

actor_snapshot 字段对齐 `zw_brain.shared.session_context.resolve_trusted_role` 期望：
  - tenant_id：租户隔离（默认 sd-default）
  - available_contexts: [{org_code, role_code, actor_tags}] —— 用于 role allowlist
  - current_org_code + current_role —— BFF 当前会话上下文
  - org_code + role_codes —— 兼容旧 actor_snapshot 形态（无 available_contexts 时 fallback）
  - actor_tags：tag_lead_dept 等业务侧标记
"""
from __future__ import annotations

from typing import Any

from zw_brain.shared.session_context import build_trusted_skill_payload


def _default_actor_snapshot(role: str = "ROLE_ORGAN_MANAGER", *, org_code: str = "ORG-A", tenant_id: str = "sd-default") -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "actor": f"test-actor:{role.lower()}",
        "org_code": org_code,
        "current_org_code": org_code,
        "current_role": role,
        "role_codes": [role],
        "available_contexts": [{"org_code": org_code, "role_code": role, "actor_tags": {}}],
        "actor_tags": {},
    }


def actor_snapshot(role: str, *, org_code: str = "ORG-A", tenant_id: str = "sd-default", **extra: Any) -> dict[str, Any]:
    """Build a complete actor_snapshot for a given product role.

    Use the kwargs to override or extend (e.g. multi-context BFF, extra actor_tags).
    """
    snapshot = _default_actor_snapshot(role, org_code=org_code, tenant_id=tenant_id)
    snapshot.update(extra)
    return snapshot


def trusted_payload(
    client_payload: dict[str, Any] | None = None,
    *,
    role: str = "ROLE_ORGAN_MANAGER",
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Wrap a client payload through build_trusted_skill_payload.

    Returns a payload with the trust sentinel marker set, suitable to pass to
    `BrainService.invoke_skill`. Either pass a fully-built `snapshot` or rely on
    the default actor_snapshot built from `role` (and ORG-A / sd-default).
    """
    if snapshot is None:
        snapshot = _default_actor_snapshot(role)
    return build_trusted_skill_payload(client_payload or {}, actor_snapshot=snapshot)


def invoke_trusted(
    brain: Any,
    skill_id: str,
    client_payload: dict[str, Any] | None = None,
    *,
    role: str = "ROLE_ORGAN_MANAGER",
    snapshot: dict[str, Any] | None = None,
) -> Any:
    """Single-call helper: build trusted payload + invoke_skill.

    Mirror what production BFF (REST/MCP/CLI) does post-session-validation. Mutate
    skill integration tests should use this entry point — read-side skill tests
    may keep using brain.invoke_skill directly (no audit/policy diff).
    """
    payload = trusted_payload(client_payload, role=role, snapshot=snapshot)
    return brain.invoke_skill(skill_id, payload)
