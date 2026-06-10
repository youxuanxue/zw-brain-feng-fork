# Wave: 2
# Engine: 三引擎客户落地 sign-off（E3 F8 验收）
# Covers: AC5（≤1 周不改代码完成鞍山+四川+荆州三个项目级定制）
"""F8 — E3 Wave-2 三引擎客户落地证据材料生成。

技术证据：跑 3 个端到端用例 + 1 个 consolidated；产出 `.data/wave2-acceptance/
SIGN_OFF.md` + `.data/wave2-acceptance/*.json`（**全是 artifact，不进 git**，本地
复跑后生成）。每个 e2e 测量 NL→draft→preview→commit→live 总耗时。

2026-05-28 重构（业务方第二次 Jobs 视角穿透）：SIGN_OFF.md 是 derived 产物，与
consolidated.json 同性质，按 "derived 不入 git" 规矩**不再 tracked**——原 R-003
fix（迁到 docs/）和 PR #144 D17 确定性化（让重复跑产物 byte-identical）都是为
让 tracked 状态稳定打的补丁，根本病是"derived 产物本就不该 tracked"。

**sign-off 权威源 = `.testing/signoff/e3-engines.signoff.yaml` 账本（D46.b）；历史也曾记于
F8.actual_evidence**（业务方身份 / 签字载体 / 4 子项判定 / 日期全量住此字段）。
reviewer 看证据：(a) plan.yaml F8.actual_evidence；(b) 本地跑本 test 生成
`.data/wave2-acceptance/` 下完整证据；(c) PR 评论 `business-signoff: <角色> <日期>`。
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import pytest

from tests._trusted_payload import invoke_trusted

REPO_ROOT = Path(__file__).resolve().parents[2]
SHADOW_DB = REPO_ROOT / ".data" / "test_F8_wave2_acceptance_shadow.db"
# 2026-05-28 重构：SIGN_OFF.md 与 consolidated.json 同入 .data/（artifact，
# gitignored）；权威 sign-off 住 .testing/signoff/e3-engines.signoff.yaml 账本（D46.b）。
ACCEPTANCE_DIR = REPO_ROOT / ".data" / "wave2-acceptance"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def _remove_shadow_db_files() -> None:
    # WAL 模式（db.py PRAGMA journal_mode=WAL）会留 `-wal` / `-shm` 旁路文件。
    # 只删 `.db` 而留下旧 WAL，会让新建的 `.db` 重挂不匹配的 WAL → SQLite 间歇报
    # "database disk image is malformed"（取决于上次 run / 被 kill 的 run 是否留下旁路）。
    # 必须三件一起删；调用前须先 dispose 引擎，释放可能仍持旧 inode 的连接。
    for suffix in ("", "-wal", "-shm"):
        (SHADOW_DB.parent / f"{SHADOW_DB.name}{suffix}").unlink(missing_ok=True)


@pytest.fixture(scope="session", autouse=True)
def _shadow_db() -> None:
    SHADOW_DB.parent.mkdir(parents=True, exist_ok=True)
    ACCEPTANCE_DIR.mkdir(parents=True, exist_ok=True)
    from zw_brain.shared import db as _db
    _db.reset_engine_cache()  # 先释放旧连接，再删文件（含 WAL/SHM 旁路）
    _remove_shadow_db_files()
    os.environ["ZW_BRAIN_DB_PATH"] = str(SHADOW_DB)
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
    _db.reset_engine_cache()
    from zw_brain.shared.migrate import reset_and_upgrade
    reset_and_upgrade()
    yield
    # 收尾：释放引擎并清掉 shadow DB 三件套，不给后续 run 留脏 WAL
    _db.reset_engine_cache()
    _remove_shadow_db_files()


def _new_brain():
    import zw_brain.domain.approval_flow_nl_draft as af_nl
    import zw_brain.domain.form_schema_nl_draft as fs_nl
    from zw_brain.command.brain import BrainService
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.inference.client import InferenceError
    from zw_brain.shared.state_store import StateStore

    def _raising(*a, **k):
        raise InferenceError("F8 acceptance — LLM unavailable, use deterministic")

    af_nl._inference_chat = _raising  # type: ignore
    fs_nl._inference_chat = _raising  # type: ignore

    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    audit_bus.clear_sink()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=ss), audit_bus


def _write_report(name: str, payload: dict) -> Path:
    path = ACCEPTANCE_DIR / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


# ──────────────────────────────────────────────────────────────────────────
# Engine helpers（被 individual test 和 consolidated 共享调用；每次 unique schema_code）
# ──────────────────────────────────────────────────────────────────────────

def _run_anshan_e2e() -> dict:
    brain, audit_bus = _new_brain()
    intent = "鞍山审批流程：编制→二级部门审→一级部门审→发布，共 4 级审批"
    schema_code = f"anshan_acceptance_{_short_id()}_v1"
    try:
        t0 = time.perf_counter()
        draft = invoke_trusted(
                    brain,
                    "approval_flow.nl_draft",
                    {
                "tenant_id": "sd-default",
                "schema_code": schema_code,
                "title": "鞍山 4 级审批流（F8 sign-off）",
                "intent_text": intent,
                "created_by": "user:gov:ROLE_ORGAN_MANAGER:f8",
            },
                    role="ROLE_SYSTEM",
                )
        t_draft = time.perf_counter()
        assert draft["result"]["status"] == "draft"
        schema_id = draft["result"]["schema_id"]
        invoke_trusted(
            brain,
            "approval_flow.schema.promote_to_preview",
            {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_SYSTEM"},
            role="ROLE_SYSTEM",
        )
        t_preview = time.perf_counter()
        committed = invoke_trusted(
                        brain,
                        "approval_flow.schema.commit",
                        {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_SYSTEM"},
                        role="ROLE_SYSTEM",
                    )
        t_live = time.perf_counter()
    finally:
        audit_bus.clear_sink()

    assert committed["result"]["version"] == 2
    assert committed["result"]["committed_at"]
    assert draft["result"]["payload_summary"]["node_count"] == 6
    duration = t_live - t0
    assert duration < 60.0, f"鞍山 4 级 e2e 耗时 {duration:.3f}s 超 60s 演示上限"

    return {
        "engine": "approval_flow",
        "scenario": "鞍山 4 级审批流",
        "intent_text": intent,
        "schema_code": schema_code,
        "schema_id": schema_id,
        "version": committed["result"]["version"],
        "committed_at": committed["result"]["committed_at"],
        "approval_nodes": 4,
        "duration_seconds": {
            "total": round(duration, 3),
            "nl_draft": round(t_draft - t0, 3),
            "promote_preview": round(t_preview - t_draft, 3),
            "commit_live": round(t_live - t_preview, 3),
        },
        "config_change_class_transitions": ["draft", "preview", "live"],
    }


def _run_sichuan_e2e() -> dict:
    brain, audit_bus = _new_brain()
    intent = "四川申请表单：姓名、身份证号、联系电话、单位、申请事由、申请日期、附件"
    form_code = f"sichuan_acceptance_{_short_id()}_v1"
    try:
        t0 = time.perf_counter()
        draft = invoke_trusted(
                    brain,
                    "form_schema.nl_draft",
                    {
                "tenant_id": "sd-default",
                "form_code": form_code,
                "title": "四川 7 字段表单（F8 sign-off）",
                "intent_text": intent,
                "created_by": "user:gov:ROLE_ORGAN_MANAGER:f8",
            },
                    role="ROLE_SYSTEM",
                )
        t_draft = time.perf_counter()
        assert draft["result"]["status"] == "draft"
        schema_id = draft["result"]["schema_id"]
        invoke_trusted(
            brain,
            "form_schema.promote_to_preview",
            {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_SYSTEM"},
            role="ROLE_SYSTEM",
        )
        t_preview = time.perf_counter()
        committed = invoke_trusted(
                        brain,
                        "form_schema.commit",
                        {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_SYSTEM"},
                        role="ROLE_SYSTEM",
                    )
        t_live = time.perf_counter()
    finally:
        audit_bus.clear_sink()

    assert committed["result"]["version"] == 2
    assert committed["result"]["committed_at"]
    assert draft["result"]["payload_summary"]["field_count"] == 7
    duration = t_live - t0
    assert duration < 60.0, f"四川 7 字段 e2e 耗时 {duration:.3f}s 超 60s 演示上限"

    return {
        "engine": "form_schema",
        "scenario": "四川 7 字段申请表",
        "intent_text": intent,
        "form_code": form_code,
        "schema_id": schema_id,
        "version": committed["result"]["version"],
        "committed_at": committed["result"]["committed_at"],
        "field_count": 7,
        "duration_seconds": {
            "total": round(duration, 3),
            "nl_draft": round(t_draft - t0, 3),
            "promote_preview": round(t_preview - t_draft, 3),
            "commit_live": round(t_live - t_preview, 3),
        },
        "config_change_class_transitions": ["draft", "preview", "live"],
    }


def _run_jinzhou_e2e() -> dict:
    from sqlalchemy import select

    from zw_brain.domain.models import (
        CatalogItemRecord,
        RecommendationRuleRecord,
        RequirementHistoryRecord,
    )
    from zw_brain.domain.recommendation_engine import RecommendationEngine
    from zw_brain.domain.recommendation_rule import RecommendationRuleRepo
    from zw_brain.shared.db import create_session_factory

    SessionLocal = create_session_factory()
    history_data = json.loads((FIXTURES_DIR / "dsp_require_sample.json").read_text(encoding="utf-8"))
    rules_data = json.loads((FIXTURES_DIR / "jinzhou_recommendation_rules.json").read_text(encoding="utf-8"))

    t0 = time.perf_counter()
    with SessionLocal() as s:
        existing_require_ids = {
            row[0]
            for row in s.execute(
                select(RequirementHistoryRecord.source_require_id).where(
                    RequirementHistoryRecord.tenant_id == "sd-default"
                )
            ).all()
        }
        catalog_ids: set[str] = set()
        for rec in history_data["records"]:
            if rec.get("catalog_id"):
                catalog_ids.add(rec["catalog_id"])
            if rec["source_require_id"] in existing_require_ids:
                continue
            s.add(
                RequirementHistoryRecord(
                    tenant_id="sd-default",
                    source_require_id=rec["source_require_id"],
                    catalog_id=rec.get("catalog_id"),
                    resource_id=rec.get("resource_id"),
                    name=rec["name"],
                    org=rec.get("org"),
                    status=rec.get("status"),
                )
            )
        existing_item_codes = {
            row[0]
            for row in s.execute(
                select(CatalogItemRecord.item_code).where(CatalogItemRecord.tenant_id == "sd-default")
            ).all()
        }
        for idx, cid in enumerate(sorted(catalog_ids)):
            item_code = f"item-{cid}"
            if item_code in existing_item_codes:
                continue
            first = next(r for r in history_data["records"] if r.get("catalog_id") == cid)
            s.add(
                CatalogItemRecord(
                    tenant_id="sd-default",
                    item_code=item_code,
                    catalog_code=cid,
                    resource_code=first.get("resource_id"),
                    title=first["name"],
                    item_kind="dataset",
                    display_order=idx,
                    summary_json={"seed": "F8 acceptance"},
                )
            )
        s.commit()

        repo = RecommendationRuleRepo(s)
        existing_codes = {
            row[0]
            for row in s.execute(
                select(RecommendationRuleRecord.rule_code).where(
                    RecommendationRuleRecord.tenant_id == "sd-default"
                )
            ).all()
        }
        for rule in rules_data["rules"]:
            if rule["rule_code"] in existing_codes:
                continue
            rec = repo.create_draft(
                tenant_id="sd-default",
                rule_code=rule["rule_code"],
                title=rule["title"],
                payload=rule["payload"],
                created_by="user:gov:ROLE_ORGAN_MANAGER:f8",
            )
            repo.promote_to_preview(rec.id)
            repo.commit_to_live(rec.id)
    t_seed = time.perf_counter()

    with SessionLocal() as s:
        engine = RecommendationEngine(s)
        hits = 0
        per_record: list[dict] = []
        for rec in history_data["records"]:
            candidates = engine.suggest(
                tenant_id="sd-default",
                intent_text=rec["name"],
                intent_org=rec.get("org"),
                top_k=5,
            )
            top = candidates[0].catalog_id if candidates else None
            hit = bool(candidates) and candidates[0].catalog_id == rec["catalog_id"]
            if hit:
                hits += 1
            per_record.append(
                {
                    "name": rec["name"],
                    "expected_catalog_id": rec["catalog_id"],
                    "top_candidate": top,
                    "hit": hit,
                    "candidates_count": len(candidates),
                }
            )
    t_done = time.perf_counter()

    duration = t_done - t0
    hit_rate = hits / len(history_data["records"])
    assert hit_rate >= 0.2, f"荆州 hit-rate {hit_rate:.0%} 低于 20% baseline"
    assert duration < 60.0, f"荆州验收耗时 {duration:.3f}s 超 60s 演示上限"

    return {
        "engine": "recommendation",
        "scenario": "荆州 5 条推荐规则 + 5 条真实 dsp_require 历史",
        "rule_count": len(rules_data["rules"]),
        "history_sample_size": len(history_data["records"]),
        "hit_rate": round(hit_rate, 3),
        "hit_count": hits,
        "per_record": per_record,
        "duration_seconds": {
            "total": round(duration, 3),
            "seed": round(t_seed - t0, 3),
            "suggest": round(t_done - t_seed, 3),
        },
    }


# ──────────────────────────────────────────────────────────────────────────
# pytest tests
# ──────────────────────────────────────────────────────────────────────────

def test_anshan_approval_flow_one_week_landing() -> None:
    report = _run_anshan_e2e()
    _write_report("anshan_approval.json", report)
    assert report["version"] == 2
    assert report["approval_nodes"] == 4


def test_sichuan_form_schema_one_week_landing() -> None:
    report = _run_sichuan_e2e()
    _write_report("sichuan_form.json", report)
    assert report["version"] == 2
    assert report["field_count"] == 7


def test_jinzhou_recommendation_one_week_landing() -> None:
    report = _run_jinzhou_e2e()
    _write_report("jinzhou_recommendation.json", report)
    assert report["hit_rate"] >= 0.2
    assert report["rule_count"] == 5


def test_three_engines_consolidated_acceptance() -> None:
    from datetime import UTC, datetime

    from sqlalchemy import select

    from zw_brain.domain.models import AuditEventRecord
    from zw_brain.shared.db import create_session_factory

    # D17 确定性：在跑 3 个 e2e 前打 UTC marker（AuditEventRecord.occurred_at 也是
    # UTC），consolidated audit_total 仅计本次三场景产生的事件，不受
    # test_anshan/test_sichuan/test_jinzhou 个体用例先跑的影响（避免「全套跑」vs
    # 「单跑 consolidated」count 漂移 → SIGN_OFF.md 漂移）。
    consolidated_t0 = datetime.now(UTC)
    t0 = time.perf_counter()
    anshan = _run_anshan_e2e()
    sichuan = _run_sichuan_e2e()
    jinzhou = _run_jinzhou_e2e()
    total_duration = time.perf_counter() - t0

    SessionLocal = create_session_factory()
    with SessionLocal() as s:
        audit_rows = s.execute(
            select(AuditEventRecord).where(AuditEventRecord.occurred_at >= consolidated_t0)
        ).all()
        audit_total = len(audit_rows)

    summary = {
        "wave": "E3 Wave-2",
        "acceptance_id": "F8-three-engines",
        "engines": {
            "approval_flow": anshan,
            "form_schema": sichuan,
            "recommendation": jinzhou,
        },
        "total_duration_seconds": round(total_duration, 3),
        "audit_event_count": audit_total,
        "all_config_change_class_live": True,
    }
    _write_report("consolidated.json", summary)

    md_lines = [
        "# E3 Wave-2 三引擎客户落地 sign-off 材料",
        "",
        "> 自动生成自 `tests/integration/test_wave2_three_engines_acceptance.py`。",
        "> 业务方在 § 3 签字后此条状态可从 pending 升 completed。",
        "> **确定性**：本文档不嵌入随机 UUID / 精确耗时数（每次 e2e 重跑会漂；",
        "> 违反 D17 数字漂移防御层）；精确 schema_id 与 duration 走 `.data/wave2-acceptance/*.json`。",
        "",
        "## § 0 签字身份与载体（签字前先填）",
        "",
        "| 角色 | 具体身份 | 签字载体 |",
        "|---|---|---|",
        "| 业务方 (e3 F8 三引擎) | _待填，例：海若产品部产品负责人 / 客户验收方 IT 主管_ | _待填，例：PR #144 评论 / 邮件归档 / 验收报告盖章扫描件_ |",
        "",
        "> § 3 / § 4 表内\"签字\"列填具体人名与日期；本节抬头先把\"业务方=谁、签字证据以什么形式保存\"",
        "> 定下来，避免每次 review 重新讨论这个 meta 问题。线下盖章 / 邮件确认场景下，",
        "> 把扫描件 / 邮件截图归入 `docs/approved/` 并在 § 3 备注链接。",
        "",
        "## § 1 三引擎技术证据",
        "",
        "| 引擎 | 场景 | 入库 | version | 状态机 |",
        "|---|---|:--:|---:|---|",
        f"| 审批流 | {anshan['scenario']} | ✓ | {anshan['version']} | draft→preview→live |",
        f"| 申请表单 | {sichuan['scenario']} | ✓ | {sichuan['version']} | draft→preview→live |",
        f"| 推荐规则 | {jinzhou['scenario']} | 5 rules live | live | draft→preview→live |",
        "",
        "**相关 commit**：",
        "",
        "- F1 `8752331` — 审批流引擎数据模型 + 状态机 + commit skill",
        "- F2 `2b21233` — 审批流基线 seeder + J1 申请提交自动启动",
        "- F3 `4c944ce` — 审批流 NL 草稿 + 三步流程 + 鞍山 4 级 e2e",
        "- F4 `f36df22` — 表单 schema 化引擎数据模型 + 校验 + commit skill",
        "- F5 `1863c53` — 表单 schema NL 草稿 + 三步流程 + 四川 7 字段 e2e",
        "- F6 `292710b` — 智能推荐前置引擎 + 5 条荆州规则 + 真实历史 hit-rate",
        "- F7 `08adea0` — 三引擎管理员配置页 UI (B1.2 子页 /integration-admin/engines)",
        "",
        "## § 2 真实数据回归",
        "",
        f"- 荆州 5 条真实 `dump-dsp_require` 历史申请命中率：**{int(jinzhou['hit_rate'] * 100)}%** ({jinzhou['hit_count']}/{jinzhou['history_sample_size']})",
        "- baseline ≥ 20%（pipeline smoke test 性质），**实测超出 baseline**。",
        "- **测度局限**：本期 fixture 规则（`tests/fixtures/jinzhou_recommendation_rules.json`）与 5 条 records",
        "  （`tests/fixtures/dsp_require_sample.json`）同期手工编排（如 `残疾人` keyword 命中 `残疾人信息资源`），",
        "  此命中率是端到端 pipeline 跑通的烟雾测度，**不是**推荐质量的可外推度量。",
        "  真实质量评估需待客户接入后用未见 records 跑 holdout / cross-validation。",
        "- **per_record 同 top_candidate 现象说明**：jinzhou_recommendation.json 显示 5 query",
        "  共享同一 top_candidate `cat-disabled-info-001`，**非 bug，是 fixture 关键字 + 引擎",
        "  `keyword_match` OR-逻辑的协同产物**——title 含「残疾」的 catalog 对任意 query 自动加",
        "  1.5 分，其他 catalog 缺差异化得分源全部输给该项。要做有区分度的多样化推荐，需 (a)",
        "  补 fixture rules 让每条 query 有独立得分源，或 (b) 引擎引入 query-catalog 相关性",
        "  评分（embedding / TF-IDF 等），均属 Wave 2.x+ 立项。",
        "- 命中明细见 `.data/wave2-acceptance/jinzhou_recommendation.json`（本地复跑后生成）。",
        "",
        "## § 3 业务方 sign-off 状态",
        "",
        "> **权威源**：`.testing/signoff/e3-engines.signoff.yaml` 账本（D46.b 单源）；",
        "> 本节不持有签字数据（derived 产物不入 git，避免「同信息存两处需手同步」）。",
        "> 业务方判定 4 子项（鞍山 4 级审批流 / 四川 7 字段申请表 / 荆州 5 条推荐规则 /",
        "> 「1 周内不改代码」承诺）的结果落在 plan.yaml F8.actual_evidence 末段 sign-off 条；",
        "> 任一子项 = 「需修改」按 R13 元规则触发新一轮 review。",
        "",
        "## § 4 已知 deferred 项",
        "",
        "- **D25 审批流可配置化承诺**：项目级流程定制（鞍山 4 级 = 编制 → 二级部门 → 一级部门 → 发布）",
        "  本期由 F1/F3 兑现技术骨架；流程引擎本身下期立项。",
        "- **D26 表单 schema 化承诺**：项目级表单定制（四川 7 字段 / 荆州本期 5 规则）",
        "  本期由 F4/F5 兑现技术骨架；表单引擎本身下期立项。",
        "- **E1 J1 后续 refactor 契约**：F2 提供的 `start_approval_workflow_from_baseline` hook",
        "  需在 E1 application.submit handler 正式接管时保留调用契约（baseline 路径 vs",
        "  legacy upsert_from_request_and_approval 路径并行存在，以 #baseline 后缀避免冲突）。",
        "- **AgentRuntime + 三引擎 NL 草稿 LLM 真路径**：本期 LLM 未配凭证，e2e 都走",
        "  deterministic 兜底；接入集团推理平台后需在 staging 验真 LLM Tier 2 路径。",
        "",
        "## § 5 1 周硬上限",
        "",
        "- 自动化 e2e 实测总耗时：**单场景 <60s 演示上限内**（每场景 assert duration < 60.0；",
        "  跨场景 consolidated 走架构约束 R7 反假绿）；精确数走 `.data/wave2-acceptance/consolidated.json`。",
        "- 远低于 1 周 (604800s) 硬上限。",
        "- 真实工作量评估（业务方判断含调研、需求确认、人工 review）请在 § 3 填补。",
        "",
        f"- 审计事件总数：**{audit_total}** 条（写态 skill 全部经 audit bus 同步落库；D4 — 计数",
        "  随 e2e 路径稳定，不随机生成）。",
        "",
        "---",
        "",
        "**版本**：自动生成；如需更新，重新跑",
        "`pytest tests/integration/test_wave2_three_engines_acceptance.py -v` 后回写。",
        "",
    ]
    # 2026-05-28 重构：SIGN_OFF.md 与 consolidated.json 同入 .data/（gitignored
    # artifact）。sign-off 权威源住 .testing/signoff/e3-engines.signoff.yaml 账本（D46.b）。
    # 无 preserve 逻辑——本文档纯 auto-gen 证据材料，无需保护"手填行"。
    sign_off_path = ACCEPTANCE_DIR / "SIGN_OFF.md"
    sign_off_path.write_text("\n".join(md_lines), encoding="utf-8")
    assert sign_off_path.exists()
    assert summary["audit_event_count"] >= 6, f"审计事件数 {summary['audit_event_count']} 过低"
