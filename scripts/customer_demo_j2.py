#!/usr/bin/env python3
"""F6 J2 30 分钟客户演示 — 端到端跑通 P5 提供方旅程 + 异议响应面.

按 e2-j2-journey core_goal：让 ROLE_ORGAN_OPERATER / MANAGER / BUSIAUDIT 三角色
在 30 分钟内 sd-default 真实数据上跑通：
  在线编制 → 资源挂接 (table 物化真数据) → 3 层默认审批 (F1)
  → 发布触发重复率检测 (F3) → 接收异议 → 提供方响应 → 评价归档 (F4)

实际执行不依赖 REST server，直接通过 BrainService.invoke_skill 驱动 dispatch；
真实数据来自 .data/zw_brain.db (sd-default tenant)，需先跑 M0 acceptance。

Exit code: 0 = 全链路成功；非 0 = 任一步失败。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB_DEFAULT = REPO_ROOT / ".data" / "customer-demo-j2-shadow.db"
TENANT = "sd-default"

# 30 minute budget — 演示验收脚本上限
DEFAULT_BUDGET_SECONDS = 30 * 60


def _log(step: str, msg: str = "", **kv) -> None:
    extras = " ".join(f"{k}={v}" for k, v in kv.items()) if kv else ""
    print(f"[demo-j2] {step:<32s} {msg} {extras}".rstrip(), flush=True)


def _prepare_shadow_db(seed_db: Path, shadow_db: Path) -> None:
    if not seed_db.exists():
        raise RuntimeError(f"seed db not found: {seed_db} — 请先跑 M0 acceptance")
    if shadow_db.exists():
        shadow_db.unlink()
    shadow_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(seed_db, shadow_db)
    os.environ["ZW_BRAIN_DB_PATH"] = str(shadow_db)
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
    from zw_brain.shared import db as _db
    with _db._CACHE_LOCK:
        _db._ENGINE_CACHE.clear()


def _build_brain():
    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore
    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    ss = StateStore(database_store=ds)
    return BrainService(state_store=ss)


def _invoke(brain, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    out = brain.invoke_skill(skill_id, payload)
    if isinstance(out, dict) and "result" in out and "audit_id" in out:
        return out["result"]
    return out


def _find_table_resource(shadow_db: Path) -> dict[str, str]:
    """从真实 sd-default 找一个 resource_kind=table 的资源 (M0 已加载，F2 fixture 路径)."""
    with sqlite3.connect(f"file:{shadow_db}?mode=ro", uri=True) as conn:
        row = conn.execute(
            "SELECT resource_code, title, owner_org_id "
            "FROM resource_asset WHERE tenant_id=? AND resource_kind='table' "
            "AND owner_org_id IS NOT NULL AND owner_org_id != '' "
            "ORDER BY resource_code LIMIT 1",
            (TENANT,),
        ).fetchone()
    if row is None:
        raise RuntimeError(
            "sd-default 中找不到 resource_kind=table 且 owner_org_id 非空的资源；"
            "请检查 M0 acceptance 是否已 wire resource_asset"
        )
    return {"resource_code": row[0], "title": row[1], "owner_org_id": row[2]}


def _new_demo_catalog_code() -> str:
    return f"DEMO-J2-{uuid.uuid4().hex[:10]}"


# ──────────────────────────────────────────────────────────────────────
# Demo 链路 — J2 提供方 12 步黄金链 + 异议 7 步闭环
# ──────────────────────────────────────────────────────────────────────


def run_demo(seed_db: Path, shadow_db: Path) -> dict[str, Any]:
    started = time.monotonic()
    _log("STEP-0", "准备 shadow DB", seed=str(seed_db), shadow=str(shadow_db))
    _prepare_shadow_db(seed_db, shadow_db)

    table_resource = _find_table_resource(shadow_db)
    provider_org = table_resource["owner_org_id"]
    _log("STEP-0", f"M0 真实 table 资源命中 {table_resource['resource_code']}",
         provider_org=provider_org)

    brain = _build_brain()
    catalog_code = _new_demo_catalog_code()

    # ── STEP-1 在线编制 ───────────────────────────────────────────────
    _log("STEP-1.P5", "OPERATER 在线编制新目录", catalog=catalog_code)
    _invoke(brain, "catalog.entry.create_draft", {
        "catalog_code": catalog_code,
        "title": f"F6 J2 demo 目录 — {table_resource['title']}",
        "owner_org_id": provider_org,
        "region_code": "370100",
        "role": "ROLE_ORGAN_OPERATER",
        "confirmed": True,
    })

    # ── STEP-2 补元数据 ───────────────────────────────────────────────
    _log("STEP-2.P5", "OPERATER 补元数据 (catalog.entry.update)")
    _invoke(brain, "catalog.entry.update", {
        "catalog_code": catalog_code,
        "title": f"F6 J2 demo 目录 — {table_resource['title']} (补元)",
        "owner_org_id": provider_org,
        "region_code": "370100",
        "summary_json": {"demo": True, "stage": "metadata_filled"},
        "role": "ROLE_ORGAN_OPERATER",
        "confirmed": True,
    })

    # ── STEP-3 资源挂接 (table 物化真数据) ────────────────────────────
    _log("STEP-3.P5", "OPERATER 挂接 table 物化资源",
         resource=table_resource["resource_code"])
    bind_result = _invoke(brain, "catalog.resource.bind", {
        "catalog_code": catalog_code,
        "resource_code": table_resource["resource_code"],
        "catalog_item_code": f"item-demo-j2-{uuid.uuid4().hex[:8]}",
        "binding_code": f"bind-demo-j2-{uuid.uuid4().hex[:8]}",
        "materialization_kind": "table",
        "source_schema_ref": {"materialization": "table", "demo": True},
        "mapping_rule_json": {"materialization": "table", "rule": "passthrough"},
        "role": "ROLE_ORGAN_OPERATER",
        "confirmed": True,
    })
    if bind_result.get("materialization_kind") != "table":
        raise RuntimeError(f"F2 surface 失效：bind 未反射 materialization_kind=table；got {bind_result}")

    # ── STEP-4 提交部门审 ────────────────────────────────────────────
    _log("STEP-4.P5", "OPERATER submit_review → pending_review")
    submit = _invoke(brain, "catalog.entry.submit_review", {
        "catalog_code": catalog_code,
        "role": "ROLE_ORGAN_OPERATER",
        "confirmed": True,
    })
    if submit["lifecycle_status"] != "pending_review":
        raise RuntimeError(f"submit_review 状态机异常：{submit}")

    # ── STEP-5 部门审 — 3 层第 1 步 (F1) ─────────────────────────────
    _log("STEP-5.P5", "MANAGER review approve → pending_platform_review (F1 3 层第 1 步)")
    mgr_review = _invoke(brain, "catalog.entry.review", {
        "catalog_code": catalog_code,
        "decision": "approve",
        "role": "ROLE_ORGAN_MANAGER",
        "confirmed": True,
    })
    if mgr_review["lifecycle_status"] != "pending_platform_review":
        raise RuntimeError(f"MANAGER 部门审 stage-aware 失效：{mgr_review}")

    # ── STEP-6 平台审 — 3 层第 2 步 (F1) ─────────────────────────────
    _log("STEP-6.P5", "BUSIAUDIT review approve → approved_pending_publish (F1 3 层第 2 步)")
    plt_review = _invoke(brain, "catalog.entry.review", {
        "catalog_code": catalog_code,
        "decision": "approve",
        "role": "ROLE_BUSIAUDIT",
        "confirmed": True,
    })
    if plt_review["lifecycle_status"] != "approved_pending_publish":
        raise RuntimeError(f"BUSIAUDIT 平台审 stage-aware 失效：{plt_review}")

    # ── STEP-7 发布 + 自动重复率检测 (F3) ────────────────────────────
    _log("STEP-7.P5", "BUSIAUDIT publish → active (自动触发 F3 catalog.duplicate.check)")
    publish = _invoke(brain, "catalog.entry.publish", {
        "catalog_code": catalog_code,
        "role": "ROLE_BUSIAUDIT",
        "confirmed": True,
    })
    if publish["lifecycle_status"] != "active":
        raise RuntimeError(f"publish 状态机异常：{publish}")
    duplicate_warnings_count = len(publish.get("duplicate_warnings") or [])
    duplicate_check_triggered = "duplicate_warnings" in publish
    _log("STEP-7.P5", f"publish envelope 含 duplicate_warnings (F3 反射)：{duplicate_warnings_count} 条")

    # ── STEP-8 异议创建 (申请方对该 catalog) ─────────────────────────
    _log("STEP-8.OBJ", "OPERATER create objection on new catalog")
    case = _invoke(brain, "objection.case.create", {
        "objection_kind": "catalog_quality",
        "target_type": "catalog",
        "target_id": catalog_code,
        "title": f"F6 J2 demo 异议 — {table_resource['title']} 字段描述偏差",
        "complainant_org_id": "U_DEMO_COMPLAINANT",
        "provider_org_id": provider_org,
        "basis_text": "F6 demo: 示例字段描述与底册不一致",
        "evidence": [{"evidence_type": "catalog", "content_json": {"demo": True}}],
        "role": "ROLE_ORGAN_OPERATER",
        "confirmed": True,
    })
    objection_id = case["id"]
    if case["status"] != "draft":
        raise RuntimeError(f"objection create 状态异常：{case}")

    # ── STEP-9 异议生命周期：submit + assign×2 ────────────────────────
    _log("STEP-9.OBJ", "submit + assign(platform) + assign(provider)")
    common = {"objection_id": objection_id, "role": "ROLE_BUSIAUDIT", "confirmed": True}
    _invoke(brain, "objection.case.submit", {**common, "role": "ROLE_ORGAN_OPERATER"})
    _invoke(brain, "objection.case.assign", {**common, "target_status": "platform_investigating"})
    assigned = _invoke(brain, "objection.case.assign", {
        **common, "target_status": "provider_investigating", "handler_org_id": provider_org
    })
    if assigned["status"] != "provider_investigating":
        raise RuntimeError(f"assign provider_investigating 状态异常：{assigned}")

    # ── STEP-10 提供方 reply (F4) ────────────────────────────────────
    _log("STEP-10.OBJ", "MANAGER 提供方 reply (F4 提供方响应面)")
    _invoke(brain, "objection.case.reply", {
        "objection_id": objection_id,
        "node_name": "提供方部门核查回复",
        "opinion": "已核实，准备修正字段描述",
        "action_result": "submitted",
        "handler_org_id": provider_org,
        "role": "ROLE_ORGAN_MANAGER",
        "confirmed": True,
    })

    # ── STEP-11 review → resolved ────────────────────────────────────
    _log("STEP-11.OBJ", "MANAGER review approve → resolved")
    resolved = _invoke(brain, "objection.case.review", {
        "objection_id": objection_id,
        "decision": "resolve",
        "resolved_summary": "提供方已修正字段描述",
        "role": "ROLE_ORGAN_MANAGER",
        "confirmed": True,
    })
    if resolved["status"] != "resolved":
        raise RuntimeError(f"review 状态异常：{resolved}")

    # ── STEP-12 申请方 evaluate ──────────────────────────────────────
    _log("STEP-12.OBJ", "OPERATER 申请方 evaluate")
    _invoke(brain, "objection.case.evaluate", {
        "objection_id": objection_id,
        "solved_flag": True,
        "overall_score": 5,
        "timeliness_score": 4,
        "result_score": 5,
        "comment": "提供方响应及时，问题已闭环",
        "role": "ROLE_ORGAN_OPERATER",
        "confirmed": True,
    })

    # ── 归档 close（13 步收官，超 12 步 demo 强度但保 lifecycle 闭环）
    _log("STEP-13.OBJ", "close → closed")
    _invoke(brain, "objection.case.close", {
        "objection_id": objection_id,
        "role": "ROLE_ORGAN_MANAGER",
        "confirmed": True,
    })

    # ── 全链路 audit_event 链路校验 ───────────────────────────────────
    # brain._snapshot["audit_events"] 仅记录走 _mutate / _append_audit_feed 的事件；
    # read-only skill (catalog.duplicate.check) 走 _invoke_traced_read，audit 只落
    # capability_call 表（见后续核查），不进 audit_events feed。
    feed = brain.snapshot()["audit_events"]
    required_events = {
        # F1+F2+F3 部分：编制+审批+发布（mutate 路径，写 audit_events）
        "catalog.entry.create_draft",
        "catalog.entry.update",
        "catalog.resource.bind",
        "catalog.entry.submit_review",
        "catalog.entry.review",
        "catalog.entry.publish",
        # F4 部分：异议响应链
        "objection.case.create",
        "objection.case.submit",
        "objection.case.assign",
        "objection.case.reply",
        "objection.case.review",
        "objection.case.evaluate",
        "objection.case.close",
    }
    event_types = {e.get("type") for e in feed}
    missing = required_events - event_types
    if missing:
        raise RuntimeError(f"全链路 audit_event 缺失: {sorted(missing)}")

    # capability_call 覆盖核查（持久化 SoT）
    capability_call_total = 0
    capability_call_skills = set()
    with sqlite3.connect(f"file:{shadow_db}?mode=ro", uri=True) as conn:
        for row in conn.execute("SELECT skill_id FROM capability_call WHERE tenant_id=?", (TENANT,)):
            capability_call_total += 1
            capability_call_skills.add(row[0])
    core_caps = {
        "catalog.entry.create_draft",
        "catalog.entry.submit_review",
        "catalog.entry.review",
        "catalog.entry.publish",
        "catalog.resource.bind",
        "catalog.duplicate.check",
        "objection.case.create",
        "objection.case.review",
        "objection.case.evaluate",
    }
    capability_call_missing = sorted(core_caps - capability_call_skills)

    elapsed = time.monotonic() - started
    _log("DONE", f"J2 全链路成功，{len(event_types)} 类 audit_event + {capability_call_total} capability_call",
         elapsed_seconds=round(elapsed, 2),
         budget_seconds=DEFAULT_BUDGET_SECONDS)

    return {
        "ok": True,
        "elapsed_seconds": round(elapsed, 2),
        "budget_seconds": DEFAULT_BUDGET_SECONDS,
        "catalog_code": catalog_code,
        "resource_code": table_resource["resource_code"],
        "resource_kind": "table",
        "provider_org": provider_org,
        "objection_id": objection_id,
        "audit_event_total": len(feed),
        "audit_event_types_covered": len(required_events),
        "duplicate_check_triggered": duplicate_check_triggered,
        "duplicate_warnings_count": duplicate_warnings_count,
        "capability_call_total": capability_call_total,
        "capability_call_core_missing": capability_call_missing,
        "quality_flags": {
            "f1_three_layer_review_active": True,
            "f2_table_materialization_real_data": True,
            "f2_file_materialization_real_data": False,  # M0 mapper chip pending
            "f2_api_materialization_real_data": False,  # M0 mapper chip pending
            "f3_duplicate_check_auto_triggered": duplicate_check_triggered,
            "f4_provider_response_chain_complete": True,
            "f5_national_ext_elem_deferred": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="F6 J2 30 分钟客户演示验收脚本")
    parser.add_argument("--seed-db", type=Path, default=DEFAULT_DB,
                        help="M0 已灌库 sd-default seed DB (default: .data/zw_brain.db)")
    parser.add_argument("--shadow-db", type=Path, default=SHADOW_DB_DEFAULT,
                        help="shadow DB 路径 (default: .data/customer-demo-j2-shadow.db)")
    parser.add_argument("--report", type=Path,
                        help="演示完成后写入 JSON 报告")
    args = parser.parse_args()

    try:
        result = run_demo(args.seed_db, args.shadow_db)
    except AssertionError as exc:
        _log("FAIL", f"assertion: {exc}")
        return 2
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
