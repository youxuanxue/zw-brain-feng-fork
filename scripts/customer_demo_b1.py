#!/usr/bin/env python3
"""F8 B1 30 分钟客户演示 — 端到端跑通 B1.1 合规审计 + B1.2 接入扩展中心.

按 e4-b1-agentruntime core_goal: ROLE_SECURITY_AUDIT + ROLE_SYSTEM 在 30 分钟
内 sd-default 真实数据 + 合成审计事件 上跑通：
  B1.1 四 panel (statistics / anomaly / accountability / investigation_summary)
  B1.2 能力包 lifecycle (review → enable → exposure_matrix → trust_level → rollback)

实际执行不依赖 REST server，直接通过 BrainService.invoke_skill 驱动 dispatch；
真实数据来自 ZW_BRAIN_DATABASE_URL 指向的 PostgreSQL 库 (sd-default tenant)，
需先用 scripts.build_realistic_pg_template 灌入真实旧平台数据（或 pytest 下由
realistic_pg_module 克隆 zw_realistic_tmpl）。

B1.2 写类 skill 走 build_trusted_skill_payload trust-stamp 路径（生产 BFF 行为）。
B1.1 投影读 skill 直接 invoke（payload 带 role 即可）。

Exit code: 0 = 全链路成功；非 0 = 任一步失败。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parent.parent
TENANT = "sd-default"

DEFAULT_BUDGET_SECONDS = 30 * 60

BAD_ACTOR = "user:gov:ROLE_ORGAN_OPERATER:bad_user"
DEMO_PACKAGE_ID = "PKG-DEMO-B1-001"


def _log(step: str, msg: str = "", **kv) -> None:
    extras = " ".join(f"{k}={v}" for k, v in kv.items()) if kv else ""
    print(f"[demo-b1] {step:<32s} {msg} {extras}".rstrip(), flush=True)


def _prepare_db() -> str:
    """Resolve the PG database the demo runs against and clear stale engines.

    Full-PG migration: runtime + audit both live in the single
    ``ZW_BRAIN_DATABASE_URL`` database (per-test clone under pytest, or a库
    seeded by scripts.build_realistic_pg_template for ops/demo). No file copy,
    no shadow DB, no ZW_BRAIN_DB_PATH/AUDIT_DB_PATH — those SQLite-era knobs are
    retired. Returns the resolved URL for downstream coverage verification.
    """
    from zw_brain.shared import db as _db

    url = _db.get_database_url()  # fail-closed if it ever resolves to sqlite
    _db.reset_engine_cache()
    return url


def _build_brain():
    """走 runtime.get_service() 拿到生产多路 sink（AuditStore + DatabaseStore），
    与 BFF 入口行为一致；B1.1 anomaly 依赖 AuditStore 索引才能查到合成事件。"""
    from zw_brain.command import runtime as runtime_mod
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.audit import store as audit_store_mod

    audit_store_mod.set_default_store(None)
    runtime_mod._service = None
    audit_bus.clear_sink()
    audit_bus.drain()
    return runtime_mod.get_service()


def _invoke(brain, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    out = brain.invoke_skill(skill_id, payload)
    if isinstance(out, dict) and "result" in out and "audit_id" in out:
        return out["result"]
    return out


def _invoke_trusted(brain, skill_id: str, client_payload: dict[str, Any], *, role: str) -> dict[str, Any]:
    from zw_brain.shared.session_context import build_trusted_skill_payload
    snapshot = {
        "tenant_id": TENANT,
        "actor": f"demo-b1:{role.lower()}",
        "org_code": "ORG-DEMO-B1",
        "current_org_code": "ORG-DEMO-B1",
        "current_role": role,
        "role_codes": [role],
        "available_contexts": [{"org_code": "ORG-DEMO-B1", "role_code": role, "actor_tags": {}}],
        "actor_tags": {},
    }
    payload = build_trusted_skill_payload(client_payload, actor_snapshot=snapshot)
    out = brain.invoke_skill(skill_id, payload)
    if isinstance(out, dict) and "result" in out and "audit_id" in out:
        return out
    return {"ok": True, "result": out}


def _demo_package_by_id(brain, package_id: str) -> dict[str, Any]:
    """Live snapshot ref for demo state tweaks (Action E retired BrainService._package_by_id)."""
    return brain._get_handler_deps().view.packages.find_by_id(package_id)


def _seed_audit_events() -> None:
    """合成 4 类共 13 条审计事件供 B1.1 4 panel 演示——不依赖任何 J1/J2 演示先跑。

    覆盖 anomaly handler 中 high-failure-rate + repeated-denied 两规则；第 3 规则
    cross-tenant-read 需跨租户事件，本 demo 不演示（演示场景在单租户 sd-default 内）。
    """
    import zw_brain.shared.audit as audit_bus

    def _emit(*, request_id, actor, skill_id, phase, audit_class="write-critical", payload=None):
        audit_bus.emit(
            audit_bus.AuditEvent(
                request_id=request_id,
                actor=actor,
                skill_id=skill_id,
                phase=phase,
                payload=payload or {},
                tenant_id=TENANT,
                audit_class=audit_class,
                event_type="capability_call",
            )
        )

    # (a) 4 次 write-critical commit (供 statistics)
    for i in range(4):
        _emit(request_id=f"REQ-DEMO-OK-{i}", actor=f"normal-actor-{i % 2}",
              skill_id="application.grant.approve", phase="commit")

    # (b) 4 次 high-failure-rate denied (供 anomaly)
    for i in range(4):
        _emit(request_id=f"REQ-DEMO-FAIL-{i}", actor=BAD_ACTOR,
              skill_id="application.resource.review", phase="error",
              payload={"error": "DomainAccessDeniedError"})

    # (c) 3 次 repeated-denied 同 request_id (供 anomaly 第 2 规则)
    for i in range(3):
        _emit(request_id="REQ-DEMO-DENY-LOOP", actor=BAD_ACTOR,
              skill_id="application.grant.approve", phase="error",
              payload={"outcome": "denied", "attempt": i})

    # (d) 2 次 accountability 链 (含敏感字段，验脱敏)
    secret = "AKIA-DEMO-SECRET-DO-NOT-LEAK"
    _emit(request_id="REQ-DEMO-DENY-CRED", actor=BAD_ACTOR,
          skill_id="application.grant.approve", phase="error",
          payload={"outcome": "denied", "reason": "rbac", "credential": secret})
    _emit(request_id="REQ-DEMO-DENY-API", actor=BAD_ACTOR,
          skill_id="application.grant.revoke", phase="error",
          payload={"outcome": "denied", "api_key": secret})


def _seed_demo_package(brain) -> None:
    """直接 snapshot 注入一个 draft 状态能力包；review/enable/rollback 都拿它演示."""
    package = {
        "id": DEMO_PACKAGE_ID,
        "slug": "demo-b1",
        "source": "zw-brain registry",
        "status": "pending",
        "versionStatus": "draft",
        "registeredVersion": "v1.2.0",
        "rollbackTarget": "v1.1.0",
        "exposure": ["api", "webui"],
        "auditClass": "read-normal",
        "desc": "F8 客户演示能力包",
        "trustLevel": "baseline",
        "aiReview": {"summary": "stub", "missing": [], "safe": [], "draft": ""},
        "contract": {},
        "tenantPolicy": {"scope": "tenant-bound"},
        "failureWriteback": {"target": "audit_event"},
        "runtimeBinding": {"protocol": "brain_service"},
    }
    brain._snapshot.setdefault("capability_packages", []).append(package)


# ──────────────────────────────────────────────────────────────────────
# Demo 链路
# ──────────────────────────────────────────────────────────────────────


def run_demo() -> dict[str, Any]:

    started = time.monotonic()
    db_url = _prepare_db()
    _log("STEP-0", "准备 PG 库", database=make_url(db_url).render_as_string(hide_password=True))
    brain = _build_brain()

    # ── B1.1 SEGMENT — 审计 4 panel ────────────────────────────────────
    _log("STEP-1.B11", "seed 合成审计事件（4 ok + 4 high-fail + 3 deny-loop + 2 accountability）")
    _seed_audit_events()

    _log("STEP-2.B11", "audit.event.statistics 按 audit_class 维度 day 桶聚合")
    stats = _invoke(brain, "audit.event.statistics", {
        "bucket": "day",
        "dimension": "audit_class",
        "tenant_id": TENANT,
        "limit": 1000,
        "role": "ROLE_SECURITY_AUDIT",
    })
    if stats["scanned"] < 13:
        raise RuntimeError(f"statistics scanned 数偏低：{stats['scanned']}（应 ≥13）")

    _log("STEP-3.B11", "audit.event.anomaly 找高失败率 + repeated-denied")
    anomaly = _invoke(brain, "audit.event.anomaly", {
        "tenant_id": TENANT,
        "min_failure_count": 3,
        "top_n": 20,
        "role": "ROLE_SECURITY_AUDIT",
    })
    rules_hit = {a["rule"] for a in anomaly["anomalies"]}
    if "high-failure-rate" not in rules_hit:
        raise RuntimeError(f"anomaly 未命中 high-failure-rate；rules={rules_hit}")
    if "repeated-denied" not in rules_hit:
        raise RuntimeError(f"anomaly 未命中 repeated-denied；rules={rules_hit}")

    _log("STEP-4.B11", "audit.event.accountability 追责 + 敏感字段脱敏验证")
    account = _invoke(brain, "audit.event.accountability", {
        "actor": BAD_ACTOR,
        "tenant_id": TENANT,
        "limit": 50,
        "role": "ROLE_SECURITY_AUDIT",
    })
    flat = json.dumps(account, ensure_ascii=False)
    if "AKIA-DEMO-SECRET-DO-NOT-LEAK" in flat:
        raise RuntimeError("accountability 外泄了 credential 原文（敏感字段脱敏失效）")
    if account["total"] < 2:
        raise RuntimeError(f"accountability 拒绝链路数过低：{account['total']}（应 ≥2）")

    _log("STEP-5.B11", "assistant.investigation_summary — 推理回落规则摘要")
    summary = _invoke(brain, "assistant.investigation_summary", {
        "panel": "anomaly",
        "panel_payload": anomaly,
        "request_id": f"DEMO-B1-INV-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}",
        "tenant_id": TENANT,
        "max_tokens": 400,
        "role": "ROLE_SECURITY_AUDIT",
    })
    if not summary["summary"]:
        raise RuntimeError("investigation_summary 返回空摘要")
    summary_model = summary["model"]

    # ── B1.2 SEGMENT — 能力包 lifecycle ───────────────────────────────
    _log("STEP-6.B12", f"seed 演示能力包 {DEMO_PACKAGE_ID} draft→pending")
    _seed_demo_package(brain)

    _log("STEP-7.B12", "package.review_decide approve → status=approved")
    review = _invoke_trusted(brain, "package.review_decide",
        {"package_id": DEMO_PACKAGE_ID, "decision": "approve", "confirmed": True},
        role="ROLE_SYSTEM")
    if not review["ok"]:
        raise RuntimeError(f"package.review_decide 未 ok：{review}")
    pkg_after_review = _demo_package_by_id(brain, DEMO_PACKAGE_ID)
    if pkg_after_review["status"] != "approved":
        raise RuntimeError(f"review 后 status 不是 approved：{pkg_after_review['status']}")

    _log("STEP-8.B12", "tenant.capability.enable 启用到 sd-default")
    # enable 要求 versionStatus=registered；review 不会自动转，手工置位（生产路径 capability.version.submit 推进）
    pkg_after_review["versionStatus"] = "registered"
    enable = _invoke_trusted(brain, "tenant.capability.enable",
        {"package_id": DEMO_PACKAGE_ID, "tenant_id": TENANT, "confirmed": True},
        role="ROLE_SYSTEM")
    if not enable["ok"]:
        raise RuntimeError(f"tenant.capability.enable 未 ok：{enable}")

    _log("STEP-9.B12", "package.exposure.matrix.query — 200+ manifest × 5 surface 投影")
    matrix = _invoke(brain, "package.exposure.matrix.query", {
        "tenant_id": TENANT,
        "limit": 500,
        "role": "ROLE_SYSTEM",
    })
    if matrix["totals"]["manifests"] < 200:
        raise RuntimeError(f"matrix manifest 数偏低：{matrix['totals']['manifests']}（应 ≥200）")
    manifest_total = matrix["totals"]["manifests"]
    surfaces = list(matrix["totals"]["by_surface"].keys())
    _log("STEP-9.B12", f"  实测 {manifest_total} manifest × {len(surfaces)} surface")

    _log("STEP-10.B12", "package.trust_level.update baseline → reviewed")
    trust = _invoke_trusted(brain, "package.trust_level.update",
        {"package_id": DEMO_PACKAGE_ID, "trust_level": "reviewed",
         "reason": "F8 客户演示合规审核通过", "confirmed": True},
        role="ROLE_SYSTEM")
    if not trust["ok"]:
        raise RuntimeError(f"trust_level.update 未 ok：{trust}")

    _log("STEP-11.B12", "package.rollback v1.2.0 → v1.1.0")
    # rollback handler 只在 status=active 时转 rolled-back（生产是 enable 完成 →
    # capability.version.submit 把 status 推到 active 后才 rollback；演示直接置位）。
    _demo_package_by_id(brain, DEMO_PACKAGE_ID)["status"] = "active"
    rollback = _invoke_trusted(brain, "package.rollback",
        {"package_id": DEMO_PACKAGE_ID, "reason": "F8 演示版本回滚", "confirmed": True},
        role="ROLE_SYSTEM")
    if not rollback["ok"]:
        raise RuntimeError(f"package.rollback 未 ok：{rollback}")
    pkg_after_rollback = _demo_package_by_id(brain, DEMO_PACKAGE_ID)
    if pkg_after_rollback["registeredVersion"] != "v1.1.0":
        raise RuntimeError(f"rollback 后 registeredVersion 不对：{pkg_after_rollback['registeredVersion']}")
    if pkg_after_rollback["status"] != "rolled-back":
        raise RuntimeError(f"rollback 后 status 不对：{pkg_after_rollback['status']}")

    # ── 全链路 audit / capability_call 覆盖核查 ───────────────────────
    # B1 read 类 cap (audit_required=false) 走 handler 自写 meta-audit，落
    # audit_event 表；write 类 cap (audit_required=true) 走 pipeline 中间件，
    # 同时落 audit_event + capability_call 表。两表合在一起检 9 cap 全覆盖。
    write_caps = {
        "package.review_decide",
        "tenant.capability.enable",
        "package.trust_level.update",
        "package.rollback",
    }
    read_caps = {
        "audit.event.statistics",
        "audit.event.anomaly",
        "audit.event.accountability",
        "assistant.investigation_summary",
        "package.exposure.matrix.query",
    }
    required_caps = write_caps | read_caps

    # Runtime (public.capability_call) + audit (<schema>.audit_event) tables both
    # live in the single PG database now — one read-only psycopg connection
    # covers both. The audit store owns its own schema (default ``audit``, env
    # ZW_BRAIN_AUDIT_DB_PATH overrides the schema *name*), so the audit_event read
    # is schema-qualified from the store's own resolver — the unqualified
    # public.audit_event is a separate legacy runtime table without tenant_id.
    from zw_brain.shared.audit.store import _default_audit_schema

    audit_schema = _default_audit_schema()
    su = make_url(db_url)
    capability_call_skills: set[str] = set()
    capability_call_total = 0
    audit_event_skills: set[str] = set()
    with psycopg.connect(
        host=su.host, port=su.port, user=su.username,
        password=su.password, dbname=su.database,
    ) as conn:
        for row in conn.execute("SELECT skill_id FROM public.capability_call WHERE tenant_id=%s", (TENANT,)):
            capability_call_total += 1
            capability_call_skills.add(row[0])
        audit_q = (
            'SELECT DISTINCT skill_id FROM "'
            + audit_schema.replace('"', '""')
            + '".audit_event WHERE tenant_id=%s'
        )
        for row in conn.execute(audit_q, (TENANT,)):
            audit_event_skills.add(row[0])

    missing_writes = sorted(write_caps - capability_call_skills)
    if missing_writes:
        raise RuntimeError(f"全链路 capability_call 缺 write cap：{missing_writes}")
    missing_reads = sorted(read_caps - audit_event_skills)
    if missing_reads:
        raise RuntimeError(f"全链路 audit_event 缺 read cap meta-audit：{missing_reads}")

    elapsed = time.monotonic() - started
    _log("DONE", f"B1 全链路成功，{len(required_caps)} 类 capability 覆盖",
         elapsed_seconds=round(elapsed, 2),
         budget_seconds=DEFAULT_BUDGET_SECONDS)

    return {
        "ok": True,
        "elapsed_seconds": round(elapsed, 2),
        "budget_seconds": DEFAULT_BUDGET_SECONDS,
        "b11": {
            "audit_events_seeded": 13,
            "statistics_scanned": stats["scanned"],
            "anomaly_rules_hit": sorted(rules_hit),
            "accountability_chains_total": account["total"],
            "investigation_summary_model": summary_model,
        },
        "b12": {
            "package_id": DEMO_PACKAGE_ID,
            "manifest_total": manifest_total,
            "surfaces": sorted(surfaces),
            "trust_level_after": "reviewed",
            "registered_version_after_rollback": "v1.1.0",
            "status_after_rollback": "rolled-back",
        },
        "capability_call_total": capability_call_total,
        "audit_event_skills_seen": len(audit_event_skills),
        "required_caps_covered": sorted(required_caps),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="F8 B1 30 分钟客户演示验收脚本")
    parser.add_argument(
        "--report", type=Path,
        help="可选报告输出路径；演示库由 ZW_BRAIN_DATABASE_URL 指定（PG）",
    )
    args = parser.parse_args()

    try:
        result = run_demo()
    except Exception as exc:
        _log("FAIL", f"{type(exc).__name__}: {exc}")
        return 1

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        _log("REPORT", f"written {args.report}")
    if result["elapsed_seconds"] > DEFAULT_BUDGET_SECONDS:
        _log("BUDGET", f"超 30 分钟预算 ({result['elapsed_seconds']}s)")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
