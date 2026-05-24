"""E3 Wave-2 三引擎 F6 — 智能推荐引擎执行端。

读 live 规则 + RequirementHistory + CatalogItem，按 6 种 clause_kind 评分；
低于阈值 → 空列表，由调用方决定是否走 fallback 人工登记。

不引外部 NLP 库；fuzzy_text 用纯 Python token-overlap（jieba 等不在 F6 范围）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from zw_brain.domain.models import (
    CatalogItemRecord,
    RecommendationRuleClauseRecord,
    RequirementHistoryRecord,
    RequirementSubmissionRecord,
)
from zw_brain.domain.recommendation_rule import RecommendationRuleRepo

DEFAULT_SCORE_THRESHOLD = 0.1
DEFAULT_TOP_K = 5


@dataclass
class RecommendationCandidate:
    catalog_id: str
    catalog_title: str
    score: float
    hit_clauses: list[str] = field(default_factory=list)
    source_history_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "catalog_id": self.catalog_id,
            "catalog_title": self.catalog_title,
            "score": round(self.score, 4),
            "hit_clauses": list(self.hit_clauses),
            "source_history_ids": list(self.source_history_ids),
        }


def _tokenize(text: str) -> set[str]:
    """简单 token 化：去标点，按字符 bigram + 整词分。中文场景够用。"""
    text = (text or "").lower().strip()
    if not text:
        return set()
    cleaned = "".join(ch if ch.isalnum() or "一" <= ch <= "鿿" else " " for ch in text)
    tokens: set[str] = set()
    for word in cleaned.split():
        if word:
            tokens.add(word)
            if len(word) >= 2:
                for i in range(len(word) - 1):
                    tokens.add(word[i : i + 2])
    return tokens


class RecommendationEngine:
    """6 种 clause_kind：keyword_match / category_match / org_affinity /
    usage_frequency / fuzzy_text / negative_filter；规则 weight 线性叠加。
    """

    def __init__(
        self,
        session: Session,
        *,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    ) -> None:
        self._session = session
        self._score_threshold = score_threshold

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def suggest(
        self,
        tenant_id: str,
        intent_text: str,
        *,
        intent_org: str | None = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[RecommendationCandidate]:
        rules = RecommendationRuleRepo(self._session).list_live(tenant_id)
        if not rules:
            return []

        rule_ids = [rule.id for rule in rules]
        clauses = list(
            self._session.execute(
                select(RecommendationRuleClauseRecord).where(
                    RecommendationRuleClauseRecord.rule_id.in_(rule_ids)
                )
            ).scalars()
        )

        catalog_items = list(
            self._session.execute(
                select(CatalogItemRecord).where(CatalogItemRecord.tenant_id == tenant_id)
            ).scalars()
        )
        histories = list(
            self._session.execute(
                select(RequirementHistoryRecord).where(
                    RequirementHistoryRecord.tenant_id == tenant_id
                )
            ).scalars()
        )

        history_count_by_catalog: dict[str, int] = {}
        history_ids_by_catalog: dict[str, list[str]] = {}
        for h in histories:
            if h.catalog_id:
                history_count_by_catalog[h.catalog_id] = history_count_by_catalog.get(h.catalog_id, 0) + 1
                history_ids_by_catalog.setdefault(h.catalog_id, []).append(h.id)

        intent_tokens = _tokenize(intent_text)
        intent_org_value = (intent_org or "").strip()

        # 推荐候选池：CatalogItem ∪ history.catalog_id（fixture 场景下 catalog_item 可能没建，但 history 有 catalog_id）
        catalog_by_id: dict[str, dict[str, Any]] = {}
        for item in catalog_items:
            catalog_id_key = item.catalog_code or item.id
            catalog_by_id[catalog_id_key] = {
                "catalog_id": catalog_id_key,
                "title": item.title or item.catalog_code,
            }
        for cid in history_count_by_catalog:
            if cid not in catalog_by_id:
                # 用历史申请的 name 作为 catalog 标题占位（fixture 场景）
                for h in histories:
                    if h.catalog_id == cid:
                        catalog_by_id[cid] = {"catalog_id": cid, "title": h.name}
                        break

        candidates: dict[str, RecommendationCandidate] = {}
        for catalog_id, meta in catalog_by_id.items():
            score, hit_codes = self._score_catalog(
                catalog_id=catalog_id,
                catalog_title=meta["title"],
                clauses=clauses,
                intent_tokens=intent_tokens,
                intent_org=intent_org_value,
                history_count=history_count_by_catalog.get(catalog_id, 0),
                histories=histories,
            )
            if score <= 0:
                continue
            candidate = RecommendationCandidate(
                catalog_id=catalog_id,
                catalog_title=meta["title"],
                score=score,
                hit_clauses=hit_codes,
                source_history_ids=history_ids_by_catalog.get(catalog_id, []),
            )
            candidates[catalog_id] = candidate

        ranked = sorted(candidates.values(), key=lambda c: c.score, reverse=True)
        if not ranked or ranked[0].score < self._score_threshold:
            return []
        return ranked[:top_k]

    def register_manual_requirement(
        self,
        tenant_id: str,
        submitted_by: str,
        intent_text: str,
    ) -> RequirementSubmissionRecord:
        record = RequirementSubmissionRecord(
            tenant_id=tenant_id,
            submitted_by=submitted_by,
            intent_text=intent_text,
            submission_kind="manual_requirement",
            target_catalog_id=None,
            recommendation_audit_json={"candidates": [], "reason": "no_match_above_threshold"},
        )
        self._session.add(record)
        self._session.commit()
        return record

    def record_recommended_pick(
        self,
        tenant_id: str,
        submitted_by: str,
        intent_text: str,
        candidates: list[RecommendationCandidate],
        picked_catalog_id: str,
    ) -> RequirementSubmissionRecord:
        record = RequirementSubmissionRecord(
            tenant_id=tenant_id,
            submitted_by=submitted_by,
            intent_text=intent_text,
            submission_kind="recommended_pick",
            target_catalog_id=picked_catalog_id,
            recommendation_audit_json={
                "candidates": [c.to_dict() for c in candidates],
                "picked_catalog_id": picked_catalog_id,
            },
        )
        self._session.add(record)
        self._session.commit()
        return record

    # ------------------------------------------------------------------
    # 评分内部
    # ------------------------------------------------------------------

    def _score_catalog(
        self,
        *,
        catalog_id: str,
        catalog_title: str,
        clauses: list[RecommendationRuleClauseRecord],
        intent_tokens: set[str],
        intent_org: str,
        history_count: int,
        histories: list[RequirementHistoryRecord],
    ) -> tuple[float, list[str]]:
        title_tokens = _tokenize(catalog_title)
        score = 0.0
        hit_codes: list[str] = []
        history_titles = [h.name for h in histories if h.catalog_id == catalog_id]

        for clause in clauses:
            payload = clause.clause_payload_json or {}
            weight = float(clause.weight or 1.0)
            kind = clause.clause_kind
            hit = False
            delta = 0.0

            if kind == "keyword_match":
                keywords = [str(k).lower() for k in payload.get("keywords", []) if k]
                # 命中条件：keyword 落在 intent_tokens 里 或 catalog 标题里
                for kw in keywords:
                    kw_tokens = _tokenize(kw)
                    if kw_tokens & intent_tokens or kw_tokens & title_tokens:
                        hit = True
                        delta = weight
                        break
            elif kind == "category_match":
                target_categories = {str(c) for c in payload.get("categories", [])}
                # fixture 场景：catalog 没真分类，用 title 关键字 fallback
                catalog_category = str(payload.get("catalog_category_hint", catalog_title))
                if target_categories and any(c in catalog_category for c in target_categories):
                    hit = True
                    delta = weight
            elif kind == "org_affinity":
                org_list = {str(o) for o in payload.get("orgs", [])}
                if intent_org and intent_org in org_list:
                    hit = True
                    delta = weight
            elif kind == "usage_frequency":
                # 历史次数 × weight × scale
                scale = float(payload.get("scale", 0.2))
                min_count = int(payload.get("min_count", 1))
                if history_count >= min_count:
                    hit = True
                    delta = weight * scale * history_count
            elif kind == "fuzzy_text":
                # token overlap 比例 × weight
                if intent_tokens and title_tokens:
                    overlap = len(intent_tokens & title_tokens)
                    union = len(intent_tokens | title_tokens)
                    similarity = overlap / union if union else 0.0
                    # 也对历史 title 算一次 max
                    for ht in history_titles:
                        ht_tokens = _tokenize(ht)
                        if ht_tokens:
                            ov2 = len(intent_tokens & ht_tokens)
                            un2 = len(intent_tokens | ht_tokens)
                            similarity = max(similarity, ov2 / un2 if un2 else 0.0)
                    if similarity > 0:
                        hit = True
                        delta = weight * similarity
            elif kind == "negative_filter":
                blockers = [str(b).lower() for b in payload.get("blockers", []) if b]
                for blocker in blockers:
                    b_tokens = _tokenize(blocker)
                    if b_tokens & intent_tokens or b_tokens & title_tokens:
                        hit = True
                        delta = -weight
                        break

            if hit:
                score += delta
                hit_codes.append(clause.clause_code)

        return score, hit_codes
