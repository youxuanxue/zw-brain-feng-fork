from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

from zw_brain.shared.sanitization import safe_json


@dataclass(frozen=True)
class AuthContext:
    subject: str
    username: str
    tenant_id: str
    org_code: str | None
    role_codes: tuple[str, ...]
    claims: dict[str, Any]
    development_iam_bypass: bool = False


_AUTH_CONTEXT: ContextVar[AuthContext | None] = ContextVar("zw_brain_auth_context", default=None)


def set_auth_context(context: AuthContext) -> Token[AuthContext | None]:
    return _AUTH_CONTEXT.set(context)


def get_auth_context() -> AuthContext | None:
    return _AUTH_CONTEXT.get()


def reset_auth_context(token: Token[AuthContext | None]) -> None:
    _AUTH_CONTEXT.reset(token)


def role_codes_from_claims(claims: dict[str, Any], *, client_id: str) -> tuple[str, ...]:
    roles: set[str] = set()
    realm_access = claims.get("realm_access")
    if isinstance(realm_access, dict):
        roles.update(str(item) for item in realm_access.get("roles") or [] if str(item))
    elif isinstance(realm_access, list):
        roles.update(str(item) for item in realm_access if str(item))
    resource_access = claims.get("resource_access")
    if isinstance(resource_access, dict):
        service_roles = resource_access.get(client_id)
        if isinstance(service_roles, dict):
            roles.update(str(item) for item in service_roles.get("roles") or [] if str(item))
    return tuple(sorted(roles))


def auth_context_from_claims(
    claims: dict[str, Any], *, client_id: str, development_iam_bypass: bool = False
) -> AuthContext:
    clean_claims = safe_json(claims)
    return AuthContext(
        subject=str(clean_claims.get("sub") or ""),
        username=str(clean_claims.get("preferred_username") or clean_claims.get("sub") or ""),
        tenant_id=str(clean_claims.get("project_id") or "sd-default"),
        org_code=str(clean_claims.get("org_code") or "") or None,
        role_codes=role_codes_from_claims(clean_claims, client_id=client_id),
        claims=clean_claims,
        development_iam_bypass=development_iam_bypass,
    )


_DEV_IAM_BYPASS_SUBJECT = "dev-iam-bypass"
_DEV_IAM_BYPASS_USERNAME = "dev_iam_bypass"


def dev_iam_bypass_auth_context() -> AuthContext:
    """Build the synthetic dev-IAM-bypass identity used by the headless consumer surfaces.

    The MCP / A2A / CLI in-process entry paths call ``brain.invoke_skill`` directly and,
    unlike REST, never establish a per-request AuthContext from real token claims. Without
    one, the C1/N1 boundary resolver would treat every call as system-origin and skip the
    held-role check — re-opening the forge gap on exactly the surfaces #183 missed.

    These daemons are gated to start only under dev-IAM-bypass, so they bind the same
    synthetic identity REST uses for bypass requests. Its role set comes from
    ``get_dev_iam_bypass_role_codes`` (default = all product roles; overridable via
    ``ZW_BRAIN_DEV_IAM_BYPASS_ROLES`` to reproduce restricted-identity scenarios), so the
    resolver is a no-op under the default full-role identity yet still rejects a forged
    role when the identity is deliberately narrowed.
    """
    from zw_brain.shared.runtime_config import get_dev_iam_bypass_role_codes

    role_codes = tuple(get_dev_iam_bypass_role_codes())
    return AuthContext(
        subject=_DEV_IAM_BYPASS_SUBJECT,
        username=_DEV_IAM_BYPASS_USERNAME,
        tenant_id="sd-default",
        org_code="dev",
        role_codes=role_codes,
        claims={"development_iam_bypass": True},
        development_iam_bypass=True,
    )


SYSTEM_ORIGIN_KEY = "_system_origin_call"

