"""J1 供需对接 repository — 复用 application_record 表存 demand + business_requirement.

设计取舍（plan e1-j1-journey F4）:
- meta 合并而非数据合并：BR (BusinessRequirement) 不复制原始 demand 的业务字段
  (purpose / period / files 等)；仅持 application_ids 列表 + merge_reason + 时间戳。
- 不引入新 schema：复用 application_record 表，kind='demand' / 'business_requirement'
  存于 payload_json["kind"]；6 步 phase 存于 payload_json["demand_phase"]；BR 引用
  存于 payload_json["application_ids"]。
- 规则匹配（同 title 前缀 / 同 target_resource_hint）；AI 推荐归 E3 Wave 2，不在本期。

国家通道占位 (feature §scenario 5)：payload_json["channel_class"]="national" 即
标识；Wave 1 不实施完整国家直达流程。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import ApplicationRecord
from zw_brain.domain.repositories.application import ApplicationRepository
from zw_brain.domain.supply_demand_phase import (
    PHASE_GAP_DISCOVERED,
    PHASE_PROVIDER_RESPONDED,
    PHASE_SUBSCRIBED,
    assert_phase_transition,
)
from zw_brain.shared.db import create_session_factory


def _load_payload(record: ApplicationRecord) -> dict[str, Any]:
    raw = record.payload_json
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return dict(raw or {})


class SupplyDemandRepository:
    def __init__(self) -> None:
        self.app_repo = ApplicationRepository()

    # ------------------------------------------------------------------
    # demand lifecycle (6 步 phase)
    # ------------------------------------------------------------------

    def register_demand(
        self,
        *,
        demand_id: str,
        title: str,
        applicant: str,
        applicant_dept: str,
        tenant_id: str = "sd-default",
        target_resource_hint: str | None = None,
        channel_class: str = "internal",
        phase: str = PHASE_GAP_DISCOVERED,
    ) -> dict[str, Any]:
        """登记需求 (P3 供需对接段「找不到数据」入口)."""
        payload = {
            "id": demand_id,
            "status": "submitted",
            "applicant": applicant,
            "applicantDept": applicant_dept,
            "kind": "demand",
            "title": title,
            "demand_phase": phase,
            "target_resource_hint": target_resource_hint,
            "channel_class": channel_class,
        }
        self.app_repo.upsert_from_request(payload, tenant_id=tenant_id)
        return payload

    def advance_phase(
        self,
        demand_id: str,
        next_phase: str,
        *,
        tenant_id: str = "sd-default",
    ) -> dict[str, Any]:
        record = self._get_record(demand_id, tenant_id=tenant_id)
        payload = _load_payload(record)
        if payload.get("kind") != "demand":
            raise KeyError(f"not a demand record: {demand_id}")
        current = str(payload.get("demand_phase") or PHASE_GAP_DISCOVERED)
        assert_phase_transition(current, next_phase)
        payload["demand_phase"] = next_phase
        if next_phase == PHASE_PROVIDER_RESPONDED:
            payload["status"] = "approved"
        elif next_phase == PHASE_SUBSCRIBED:
            payload["status"] = "effective"
        self.app_repo.upsert_from_request(payload, tenant_id=tenant_id)
        return payload

    def get_demand(self, demand_id: str, *, tenant_id: str = "sd-default") -> dict[str, Any] | None:
        record = self._get_record(demand_id, tenant_id=tenant_id, required=False)
        if record is None:
            return None
        return _load_payload(record)

    def list_demands(
        self, *, tenant_id: str = "sd-default", phase: str | None = None
    ) -> list[dict[str, Any]]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            records = list(
                session.execute(
                    select(ApplicationRecord)
                    .where(ApplicationRecord.tenant_id == tenant_id)
                ).scalars()
            )
        out: list[dict[str, Any]] = []
        for r in records:
            payload = _load_payload(r)
            if payload.get("kind") != "demand":
                continue
            if phase is not None and payload.get("demand_phase") != phase:
                continue
            out.append(payload)
        return out

    # ------------------------------------------------------------------
    # Business Requirement (meta 合并)
    # ------------------------------------------------------------------

    def create_business_requirement(
        self,
        *,
        br_id: str,
        application_ids: list[str],
        merge_reason: str,
        merged_by: str,
        merged_by_role: str,
        tenant_id: str = "sd-default",
    ) -> dict[str, Any]:
        """meta 合并：BR 仅存 application_ids + 合并理由，不复制 application 业务字段."""
        if merged_by_role != "ROLE_BUSIAUDIT":
            raise PermissionError(
                "merge into business_requirement requires ROLE_BUSIAUDIT"
            )
        if len(application_ids) < 2:
            raise ValueError("business requirement merge needs at least 2 application_ids")
        payload = {
            "id": br_id,
            "status": "submitted",
            "applicant": merged_by,
            "applicantDept": "BUSIAUDIT",
            "kind": "business_requirement",
            "application_ids": list(application_ids),
            "merge_reason": merge_reason,
            "br_status": "dispatched",  # 已派发
        }
        self.app_repo.upsert_from_request(payload, tenant_id=tenant_id)
        return payload

    def update_business_requirement_status(
        self,
        br_id: str,
        br_status: str,
        *,
        tenant_id: str = "sd-default",
    ) -> dict[str, Any]:
        """BR 状态流转：dispatched → responded → evaluated (feature §scenario 1 末段)."""
        record = self._get_record(br_id, tenant_id=tenant_id)
        payload = _load_payload(record)
        if payload.get("kind") != "business_requirement":
            raise KeyError(f"not a business requirement: {br_id}")
        allowed_next = {
            "dispatched": {"responded"},
            "responded": {"evaluated"},
            "evaluated": set(),
        }
        current = str(payload.get("br_status") or "dispatched")
        if br_status not in allowed_next.get(current, set()):
            raise ValueError(
                f"invalid business_requirement status transition: {current} -> {br_status}"
            )
        payload["br_status"] = br_status
        if br_status == "evaluated":
            payload["status"] = "effective"
        self.app_repo.upsert_from_request(payload, tenant_id=tenant_id)
        return payload

    def remove_application_from_business_requirement(
        self,
        br_id: str,
        application_id: str,
        *,
        reason: str,
        tenant_id: str = "sd-default",
    ) -> dict[str, Any]:
        """原始申请撤回时，从 BR.application_ids 自动剔除 + 留事件记录."""
        record = self._get_record(br_id, tenant_id=tenant_id)
        payload = _load_payload(record)
        if payload.get("kind") != "business_requirement":
            raise KeyError(f"not a business requirement: {br_id}")
        ids = list(payload.get("application_ids", []))
        if application_id not in ids:
            return payload
        ids.remove(application_id)
        events = list(payload.get("events", []))
        events.append({"event": "application_removed", "application_id": application_id, "reason": reason})
        payload["application_ids"] = ids
        payload["events"] = events
        self.app_repo.upsert_from_request(payload, tenant_id=tenant_id)
        return payload

    # ------------------------------------------------------------------
    # 规则匹配 (Wave 1 — AI 推荐归 E3)
    # ------------------------------------------------------------------

    def cluster_similar_demands(
        self,
        demands: list[dict[str, Any]],
        *,
        title_prefix_len: int = 6,
    ) -> list[list[dict[str, Any]]]:
        """规则聚类：同标题前缀 N 字符 + 同 target_resource_hint 归一簇.

        Wave 1 stub；AI 推荐升级见 E3 Wave 2 reverse_draft_suggest.search_intent_parse.
        """
        clusters: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for d in demands:
            title = str(d.get("title") or "")
            hint = str(d.get("target_resource_hint") or "")
            key = (title[:title_prefix_len], hint)
            clusters.setdefault(key, []).append(d)
        return [v for v in clusters.values() if len(v) >= 1]

    def find_resource_match(
        self,
        title: str,
        target_resource_hint: str | None,
        *,
        catalog_titles: list[str],
    ) -> str | None:
        """规则匹配命中：title 子串出现在某个 catalog title → 返回；否则 None."""
        for cat in catalog_titles:
            if title and (title in cat or cat in title):
                return cat
            if target_resource_hint and target_resource_hint in cat:
                return cat
        return None

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _get_record(
        self,
        application_code: str,
        *,
        tenant_id: str,
        required: bool = True,
    ) -> ApplicationRecord | None:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(ApplicationRecord).where(
                    ApplicationRecord.tenant_id == tenant_id,
                    ApplicationRecord.application_code == application_code,
                )
            ).scalar_one_or_none()
        if record is None and required:
            raise KeyError(application_code)
        return record
