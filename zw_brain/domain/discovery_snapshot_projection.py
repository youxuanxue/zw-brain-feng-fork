"""Live J1 list projections for WebUI snapshot — DB is the single source of truth.

C-1（去 snapshot↔DB 双轨）：``system.snapshot`` 的 J1 核心列表字段（``requests`` /
``approvals`` / ``discovery.resources``）**始终从 DB 现算投影**，不再以 ``seed_snapshot.json``
的演示记录为基底。

投影策略：**无条件以 DB 投影为准**——DB 有行给全量真实，DB 空 → **诚实空列表**（不回退
演示单）。这是「DB 单一事实源」的落点：内存快照不再承载可与 DB 分歧的业务真相，演示单随
seed 删除一并消失，真实数据的字段缺口/冲突自然浮出而非被 demo 掩盖。

轻量 serializer：只产页面列表**真正读**的字段，不做 per-record resource / delivery /
legacy 查找——那是 ``application_service.record_to_request`` 详情序列化器的活，对数百条
列表会炸 D-9 perf 预算。详情页仍走重序列化器，本模块只喂收件箱/发现列表。
"""

from __future__ import annotations

import copy
from typing import Any

from zw_brain.domain.data_quality import classify_purpose, is_dirty_purpose, purpose_from_payload
from zw_brain.domain.repositories.application import ApplicationRepository
from zw_brain.domain.repositories.approval import ApprovalRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.domain.resource_kind import canonical_resource_kind
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id
from zw_brain.shared.sensitive_mask import mask_default

# application_record.payload_json.kind：apply / None = 申请（有 resource_name，进 P3 在途申请）；
# require / original_require = 需求（无 resource_name，属 J2 供需匹配线，不进 P3 申请收件箱）。
_DEMAND_KINDS = frozenset({"require", "original_require"})

# resource_asset.lifecycle_status → 发现页展示态
_RESOURCE_STATUS_DISPLAY = {
    "active": "可复用",
    "approved_pending_publish": "待发布",
    "pending_review": "审核中",
    "draft": "草稿",
    "suspended": "已暂停",
    "expired": "已过期",
    "revoked": "已下线",
}

# 发现页只展示「已发布」资源（D53① 业务裁决 2026-06-06，反转 D45.b）：仅 active（可复用/已发布）。
# 待发布 approved_pending_publish 退出默认发现视图——未发布不应在消费端可见、更不可申请
# （用户反馈 0605#1：只有已发布才可供申请使用）。草稿/审核中/待发布/已暂停/已下线/已过期
# 均不进发现视图（资源详情/目录线仍可达，仅不在「找数据」列表 + 不可申请）。
_DISCOVERABLE_STATUSES = frozenset({"active"})

# 无意义 desc 占位值（真实库 res_desc 82% 是空/「无」/标题复读 → 卡片不渲染噪声）
_DESC_NOISE = frozenset({"", "无", "-", "暂无", "无。"})

# 共享类型 access_policy_json.share_type → 中文（决策信号：能不能拿、要不要审批）。
# **权威来源 = 源表 dc_resource_base_info DDL 注释「1：无条件共享 2：有条件共享 3：不予共享」
# + 真实数据双重确认**（人口信息=2=有条件 / 学校名单=1=无条件）。注意：approval_flow_baseline 的
# SHARED_TYPE 常量是反的（1=有条件），那是审批流另一码空间，**禁止用于资源卡**。
_SHARE_TYPE_DISPLAY = {
    "1": "无条件共享",
    "2": "有条件共享",
    "3": "不予共享",
    "unconditional": "无条件共享",
    "conditional": "有条件共享",
}
# 卡片色级：无条件=畅通 / 有条件=需审批 / 不予=不可得
_SHARE_TYPE_LEVEL = {"无条件共享": "open", "有条件共享": "conditional", "不予共享": "closed"}


# ───────────────────────────────────────────────────────────────────────────
# requests — P3RequestFlow 在途申请 + P3RequestDetail 预填底座
# ───────────────────────────────────────────────────────────────────────────

def _record_to_request_card(record: Any) -> dict[str, Any]:
    """application_record → 轻量申请卡（snake→camel；applicant PII 走 mask_default）。

    本组（数据呈现规范化 + 角色投影）追加 3 个**诚实信号**，供前端三视图 / 供方质量队列：
      - ``isLegacyImport``：源自旧平台导入（payload 有 source_ref / legacy_object_ref）
        ⇒ 列表给克制的「历史导入」次要标识，帮用户理解为何有 2023 年的单子（缺陷 3）。
        D47.b：历史导入单的**在线动作混合门控**是已记账债，本组只做呈现层区分、不做动作门控。
      - ``purposeQuality`` / ``purposeDirty``：用途脏值机械化判定（data_quality 单源）；
        前端据此降级显示「未填写用途」，脏单计入供方数据质量队列（缺陷 3）。
    """
    payload = copy.deepcopy(record.payload_json or {})
    applicant = mask_default(
        {"applicant_name": record.applicant_name, "applicant_org": record.applicant_org}
    )
    raw_purpose = purpose_from_payload(payload)
    is_legacy_import = bool(payload.get("source_ref") or payload.get("legacy_object_ref"))
    return {
        "id": payload.get("id") or record.application_code,
        "resourceId": payload.get("resourceId") or payload.get("resource_id") or "",
        "resourceName": payload.get("resource_name") or payload.get("resourceName") or "",
        "applicant": applicant["applicant_name"],
        "applicantOrgId": payload.get("applicant_org_id") or "",
        "applicantDept": payload.get("applicantDept")
        or payload.get("applicant_org_name")
        or applicant["applicant_org"],
        "providerOrgId": payload.get("provider_org_id") or "",
        "providerOrgName": payload.get("provider_org_name") or "",
        "purpose": raw_purpose,
        # 用途脏值诚实信号（data_quality 单源；前端 dataQuality.ts 镜像降级渲染）。
        "purposeQuality": classify_purpose(raw_purpose),
        "purposeDirty": is_dirty_purpose(raw_purpose),
        "status": payload.get("status") or "",
        # 来源诚实标识（缺陷 3）：旧平台导入 vs 在产单视觉区分。
        "isLegacyImport": is_legacy_import,
        # 国家通道指示（C9）：channel_class=='national' 标识「请求国家级数据」的申请，
        # 供 P3 国家通道 tab 筛「待转报」队列（dept_approved ∩ national），不再误列 own-items。
        # 真实信号取 payload_json["channel_class"]（supply_demand §scenario 5 占位口径）；缺省 internal。
        "channelClass": str(payload.get("channel_class") or "internal"),
        "submittedAt": payload.get("submittedAt") or payload.get("create_time") or "",
        "sharingType": payload.get("sharingType"),
    }


