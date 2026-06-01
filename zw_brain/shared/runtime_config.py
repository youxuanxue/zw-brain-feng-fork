from __future__ import annotations

import os
from typing import Any

from zw_brain.shared.iaf_oidc import IafIamConfig

# Bind all interfaces so Cursor Cloud / container previews can reach the dev server
# (127.0.0.1-only rejects forwarded connections from the preview proxy).
DEFAULT_HOST = "0.0.0.0"
DEFAULT_REST_PORT = 8800


def _get_port(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535")
    return port


def get_rest_host() -> str:
    return os.environ.get("ZW_BRAIN_REST_HOST", DEFAULT_HOST)


def get_rest_port() -> int:
    # PaaS / cloud agents often inject PORT; prefer explicit ZW_BRAIN_REST_PORT when set.
    if os.environ.get("ZW_BRAIN_REST_PORT"):
        return _get_port("ZW_BRAIN_REST_PORT", DEFAULT_REST_PORT)
    if os.environ.get("PORT"):
        return _get_port("PORT", DEFAULT_REST_PORT)
    return DEFAULT_REST_PORT


# Hostname used in generated base URLs (0.0.0.0 is listen-only, not a valid client target).
_DEFAULT_URL_HOST = "127.0.0.1"


def get_rest_base_url() -> str:
    default = f"http://{_DEFAULT_URL_HOST}:{get_rest_port()}"
    return os.environ.get("ZW_BRAIN_REST_BASE_URL", default).rstrip("/")


def get_rest_api_skills_endpoint() -> str:
    return f"{get_rest_base_url()}/api/skills"


_DEV_BYPASS_ACK_VALUE = "development-only"
_PROD_DEPLOY_MODES = {"prod", "production"}


def get_dev_iam_bypass_ack() -> bool:
    return os.environ.get("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "").strip() == _DEV_BYPASS_ACK_VALUE


def _is_prod_deploy_mode() -> bool:
    # Reuse the existing deploy-mode signal (ZW_BRAIN_DEPLOY_MODE) already consulted by
    # auth_session.validate_session_store_for_deploy — do NOT invent a parallel prod flag.
    return os.environ.get("ZW_BRAIN_DEPLOY_MODE", "").strip().lower() in _PROD_DEPLOY_MODES


class DevBypassInProductionError(RuntimeError):
    """dev-IAM-bypass env present while the deploy mode is prod/production.

    M5 fail-closed guard. The two bypass env vars synthesize a full-role identity with no
    real authentication; if they leak into a production rollout the entire authz model is
    open. Rather than silently honoring them, refuse at the point of evaluation so the
    process fails closed (no auth bypass) instead of fails open.
    """


def get_dev_iam_bypass_enabled() -> bool:
    # Two env vars are required so a single typo cannot disable auth in a production rollout.
    bypass_requested = (
        os.environ.get("ZW_BRAIN_DEV_IAM_BYPASS", "").strip() == "1" and get_dev_iam_bypass_ack()
    )
    if bypass_requested and _is_prod_deploy_mode():
        # M5: fail closed. The dev bypass must never be honored under a prod deploy mode.
        raise DevBypassInProductionError(
            "ZW_BRAIN_DEV_IAM_BYPASS=1 + ACK is set while ZW_BRAIN_DEPLOY_MODE is "
            "prod/production. The dev IAM bypass synthesizes an unauthenticated full-role "
            "identity and is forbidden in production. Unset the bypass env vars (production "
            "must authenticate via IAF cookie/bearer) or use a non-prod ZW_BRAIN_DEPLOY_MODE."
        )
    return bypass_requested


def get_dev_iam_bypass_role_codes() -> list[str]:
    """Resolve the role list for the dev-iam-bypass synthetic identity (shared SoT).

    Conventions (kept identical to the historical REST helper so reproduction scenarios
    such as A3 无产品岗位 are unchanged):
      - env unset → ALL_ROLE_CODES (default; full-role synthetic identity).
      - env =""   → empty list (无产品岗位 path).
      - env ="ROLE_ORGAN_OPERATER,ROLE_BUSIAUDIT" → exactly those.

    Lives in shared so REST, MCP, A2A, and CLI all establish the *same* dev-bypass
    AuthContext, letting the C1/N1 boundary resolver enforce role-holding uniformly.
    """
    from zw_brain.domain.role_codes import ALL_ROLE_CODES

    raw = os.environ.get("ZW_BRAIN_DEV_IAM_BYPASS_ROLES")
    if raw is None:
        return list(ALL_ROLE_CODES)
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_iaf_verify_ssl() -> bool:
    return os.environ.get("ZW_BRAIN_IAF_VERIFY_SSL", "true").strip().lower() != "false"


def get_iaf_insecure_tls_dev_ack() -> bool:
    return os.environ.get("ZW_BRAIN_IAF_INSECURE_TLS_DEV_ACK", "").strip() == _DEV_BYPASS_ACK_VALUE


def get_iaf_iam_config() -> IafIamConfig:
    return IafIamConfig.from_env()


def get_iaf_iam_public_config() -> dict[str, Any]:
    return get_iaf_iam_config().public_dict()
