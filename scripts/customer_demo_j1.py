#!/usr/bin/env python3
"""F9 J1 30 分钟客户演示 — 端到端跑通 P2→P3→P4→Objection 全链路.

按 e1-j1-journey core_goal: 多岗位协同（操作员申请/运营员受理/管理员审定）在 30 分钟内 sd-default 真实数据上跑通
P2 搜索 → P3 草拟+审批 → P4 凭据+样例+解释 → 异议 5 维度任一全闭环。

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
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB_DEFAULT = REPO_ROOT / ".data" / "customer-demo-j1-shadow.db"
TENANT = "sd-default"

# 30 minute budget — 演示验收脚本上限
DEFAULT_BUDGET_SECONDS = 30 * 60

# core_goal 要求的 3 个 catalog (sd-default 真实数据)
TARGET_CATALOG_TITLES = ("医疗救助信息", "医保码信息", "异地就医统筹区开通信息")


def _log(step: str, msg: str = "", **kv) -> None:
    extras = " ".join(f"{k}={v}" for k, v in kv.items()) if kv else ""
    print(f"[demo-j1] {step:<32s} {msg} {extras}".rstrip(), flush=True)


def _prepare_shadow_db(seed_db: Path, shadow_db: Path) -> None:
    if not seed_db.exists():
        raise RuntimeError(f"seed db not found: {seed_db} — 请先跑 M0 acceptance (uv run python -m zw_brain.entry.legacy_migration.main ...)")
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


def _find_target_catalog(shadow_db: Path) -> list[dict[str, str]]:
    """从真实 sd-default 找到 core_goal 要求的 3 个 catalog."""
    found: list[dict[str, str]] = []
    with sqlite3.connect(f"file:{shadow_db}?mode=ro", uri=True) as conn:
        for title_kw in TARGET_CATALOG_TITLES:
            row = conn.execute(
                "SELECT catalog_code, title FROM catalog_entry "
                "WHERE tenant_id=? AND title LIKE ? LIMIT 1",
                (TENANT, f"%{title_kw}%"),
            ).fetchone()
            if row:
                found.append({"catalog_code": row[0], "title": row[1], "match": title_kw})
    return found


def _inject_approved_request(brain, request_id: str, resource_id: str, resource_name: str) -> None:
    # Action D：申请/交付单一事实源在 DB——演示前置单直接 upsert 进
    # application_record / delivery_task（幂等，同 code 覆盖），不再写内存快照。
    store = brain._state_store.database_store
    store.application_repo.upsert_from_request({
        "id": request_id,
        "status": "approved",
        "applicant": "U_BUSIAUDIT_DEMO",
        "applicantDept": "省大数据局",
        "resourceId": resource_id,
        "resourceName": resource_name,
        "purpose": "F9 客户演示 — 医疗救助数据查询",
        "auditId": "AE-DEMO-F9",
    })
    store.delivery_repo.upsert_from_delivery({
        "id": f"DT-{request_id}",
        "requestId": request_id,
        "resourceId": resource_id,
        "resourceName": resource_name,
        "status": "granted",
        "state": "granted",
        "channel": "api",
        "accessGrantSnapshot": {},
        "history": [],
    })


def _inject_objection_catalog_target(shadow_db: Path, catalog_code: str) -> None:
    """让 catalog_code 在 catalog_entry 中可解析（M0 已导入，no-op）."""
    # M0 dump 已含真实 catalog_entry，无需额外操作
    return None


# ──────────────────────────────────────────────────────────────────────
# Demo 链路
# ──────────────────────────────────────────────────────────────────────


def run_demo(seed_db: Path, shadow_db: Path, *, dry_run: bool = False) -> dict[str, Any]:
    started = time.monotonic()
    _log("STEP-0", "准备 shadow DB", seed=str(seed_db), shadow=str(shadow_db))
    _prepare_shadow_db(seed_db, shadow_db)
    targets = _find_target_catalog(shadow_db)
    if len(targets) < 1:
        raise RuntimeError("sd-default 中找不到 医疗救助/医保码/异地就医统筹区开通 任一 catalog；请检查 M0 导入完整性")
    _log("STEP-0", f"M0 真实 catalog 命中 {len(targets)}/3", titles=[t["title"] for t in targets])
    primary = targets[0]

    brain = _build_brain()

    # ── P2 search.intent.parse ────────────────────────────────────────
    _log("STEP-1.P2", "搜索意图解析「医疗救助相关」")
    p2 = _invoke(brain, "search.intent.parse", {
        "query": "医疗救助相关数据",
        "role": "ROLE_BUSIAUDIT",
        "enabled": False,
    })
    assert p2["intent"] in ("discover_resource", "register_demand"), p2
    assert any("医疗救助" in k for k in p2["keywords"]), p2

    # ── P3 application.draft.suggest ──────────────────────────────────
    _log("STEP-2.P3", "申请草拟", resource=primary["title"])
    draft = _invoke(brain, "application.draft.suggest", {
        "resource_name": primary["title"],
        "applicant_org": "省大数据局",
        "use_case": "省大数据局行政依据查询医疗救助分布",
        # D55/P7：业务运营员退申请人身份——申请草拟由部门操作员（申请人）发起
        "role": "ROLE_ORGAN_OPERATER",
        "enabled": False,
    })
    assert draft["suggested_fields"]["use_reason"] in ("行政依据", "审批办理", "信用核查", "其他"), draft

    # ── 注入 1 个真实 approved 申请单作演示载体 ─────────────────────────
    request_id = "REQ-DEMO-F9-MEDICAL-AID"
    _inject_approved_request(brain, request_id, primary["catalog_code"], primary["title"])

    # ── P3 approval.evidence.summarize ────────────────────────────────
    # evidence helper 期望 application_id 在 application_record 表中（_load_application 查表）
    # 用真实 approved apply 作 evidence 锚（任选 1 条）
    with sqlite3.connect(f"file:{shadow_db}?mode=ro", uri=True) as conn:
        row = conn.execute(
            "SELECT application_code FROM application_record WHERE tenant_id=? "
            " AND json_extract(payload_json,'$.kind')='apply' AND status='approved' LIMIT 1",
            (TENANT,),
        ).fetchone()
    if row is None:
        raise RuntimeError("sd-default 中找不到 apply kind+approved 申请；请检查 M0 导入")
    real_app_id = row[0]
    _log("STEP-3.P3", "审批依据归纳", real_app_id=real_app_id)
    evidence = _invoke(brain, "approval.evidence.summarize", {
        "application_id": real_app_id,
        "role": "ROLE_BUSIAUDIT",
        "enabled": False,
    })
    assert evidence["recommendation"] in ("approve", "return_for_fix", "reject"), evidence
    assert evidence["bases"], evidence

    # ── P4 credential.issue + sample.render ───────────────────────────
    _log("STEP-4.P4", "凭据下发 (注入 approved request)")
    cred = _invoke(brain, "credential.issue", {
        "request_id": request_id,
        "role": "ROLE_ORGAN_MANAGER",
        "confirmed": True,
    })
    assert cred["credential"]["app_key"].startswith("AK-SELF-"), cred
    _log("STEP-5.P4", "凭据三语样例渲染（R-001 fix: 申请人本人渲染，避免审计角色读取明文 app_secret）")
    samples = _invoke(brain, "credential.sample.render", {
        "request_id": request_id,
        "role": "ROLE_ORGAN_OPERATER",
    })
    assert samples["status"] == "rendered", samples
    assert set(samples["samples"].keys()) == {"curl", "python", "java"}, samples
    assert cred["credential"]["app_key"] in samples["samples"]["curl"]

    # ── P4 delivery.status.explain ────────────────────────────────────
    _log("STEP-6.P4", "状态解释 (granted)")
    # 注入的 delivery_task 在 in-memory snapshot；explain cap 查 DB 表，所以用真实 sd-default delivery 作锚
    with sqlite3.connect(f"file:{shadow_db}?mode=ro", uri=True) as conn:
        row = conn.execute(
            "SELECT delivery_code FROM delivery_task WHERE tenant_id=? LIMIT 1", (TENANT,)
        ).fetchone()
    assert row is not None
    real_delivery = row[0]
    explain = _invoke(brain, "delivery.status.explain", {
        "delivery_code": real_delivery,
        # 交付面=操作员+管理员（D53⑥ 业务运营员无交付场景；D55/P13·P18）
        "role": "ROLE_ORGAN_OPERATER",
        "enabled": False,
    })
    assert explain["phase"], explain
    assert explain["evidence_sources"], explain

    # ── 异议 catalog 维度全闭环 ───────────────────────────────────────
    _log("STEP-7.OBJ", "创建 catalog 异议", catalog=primary["catalog_code"])
    case = _invoke(brain, "objection.case.create", {
        # 异议由用数方（部门操作员）发起；受理/分发/复核仍归业务运营员（common）
        "role": "ROLE_ORGAN_OPERATER",
        "confirmed": True,
        "objection_kind": "catalog_quality",
        "target_type": "catalog",
        "target_id": primary["catalog_code"],
        "title": f"F9 演示: {primary['title']} 字段描述异议",
        "complainant_org_id": "U_OPERATER_DEMO",
        "provider_org_id": "U_PROVIDER_DEMO",
        "basis_text": "示例字段描述与底册不一致",
        "evidence": [{"evidence_type": "catalog", "content_json": {"demo": True, "title": primary["title"]}}],
    })
    objection_id = case["id"]
    assert case["status"] == "draft", case

    common = {"role": "ROLE_BUSIAUDIT", "confirmed": True, "objection_id": objection_id}
    _log("STEP-8.OBJ", "提交 → 平台核查 → 分发部门")
    _invoke(brain, "objection.case.submit", {**common, "role": "ROLE_ORGAN_OPERATER"})
    _invoke(brain, "objection.case.assign", {**common, "target_status": "platform_investigating"})
    _invoke(brain, "objection.case.assign", {**common, "target_status": "provider_investigating"})
    _log("STEP-9.OBJ", "部门 reply 补充处理材料")
    _invoke(brain, "objection.case.reply", {**common, "role": "ROLE_ORGAN_MANAGER", "node_name": "部门核查回复", "opinion": "已修正字段描述", "action_result": "submitted"})
    _log("STEP-10.OBJ", "平台 review → resolved")
    _invoke(brain, "objection.case.review", {**common, "decision": "resolve", "resolved_summary": "已修正字段描述"})
    _log("STEP-11.OBJ", "申请方 evaluate 评价")
    _invoke(brain, "objection.case.evaluate", {**common, "role": "ROLE_ORGAN_OPERATER",
            "solved_flag": True, "overall_score": 5, "comment": "处理及时"})
    _log("STEP-12.OBJ", "归档 closed")
    _invoke(brain, "objection.case.close", common)

    # ── 全链路 audit_event 链路校验 ────────────────────────────────────
    feed = brain.snapshot()["audit_events"]
    required_events = {
        "search.intent.parse",
        "application.draft.suggest",
        "approval.evidence.summarize",
        "credential.issue",
        "credential.sample.render",
        "delivery.status.explain",
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

    elapsed = time.monotonic() - started
    _log("DONE", f"全链路成功，{len(event_types)} 类 audit_event 类型覆盖",
         elapsed_seconds=round(elapsed, 2),
         budget_seconds=DEFAULT_BUDGET_SECONDS)

    return {
        "ok": True,
        "elapsed_seconds": round(elapsed, 2),
        "budget_seconds": DEFAULT_BUDGET_SECONDS,
        "catalog_targets_hit": len(targets),
        "audit_event_types_covered": len(required_events),
        "audit_event_total": len(feed),
        "primary_catalog": primary,
        "request_id": request_id,
        "real_application_id": real_app_id,
        "real_delivery_code": real_delivery,
        "objection_id": objection_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="F9 J1 30 分钟客户演示验收脚本")
    parser.add_argument("--seed-db", type=Path, default=DEFAULT_DB,
                        help="M0 已灌库 sd-default seed DB (default: .data/zw_brain.db)")
    parser.add_argument("--shadow-db", type=Path, default=SHADOW_DB_DEFAULT,
                        help="shadow DB 路径 (default: .data/customer-demo-j1-shadow.db)")
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
