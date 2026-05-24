# Wave: 2
# Engine: 智能推荐前置（E3 三引擎 F6）
# Covers: AC3（规则三态 + 引擎评分 + 5 真实历史 hit-rate ≥ 20%）
# Not covered: NL 草稿（F5 表单引擎只覆盖表单 NL；推荐引擎 NL 不在 F6 范围）/ UI（F7）/ P3 申请前置真实接入（属 E1）
"""F6 — 推荐规则三态 + 引擎评分 + commit/suggest skill dispatch + 真实 5 条 dsp_require hit-rate。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests._trusted_payload import invoke_trusted

REPO_ROOT = Path(__file__).resolve().parents[2]
SHADOW_DB = REPO_ROOT / ".data" / "test_F6_recommendation_shadow.db"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def _build_rule_payload() -> dict:
    return {
        "clauses": [
            {
                "clause_code": "kw_demo",
                "clause_kind": "keyword_match",
                "clause_payload_json": {"keywords": ["人口", "户籍"]},
                "weight": 1.0,
                "order_index": 0,
            },
            {
                "clause_code": "freq_demo",
                "clause_kind": "usage_frequency",
                "clause_payload_json": {"min_count": 1, "scale": 0.3},
                "weight": 1.0,
                "order_index": 1,
            },
        ]
    }


@pytest.fixture(scope="session", autouse=True)
def _shadow_db() -> None:
    SHADOW_DB.parent.mkdir(parents=True, exist_ok=True)
    if SHADOW_DB.exists():
        SHADOW_DB.unlink()
    os.environ["ZW_BRAIN_DB_PATH"] = str(SHADOW_DB)
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
    from zw_brain.shared import db as _db
    _db.reset_engine_cache()
    from zw_brain.shared.migrate import reset_and_upgrade
    reset_and_upgrade()
    yield


@pytest.fixture()
def session():
    from zw_brain.shared.db import create_session_factory

    SessionLocal = create_session_factory()
    with SessionLocal() as s:
        yield s


# ──────────────────────────────────────────────────────────────────────────
# 规则三态流转
# ──────────────────────────────────────────────────────────────────────────

def test_create_draft(session):
    from zw_brain.domain.recommendation_rule import RecommendationRuleRepo

    repo = RecommendationRuleRepo(session)
    rec = repo.create_draft(
        tenant_id="sd-default",
        rule_code="kw_test_v1",
        title="kw test",
        payload=_build_rule_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    assert rec.status == "draft"
    assert rec.version == 1
    assert rec.committed_at is None


def test_promote(session):
    from zw_brain.domain.recommendation_rule import RecommendationRuleRepo

    repo = RecommendationRuleRepo(session)
    rec = repo.create_draft(
        tenant_id="sd-default",
        rule_code="promote_v1",
        title="promote",
        payload=_build_rule_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    p = repo.promote_to_preview(rec.id)
    assert p.status == "preview"


def test_revert(session):
    from zw_brain.domain.recommendation_rule import RecommendationRuleRepo

    repo = RecommendationRuleRepo(session)
    rec = repo.create_draft(
        tenant_id="sd-default",
        rule_code="revert_v1",
        title="revert",
        payload=_build_rule_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    repo.promote_to_preview(rec.id)
    r = repo.revert_to_draft(rec.id)
    assert r.status == "draft"


def test_commit_bumps_version(session):
    from zw_brain.domain.recommendation_rule import RecommendationRuleRepo

    repo = RecommendationRuleRepo(session)
    rec = repo.create_draft(
        tenant_id="sd-default",
        rule_code="commit_v1",
        title="commit",
        payload=_build_rule_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    repo.promote_to_preview(rec.id)
    live = repo.commit_to_live(rec.id)
    assert live.status == "live"
    assert live.version == 2
    assert live.committed_at is not None


# ──────────────────────────────────────────────────────────────────────────
# 非法跃迁
# ──────────────────────────────────────────────────────────────────────────

def test_draft_to_live_raises(session):
    from zw_brain.domain.recommendation_rule import (
        RecommendationRuleRepo,
        RecommendationRuleTransitionError,
    )

    repo = RecommendationRuleRepo(session)
    rec = repo.create_draft(
        tenant_id="sd-default",
        rule_code="bad_d2l_v1",
        title="bad",
        payload=_build_rule_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    with pytest.raises(RecommendationRuleTransitionError):
        repo.commit_to_live(rec.id)


def test_live_to_anything_raises(session):
    from zw_brain.domain.recommendation_rule import (
        RecommendationRuleRepo,
        RecommendationRuleTransitionError,
    )

    repo = RecommendationRuleRepo(session)
    rec = repo.create_draft(
        tenant_id="sd-default",
        rule_code="bad_l2x_v1",
        title="bad",
        payload=_build_rule_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    repo.promote_to_preview(rec.id)
    repo.commit_to_live(rec.id)
    with pytest.raises(RecommendationRuleTransitionError):
        repo.promote_to_preview(rec.id)
    with pytest.raises(RecommendationRuleTransitionError):
        repo.revert_to_draft(rec.id)
    with pytest.raises(RecommendationRuleTransitionError):
        repo.commit_to_live(rec.id)


# ──────────────────────────────────────────────────────────────────────────
# payload 校验
# ──────────────────────────────────────────────────────────────────────────

def test_clauses_non_empty(session):
    from zw_brain.domain.recommendation_rule import (
        RecommendationRulePayloadError,
        RecommendationRuleRepo,
    )

    repo = RecommendationRuleRepo(session)
    with pytest.raises(RecommendationRulePayloadError):
        repo.create_draft(
            tenant_id="sd-default",
            rule_code="empty",
            title="empty",
            payload={"clauses": []},
            created_by="user:gov:ROLE_ORGAN_MANAGER:test",
        )


def test_clause_codes_unique(session):
    from zw_brain.domain.recommendation_rule import (
        RecommendationRulePayloadError,
        RecommendationRuleRepo,
    )

    payload = _build_rule_payload()
    payload["clauses"].append(payload["clauses"][0])  # 复制第一条 → 重复 code
    repo = RecommendationRuleRepo(session)
    with pytest.raises(RecommendationRulePayloadError):
        repo.create_draft(
            tenant_id="sd-default",
            rule_code="dup_code",
            title="dup",
            payload=payload,
            created_by="user:gov:ROLE_ORGAN_MANAGER:test",
        )


def test_unsupported_clause_kind_raises(session):
    from zw_brain.domain.recommendation_rule import (
        RecommendationRulePayloadError,
        RecommendationRuleRepo,
    )

    payload = _build_rule_payload()
    payload["clauses"][0]["clause_kind"] = "embedding_cosine"  # unsupported
    repo = RecommendationRuleRepo(session)
    with pytest.raises(RecommendationRulePayloadError):
        repo.create_draft(
            tenant_id="sd-default",
            rule_code="bad_kind",
            title="bad",
            payload=payload,
            created_by="user:gov:ROLE_ORGAN_MANAGER:test",
        )


# ──────────────────────────────────────────────────────────────────────────
# 引擎评分
# ──────────────────────────────────────────────────────────────────────────

def _seed_history_and_catalog(session, tenant_id: str = "sd-default") -> dict:
    """Seed RequirementHistory + CatalogItem 从 fixture；幂等（已存在则跳过）。"""
    from sqlalchemy import select

    from zw_brain.domain.models import (
        CatalogItemRecord,
        RequirementHistoryRecord,
    )

    data = json.loads((FIXTURES_DIR / "dsp_require_sample.json").read_text(encoding="utf-8"))
    catalog_ids: set[str] = set()
    existing_require_ids = {
        row[0]
        for row in session.execute(
            select(RequirementHistoryRecord.source_require_id).where(
                RequirementHistoryRecord.tenant_id == tenant_id
            )
        ).all()
    }
    for rec in data["records"]:
        if rec.get("catalog_id"):
            catalog_ids.add(rec["catalog_id"])
        if rec["source_require_id"] in existing_require_ids:
            continue
        session.add(
            RequirementHistoryRecord(
                tenant_id=tenant_id,
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
        for row in session.execute(
            select(CatalogItemRecord.item_code).where(
                CatalogItemRecord.tenant_id == tenant_id
            )
        ).all()
    }
    for idx, cid in enumerate(sorted(catalog_ids)):
        item_code = f"item-{cid}"
        if item_code in existing_item_codes:
            continue
        first = next(r for r in data["records"] if r.get("catalog_id") == cid)
        session.add(
            CatalogItemRecord(
                tenant_id=tenant_id,
                item_code=item_code,
                catalog_code=cid,
                resource_code=first.get("resource_id"),
                title=first["name"],
                item_kind="dataset",
                display_order=idx,
                summary_json={"seed": "F6 fixture"},
            )
        )
    session.commit()
    return {"records": data["records"], "catalog_ids": sorted(catalog_ids)}


def _seed_jinzhou_rules(session, tenant_id: str = "sd-default") -> list:
    from sqlalchemy import select

    from zw_brain.domain.models import RecommendationRuleRecord
    from zw_brain.domain.recommendation_rule import RecommendationRuleRepo

    data = json.loads(
        (FIXTURES_DIR / "jinzhou_recommendation_rules.json").read_text(encoding="utf-8")
    )
    repo = RecommendationRuleRepo(session)
    existing_codes = {
        row[0]
        for row in session.execute(
            select(RecommendationRuleRecord.rule_code).where(
                RecommendationRuleRecord.tenant_id == tenant_id
            )
        ).all()
    }
    committed: list = []
    for rule in data["rules"]:
        if rule["rule_code"] in existing_codes:
            continue
        rec = repo.create_draft(
            tenant_id=tenant_id,
            rule_code=rule["rule_code"],
            title=rule["title"],
            payload=rule["payload"],
            created_by="user:gov:ROLE_ORGAN_MANAGER:fixture",
        )
        repo.promote_to_preview(rec.id)
        live = repo.commit_to_live(rec.id)
        committed.append(live)
    return committed


def test_engine_suggest_via_keyword_rule(session):
    from zw_brain.domain.recommendation_engine import RecommendationEngine

    _seed_history_and_catalog(session)
    _seed_jinzhou_rules(session)

    engine = RecommendationEngine(session)
    candidates = engine.suggest("sd-default", intent_text="残疾人证补办", top_k=5)
    assert candidates, "残疾人 关键词应至少命中一个候选"
    assert any(c.catalog_id == "cat-disabled-info-001" for c in candidates)


def test_engine_returns_empty_when_below_threshold(session):
    from zw_brain.domain.recommendation_engine import RecommendationEngine

    _seed_history_and_catalog(session)
    _seed_jinzhou_rules(session)
    engine = RecommendationEngine(session, score_threshold=10.0)  # 极高阈值
    candidates = engine.suggest("sd-default", intent_text="残疾人证补办", top_k=5)
    assert candidates == []


def test_engine_register_manual_requirement_fallback(session):
    from zw_brain.domain.recommendation_engine import RecommendationEngine

    engine = RecommendationEngine(session)
    rec = engine.register_manual_requirement(
        tenant_id="sd-default",
        submitted_by="user:gov:ROLE_ORGAN_OPERATER:fixture",
        intent_text="某种无规则可命中的小众需求",
    )
    assert rec.submission_kind == "manual_requirement"
    assert rec.target_catalog_id is None


def test_engine_record_recommended_pick_audits_candidates(session):
    from zw_brain.domain.recommendation_engine import (
        RecommendationCandidate,
        RecommendationEngine,
    )

    engine = RecommendationEngine(session)
    fake_candidates = [
        RecommendationCandidate(
            catalog_id="cat-X", catalog_title="X", score=0.9, hit_clauses=["c1"], source_history_ids=[]
        )
    ]
    rec = engine.record_recommended_pick(
        tenant_id="sd-default",
        submitted_by="user:gov:ROLE_ORGAN_OPERATER:fixture",
        intent_text="挑了 X",
        candidates=fake_candidates,
        picked_catalog_id="cat-X",
    )
    assert rec.submission_kind == "recommended_pick"
    assert rec.target_catalog_id == "cat-X"
    assert rec.recommendation_audit_json["picked_catalog_id"] == "cat-X"
    assert len(rec.recommendation_audit_json["candidates"]) == 1


# ──────────────────────────────────────────────────────────────────────────
# skill 端到端
# ──────────────────────────────────────────────────────────────────────────

def test_commit_rule_skill_returns_ok_and_audit_id(session):
    from zw_brain.command.brain import BrainService
    from zw_brain.domain.recommendation_rule import RecommendationRuleRepo
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    repo = RecommendationRuleRepo(session)
    rec = repo.create_draft(
        tenant_id="sd-default",
        rule_code="dispatch_e2e_v1",
        title="dispatch e2e",
        payload=_build_rule_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:fixture",
    )
    repo.promote_to_preview(rec.id)

    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    audit_bus.clear_sink()
    audit_bus.configure_sink(ds.append_audit_event)
    try:
        brain = BrainService(state_store=ss)
        result = invoke_trusted(
                     brain,
                     "recommendation.rule.commit",
                     {
                "tenant_id": "sd-default",
                "rule_id": rec.id,
                "confirmed": True,
            },
                     role="ROLE_ORGAN_MANAGER",
                 )
    finally:
        audit_bus.clear_sink()

    assert result["ok"] is True
    assert result["skill_id"] == "recommendation.rule.commit"
    assert result["audit_id"]
    assert result["result"]["rule_id"] == rec.id
    assert result["result"]["version"] == 2


def test_suggest_skill_returns_candidates_or_fallback(session):
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    _seed_history_and_catalog(session)
    _seed_jinzhou_rules(session)

    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    brain = BrainService(state_store=ss)
    result = invoke_trusted(
                 brain,
                 "recommendation.similar_catalog.suggest",
                 {
            "tenant_id": "sd-default",
            "intent_text": "残疾人证补办",
            "submitted_by": "user:gov:ROLE_ORGAN_OPERATER:fixture",
            "top_k": 5,
        },
                 role="ROLE_ORGAN_OPERATER",
             )
    assert result["ok"] is True
    assert result["skill_id"] == "recommendation.similar_catalog.suggest"
    res = result["result"]
    assert isinstance(res["candidates"], list)
    assert res["fallback_required"] is False  # 残疾人 应命中

    # 不命中 + fallback 路径在 test_engine_register_manual_requirement_fallback 直接覆盖
    # （走 skill dispatch 时 tenant scope 守卫强制 sd-default，命中规则在；
    #  「无规则租户」场景在 skill 层不可达，是 policy 设计）


# ──────────────────────────────────────────────────────────────────────────
# 真实 5 条 dsp_require 命中率（≥ 20% 即 ≥1/5）
# ──────────────────────────────────────────────────────────────────────────

def test_suggest_against_5_real_dsp_require_history_hits_at_least_one(session, capsys):
    from zw_brain.domain.recommendation_engine import RecommendationEngine

    seed = _seed_history_and_catalog(session)
    _seed_jinzhou_rules(session)

    engine = RecommendationEngine(session)
    records = seed["records"]
    hits = 0
    for rec in records:
        candidates = engine.suggest(
            tenant_id="sd-default",
            intent_text=rec["name"],
            intent_org=rec.get("org"),
            top_k=5,
        )
        top_match = bool(candidates) and candidates[0].catalog_id == rec["catalog_id"]
        if top_match:
            hits += 1

    hit_rate = hits / len(records)
    print(f"\n[F6 hit-rate report] real dsp_require history N={len(records)}, hits={hits}, rate={hit_rate:.2%}")
    captured = capsys.readouterr()
    assert "hit-rate" in captured.out
    assert hit_rate >= 0.2, f"hit-rate {hit_rate:.2%} < 20% baseline"


def test_manifests_registered_and_validate() -> None:
    from zw_brain.skill_registration.runtime import load_manifests

    manifests = load_manifests()
    assert "recommendation.rule.commit" in manifests
    assert "recommendation.similar_catalog.suggest" in manifests
    m_rule = manifests["recommendation.rule.commit"]
    m_sug = manifests["recommendation.similar_catalog.suggest"]
    assert m_rule["audit_class"] == "write-critical"
    assert m_rule["product_scope"]["journey"] == "b1"
    assert m_sug["audit_class"] == "read-normal"
    assert m_sug["product_scope"]["journey"] == "j1"
    assert m_sug["human_confirmation_required"] is False
