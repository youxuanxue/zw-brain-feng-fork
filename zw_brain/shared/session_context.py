"""BFF 可信运行时上下文：多组织 binding → session → Skill payload（阶段 D）。"""
from __future__ import annotations

from typing import Any

from zw_brain.domain.policy import ACTOR_NAMES, DomainAccessDeniedError, filter_product_role_codes
from zw_brain.domain.role_codes import BUSINESS_ROLE_CODES, TAG_LEAD_DEPT

TRUSTED_SESSION_CONTEXT_KEY = "_trusted_session_context"

# Process-local sentinel: only `build_trusted_skill_payload` (server-side, after BFF
# cookie session lookup) puts this object into a payload. JSON-deserialized values
# (e.g. a client smuggling `{"_trusted_session_context": true}` in their request body)
# can never compare `is` equal to this object, so `is_trusted_session_payload` fails
# closed for any non-server-constructed payload — defends Bearer / A2A / MCP / CLI
# entry paths that don't pass through `build_trusted_skill_payload`.
_TRUSTED_SESSION_MARKER: object = object()


def is_trusted_session_payload(payload: dict[str, Any]) -> bool:
    return payload.get(TRUSTED_SESSION_CONTEXT_KEY) is _TRUSTED_SESSION_MARKER


def _pick_default_role(allowed: set[str]) -> str:
    for code in BUSINESS_ROLE_CODES:
        if code in allowed:
            return code
    for code in sorted(allowed):
        if code in ACTOR_NAMES:
            return code
    raise DomainAccessDeniedError("no product role available for session context")


def contexts_from_bindings(bindings: list[dict[str, Any]], *, fallback_org_code: str | None = None) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for item in bindings:
        role_code = str(item.get("role_code") or "")
        if role_code not in ACTOR_NAMES:
            continue
        tags = item.get("actor_tags") if isinstance(item.get("actor_tags"), dict) else {}
        contexts.append(
            {
                "org_code": str(item.get("org_code") or fallback_org_code or ""),
                "role_code": role_code,
                "actor_tags": tags,
            }
        )
    return contexts


def contexts_from_role_codes(role_codes: list[str], *, org_code: str | None = None) -> list[dict[str, Any]]:
    product_roles = filter_product_role_codes(role_codes)
    org = str(org_code or "")
    return [{"org_code": org, "role_code": role, "actor_tags": {}} for role in product_roles]


def apply_runtime_context(
    snapshot: dict[str, Any],
    contexts: list[dict[str, Any]],
    *,
    preferred_org_code: str | None = None,
    preferred_role_code: str | None = None,
) -> dict[str, Any]:
    enriched = dict(snapshot)
    available = contexts or contexts_from_role_codes(
        [str(item) for item in enriched.get("role_codes") or []],
        org_code=str(enriched.get("org_code") or preferred_org_code or ""),
    )
    enriched["available_contexts"] = available
    allowed = {(str(item.get("org_code") or ""), str(item["role_code"])) for item in available if item.get("role_code")}

    current_org = str(preferred_org_code or enriched.get("current_org_code") or enriched.get("org_code") or "")
    current_role = str(preferred_role_code or enriched.get("current_role") or "")
    if (current_org, current_role) not in allowed and allowed:
        if preferred_org_code:
            matches = [item for item in available if str(item.get("org_code") or "") == str(preferred_org_code)]
            if matches:
                current_org = str(matches[0].get("org_code") or current_org)
                current_role = str(matches[0]["role_code"])
            else:
                current_org, current_role = next(iter((str(o), str(r)) for o, r in allowed))
        else:
            current_org, current_role = next(iter((str(o), str(r)) for o, r in allowed))
    if not current_role and allowed:
        allowed_roles = {role for _, role in allowed}
        current_role = _pick_default_role(allowed_roles)
        if not current_org and available:
            for item in available:
                if item["role_code"] == current_role:
                    current_org = str(item.get("org_code") or "")
                    break
    # 无产品岗位时仍允许建立 BFF 会话（current_role 留空）；Skill 调用由 resolve_trusted_role 拒绝。

    current_ctx = next(
        (item for item in available if str(item.get("org_code") or "") == current_org and item["role_code"] == current_role),
        None,
    )
    actor_tags = current_ctx.get("actor_tags") if isinstance(current_ctx, dict) else {}
    if TAG_LEAD_DEPT in (enriched.get("role_codes") or []) and not actor_tags.get(TAG_LEAD_DEPT):
        actor_tags = dict(actor_tags)
        actor_tags[TAG_LEAD_DEPT] = True

    enriched["current_org_code"] = current_org
    enriched["current_role"] = current_role
    enriched["actor_tags"] = actor_tags
    enriched["org_code"] = current_org or enriched.get("org_code")
    return enriched


