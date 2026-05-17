from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from zw_brain.shared.iaf_oidc import IafIamConfig

# Bind all interfaces so Cursor Cloud / container previews can reach the dev server
# (127.0.0.1-only rejects forwarded connections from the preview proxy).
DEFAULT_HOST = "0.0.0.0"
DEFAULT_REST_PORT = 8800
DEFAULT_DASHBOARD_BFF_PORT = 8801


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


def get_dashboard_bff_host() -> str:
    return os.environ.get("ZW_BRAIN_DASHBOARD_BFF_HOST", DEFAULT_HOST)


def get_dashboard_bff_port() -> int:
    if os.environ.get("ZW_BRAIN_DASHBOARD_BFF_PORT"):
        return _get_port("ZW_BRAIN_DASHBOARD_BFF_PORT", DEFAULT_DASHBOARD_BFF_PORT)
    rest = get_rest_port()
    if rest >= 65535:
        return DEFAULT_DASHBOARD_BFF_PORT
    return rest + 1


def get_webui_dashboard_href() -> str | None:
    raw = (os.environ.get("ZW_BRAIN_WEBUI_DASHBOARD_URL") or "").strip()
    if raw.lower() in {"none", "off", "false", "-", "0"}:
        return None
    if not raw:
        return "/dashboard/"
    if raw.startswith("/"):
        url = raw.rstrip("/")
        return url + "/" if url else "/"
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        url = raw.rstrip("/")
        return url + "/"
    return None


_DEV_BYPASS_ACK_VALUE = "development-only"


def get_dev_iam_bypass_ack() -> bool:
    return os.environ.get("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "").strip() == _DEV_BYPASS_ACK_VALUE


def get_dev_iam_bypass_enabled() -> bool:
    # Two env vars are required so a single typo cannot disable auth in a production rollout.
    return os.environ.get("ZW_BRAIN_DEV_IAM_BYPASS", "").strip() == "1" and get_dev_iam_bypass_ack()


def get_iaf_verify_ssl() -> bool:
    return os.environ.get("ZW_BRAIN_IAF_VERIFY_SSL", "true").strip().lower() != "false"


def get_iaf_insecure_tls_dev_ack() -> bool:
    return os.environ.get("ZW_BRAIN_IAF_INSECURE_TLS_DEV_ACK", "").strip() == _DEV_BYPASS_ACK_VALUE


def get_iaf_iam_config() -> IafIamConfig:
    return IafIamConfig.from_env()


def get_iaf_iam_public_config() -> dict[str, Any]:
    return get_iaf_iam_config().public_dict()
