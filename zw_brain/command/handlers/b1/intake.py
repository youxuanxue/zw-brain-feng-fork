"""B1.2 intake handlers — F4 capability.package.* 后端扩展.

3 个新 cap：
  - package.rollback：能力包版本回滚（write-critical, human_confirmation_required）
  - package.exposure.matrix.query：暴露矩阵只读查询（read-sensitive, sanitized
    meta-audit；不重新计算 manifest 内容，直接派生 compatibility / product_scope
    / execution_binding 三字段）
  - package.trust_level.update：能力包内置 trust_level 升降级（write-critical）
    **本字段语义边界**：F4 业务字段（baseline / reviewed / restricted / revoked），
    描述「平台对能力包信任评估」；与 F6 T1 触发的 AgentRuntime Registry
    trust_level（描述「外部 Agent 来源信任级」）**不是同一字段**。本 F4 不动
    Registry 字段。

handlers/b1/capability_admin.py 已承担 12 个旧 cap（register/review/version/
exposure/enable/disable/policy/list/view），本模块只补 3 个 F4 新 cap，零重复
旧逻辑。
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import zw_brain.shared.audit as audit_bus
from zw_brain.capability_registry.runtime import (
    PACKAGE_TRUST_LEVELS,
    load_manifests,
    package_trust_levels,
    validate_package_lifecycle_transition,
)
from zw_brain.command.brain import BrainServiceError, InvalidStateError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.policy import DomainAccessDeniedError, tenant_for_role
from zw_brain.shared.runtime_tenant import (
    get_runtime_tenant_id,
)

# ──────────────────────────────────────────────────────────────────────────
# package.rollback —— 写敏感，走 deps.write（自动 audit_required=true）
# ──────────────────────────────────────────────────────────────────────────


def _rollback_package(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    package_id = str(payload["package_id"])
    item = deps.view.packages.find_by_id(package_id)
    current_version = item.get("registeredVersion") or item.get("version")
    target_version = str(payload.get("target_version") or item.get("rollbackTarget") or "")
    if not target_version:
        raise InvalidStateError(
            f"package {package_id} has no rollbackTarget recorded; explicit target_version required"
        )
    if current_version == target_version:
        raise InvalidStateError(
            f"package {package_id} active version already at {target_version}; rollback is a no-op"
        )

    current_status = item.get("status", "active")
    # 状态机校验：active → rolled-back 是合法迁移；其他 from 状态走分支
    target_state = "rolled-back" if current_status == "active" else current_status
    if current_status == "active":
        validate_package_lifecycle_transition(current_status, target_state)

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        item["registeredVersion"] = target_version
        item["status"] = target_state
        item["rollbackTarget"] = current_version
        item["lastRollbackAt"] = datetime.now(UTC).isoformat()
        item["lastRollbackReason"] = str(payload.get("reason") or "")
        item.setdefault("aiReview", {})
        item["aiReview"]["summary"] = (
            f"已回滚到 {target_version}；上一活跃版本 {current_version} 入 rollbackTarget。"
        )
        store = deps.state_store.database_store
        if store is not None and hasattr(store, "capability_package_repo"):
            deps.repos.capability_package.upsert_from_package(item)
        deps.append_audit_feed("package.rollback", package_id, "ok", actor)
        return {
            "package_id": package_id,
            "previous_version": current_version or "",
            "rolled_back_to": target_version,
            "rollback_at": item["lastRollbackAt"],
        }

    return deps.write(ctx, payload, mutation)


def handler_package_rollback(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _rollback_package(brain, deps, ctx, payload)


# ──────────────────────────────────────────────────────────────────────────
# package.trust_level.update —— 写敏感，走 deps.write
# ──────────────────────────────────────────────────────────────────────────


def _update_package_trust_level(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    package_id = str(payload["package_id"])
    target_trust = str(payload["trust_level"])
    if target_trust not in package_trust_levels():
        raise BrainServiceError(
            f"trust_level must be one of {list(PACKAGE_TRUST_LEVELS)}; got {target_trust!r}"
        )

    item = deps.view.packages.find_by_id(package_id)
    previous_trust = str(item.get("trustLevel") or "baseline")
    if previous_trust == target_trust:
        raise InvalidStateError(
            f"package {package_id} trustLevel already {target_trust}; no-op"
        )

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        item["trustLevel"] = target_trust
        item["lastTrustLevelChangeAt"] = datetime.now(UTC).isoformat()
        item["lastTrustLevelReason"] = str(payload.get("reason") or "")
        item.setdefault("aiReview", {})
        item["aiReview"]["summary"] = (
            f"能力包内置 trust_level: {previous_trust} → {target_trust}（业务字段，"
            f"与 AgentRuntime Registry trust_level 不同；F6 触发前 Registry 不存在）。"
        )
        store = deps.state_store.database_store
        if store is not None and hasattr(store, "capability_package_repo"):
            deps.repos.capability_package.upsert_from_package(item)
        deps.append_audit_feed("package.trust_level.update", package_id, "ok", actor)
        return {
            "package_id": package_id,
            "previous_trust_level": previous_trust,
            "new_trust_level": target_trust,
            "updated_at": item["lastTrustLevelChangeAt"],
        }

    return deps.write(ctx, payload, mutation)


def handler_package_trust_level_update(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _update_package_trust_level(brain, deps, ctx, payload)


# ──────────────────────────────────────────────────────────────────────────
# package.exposure.matrix.query —— 只读，handler 自己写 sanitized meta-audit
# ──────────────────────────────────────────────────────────────────────────


def _enforce_tenant_scope(payload: dict[str, Any]) -> str:
    role = payload.get("role")
    runtime_tenant = tenant_for_role(str(role)) if role else get_runtime_tenant_id()
    requested = payload.get("tenant_id")
    if requested is None or requested == "":
        return runtime_tenant
    requested_str = str(requested)
    if requested_str != runtime_tenant:
        raise DomainAccessDeniedError(
            f"tenant scope violation for package.exposure.matrix.query: requested={requested_str}, runtime={runtime_tenant}"
        )
    return requested_str


def _param_hash(params: dict[str, Any]) -> str:
    serializable = {k: v for k, v in sorted(params.items()) if v is not None and v != ""}
    body = json.dumps(serializable, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(body.encode("utf-8")).hexdigest()


def _emit_meta_audit(
    *,
    skill_id: str,
    payload: dict[str, Any],
    tenant_id: str,
    param_hash: str,
    result_count: int,
) -> None:
    role = str(payload.get("role") or "ROLE_BUSIAUDIT")
    actor = f"user:gov:{role}:intake-meta"
    request_id = f"AUDIT-META-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}-{param_hash[:8]}"
    audit_bus.emit(
        audit_bus.AuditEvent(
            request_id=request_id,
            actor=actor,
            skill_id=skill_id,
            phase="commit",
            payload={
                "param_hash": param_hash,
                "result_count": int(result_count),
                "skill_id": skill_id,
            },
            tenant_id=tenant_id,
            audit_class="read-sensitive",
            event_type="package_intake_query",
        )
    )


def _matrix_row_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    product_scope = manifest.get("product_scope") or {}
    return {
        "skill_id": manifest["slug"],
        # 人话名 + 说明：238 manifest 全部自带 title/description；投影出来让 UI 去 slug、上人话
        # （现场反馈：开放范围全是技术术语看不懂）。仍只读 manifest，不重算。
        "name": str(manifest.get("title") or manifest.get("name") or ""),
        "description": str(manifest.get("description") or manifest.get("summary") or ""),
        "journey": str(product_scope.get("journey") or ""),
        "status": str(product_scope.get("status") or ""),
        "execution_binding": str(manifest.get("execution_binding") or ""),
        "audit_class": str(manifest.get("audit_class") or ""),
        "surfaces": list(manifest.get("compatibility") or []),
        "human_confirmation_required": bool(manifest.get("human_confirmation_required") or False),
        # 能力包内置 trust_level（manifest 字段；缺省 baseline）；与 AgentRuntime
        # Registry trust_level（F6 触发）不是同一字段。
        "trust_level": str(manifest.get("trust_level") or "baseline"),
    }


def handler_package_exposure_matrix_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    """F4 package.exposure.matrix.query —— 只读 manifest × 5 消费面暴露矩阵。

    投影派生自 zw_brain/capability_registry/registered/*.json，不复制 manifest
    内容；handler 自身写 sanitized meta-audit（与 F2/F3 同 pattern）。
    """
    tenant_id = _enforce_tenant_scope(payload)
    journey = payload.get("journey")
    status = payload.get("status")
    execution_binding = payload.get("execution_binding")
    surface = payload.get("surface")
    limit_raw = payload.get("limit")
    limit = int(limit_raw) if limit_raw is not None else 500

    all_manifests = load_manifests()
    rows: list[dict[str, Any]] = []
    by_surface: dict[str, int] = {}
    by_journey: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_binding: dict[str, int] = {}
    for skill_id_key in sorted(all_manifests):
        manifest = all_manifests[skill_id_key]
        row = _matrix_row_from_manifest(manifest)
        if journey is not None and row["journey"] != str(journey):
            continue
        if status is not None and row["status"] != str(status):
            continue
        if execution_binding is not None and row["execution_binding"] != str(execution_binding):
            continue
        if surface is not None and str(surface) not in row["surfaces"]:
            continue
        rows.append(row)
        for s in row["surfaces"]:
            by_surface[s] = by_surface.get(s, 0) + 1
        by_journey[row["journey"]] = by_journey.get(row["journey"], 0) + 1
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
        by_binding[row["execution_binding"]] = by_binding.get(row["execution_binding"], 0) + 1

    scanned = len(rows)
    if limit and limit > 0:
        rows = rows[:limit]

    fingerprint = _param_hash(
        {
            "tenant_id": tenant_id,
            "journey": journey,
            "status": status,
            "execution_binding": execution_binding,
            "surface": surface,
            "limit": limit,
        }
    )
    _emit_meta_audit(
        skill_id=skill_id,
        payload=payload,
        tenant_id=tenant_id,
        param_hash=fingerprint,
        result_count=scanned,
    )

    return {
        "matrix": rows,
        "totals": {
            "manifests": len(all_manifests),
            "by_surface": by_surface,
            "by_journey": by_journey,
            "by_status": by_status,
            "by_execution_binding": by_binding,
        },
        "scanned": scanned,
    }


__all__ = (
    "handler_package_rollback",
    "handler_package_trust_level_update",
    "handler_package_exposure_matrix_query",
)