def enrich_requests_snapshot(snapshot: dict[str, Any], *, tenant_id: str | None = None) -> dict[str, Any]:
    """Project snapshot['requests'] from the real **application** table (DB single SoT).

    只取申请类（kind ∉ _DEMAND_KINDS）；需求类记录无 resource_name、属 J2 供需线，
    不进 P3「在途申请」收件箱。**无条件替换**：空库 → 空列表（诚实空，不回退 seed 演示单）。
    """
    out = copy.deepcopy(snapshot)
    records = [
        r
        for r in ApplicationRepository().list_records(tenant_id=tenant_id or get_runtime_tenant_id())
        if (r.payload_json or {}).get("kind") not in _DEMAND_KINDS
    ]
    out["requests"] = [_record_to_request_card(r) for r in records]
    return out


# ───────────────────────────────────────────────────────────────────────────
# approvals — P3RequestFlow 审批人收件箱（按 id 交叉引用 requests 取状态/资源名）
# ───────────────────────────────────────────────────────────────────────────

def _case_to_approval_card(record: Any) -> dict[str, Any]:
    # P3RequestFlow 只读 it.id + (it.suggestion ?? '待审')；状态/资源从 requests 交叉引用。
    return {"id": record.application_code, "suggestion": "待审"}


def enrich_approvals_snapshot(snapshot: dict[str, Any], *, tenant_id: str | None = None) -> dict[str, Any]:
    """Project snapshot['approvals'] from the real approval_case table (DB single SoT).

    **无条件替换**：空库 → 空列表（诚实空，不回退 seed）。legacy 导入的 approval_case
    经此现算投影，不再陈旧（关 approval-case-projection-stale）。
    """
    out = copy.deepcopy(snapshot)
    cases = ApprovalRepository().list_cases(tenant_id=tenant_id or get_runtime_tenant_id())
    out["approvals"] = [_case_to_approval_card(c) for c in cases]
    return out


# ───────────────────────────────────────────────────────────────────────────
# discovery.resources — P2Discovery 「可复用资源」（资源中心，架构 §5.2.1）
# ───────────────────────────────────────────────────────────────────────────

def _asset_to_resource_card(record: Any) -> dict[str, Any]:
    owner = record.owner_org_snapshot_json or {}
    summary = record.summary_json or {}
    access = record.access_policy_json or {}
    raw_desc = str(summary.get("res_desc") or "").strip()
    desc = "" if raw_desc in _DESC_NOISE or raw_desc == (record.title or "").strip() else raw_desc
    share_type = _SHARE_TYPE_DISPLAY.get(str(access.get("share_type")).strip().lower(), "")
    return {
        "id": record.resource_code,
        "name": record.title,
        "status": _RESOURCE_STATUS_DISPLAY.get(record.lifecycle_status, record.lifecycle_status),
        "shareType": share_type,
        "shareLevel": _SHARE_TYPE_LEVEL.get(share_type, ""),
        "provider": owner.get("org_name") or owner.get("owner_org_name") or record.owner_org_id or "",
        "providerOrgCode": record.owner_org_id or "",
        "regionCode": record.region_code or "",
        "catalogCode": record.catalog_code or "",
        "desc": desc,
        "updatedAt": record.updated_at.strftime("%Y-%m-%d") if getattr(record, "updated_at", None) else "",
        # 读路径折叠（D53）：存量库 legacy folder/url/link 经 canonical 归入 file，绝不泄漏到
        # 发现卡徽标 / 「资源类型」筛选项（写侧 _normalize_resource_kind 只管新入库行）。
        "kind": canonical_resource_kind(record.resource_kind),
    }


def project_resource_cards(*, tenant_id: str | None = None) -> list[dict[str, Any]]:
    """发现页「可复用资源」卡片 — 共享给 snapshot enrich + data.search 空 query。

    只投影**可用**资源（D45.b：active + approved_pending_publish）；草稿/审核中/已暂停/
    已下线/已过期不进默认发现视图。
    """
    records = ResourceApiRepository().list_assets(tenant_id=tenant_id or get_runtime_tenant_id())
    return [
        _asset_to_resource_card(r)
        for r in records
        if r.lifecycle_status in _DISCOVERABLE_STATUSES
    ]


def enrich_discovery_resources_snapshot(
    snapshot: dict[str, Any], *, tenant_id: str | None = None
) -> dict[str, Any]:
    """Replace snapshot['discovery']['resources'] with the full real resource_asset list (deep copy)."""
    out = copy.deepcopy(snapshot)
    cards = project_resource_cards(tenant_id=tenant_id)
    # DB single SoT: 无条件替换（空库 → 空发现列表，不回退 seed 演示资源）。
    discovery = out.setdefault("discovery", {})
    discovery["resources"] = cards
    return out
