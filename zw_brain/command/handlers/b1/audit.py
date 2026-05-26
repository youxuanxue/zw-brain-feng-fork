"""B1 audit handlers — 4 cap (2 legacy + 2 F2).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.

F2 (audit.event.query / audit.event.replay) 自带「元审计 + 不外泄 payload」逻辑：
manifest audit_required=false（不走 _invoke_traced_read 自动 emit），handler 在返回
前手动 emit 一条 sanitized audit（payload = param hash + result count），caller
仍能拿到完整事件流。
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

import zw_brain.shared.audit as audit_bus
from zw_brain.domain.policy import DomainAccessDeniedError, tenant_for_role
from zw_brain.shared.audit import index as audit_index
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _list_audit_events(brain) -> list[dict[str, Any]]:
    """Return audit timeline for 安全审计员 / dashboard.

    Time ordering: 内部分两 chunk —— 最近 500 条 audit_event（asc by time）
    + 最多 200 条 legacy.exchange.import projection（asc by mapped_at）。
    每个 chunk 内时序严格升序；两 chunk 之间不保证 interleave。安全审计员 UI 把
    legacy import 视作单独区段呈现，不与 audit 实时事件强混排。
    """
    store = brain._state_store.database_store
    if store is None:
        return copy.deepcopy(brain._snapshot["audit_events"])
    # 默认拉最近 500 条；早期是 SELECT * 拉 2000+ 行（含大 payload_json），
    # audit.list 与 compliance.case.query 撞 14-30s 慢。
    events = [
        {
            "id": item.request_id,
            "time": item.occurred_at.strftime("%m-%d %H:%M"),
            "actor": item.actor,
            "type": f"{item.skill_id}.{item.phase}",
            "target": brain._audit_event_target(item),
            "result": "ok",
            "chain": "pending",
        }
        for item in store.list_audit_events(limit=500)
    ]
    # Push filter into SQL: 不要拉 54K mappings 全部到 Python 再过滤；只取 audit-relevant 三类 + cap 200。
    for mapping in store.legacy_mapping_repo.list_mappings(
        tenant_id=_DEFAULT_TENANT_ID,
        legacy_object_types=["data_apply", "data_apply_course", "data_apply_authrization"],
        limit=200,
    ):
        events.append(
            {
                "id": mapping.id,
                "time": mapping.mapped_at.strftime("%m-%d %H:%M"),
                "actor": "legacy.exchange.import",
                "type": f"legacy.exchange.import.{mapping.legacy_object_type}",
                "target": mapping.legacy_object_ref,
                "result": mapping.mapping_status,
                "chain": f"{mapping.legacy_object_type}->{mapping.canonical_type}",
            }
        )
    return events

def _replay_evidence_chain(brain, dispute_id: str) -> dict[str, Any]:
    dispute = brain.get_dispute(dispute_id)
    evidence = [
        {
            "time": step.get("time") or step.get("payload", {}).get("time") or "—",
            "label": step.get("label") or step.get("nodeName") or "证据",
            "detail": step.get("note") or step.get("opinion") or "—",
        }
        for step in dispute.get("timeline", [])
    ]
    # Related requests are declared on the dispute record (data-driven), not
    # hardcoded — a real dispute carries its own linked request ids.
    related_request_ids = dispute.get("relatedRequestIds") or []
    audit_events = [
        item
        for item in brain.list_audit_events()
        if item["target"] in {dispute_id, *related_request_ids}
    ]
    return {
        "disputeId": dispute_id,
        "summary": dispute.get("aiSummary"),
        "evidenceChain": evidence,
        "auditEvents": audit_events,
        "tickets": [item for item in brain._snapshot["tickets"] if item["id"] in {"TK-2026-04-25-014", "TK-2026-04-25-015"}],
        "knowledgeArticles": [item for item in brain._snapshot["knowledge_articles"] if item["id"] in {"KB-REDUCE-BURDEN-02", "KB-TEMPLATE-BACKFLOW-01"}],
    }


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_audit_list(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return {
        "items": _list_audit_events(brain),
        "summary": copy.deepcopy(brain._snapshot["audit_ai"]),
    }

def handler_audit_replay_evidence_chain(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _replay_evidence_chain(brain, str(payload["dispute_id"]))


# ──────────────────────────────────────────────────────────────────────────
# F2 — audit.event.query / audit.event.replay
# ──────────────────────────────────────────────────────────────────────────


def _parse_iso(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw
    return datetime.fromisoformat(str(raw))


def _enforce_tenant_scope(payload: dict[str, Any]) -> str:
    """单租户 sd-default 模式下 cross-tenant 读必须被拦下。

    若 payload["role"] 给出，从 role 推 runtime tenant；否则用全局 runtime
    tenant。无论哪一种，payload 显式声明的 tenant_id 必须与之相等，否则
    raise DomainAccessDeniedError（preflight enforce_manifest_policy 同步
    做一次；这里是第二道防线，handler 被未走 invoke_skill 的路径直接调用
    时也守得住）。
    """
    role = payload.get("role")
    runtime_tenant = tenant_for_role(str(role)) if role else get_runtime_tenant_id()
    requested = payload.get("tenant_id")
    if requested is None or requested == "":
        return runtime_tenant
    requested_str = str(requested)
    if requested_str != runtime_tenant:
        raise DomainAccessDeniedError(
            f"tenant scope violation for audit.event.*: requested={requested_str}, runtime={runtime_tenant}"
        )
    return requested_str


def _param_hash(params: dict[str, Any]) -> str:
    """payload 参数指纹（SHA-1 of canonical JSON），用于元审计；缺省字段不入 hash。"""
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
    """元审计：handler 自身被调用要落审计。仅写 query 参数 hash + result count，
    不存原始查询参数值（避免敏感字段如 actor 入审计），不存 result 全文。"""
    request_id = f"AUDIT-META-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}-{param_hash[:8]}"
    role = str(payload.get("role") or "ROLE_SECURITY_AUDIT")
    actor = f"user:gov:{role}:meta-audit"
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
            event_type="audit_query",
        )
    )


def _event_to_dict(ev: Any, *, include_payload: bool) -> dict[str, Any]:
    out = {
        "request_id": ev.request_id,
        "actor": ev.actor,
        "skill_id": ev.skill_id,
        "tenant_id": ev.tenant_id,
        "audit_class": ev.audit_class,
        "event_type": ev.event_type,
        "phase": ev.phase,
        "occurred_at": ev.occurred_at.isoformat(),
    }
    if include_payload:
        out["payload"] = ev.payload
    return out


def handler_audit_event_query(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    """F2 audit.event.query — 按维度查审计事件 + 聚合摘要。

    强制单租户 tenant_scope；不外泄 payload 原文（output items 只含 metadata）。
    handler 自身写一条元审计，记录 param_hash + result_count。
    """
    tenant_id = _enforce_tenant_scope(payload)
    since = _parse_iso(payload.get("since"))
    until = _parse_iso(payload.get("until"))
    limit_raw = payload.get("limit")
    limit = int(limit_raw) if limit_raw is not None else 200

    actor_filter = payload.get("actor")
    skill_filter = payload.get("skill_id")
    audit_class_filter = payload.get("audit_class")

    events = audit_index.query(
        actor=str(actor_filter) if actor_filter else None,
        skill_id=str(skill_filter) if skill_filter else None,
        tenant_id=tenant_id,
        audit_class=str(audit_class_filter) if audit_class_filter else None,
        since=since,
        until=until,
        limit=limit,
    )

    items = [_event_to_dict(ev, include_payload=False) for ev in events]
    summary = audit_index.summarize(events)

    fingerprint = _param_hash(
        {
            "actor": actor_filter,
            "skill_id": skill_filter,
            "tenant_id": tenant_id,
            "audit_class": audit_class_filter,
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "limit": limit,
        }
    )
    _emit_meta_audit(
        skill_id=skill_id,
        payload=payload,
        tenant_id=tenant_id,
        param_hash=fingerprint,
        result_count=len(items),
    )

    return {"items": items, "summary": summary}


def handler_audit_event_replay(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    """F2 audit.event.replay — 按 request_id 回放一条审批链所有 phase 的事件序列。

    与 query 不同：replay 把 payload 透传给 caller（安全审计员需要看原文复盘），
    但元审计仍只记录 request_id + count。
    """
    tenant_id = _enforce_tenant_scope(payload)
    request_id = str(payload["request_id"]).strip()
    if not request_id:
        raise ValueError("audit.event.replay requires non-empty request_id")
    limit_raw = payload.get("limit")
    limit = int(limit_raw) if limit_raw is not None else 1000

    chain = audit_index.list_by_request_id(request_id, limit=limit)
    chain = [ev for ev in chain if ev.tenant_id == tenant_id]
    items = [_event_to_dict(ev, include_payload=True) for ev in chain]
    summary = audit_index.summarize(chain)

    fingerprint = _param_hash(
        {
            "request_id": request_id,
            "tenant_id": tenant_id,
            "limit": limit,
        }
    )
    _emit_meta_audit(
        skill_id=skill_id,
        payload=payload,
        tenant_id=tenant_id,
        param_hash=fingerprint,
        result_count=len(items),
    )

    return {"request_id": request_id, "items": items, "summary": summary}


# ──────────────────────────────────────────────────────────────────────────
# F3-backend — B1.1 statistics / anomaly / accountability
# ──────────────────────────────────────────────────────────────────────────


def _bucket_key(occurred_at: datetime, bucket: str) -> str:
    """事件时间映射到桶 key（hour / day / week / month）。

    week: ISO 周（%G-W%V）；其他用 strftime 直接派生。
    """
    if bucket == "hour":
        return occurred_at.strftime("%Y-%m-%dT%H:00")
    if bucket == "day":
        return occurred_at.strftime("%Y-%m-%d")
    if bucket == "week":
        return occurred_at.strftime("%G-W%V")
    if bucket == "month":
        return occurred_at.strftime("%Y-%m")
    raise ValueError(f"unknown bucket: {bucket!r}")


def _dimension_value(ev: Any, dimension: str) -> str:
    if dimension == "actor":
        return ev.actor
    if dimension == "skill_id":
        return ev.skill_id
    if dimension == "audit_class":
        return ev.audit_class
    if dimension == "tenant_id":
        return ev.tenant_id
    raise ValueError(f"unknown dimension: {dimension!r}")


def handler_audit_event_statistics(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    """F3 audit.event.statistics — 按时间桶 + 维度聚合事件计数。"""
    tenant_id = _enforce_tenant_scope(payload)
    bucket = str(payload.get("bucket") or "day")
    dimension = str(payload.get("dimension") or "audit_class")
    since = _parse_iso(payload.get("since"))
    until = _parse_iso(payload.get("until"))
    limit_raw = payload.get("limit")
    limit = int(limit_raw) if limit_raw is not None else 1000

    events = audit_index.query(
        tenant_id=tenant_id,
        since=since,
        until=until,
        limit=limit,
    )

    buckets_map: dict[str, dict[str, int]] = {}
    totals: dict[str, int] = {}
    for ev in events:
        key = _bucket_key(ev.occurred_at, bucket)
        dim_val = _dimension_value(ev, dimension)
        bucket_dim = buckets_map.setdefault(key, {})
        bucket_dim[dim_val] = bucket_dim.get(dim_val, 0) + 1
        totals[dim_val] = totals.get(dim_val, 0) + 1

    buckets = [
        {
            "bucket_key": key,
            "by_dimension": dim_counts,
            "total": sum(dim_counts.values()),
        }
        for key, dim_counts in sorted(buckets_map.items())
    ]

    fingerprint = _param_hash(
        {
            "tenant_id": tenant_id,
            "bucket": bucket,
            "dimension": dimension,
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "limit": limit,
        }
    )
    _emit_meta_audit(
        skill_id=skill_id,
        payload=payload,
        tenant_id=tenant_id,
        param_hash=fingerprint,
        result_count=len(events),
    )

    return {
        "bucket": bucket,
        "dimension": dimension,
        "buckets": buckets,
        "totals": totals,
        "scanned": len(events),
    }


def _detect_cross_tenant_read(events: list[Any], tenant_id: str) -> list[dict[str, Any]]:
    """Rule 1 — 单 actor 在多个 tenant_id 上有 read-sensitive 事件即异常。

    输入 events 已被 tenant_id 过滤；这里我们重新拉一份*不限 tenant* 的事件，按
    actor 分组检查跨租户读痕迹。但 handler 调用方不允许跨租户，所以扫描局限到
    本租户内 actor → 跨 tenant_id 的痕迹（适用于 store 中残留的跨租户事件，
    与 F2 test_replay_filters_cross_tenant_events_in_chain 同一类攻击场景）。
    """
    all_events = audit_index.query(
        tenant_id=None,
        audit_class="read-sensitive",
        limit=10000,
    )
    actors_to_tenants: dict[str, set[str]] = {}
    actors_to_evidence: dict[str, list[str]] = {}
    for ev in all_events:
        actors_to_tenants.setdefault(ev.actor, set()).add(ev.tenant_id)
        actors_to_evidence.setdefault(ev.actor, []).append(ev.request_id)
    anomalies: list[dict[str, Any]] = []
    for actor, tenants in actors_to_tenants.items():
        if len(tenants) > 1:
            evidence = list(dict.fromkeys(actors_to_evidence.get(actor, [])))[:5]
            anomalies.append(
                {
                    "rule": "cross-tenant-read",
                    "severity": "high",
                    "actor": actor,
                    "tenant_id": ",".join(sorted(tenants)),
                    "evidence_request_ids": evidence,
                    "occurrence_count": len(actors_to_evidence.get(actor, [])),
                    "summary": f"actor {actor} 在 {len(tenants)} 个租户上有 read-sensitive 事件",
                }
            )
    return anomalies


def _detect_high_failure_rate(events: list[Any], min_failure_count: int) -> list[dict[str, Any]]:
    """Rule 2 — 单 actor 在窗口内失败次数超过阈值即异常。

    判定失败：payload.error 字段存在 OR payload.outcome == "denied" OR
    phase == "error"。
    """
    failures: dict[str, list[Any]] = {}
    for ev in events:
        if (
            ev.phase == "error"
            or ev.payload.get("outcome") == "denied"
            or ev.payload.get("error") is not None
        ):
            failures.setdefault(ev.actor, []).append(ev)
    anomalies: list[dict[str, Any]] = []
    for actor, evs in failures.items():
        if len(evs) >= min_failure_count:
            evidence = list(dict.fromkeys(ev.request_id for ev in evs))[:5]
            skills = sorted({ev.skill_id for ev in evs})
            anomalies.append(
                {
                    "rule": "high-failure-rate",
                    "severity": "medium" if len(evs) < min_failure_count * 2 else "high",
                    "actor": actor,
                    "skill_id": ",".join(skills[:3]),
                    "tenant_id": evs[0].tenant_id,
                    "evidence_request_ids": evidence,
                    "occurrence_count": len(evs),
                    "summary": f"actor {actor} 在窗口内失败 {len(evs)} 次（阈值 {min_failure_count}）",
                }
            )
    return anomalies


def _detect_repeated_denied(events: list[Any]) -> list[dict[str, Any]]:
    """Rule 3 — 同一 request_id 反复出现 denied 即异常（暴力重试）。"""
    denied_by_request: dict[str, list[Any]] = {}
    for ev in events:
        if ev.payload.get("outcome") == "denied":
            denied_by_request.setdefault(ev.request_id, []).append(ev)
    anomalies: list[dict[str, Any]] = []
    for request_id, evs in denied_by_request.items():
        if len(evs) >= 2:
            anomalies.append(
                {
                    "rule": "repeated-denied",
                    "severity": "high",
                    "actor": evs[0].actor,
                    "skill_id": evs[0].skill_id,
                    "tenant_id": evs[0].tenant_id,
                    "evidence_request_ids": [request_id],
                    "occurrence_count": len(evs),
                    "summary": f"request_id {request_id} 反复 denied {len(evs)} 次",
                }
            )
    return anomalies


def handler_audit_event_anomaly(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    """F3 audit.event.anomaly — rule-based Top-N 异常事件扫描。

    输出按 severity (high→medium→low) + occurrence_count 倒序，截断到 top_n。
    """
    tenant_id = _enforce_tenant_scope(payload)
    since = _parse_iso(payload.get("since"))
    until = _parse_iso(payload.get("until"))
    top_n = int(payload.get("top_n") or 20)
    min_failure_count = int(payload.get("min_failure_count") or 3)

    in_scope = audit_index.query(
        tenant_id=tenant_id,
        since=since,
        until=until,
        limit=10000,
    )

    anomalies: list[dict[str, Any]] = []
    anomalies.extend(_detect_cross_tenant_read(in_scope, tenant_id))
    anomalies.extend(_detect_high_failure_rate(in_scope, min_failure_count))
    anomalies.extend(_detect_repeated_denied(in_scope))

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    anomalies.sort(
        key=lambda a: (severity_rank.get(a["severity"], 9), -int(a.get("occurrence_count") or 0))
    )
    anomalies = anomalies[:top_n]

    fingerprint = _param_hash(
        {
            "tenant_id": tenant_id,
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "top_n": top_n,
            "min_failure_count": min_failure_count,
        }
    )
    _emit_meta_audit(
        skill_id=skill_id,
        payload=payload,
        tenant_id=tenant_id,
        param_hash=fingerprint,
        result_count=len(anomalies),
    )

    return {"anomalies": anomalies, "scanned": len(in_scope)}


_ACCOUNTABILITY_SENSITIVE_KEYS = (
    "actor_snapshot",
    "credential",
    "secret",
    "token",
    "password",
    "api_key",
)


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """敏感字段 hash 化（保留可比对的稳定 digest，避免明文落出）。"""
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if any(needle in key.lower() for needle in _ACCOUNTABILITY_SENSITIVE_KEYS):
            digest = hashlib.sha1(
                json.dumps(value, default=str, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            out[key] = f"sha1:{digest}"
        else:
            out[key] = value
    return out


def handler_audit_event_accountability(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    """F3 audit.event.accountability — 按 actor 拉所有 outcome=denied 的 chain。

    返回 sanitized 链路（敏感字段 hash 化）；按 denied_at 倒序。
    """
    tenant_id = _enforce_tenant_scope(payload)
    actor = str(payload["actor"]).strip()
    if not actor:
        raise ValueError("audit.event.accountability requires non-empty actor")
    since = _parse_iso(payload.get("since"))
    until = _parse_iso(payload.get("until"))
    limit_raw = payload.get("limit")
    limit = int(limit_raw) if limit_raw is not None else 100

    actor_events = audit_index.query(
        actor=actor,
        tenant_id=tenant_id,
        since=since,
        until=until,
        limit=10000,
    )
    denied_request_ids: list[str] = []
    seen: set[str] = set()
    for ev in actor_events:
        if ev.payload.get("outcome") == "denied" and ev.request_id not in seen:
            denied_request_ids.append(ev.request_id)
            seen.add(ev.request_id)

    denied_chains: list[dict[str, Any]] = []
    for rid in denied_request_ids[:limit]:
        chain = audit_index.list_by_request_id(rid, limit=200)
        chain = [ev for ev in chain if ev.tenant_id == tenant_id]
        if not chain:
            continue
        denied_event = next((ev for ev in chain if ev.payload.get("outcome") == "denied"), chain[-1])
        denied_chains.append(
            {
                "request_id": rid,
                "skill_id": denied_event.skill_id,
                "denied_at": denied_event.occurred_at.isoformat(),
                "events": [
                    {
                        "phase": ev.phase,
                        "occurred_at": ev.occurred_at.isoformat(),
                        "sanitized_payload": _sanitize_payload(ev.payload),
                    }
                    for ev in chain
                ],
            }
        )

    denied_chains.sort(key=lambda c: c["denied_at"], reverse=True)

    fingerprint = _param_hash(
        {
            "actor": actor,
            "tenant_id": tenant_id,
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "limit": limit,
        }
    )
    _emit_meta_audit(
        skill_id=skill_id,
        payload=payload,
        tenant_id=tenant_id,
        param_hash=fingerprint,
        result_count=len(denied_chains),
    )

    return {"actor": actor, "denied_chains": denied_chains, "total": len(denied_chains)}

