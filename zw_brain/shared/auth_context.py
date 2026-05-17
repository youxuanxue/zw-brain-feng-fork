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
