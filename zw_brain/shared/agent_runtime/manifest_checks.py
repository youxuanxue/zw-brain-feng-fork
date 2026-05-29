from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from zw_brain.capability_registry.runtime import load_manifests

ALLOWED_SPEC_VERSIONS = ("anp-agent/v1.1", "anp-agent/v1.2")
ALLOWED_AUTH_MODES = ("static_api_key", "trusted_gateway")
ALLOWED_TRUST_LEVELS = ("platform", "verified", "untrusted")
ALLOWED_MEMORY_MODES = ("regulated_minimal", "session_memory")
ALLOWED_CONTEXT_POLICIES = ("regulated_minimal", "session_memory")
FORBIDDEN_PERMISSION_PREFIXES = (
    "tenant.",
    "policy.",
    "audit.",
    "canonical.",
    "approval.case.decide",
    "inference.direct",
)
FORBIDDEN_MODEL_HOSTS = ("api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com")
INSPUR_GATEWAY_MARKERS = ("inspur", "gateway", "openai_compatible")


def load_agent_bundle(agent_yaml: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    agent = yaml.safe_load(agent_yaml.read_text(encoding="utf-8")) or {}
    if not isinstance(agent, dict):
        raise ValueError("AGENT.yaml root must be a mapping")
    sidecar_path = agent_yaml.parent / "capabilities.json"
    sidecar: dict[str, Any] = {}
    if sidecar_path.is_file():
        loaded = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            sidecar = loaded
    return agent, sidecar


def spec_version(agent: dict[str, Any], sidecar: dict[str, Any]) -> str | None:
    return (
        agent.get("schema_version")
        or agent.get("spec")
        or sidecar.get("runtime_spec_version")
        or (agent.get("metadata") or {}).get("runtime_spec_version")
    )


def validate_agent_bundle(agent_yaml: Path) -> tuple[bool, list[str], dict[str, Any]]:
    violations: list[str] = []
    try:
        agent, sidecar = load_agent_bundle(agent_yaml)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        return False, [str(exc)], {}

    spec = spec_version(agent, sidecar)
    if spec not in ALLOWED_SPEC_VERSIONS:
        violations.append(f"runtime_spec_version must be one of {ALLOWED_SPEC_VERSIONS}; got {spec!r}")

    metadata = agent.get("metadata") if isinstance(agent.get("metadata"), dict) else {}
    for field in ("id", "name", "version"):
        if not metadata.get(field):
            violations.append(f"metadata.{field} is required")

    trust_level = (
        metadata.get("trust_level")
        or sidecar.get("trust_level")
        or "untrusted"
    )
    if trust_level not in ALLOWED_TRUST_LEVELS:
        violations.append(f"trust_level must be in {ALLOWED_TRUST_LEVELS}; got {trust_level!r}")

    source_type = sidecar.get("source_type") or agent.get("source_type")
    if trust_level == "platform" and source_type not in (None, "builtin"):
        violations.append(f"trust_level=platform requires source_type=builtin; got {source_type!r}")

    auth_mode = sidecar.get("auth_mode") or (agent.get("auth") or {}).get("mode")
    if auth_mode and auth_mode not in ALLOWED_AUTH_MODES:
        violations.append(f"auth_mode must be in {ALLOWED_AUTH_MODES}; got {auth_mode!r}")

    tenant_id = sidecar.get("tenant_id") or agent.get("tenant_id")
    if tenant_id and tenant_id != "sd-default":
        violations.append(f"tenant_id must be sd-default for Phase 1; got {tenant_id!r}")

    if agent.get("tenant_mode") == "multi" or sidecar.get("tenant_mode") == "multi":
        violations.append("tenant_mode=multi is not allowed (sd-default single-tenant)")

    context_policy = sidecar.get("context_policy")
    memory_mode = (agent.get("context") or {}).get("memory_mode")
    memory_cfg = agent.get("memory") if isinstance(agent.get("memory"), dict) else {}
    memory_write = memory_cfg.get("write")
    if isinstance(memory_write, dict):
        memory_write = memory_write.get("enabled")
    for label, value in (("context_policy", context_policy), ("context.memory_mode", memory_mode)):
        if value is not None and value not in ALLOWED_CONTEXT_POLICIES:
            violations.append(f"{label} must be in {ALLOWED_MEMORY_MODES}; got {value!r}")
    if memory_write is True:
        violations.append("context.memory.write must be false or omitted for zw-brain embed")

    model = agent.get("model") if isinstance(agent.get("model"), dict) else {}
    if not _model_provider_allowed(model):
        provider = model.get("provider")
        violations.append(
            f"model.provider must point to inspur inference gateway (D6); got provider={provider!r}"
        )

    perms = sidecar.get("permission_scopes") or []
    if not isinstance(perms, list):
        perms = []
    for scope in perms:
        if not isinstance(scope, str):
            continue
        for prefix in FORBIDDEN_PERMISSION_PREFIXES:
            if scope.startswith(prefix):
                violations.append(f"permissions.scopes forbidden prefix {scope!r} (§8.5)")
        if scope == "admin:runtime":
            violations.append(
                "admin:runtime scope must not be declared in AGENT.yaml; use ROLE_SYSTEM gateway only"
            )

    tools = agent.get("tools") if isinstance(agent.get("tools"), list) else []
    for tool in tools:
        if isinstance(tool, dict) and str(tool.get("kind") or "").lower() in {"mcp", "skill"}:
            violations.append("tools.kind must not use legacy mcp/skill entries; use mcp_servers/skills")

    capability_tools = sidecar.get("capability_tools") if isinstance(sidecar, dict) else []
    manifests = load_manifests()
    for item in capability_tools or []:
        if not isinstance(item, dict):
            continue
        skill_id = str(item.get("skill_id") or "")
        if skill_id and skill_id not in manifests:
            violations.append(f"capability_tools references unknown skill_id {skill_id!r}")

    if (agent_yaml.parent / "server.py").exists() or (agent_yaml.parent / "main.py").exists():
        violations.append("embedded agent directory must not ship standalone HTTP entrypoints")

    merged = {"agent": agent, "sidecar": sidecar, "spec_version": spec, "trust_level": trust_level}
    return not violations, violations, merged


def _model_provider_allowed(model: dict[str, Any]) -> bool:
    provider = str(model.get("provider") or "").lower()
    if any(marker in provider for marker in INSPUR_GATEWAY_MARKERS):
        return True
    for key in ("base_url", "api_base", "endpoint"):
        if _url_is_inspur_gateway(str(model.get(key) or "")):
            return True
    for env_key in ("base_url_env", "api_key_env"):
        env_name = str(model.get(env_key) or "").strip()
        if env_name:
            env_val = os.environ.get(env_name, "")
            if _url_is_inspur_gateway(env_val):
                return True
            if env_name == "ZW_BRAIN_INFERENCE_GATEWAY_URL" and env_val:
                return True
    gateway = os.environ.get("ZW_BRAIN_INFERENCE_GATEWAY_URL") or ""
    return bool(gateway and _url_is_inspur_gateway(gateway))


def _url_is_inspur_gateway(url: str) -> bool:
    if not url:
        return False
    if "${env:" in url:
        return True
    parsed = urlparse(url)
    host = (parsed.netloc or parsed.path or "").lower()
    if any(forbidden in host for forbidden in FORBIDDEN_MODEL_HOSTS):
        return False
    return bool(host)


def diagnose_agent_bundle(agent_yaml: Path, *, production: bool = False) -> list[tuple[str, str, str]]:
    valid, violations, merged = validate_agent_bundle(agent_yaml)
    diagnoses: list[tuple[str, str, str]] = []
    spec = merged.get("spec_version")
    if valid:
        diagnoses.append(("OK", "validate", f"bundle valid spec={spec}"))
    else:
        for item in violations:
            diagnoses.append(("FAIL", "validate", item))

    sidecar = merged.get("sidecar") if isinstance(merged.get("sidecar"), dict) else {}
    trust = merged.get("trust_level") or "untrusted"
    if trust == "platform":
        diagnoses.append(("OK", "trust_level", "trust_level=platform (builtin)"))
    elif trust == "untrusted":
        diagnoses.append(("HINT", "trust_level", "trust_level=untrusted; B1.2 can promote to verified"))

    gateway = os.environ.get("ZW_BRAIN_INFERENCE_GATEWAY_URL")
    if gateway:
        diagnoses.append(("OK", "inference", f"gateway env configured ({gateway})"))
    else:
        diagnoses.append(
            (
                "WARN" if not production else "FAIL",
                "inference",
                "ZW_BRAIN_INFERENCE_GATEWAY_URL not set; model calls need group inference gateway (D6)",
            )
        )

    api_key = (
        os.environ.get("ZW_BRAIN_INFERENCE_API_KEY")
        or os.environ.get("OPENAI_COMPATIBLE_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    optional_key = (os.environ.get("ZW_BRAIN_INFERENCE_API_KEY_OPTIONAL") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if api_key:
        diagnoses.append(("OK", "inference", "inference API key configured"))
    elif optional_key:
        diagnoses.append(("OK", "inference", "ZW_BRAIN_INFERENCE_API_KEY_OPTIONAL=1 (placeholder key at runtime)"))
    else:
        diagnoses.append(
            (
                "WARN" if not production else "FAIL",
                "inference",
                "ZW_BRAIN_INFERENCE_API_KEY not set; openai_compatible models need a gateway key",
            )
        )

    auth_mode = sidecar.get("auth_mode")
    if auth_mode == "none":
        diagnoses.append(
            (
                "FAIL" if production else "WARN",
                "auth",
                "auth_mode=none is rejected by production readiness gate (§8.2)",
            )
        )
    elif auth_mode in ALLOWED_AUTH_MODES:
        diagnoses.append(("OK", "auth", f"auth_mode={auth_mode}"))

    capability_tools = sidecar.get("capability_tools") if isinstance(sidecar, dict) else []
    manifests = load_manifests()
    for item in capability_tools or []:
        if not isinstance(item, dict):
            continue
        skill_id = str(item.get("skill_id") or "")
        manifest = manifests.get(skill_id)
        if manifest is None:
            diagnoses.append(("FAIL", "capability_registry", f"unknown skill_id {skill_id!r}"))
            continue
        audit_class = manifest.get("audit_class") or "(none)"
        diagnoses.append(("OK", "capability_registry", f"{skill_id} audit_class={audit_class}"))

    agent = merged.get("agent") if isinstance(merged.get("agent"), dict) else {}
    model = agent.get("model") if isinstance(agent.get("model"), dict) else {}
    if _model_provider_allowed(model):
        diagnoses.append(("OK", "model.provider", f"provider={model.get('provider')!r}"))
    else:
        diagnoses.append(("FAIL", "model.provider", "model.provider must point to inspur inference gateway"))

    server_py = agent_yaml.parent / "server.py"
    if server_py.is_file() and re.search(
        r"uvicorn|fastapi\.FastAPI",
        server_py.read_text(encoding="utf-8"),
    ):
        diagnoses.append(("FAIL", "embedded", "standalone HTTP server entry found"))
    else:
        diagnoses.append(("OK", "embedded", "no standalone HTTP entry in agent directory"))

    return diagnoses