# Process-local sentinel mirroring session_context._TRUSTED_SESSION_MARKER: only
# server-side internal code (e.g. IAM first-login projection invoking
# actor.projection.sync as role="system") stamps this object into a payload to mark a
# call as system-origin / already-authorized. A JSON-deserialized client value can never
# compare ``is`` equal to it, so a remote caller cannot smuggle a system-origin claim to
# dodge the identity-boundary check.
_SYSTEM_ORIGIN_MARKER: object = object()


def mark_system_origin(payload: dict[str, Any]) -> dict[str, Any]:
    """Tag a payload as a system-origin / internal already-authorized invocation.

    Such calls deliberately act as an infrastructure role (e.g. "system") that the
    request-scoped user identity does not personally hold; they must not be subjected to
    the verified-identity role boundary. Returns a copy with the in-process sentinel set.
    """
    tagged = dict(payload)
    tagged[SYSTEM_ORIGIN_KEY] = _SYSTEM_ORIGIN_MARKER
    return tagged


def is_system_origin_payload(payload: dict[str, Any]) -> bool:
    return payload.get(SYSTEM_ORIGIN_KEY) is _SYSTEM_ORIGIN_MARKER


class IdentityRoleForbiddenError(PermissionError):
    """Raised when a request asks for a *write* role the verified identity does not hold.

    Distinct from "no product role at all" — this is an authenticated identity
    deliberately attempting to act as a role it was never granted (forge / privilege
    escalation), on a side-effecting capability. Read capabilities degrade instead of
    raising (least-privilege), so this is reserved for writes.
    """


def resolve_role_from_identity(
    requested_role: str,
    fallback_role: str,
    *,
    is_write: bool,
) -> str:
    """Shared boundary resolver — derive the authorization role from the verified identity.

    This is the single point that closes the C1/N1 root cause for *all* client-facing
    consumer surfaces (REST bearer/dev-bypass, MCP, A2A, CLI). They share one rule:

      * When an ``AuthContext`` is set (every authenticated entry path establishes one —
        REST per-request, MCP/A2A/CLI via the dev-bypass synthetic identity), the request
        may only act as a role the identity *actually holds*:
          - requested role held            → use it.
          - requested role NOT held, READ  → degrade to the identity's first product role
                                              (least-privilege; preserves existing read flow).
          - requested role NOT held, WRITE → raise ``IdentityRoleForbiddenError`` (403):
                                              acting as an unheld role on a side-effecting
                                              capability would execute with a forged actor
                                              and corrupt audit attribution (N1).
          - no requested role              → use the identity's first product role
                                              (identity default; unchanged behavior).
          - identity holds NO product role → raise ``IdentityRoleForbiddenError`` (403)
                                              rather than silently dropping to a default.

      * When NO ``AuthContext`` is set, this is an in-process / system-origin call (test
        fixtures, scheduled jobs, internal already-authorized invocations). The legacy
        ``requested_role or fallback_role`` resolution is preserved so those callers are
        not broken by the new boundary check.

    The dev-IAM-bypass synthetic identity holds every product role, so under bypass this
    is a no-op for any valid requested role — MCP/A2A/CLI keep working unchanged.
    """
    # Lazy import: keep shared layer free of an eager domain dependency cycle.
    from zw_brain.domain.policy import filter_product_role_codes

    ctx = get_auth_context()
    if ctx is None:
        # System-origin / in-process call: no verified identity boundary to enforce.
        return requested_role or fallback_role

    allowed = filter_product_role_codes(list(ctx.role_codes))
    requested = (requested_role or "").strip()

    if requested and requested in allowed:
        return requested

    if requested and requested not in allowed and is_write:
        # Authenticated identity forging an unheld role on a side-effecting capability.
        raise IdentityRoleForbiddenError(
            f"identity does not hold role {requested!r} required to perform this write"
        )

    # Read with unheld/absent requested role, or no requested role: least-privilege default.
    if allowed:
        return allowed[0]

    raise IdentityRoleForbiddenError("identity holds no product role")