def _resolve_trusted_context(payload: dict[str, Any], *, actor_snapshot: dict[str, Any]) -> dict[str, Any]:
    # D62 A0 (browser BFF gate, defense in depth): a disabled actor must never resolve a
    # product role for a skill call, even if a stale session snapshot still carries bindings.
    if str(actor_snapshot.get("status") or "") == "disabled":
        raise DomainAccessDeniedError("actor disabled")
    contexts = actor_snapshot.get("available_contexts")
    if isinstance(contexts, list) and contexts:
        available_contexts = [item for item in contexts if isinstance(item, dict)]
        allowed_roles = {str(item["role_code"]) for item in available_contexts if item.get("role_code")}
        allowed_pairs = {
            (str(item.get("org_code") or ""), str(item["role_code"]))
            for item in available_contexts
            if item.get("role_code")
        }
    else:
        allowed_roles = set(filter_product_role_codes(actor_snapshot.get("role_codes") or []))
        org = str(actor_snapshot.get("org_code") or "")
        allowed_pairs = {(org, role) for role in allowed_roles}
        available_contexts = [
            {"org_code": org, "role_code": role, "actor_tags": actor_snapshot.get("actor_tags") or {}}
            for role in allowed_roles
        ]

    if not allowed_roles:
        raise DomainAccessDeniedError("session has no allowed product roles")

    current_role = str(actor_snapshot.get("current_role") or "")
    current_org = str(actor_snapshot.get("current_org_code") or actor_snapshot.get("org_code") or "")
    requested_role = str(payload.get("role") or "").strip()
    requested_org = str(payload.get("org_code") or payload.get("current_org_code") or "").strip()

    if requested_role:
        if requested_role not in ACTOR_NAMES:
            raise DomainAccessDeniedError(f"unknown role: {requested_role}")
        if requested_role not in allowed_roles:
            raise DomainAccessDeniedError(f"role {requested_role} not in available session contexts")
        role_orgs = sorted(
            str(item.get("org_code") or "")
            for item in available_contexts
            if str(item.get("role_code") or "") == requested_role
        )
        if requested_org:
            pair_org = requested_org
        elif current_org and (current_org, requested_role) in allowed_pairs:
            pair_org = current_org
        elif role_orgs:
            pair_org = role_orgs[0]
        else:
            pair_org = current_org
        if allowed_pairs and (pair_org, requested_role) not in allowed_pairs:
            raise DomainAccessDeniedError(f"context ({pair_org!r}, {requested_role}) not allowed for this session")
        ctx = next(
            (
                item
                for item in available_contexts
                if str(item.get("org_code") or "") == pair_org
                and str(item.get("role_code") or "") == requested_role
            ),
            {"org_code": pair_org, "role_code": requested_role, "actor_tags": actor_snapshot.get("actor_tags") or {}},
        )
        return {"role": requested_role, "org_code": pair_org, "actor_tags": ctx.get("actor_tags") or {}}

    if current_role in allowed_roles and (not allowed_pairs or (current_org, current_role) in allowed_pairs):
        ctx = next(
            (
                item
                for item in available_contexts
                if str(item.get("org_code") or "") == current_org
                and str(item.get("role_code") or "") == current_role
            ),
            {"org_code": current_org, "role_code": current_role, "actor_tags": actor_snapshot.get("actor_tags") or {}},
        )
        return {"role": current_role, "org_code": current_org, "actor_tags": ctx.get("actor_tags") or {}}
    role = _pick_default_role(allowed_roles)
    ctx = next((item for item in available_contexts if str(item.get("role_code") or "") == role), None)
    org_code = str((ctx or {}).get("org_code") or "")
    return {"role": role, "org_code": org_code, "actor_tags": (ctx or {}).get("actor_tags") or {}}


