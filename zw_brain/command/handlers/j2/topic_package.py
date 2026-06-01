"""J2 topic_package handlers — 9 cap migrated from BrainService (F1 turn 4).

Method bodies physically migrated; `self.` → `brain.` substitution applied. Per-cap handler
functions registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from zw_brain.command.brain import InvalidStateError, NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import topic_package as topic_package_ser
from zw_brain.domain.repositories.topic_package import TopicPackageStateError
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _configure_topic_package(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    package_code = str(payload["package_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        try:
            record = deps.repos.topic_package.configure_package(package_code, payload | {"actor_snapshot_json": {"actor": actor, "role": role}})
        except KeyError as exc:
            raise NotFoundError(package_code) from exc
        deps.append_audit_feed("topic.package.configure", package_code, "ok", actor)
        return topic_package_ser.topic_package_to_dict(record) | {"audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _transition_topic_package(brain, deps, ctx, package_code: str, next_status: str, action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        try:
            record = deps.repos.topic_package.transition_package(
                package_code,
                next_status,
                payload | {"action_type": action_type, "actor_snapshot_json": {"actor": actor, "role": role}},
            )
        except KeyError as exc:
            raise NotFoundError(package_code) from exc
        except TopicPackageStateError as exc:
            raise InvalidStateError(str(exc)) from exc
        deps.append_audit_feed(f"topic.package.{action_type}", package_code, "ok", actor)
        return topic_package_ser.topic_package_to_dict(record) | {"audit_id": audit_id}

    return deps.write(ctx, {"package_code": package_code, "next_status": next_status} | payload, mutation)

def _update_topic_package_policy(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    package_code = str(payload["package_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        try:
            records = deps.repos.topic_package.update_policy(package_code, payload | {"actor_snapshot_json": {"actor": actor, "role": role}})
        except KeyError as exc:
            raise NotFoundError(package_code) from exc
        deps.append_audit_feed("topic.package.policy.update", package_code, "ok", actor)
        return {"items": [topic_package_ser.topic_visibility_to_dict(item) for item in records], "total": len(records), "audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _subscribe_topic_package(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    package_code = str(payload["package_code"])
    subscription = {
        "visibility_code": str(
            payload.get("visibility_code")
            or f"{payload.get('org_code', '*')}:{payload.get('role_code', '*')}:{package_code}:subscription:use"
        ),
        "org_code": payload.get("org_code"),
        "role_code": payload.get("role_code"),
        "region_code": payload.get("region_code"),
        "surface": "subscription",
        "intent": "use",
        "policy_status": str(payload.get("policy_status", "pending_review")),
        "condition_json": payload.get("condition_json") or payload.get("condition") or {},
    }

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        try:
            records = deps.repos.topic_package.update_policy(
                package_code,
                payload | {"visibility": [subscription], "actor_snapshot_json": {"actor": actor, "role": role}},
            )
        except KeyError as exc:
            raise NotFoundError(package_code) from exc
        deps.append_audit_feed("topic.package.subscribe", package_code, "ok", actor)
        return {
            "package_code": package_code,
            "items": [topic_package_ser.topic_visibility_to_dict(item) for item in records],
            "total": len(records),
            "audit_id": audit_id,
        }

    return deps.write(ctx, payload, mutation)

def _attach_topic_package_evidence(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))
    package_code = str(payload["package_code"])

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        try:
            record = deps.repos.topic_package.attach_evidence(package_code, payload | {"actor_snapshot_json": {"actor": actor, "role": role}})
        except KeyError as exc:
            raise NotFoundError(package_code) from exc
        deps.append_audit_feed("topic.package.evidence.attach", package_code, "ok", actor)
        return topic_package_ser.topic_evidence_to_dict(record) | {"audit_id": audit_id}

    return deps.write(ctx, payload, mutation)

def _actor_is_subscribed(repo, package_code: str, *, role_code: str | None, visibility_records=None) -> bool:
    """当前 actor 是否已订阅该专题包：存在 subscription-surface 且 role 匹配（或通配）的可见性记录。

    诚实信号（D34.a / subscription-business-analysis）：订阅本期只是"标记关注"，
    无下游业务影响；isSubscribed 仅用于前端按钮态回显，不驱动数据供给。query 上下文只拿得到
    ctx.role（无 org），故按 role 维度判定：订阅写入的 visibility role_code 与当前 role 相符即已订阅。

    ``visibility_records`` 由列表页 batch context 预取后下传（避免每项再 list_visibility
    回查）；为 None 时回退单包查询（单包详情路径）。
    """
    records = visibility_records if visibility_records is not None else repo.list_visibility(package_code, tenant_id=_DEFAULT_TENANT_ID)
    for record in records:
        if record.surface != "subscription":
            continue
        if role_code is not None and record.role_code not in (None, role_code):
            continue
        return True
    return False


def _query_topic_packages(brain, deps, ctx, *, package_code: Any = None, status: Any = None) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    repo = deps.repos.topic_package
    actor_role = ctx.role
    if package_code:
        record = repo.get_package(str(package_code), tenant_id=_DEFAULT_TENANT_ID)
        if record is None:
            raise NotFoundError(str(package_code))
        items = [deps.services.topic_package.detail_to_dict(record)]
        for item in items:
            item["isSubscribed"] = _actor_is_subscribed(repo, str(item["package_code"]), role_code=actor_role)
    else:
        # 列表页：一次性预取（items/visibility/assets/deliveries/catalog），
        # list_projection 与 isSubscribed 全走 O(1) dict 查找，消除 per-package N+1。
        records = repo.list_packages(tenant_id=_DEFAULT_TENANT_ID, status=str(status) if status else None)
        store = deps.state_store.database_store
        ctx_batch = deps.services.topic_package.build_list_batch_context(store)
        items = [deps.services.topic_package.list_projection(record, context=ctx_batch) for record in records]
        for record, item in zip(records, items, strict=True):
            item["isSubscribed"] = _actor_is_subscribed(
                repo,
                str(item["package_code"]),
                role_code=actor_role,
                visibility_records=ctx_batch.visibility_by_package.get(record.package_code, []),
            )
    return {"items": items, "total": len(items)}

def _query_topic_package_metrics(brain, deps, ctx, *, package_code: Any = None) -> dict[str, Any]:
    deps = brain._get_handler_deps()  # Action A commit 3: bridge helper to deps.repos
    repo = deps.repos.topic_package
    packages = [repo.get_package(str(package_code))] if package_code else repo.list_packages()
    packages = [item for item in packages if item is not None]
    metrics = []
    if package_code:
        for package in packages:
            metrics.extend(topic_package_ser.topic_metric_to_dict(item) for item in repo.list_metrics(package.package_code))
    else:
        # P4 N+1 消除：一次性取全部 metric 按 package_code 分组，替代 per-package list_metrics。
        metrics_by_package: dict[str, list[Any]] = {}
        for record in repo.list_all_metrics():
            metrics_by_package.setdefault(record.package_code, []).append(record)
        for package in packages:
            metrics.extend(topic_package_ser.topic_metric_to_dict(item) for item in metrics_by_package.get(package.package_code, []))
    return {
        "items": metrics,
        "summary": {
            "package_count": len(packages),
            "published_count": sum(1 for item in packages if item.status == "published"),
            "metric_count": len(metrics),
        },
    }


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_topic_package_configure(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _configure_topic_package(brain, deps, ctx, payload)

def handler_topic_package_submit(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _transition_topic_package(brain, deps, ctx, str(payload["package_code"]), "submitted", "submit", payload)

def handler_topic_package_review(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    decision = str(payload["decision"])
    return _transition_topic_package(brain, deps, ctx, str(payload["package_code"]), "published" if decision == "approve" else "rejected", "review", payload)

def handler_topic_package_publish(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _transition_topic_package(brain, deps, ctx, str(payload["package_code"]), "published", "publish", payload)

def handler_topic_package_policy_update(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _update_topic_package_policy(brain, deps, ctx, payload)

def handler_topic_package_subscribe(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _subscribe_topic_package(brain, deps, ctx, payload)

def handler_topic_package_evidence_attach(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _attach_topic_package_evidence(brain, deps, ctx, payload)

def handler_topic_package_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_topic_packages(brain, deps, ctx, package_code=payload.get("package_code"), status=payload.get("status"))

def handler_topic_package_metric_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_topic_package_metrics(brain, deps, ctx, package_code=payload.get("package_code"))

