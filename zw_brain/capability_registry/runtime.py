from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import Any

REGISTRY_DIR = Path(__file__).with_name("registered")
SURFACES = {"webui", "api", "cli", "mcp", "a2a"}
JOURNEYS = {"j1", "j2", "b1", "infra", "external", "national"}
STATUS_LITERALS = {"live", "external"}
STATUS_DEFERRED_RE = re.compile(r"^deferred:wave-[1-4]$")
# R14 / 设计基线 §10.3：三引擎落地后允许 capability 进入 preview / draft 态。
# 默认 'live'；preview / draft 仅在 Wave 2 三引擎走"草稿→预览→入库"流时合法。
CONFIG_CHANGE_CLASSES = {"live", "preview", "draft"}

# F6 T1（D68）：外部第三方 Agent 经 source_type=external-register 注册时强制的 4 字段。
# agent_trust_level = 外部 Agent **来源信任级**——GATE D33.d 决议把 Registry 侧字段命名为
# agent_trust_level（与 F4 包级 trust_level / PACKAGE_TRUST_LEVELS 区分，消除同名异义）。
EXTERNAL_REGISTER_SPEC_VERSIONS = {"anp-agent/v1.1", "anp-agent/v1.2"}
EXTERNAL_REGISTER_TRUST_LEVELS = {"verified", "untrusted"}  # platform 仅限 builtin，外部不可得
EXTERNAL_REGISTER_REQUIRED_FIELDS = (
    "runtime_spec_version",
    "agent_yaml_ref",
    "agent_trust_level",
    "workspace_required",
)

# F4 — 能力包内置 trust_level（manifest / capability_package 表字段）。
# **不要与 F6 T1 触发的 AgentRuntime Registry trust_level 混淆**：前者由 BUSIAUDIT
# 评估（原 SECURITY_ADMIN 共评，已随安全管理员本期退役而收口，D55/P16），决定能力包能否
# 启用；后者描述外部 Agent 来源可信级。
# D33.a (2026-05-28) 撤回：原计划改名 package.review_status 以消除同名异义，
# 但 package.trust_level.update capability 的 slug + permission + schema 字段相互依赖，
# 完整 rename 是 5 消费面 API breaking change，超出本 PR 范围。保留现状，靠本注释 +
# manifest_checks.py:15 的 ALLOWED_TRUST_LEVELS 隔离 namespace 守住语义。下一 PR 专项处理。
PACKAGE_TRUST_LEVELS: tuple[str, ...] = ("baseline", "reviewed", "restricted", "revoked")

# F4 — 能力包生命周期合法迁移；其他迁移由 handler raise InvalidStateError。
_PACKAGE_LIFECYCLE_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"approved", "pending-fix", "rejected"},
    "pending-fix": {"pending", "rejected"},
    "approved": {"active", "rejected"},
    "active": {"rolled-back", "suspended", "revoked"},
    "rolled-back": {"active", "suspended"},
    "suspended": {"active", "revoked"},
    "rejected": set(),
    "revoked": set(),
}


def package_trust_levels() -> tuple[str, ...]:
    """枚举能力包内置 trust_level 取值（F4 manifest 字段语义）。"""
    return PACKAGE_TRUST_LEVELS


def validate_package_lifecycle_transition(from_status: str, to_status: str) -> None:
    """能力包状态机校验；非法迁移 raise ValueError。

    F4 范围：用于 package.rollback / package.trust_level.update 等写操作前校验；
    F5 UI / F6 AgentRuntime Registry 等扩展状态不在本表内。
    """
    if from_status == to_status:
        return
    allowed = _PACKAGE_LIFECYCLE_TRANSITIONS.get(from_status)
    if allowed is None:
        raise ValueError(f"unknown package lifecycle source state: {from_status!r}")
    if to_status not in allowed:
        raise ValueError(
            f"illegal package lifecycle transition: {from_status!r} → {to_status!r}; "
            f"allowed: {sorted(allowed) or '∅'}"
        )


class SurfaceNotEnabledError(PermissionError):
    pass


