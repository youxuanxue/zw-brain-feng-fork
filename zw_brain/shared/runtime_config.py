from __future__ import annotations

import os

DEFAULT_HOST = "127.0.0.1"
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
    return _get_port("ZW_BRAIN_REST_PORT", DEFAULT_REST_PORT)


def get_rest_base_url() -> str:
    default = f"http://{DEFAULT_HOST}:{get_rest_port()}"
    return os.environ.get("ZW_BRAIN_REST_BASE_URL", default).rstrip("/")


def get_rest_api_skills_endpoint() -> str:
    return f"{get_rest_base_url()}/api/skills"


def get_dashboard_bff_host() -> str:
    return os.environ.get("ZW_BRAIN_DASHBOARD_BFF_HOST", DEFAULT_HOST)


def get_dashboard_bff_port() -> int:
    return _get_port("ZW_BRAIN_DASHBOARD_BFF_PORT", DEFAULT_DASHBOARD_BFF_PORT)