def resolve_trusted_role(payload: dict[str, Any], *, actor_snapshot: dict[str, Any]) -> str:
    return str(_resolve_trusted_context(payload, actor_snapshot=actor_snapshot)["role"])


def build_trusted_skill_payload(client_payload: dict[str, Any] | None, *, actor_snapshot: dict[str, Any]) -> dict[str, Any]:
    payload = dict(client_payload or {})
    # Drop any client-supplied marker first: even though resolve_trusted_role doesn't
    # consult it, downstream `_resolve_role` only honors the sentinel value below.
    payload.pop(TRUSTED_SESSION_CONTEXT_KEY, None)
    resolved = _resolve_trusted_context(payload, actor_snapshot=actor_snapshot)
    role = str(resolved["role"])
    org_code = str(resolved.get("org_code") or "")
    actor_tags = resolved.get("actor_tags") if isinstance(resolved.get("actor_tags"), dict) else {}
    stamped_snapshot = dict(actor_snapshot)
    stamped_snapshot["current_role"] = role
    if org_code:
        stamped_snapshot["current_org_code"] = org_code
        stamped_snapshot["org_code"] = org_code
    stamped_snapshot["actor_tags"] = actor_tags
    merged = dict(payload)
    merged.pop("org_code", None)
    merged.pop("current_org_code", None)
    merged[TRUSTED_SESSION_CONTEXT_KEY] = _TRUSTED_SESSION_MARKER
    merged["role"] = role
    merged["actor_snapshot"] = stamped_snapshot
    merged["actor_tags"] = actor_tags
    merged["tenant_id"] = str(actor_snapshot.get("tenant_id") or merged.get("tenant_id") or "sd-default")
    if org_code:
        merged["org_code"] = org_code
    return merged


def caller_org_code(payload: dict[str, Any]) -> str:
    """从可信 payload 解析调用者机构 org_code（单一事实源）。

    build_trusted_skill_payload 把会话 current_org_code 钉进 payload['org_code']；
    actor_snapshot 兜底多上下文情形。bearer/CLI/A2A 等无机构上下文路径取不到则返空——
    调用方据空值 fail-closed（R11 审批方向门 / 部门数据可见性收口）。

    历史上 ops_service._caller_org_code 与 j1/approval._actor_org_code 各自复制了一份
    相同逻辑；二者现委托此处单源，新增的部门收口（visible_org_codes）亦从这里取机构。
    """
    snapshot = payload.get("actor_snapshot") if isinstance(payload.get("actor_snapshot"), dict) else {}
    return str(
        payload.get("org_code")
        or payload.get("current_org_code")
        or snapshot.get("current_org_code")
        or snapshot.get("org_code")
        or ""
    )


def org_codes_for_role(payload: dict[str, Any], role: str) -> set[str]:
    """Return trusted session org codes for a held product role.

    Browser BFF calls stamp ``actor_snapshot.available_contexts`` from live IAM
    bindings. Client supplied JSON on non-BFF paths cannot set the trust marker,
    so this helper only widens the current org for trusted session payloads.
    """
    if not is_trusted_session_payload(payload):
        current = caller_org_code(payload)
        return {current} if current else set()
    snapshot = payload.get("actor_snapshot") if isinstance(payload.get("actor_snapshot"), dict) else {}
    contexts = snapshot.get("available_contexts")
    if not isinstance(contexts, list):
        current = caller_org_code(payload)
        return {current} if current else set()
    role_code = str(role or "")
    orgs = {
        str(item.get("org_code") or "")
        for item in contexts
        if isinstance(item, dict) and str(item.get("role_code") or "") == role_code
    }
    orgs.discard("")
    return orgs