@functools.lru_cache(maxsize=1)
def load_manifests() -> dict[str, dict[str, Any]]:
    """加载并校验全部已注册 manifest（slug → manifest）。

    ``registered/*.json`` 是运行期只读的静态资产，而本函数处于五消费面
    （WebUI / REST / CLI / MCP / A2A）最热路径上——``get_manifest`` 每次调用、
    brain.py invoke 校验、每条审计 phase、snapshot 全量投影都会触达。每次重新
    glob + read + json.loads + validate 全部 manifest 是无谓的重复磁盘 I/O，
    故用进程级 ``lru_cache(maxsize=1)`` 一次性填充缓存。

    需要热替换 manifest 的测试（写入临时 manifest 后期望重新读取）必须先调用
    ``load_manifests.cache_clear()`` 使缓存失效，否则会拿到旧快照。
    """
    manifests: dict[str, dict[str, Any]] = {}
    for path in sorted(REGISTRY_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        validate_manifest(data)
        manifests[data["slug"]] = data
    return manifests


def get_manifest(slug: str) -> dict[str, Any]:
    manifests = load_manifests()
    if slug not in manifests:
        raise KeyError(slug)
    return manifests[slug]


def compatibility(manifest: dict[str, Any]) -> set[str]:
    values = manifest.get("compatibility", [])
    if not isinstance(values, list):
        return set()
    return {str(value) for value in values}


def is_surface_enabled(manifest: dict[str, Any], surface: str) -> bool:
    if surface not in SURFACES:
        raise ValueError(f"unknown surface: {surface}")
    return surface in compatibility(manifest)


def require_surface(slug: str, surface: str) -> dict[str, Any]:
    manifest = get_manifest(slug)
    if not is_surface_enabled(manifest, surface):
        raise SurfaceNotEnabledError(f"{slug} is not exposed on {surface}")
    # Defense-in-depth aligned with export_agent_contract.is_live: non-live capabilities are
    # already removed from openapi/agent_card/runtime_bindings/mcp projections; this
    # second gate ensures the runtime handler also refuses them even if an old client
    # still has a cached path or someone crafts the URL directly.
    scope = manifest.get("product_scope") or {}
    status = scope.get("status")
    if status != "live":
        raise SurfaceNotEnabledError(f"{slug} is not live (status={status!r})")
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    slug = manifest.get("slug")
    if not slug:
        raise ValueError("capability manifest missing slug")
    unknown = compatibility(manifest) - SURFACES
    if unknown:
        raise ValueError(f"{slug} has unknown compatibility surfaces: {', '.join(sorted(unknown))}")
    runtime_binding = manifest.get("runtime_binding", {})
    method = runtime_binding.get("method")
    if method and method != slug:
        raise ValueError(f"{slug} runtime_binding.method must equal slug")
    product_scope = manifest.get("product_scope")
    if not isinstance(product_scope, dict):
        raise ValueError(f"{slug} missing required product_scope field")
    journey = product_scope.get("journey")
    if journey not in JOURNEYS:
        raise ValueError(
            f"{slug} product_scope.journey must be one of {sorted(JOURNEYS)}, got {journey!r}"
        )
    status = product_scope.get("status")
    if status not in STATUS_LITERALS and not (
        isinstance(status, str) and STATUS_DEFERRED_RE.match(status)
    ):
        raise ValueError(
            f"{slug} product_scope.status must be 'live' / 'external' / 'deferred:wave-[1-4]', got {status!r}"
        )
    config_change_class = manifest.get("config_change_class", "live")
    if config_change_class not in CONFIG_CHANGE_CLASSES:
        raise ValueError(
            f"{slug} config_change_class must be one of {sorted(CONFIG_CHANGE_CLASSES)}, got {config_change_class!r}"
        )
    if manifest.get("source_type") == "external-register":
        _validate_external_register_fields(slug, manifest)


def _validate_external_register_fields(slug: str, manifest: dict[str, Any]) -> None:
    """F6 T1（D68）：source_type=external-register 的 manifest 强制 4 字段并校验取值。

    与 F4 包级 trust_level 严格区分：来源信任级字段名为 ``agent_trust_level``（GATE D33.d）。
    """
    missing = [f for f in EXTERNAL_REGISTER_REQUIRED_FIELDS if f not in manifest]
    if missing:
        raise ValueError(
            f"{slug} source_type=external-register requires fields: {', '.join(missing)}"
        )
    spec = manifest.get("runtime_spec_version")
    if spec not in EXTERNAL_REGISTER_SPEC_VERSIONS:
        raise ValueError(
            f"{slug} runtime_spec_version must be in {sorted(EXTERNAL_REGISTER_SPEC_VERSIONS)}, got {spec!r}"
        )
    if not str(manifest.get("agent_yaml_ref") or "").strip():
        raise ValueError(f"{slug} agent_yaml_ref must be a non-empty reference")
    trust = manifest.get("agent_trust_level")
    if trust not in EXTERNAL_REGISTER_TRUST_LEVELS:
        raise ValueError(
            f"{slug} agent_trust_level must be in {sorted(EXTERNAL_REGISTER_TRUST_LEVELS)} "
            f"(platform 仅限 builtin), got {trust!r}"
        )
    if not isinstance(manifest.get("workspace_required"), bool):
        raise ValueError(f"{slug} workspace_required must be a boolean")
