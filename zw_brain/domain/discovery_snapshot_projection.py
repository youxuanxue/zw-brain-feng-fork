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
from zw_brain.domain.resource_lifecycle import lifecycle_label
from zw_brain.domain.services import form_fill_service
from zw_brain.domain.services.reference_service import ReferenceService
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id
from zw_brain.shared.sensitive_mask import mask_default

# 模块级深拷贝引用：enrich_* 的 ``copy: bool`` 形参会在函数体内遮蔽 ``copy`` 模块名，
# 故经此别名调用 copy.deepcopy，不受形参遮蔽影响（S3 deepcopy 开关）。
_deepcopy = copy.deepcopy


def _copy_snapshot(snapshot: dict[str, Any], do_copy: bool) -> dict[str, Any]:
    """``do_copy=True`` → deepcopy（默认纯函数语义）；False → 原样返回供原地写（handler 已统一拷过）。"""
    return _deepcopy(snapshot) if do_copy else snapshot


# application_record.payload_json.kind：apply / None = 申请（有 resource_name，进 P3 在途申请）；
# require / original_require = 需求（无 resource_name，属 J2 供需匹配线，不进 P3 申请收件箱）。
_DEMAND_KINDS = frozenset({"require", "original_require"})

# 发现页只展示「已发布」资源（D53① 业务裁决 2026-06-06，反转 D45.b）：仅 active（已发布）。
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

def _shared_type_for(payload: dict[str, Any], share_type_by_resource: dict[str, int] | None) -> int | None:
    """申请卡共享方式：payload 显式 shared_type 优先；否则按 resourceId 从资源 access_policy 派生。

    返回 None = 两边都取不到（诚实缺位，前端按无条件兜底渲染但不据此声称口径）。
    """
    raw = payload.get("shared_type") or payload.get("sharedType")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    rid = str(payload.get("resourceId") or payload.get("resource_id") or "")
    if rid and share_type_by_resource:
        return share_type_by_resource.get(rid)
    return None


def _share_type_by_resource(tenant_id: str, assets: list[Any] | None = None) -> dict[str, int]:
    """resource_asset(id/resource_code) → access_policy_json.share_type 一次性预载（避免 N+1）。

    ``assets`` 万级规模性能：调用方（handler_system_snapshot）可一次性预取全量 resource_asset
    传入，避免一次 system.snapshot 内 resource_asset 全表被各投影各扫一遍（S3）。``None``=回落
    自查（保持本函数独立可测 / 独立调用方 request_service.shared_type_for_resource 不变）。
    """
    out: dict[str, int] = {}
    rows = assets if assets is not None else ResourceApiRepository().list_assets(tenant_id=tenant_id)
    for asset in rows:
        access = asset.access_policy_json or {}
        raw = access.get("share_type")
        try:
            st = int(raw) if raw is not None else None
        except (TypeError, ValueError):
            st = None
        if st is None:
            continue
        for key in (str(asset.id or ""), str(getattr(asset, "resource_code", "") or "")):
            if key:
                out[key] = st
    return out


def shared_type_for_resource(resource_id: str, tenant_id: str | None = None) -> int | None:
    """单资源共享方式回源（access_policy_json.share_type，与申请卡投影同源口径）。

    供写路径（request.create / submit 直提）判定有条件 (2) / 无条件 (1)——状态词汇桥接
    （j1-runtime-write-path-dual-track 方案 B）：有条件单须落 'submitted' 进受理两级队列。
    取不到返 None（调用方按无条件兜底，不虚构口径）。
    """
    rid = str(resource_id or "")
    if not rid:
        return None
    tid = tenant_id or get_runtime_tenant_id()
    return _share_type_by_resource(tid).get(rid)


def _provider_org_from_payload(payload: dict[str, Any]) -> str:
    """请求 payload 里提供方机构**码**的单一取法（申请卡 providerOrgCode 与 requests 部门收口
    同源，避免两处各写一遍漂移）：运行时铸单存 owner_org_code（request.py），legacy 导入单存
    provider_org_id（exchange mapper）。两源都可能存名/码，调用方按需经 org_in_scope 归一；
    展示名 provider_org_name 不能做机构成员判定，故不取。"""
    p = payload if isinstance(payload, dict) else {}
    return str(p.get("owner_org_code") or p.get("provider_org_id") or "")


def _record_to_request_card(
    record: Any,
    share_type_by_resource: dict[str, int] | None = None,
    request_service: Any = None,
    *,
    caller_actor: str | None = None,
) -> dict[str, Any]:
    """application_record → 轻量申请卡（snake→camel；applicant PII 走 mask_default）。

    本组（数据呈现规范化 + 角色投影）追加 3 个**诚实信号**，供前端三视图 / 供方质量队列：
      - ``isLegacyImport``：源自旧平台导入（payload 有 source_ref / legacy_object_ref）
        ⇒ 列表给克制的「历史导入」次要标识，帮用户理解为何有 2023 年的单子（缺陷 3）。
        D47.b：历史导入单的**在线动作混合门控**是已记账债，本组只做呈现层区分、不做动作门控。
      - ``purposeQuality`` / ``purposeDirty``：用途脏值机械化判定（data_quality 单源）；
        前端据此降级显示「未填写用途」，脏单计入供方数据质量队列（缺陷 3）。

    ``mine``（M5「我的申请」标记，按**个人** id 判定）：申请人个人 id 落在
    ``payload['applicant']``（运行时铸单 request.py ~293 行存 actor）。判定必须取**未脱敏**
    的原始 payload（``record.payload_json``）—— ``applicant`` 显示字段已经 mask_default 脱敏，
    拿它比对会恒不等。caller_actor 空/None → 一律 mine=False（未登录态不主张任何单是「我的」）；
    legacy 导入单 payload.applicant ≠ caller_actor 自然得 mine=False（迁移记录非当前个人在产单）。
    """
    payload = copy.deepcopy(record.payload_json or {})
    # mine 取**未脱敏**原始 payload 的 applicant 个人 id（不可用脱敏后的显示字段比对）。
    mine = bool(caller_actor) and str(payload.get("applicant") or "") == str(caller_actor or "")
    applicant = mask_default(
        {"applicant_name": record.applicant_name, "applicant_org": record.applicant_org}
    )
    raw_purpose = purpose_from_payload(payload)
    is_legacy_import = bool(payload.get("source_ref") or payload.get("legacy_object_ref"))
    card: dict[str, Any] = {
        "id": payload.get("id") or record.application_code,
        "resourceId": payload.get("resourceId") or payload.get("resource_id") or "",
        "resourceName": payload.get("resource_name") or payload.get("resourceName") or "",
        "applicant": applicant["applicant_name"],
        "applicantOrgId": payload.get("applicant_org_id") or "",
        "applicantDept": payload.get("applicantDept")
        or payload.get("applicant_org_name")
        or applicant["applicant_org"],
        "providerOrgId": payload.get("provider_org_id") or "",
        # 提供方机构**码**（审批 R11 收口的 owner 源 + requests 部门收口同源，单一取法见
        # _provider_org_from_payload）。取码不取展示名 providerOrgName（名无法做行级机构成员判定）。
        "providerOrgCode": _provider_org_from_payload(payload),
        "providerOrgName": payload.get("provider_org_name") or "",
        # M5「我的申请」标记（按个人 id；取未脱敏 payload.applicant，见函数 docstring）。
        "mine": mine,
        "purpose": raw_purpose,
        # 用途脏值诚实信号（data_quality 单源；前端 dataQuality.ts 镜像降级渲染）。
        "purposeQuality": classify_purpose(raw_purpose),
        "purposeDirty": is_dirty_purpose(raw_purpose),
        # Action D：status 列权威（update_status 类写者只写列，payload 可能滞后）。
        "status": record.status or payload.get("status") or "",
        # 来源诚实标识（缺陷 3）：旧平台导入 vs 在产单视觉区分。
        "isLegacyImport": is_legacy_import,
        # 国家通道指示（C9）：channel_class=='national' 标识「请求国家级数据」的申请，
        # 供 P3 国家通道 tab 筛「待转报」队列（dept_approved ∩ national），不再误列 own-items。
        # 真实信号取 payload_json["channel_class"]（supply_demand §scenario 5 占位口径）；缺省 internal。
        "channelClass": str(payload.get("channel_class") or "internal"),
        "submittedAt": payload.get("submittedAt") or payload.get("create_time") or "",
        "sharingType": payload.get("sharingType"),
        # 受理/审核两级（P21）路由信号：有条件共享(=2)走 受理→部门审核 两级、无条件(=1)受理即终。
        # 真实导入单 payload 不携带 shared_type（旧平台该口径在资源侧）→ 读时从资源
        # access_policy_json.share_type 派生（单一事实源，payload 显式值优先，在产/测试单可覆写）。
        "sharedType": _shared_type_for(payload, share_type_by_resource),
        # 表单填报（form-autofill）：formFields 是**只读投影**，由模型（fieldValues + fieldProvenance）
        # 读时现算（单一事实源，payload 不另存 formFields 副本）。
        # 仅 form-autofill 草稿（payload 带 fieldProvenance 模型）才投影；legacy 导入单 / 旧在产单
        # 无该模型 → 空列表，不给全量申请单平白塞 9 个空字段（避免快照膨胀 + 语义噪音）。
        "formFields": (
            form_fill_service.assemble_form_fields(payload.get("fieldValues") or {}, payload["fieldProvenance"])
            if payload.get("fieldProvenance")
            else []
        ),
        "fieldProvenance": payload.get("fieldProvenance") or {},
    }
    # 读侧 enrich：把后端权威 status_timeline 接到申请卡（申请人视角进度 stepper 单一事实源）。
    # delivery=None → 交付段由权威 status 推断，无 DB/delivery join（D56 读侧呈现，不开架构门）。
    # 仅运行时申请有「卡在谁桌上」的活旅程；历史导入单是只读迁移记录、用旧平台态词汇
    # （under_review/effective/…），不属运行时 4 段旅程 → 不发 stepper（与 isLegacyImport 诚实降级一致）。
    if request_service is not None and not is_legacy_import:
        card["statusTimeline"] = request_service.status_timeline(card, None, perspective="applicant")
    return card


def request_party_in_scope(
    record: Any,
    visible_org_codes: set[str] | None,
    *,
    tenant_id: str | None = None,
    ref: ReferenceService | None = None,
) -> bool:
    """申请单是否落在调用者部门可见域内（D61 裁决②，applicant∨provider）.

    单一事实源：申请收口口径（申请方在域内即留，否则看提供方是否在域内——本部门数据被
    别部门申请的入站单 R11）。``None``=全局放行（org_in_scope 恒 True）、空集=fail-closed
    （恒 False）。语义全在 ReferenceService.org_in_scope（含 legacy 名/码归一），不在调用方
    重复实现。被 enrich_requests_snapshot 与 workbench_backlog_projection 工作台申请待办收口
    共用，避免两处口径漂移。

    ``ref`` 可由调用方传入共享 ReferenceService 实例（带 resolve memo）——逐行过滤时复用同一
    实例消 N+1（同一批 org 只查一次 DB）；缺省每行新建则退化为原 per-record 查询。"""
    ref = ref or ReferenceService()
    tid = tenant_id or get_runtime_tenant_id()
    payload = record.payload_json or {}
    # 申请方机构：运行时单优先取 payload['applicant_org_code']（会话真实机构码，request.py 落，
    # org_in_scope 快路径零 DB）；legacy 导入单回落 applicant_org 列（可能存机构名，resolve 归一到码）。
    applicant_owner = str(payload.get("applicant_org_code") or "") or record.applicant_org
    if ref.org_in_scope(applicant_owner, visible_org_codes, tenant_id=tid):
        return True
    # provider 机构码源同申请卡 providerOrgCode（_provider_org_from_payload 单一取法）。
    return ref.org_in_scope(_provider_org_from_payload(payload), visible_org_codes, tenant_id=tid)


def enrich_requests_snapshot(
    snapshot: dict[str, Any],
    *,
    tenant_id: str | None = None,
    request_service: Any = None,
    visible_org_codes: set[str] | None = None,
    caller_actor: str | None = None,
    assets: list[Any] | None = None,
    copy: bool = True,
) -> dict[str, Any]:
    """Project snapshot['requests'] from the real **application** table (DB single SoT).

    只取申请类（kind ∉ _DEMAND_KINDS）；需求类记录无 resource_name、属 J2 供需线，
    不进 P3「在途申请」收件箱。**无条件替换**：空库 → 空列表（诚实空，不回退 seed 演示单）。

    ``visible_org_codes`` 部门数据可见域（M5 行级收口）：None=全局放行全量 / 集=本机构(+下级)、
    仅保留**本部门作为申请方或提供方参与**的单（applicant_org∈集 OR provider_org∈集）/
    空集=fail-closed 给空列表。``caller_actor`` 当前登录个人 id，算「我的申请」mine 标记
    （payload['applicant'] == caller_actor）。

    **为何 applicant OR provider 两侧都收**（集成期复核修正）：只按 applicant 收口会漏掉
    「别部门申请本部门数据」的单——而那正是供方部门管理员必须看见、去办理的单（供方审批
    队列 R11，见 enrich_approvals_snapshot：审批卡的 owner 机构正是从这份 requests 映出来的，
    若申请卡被漏掉则对应审批单无从映射→被误判 fail-closed 丢弃，部门管理员永远批不了进来的单）。

    **mine 与部门过滤正交**：mine 是逐卡按个人 id 现算的诚实信号，dept 过滤只决定哪些 record
    成卡。管理员自己提的单既是 mine 又在本机构域内（两者同时为真，不互相抑制）。

    ``copy``/``assets`` 万级规模性能（S3）：``copy`` 默认 True 深拷快照（纯函数语义，独立测试
    不变异入参）；handler 链路传 ``copy=False`` 原地写。``assets`` 预取的 resource_asset 供
    _share_type_by_resource 复用，避免重复全扫；``None``=回落自查。
    """
    out = _copy_snapshot(snapshot, copy)
    tid = tenant_id or get_runtime_tenant_id()

    # 空集=fail-closed（部门角色但无机构上下文）：连「我的」也不放行，保 D61 空集防御语义不被
    # mine 逃生口削弱（真实 IAM 登录的部门用户恒有机构=非空集，空集只在畸形/无机构会话出现）。
    _fail_closed = visible_org_codes is not None and not visible_org_codes

    def _is_mine(rec: Any) -> bool:
        # 「我的申请按个人」(D61③) 逃生口：本人提的单恒可见、绕过部门 org 过滤——org-scope
        # 过滤只服务供方审批/受理队列，不应遮蔽申请人自己的单（部门用户看不到自己刚提的草稿
        # 即此根因：草稿 applicant_org/provider 都不在会话机构域内被整条 drop）。仅 None(全局)/
        # 非空集(有效部门上下文) 下生效；取未脱敏 payload.applicant（同 _record_to_request_card
        # mine 现算口径）；caller_actor 空→恒 False。
        if _fail_closed:
            return False
        return bool(caller_actor) and str((rec.payload_json or {}).get("applicant") or "") == str(caller_actor or "")

    # 共享一个 ReferenceService（带 resolve memo）逐行过滤，消 per-record N+1（同批 org 只查一次）。
    _scope_ref = ReferenceService()
    records = [
        r
        for r in ApplicationRepository().list_records(tenant_id=tid)
        if (r.payload_json or {}).get("kind") not in _DEMAND_KINDS
        and (_is_mine(r) or request_party_in_scope(r, visible_org_codes, tenant_id=tid, ref=_scope_ref))
    ]
    share_map = _share_type_by_resource(tid, assets)
    out["requests"] = [
        _record_to_request_card(r, share_map, request_service, caller_actor=caller_actor)
        for r in records
    ]
    return out


def enrich_delivery_tasks_snapshot(
    tasks: list[dict[str, Any]],
    *,
    request_service: Any = None,
    request_map: dict[str, Any] | None = None,
    dept_scoped: bool = False,
) -> list[dict[str, Any]]:
    """交付卡读侧 enrich：把后端权威 status_timeline 接到交付任务卡（P4 交付页脊柱）。

    按 ``requestId`` 从 request_map（O(1)、避 N+1）取申请卡喂 status_timeline；取不到则跳过
    （诚实空，不破 P4 现渲染）。delivery=task 供交付段 ref 回链与「补录态」holder 现算。
    单一事实源：同 #277 申请卡，复用 status_timeline 不在前端重派生。

    ``dept_scoped`` 部门数据可见域行级收口（#294 集成期遗漏补口）：交付任务**随其申请单可见性
    收口**——交付面唯一消费者是部门角色（redaction `_DELIVERY`={操作员,管理员}，全局角色一律清空），
    本就应永远按部门隔离。``request_map`` 已是上游 `enrich_requests_snapshot` 按 applicant_org∨
    provider_org 收口后的申请卡集合（同 approvals R11 收口范式），故 dept_scoped=True 时只保留
    requestId 命中该域内申请的交付卡；命中不到 → fail-closed drop（无法证明归属即不泄漏，与
    enrich_approvals_snapshot 一致）。dept_scoped=False（全局视角/未收口）保留全量、不丢任务。
    """
    rmap = request_map or {}
    out: list[dict[str, Any]] = []
    for task in tasks:
        req = rmap.get(str(task.get("requestId") or ""))
        # 部门收口：申请单不在可见域（request_map 已收口）→ 其交付卡一并 fail-closed drop。
        if dept_scoped and req is None:
            continue
        card = dict(task)
        if request_service is not None and req is not None:
            card["statusTimeline"] = request_service.status_timeline(req, card, perspective="reviewer")
        out.append(card)
    return out


# ───────────────────────────────────────────────────────────────────────────
# approvals — P3RequestFlow 审批人收件箱（按 id 交叉引用 requests 取状态/资源名）
# ───────────────────────────────────────────────────────────────────────────

def _case_to_approval_card(record: Any) -> dict[str, Any]:
    # P3RequestFlow 只读 it.id + (it.suggestion ?? '待审')；状态/资源从 requests 交叉引用。
    return {"id": record.application_code, "suggestion": "待审"}


def enrich_approvals_snapshot(
    snapshot: dict[str, Any], *, tenant_id: str | None = None,
    visible_org_codes: set[str] | None = None, copy: bool = True,
) -> dict[str, Any]:
    """Project snapshot['approvals'] from the real approval_case table (DB single SoT).

    **无条件替换**：空库 → 空列表（诚实空，不回退 seed）。legacy 导入的 approval_case
    经此现算投影，不再陈旧（关 approval-case-projection-stale）。

    R11 部门收口（M6）：部门审批人只见**自家机构作为提供方**的审批单。审批卡本身不带 owner
    机构，故 owner 取自同一 snapshot 里**已先于 approvals 被 enrich** 的 requests 列表
    （handler 顺序保证）——按 application_code(=审批卡 id) 映到申请卡的 ``providerOrgCode``
    （提供方机构码，非展示名），再走 ReferenceService.org_in_scope 做行级机构成员判定。

    三态（与 org_in_scope 语义一致 + fail-closed 兜底）：
      - ``visible_org_codes is None``  → 全局放行（不过滤），保留全量；
      - 非 None 集（含空集）            → 仅保留 provider org ∈ 可见域的审批单；
        映射缺失（requests 里找不到该 application_code）→ **drop**（无法证明归属即 fail-closed，
        不能让一张证不出 owner 的审批单泄漏给部门角色）。

    ``copy`` 万级规模性能（S3）：默认 True 深拷（纯函数语义）；handler 链路传 ``copy=False`` 原地写。
    """
    out = _copy_snapshot(snapshot, copy)
    cases = ApprovalRepository().list_cases(tenant_id=tenant_id or get_runtime_tenant_id())
    cards = [_case_to_approval_card(c) for c in cases]

    if visible_org_codes is not None:
        tid = tenant_id or get_runtime_tenant_id()
        ref = ReferenceService()
        # application_code → providerOrgCode（取自已先行 enrich 的 requests 申请卡，避免重查 DB）。
        provider_by_app: dict[str, str] = {
            str(req.get("id") or ""): str(req.get("providerOrgCode") or "")
            for req in (out.get("requests") or [])
        }
        kept: list[dict[str, Any]] = []
        for card in cards:
            app_code = str(card.get("id") or "")
            if app_code not in provider_by_app:
                continue  # 证不出 owner 归属 → fail-closed drop。
            if ref.org_in_scope(provider_by_app[app_code], visible_org_codes, tenant_id=tid):
                kept.append(card)
        cards = kept

    out["approvals"] = cards
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
        # status = 中文展示态（前端零词表，只读不译，单一事实源 resource_lifecycle.lifecycle_label）；
        # lifecycleStatus = 机器原值，前端逻辑（申请门控/chip 抑制）只比对它，绝不比中文。
        "status": lifecycle_label(record.lifecycle_status),
        "lifecycleStatus": record.lifecycle_status,
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


def project_resource_cards(
    *, tenant_id: str | None = None, assets: list[Any] | None = None
) -> list[dict[str, Any]]:
    """发现页「可复用资源」卡片 — 共享给 snapshot enrich + data.search 空 query。

    只投影**已发布**资源（D53①，反转 D45.b：仅 active）；待发布/草稿/审核中/已暂停/
    已下线/已过期不进默认发现视图。

    ``assets`` 万级规模性能（S3）：调用方可预取全量 resource_asset 传入，避免 system.snapshot
    内 resource_asset 全表重复全扫。``None``=回落自查（保 data_search 等独立调用方不变）。
    """
    records = (
        assets if assets is not None
        else ResourceApiRepository().list_assets(tenant_id=tenant_id or get_runtime_tenant_id())
    )
    return [
        _asset_to_resource_card(r)
        for r in records
        if r.lifecycle_status in _DISCOVERABLE_STATUSES
    ]


def enrich_discovery_resources_snapshot(
    snapshot: dict[str, Any], *, tenant_id: str | None = None,
    assets: list[Any] | None = None, copy: bool = True,
) -> dict[str, Any]:
    """Replace snapshot['discovery']['resources'] with the full real resource_asset list.

    ``copy`` 万级规模性能（S3）：默认 True 深拷贝传入快照（保持纯函数语义 / 独立测试不变异
    入参）；handler 链路上一次性深拷过后传 ``copy=False`` 原地写、消重复深拷。
    ``assets`` 预取的 resource_asset（见 project_resource_cards）；``None``=回落自查。
    """
    out = _copy_snapshot(snapshot, copy)
    cards = project_resource_cards(tenant_id=tenant_id, assets=assets)
    # DB single SoT: 无条件替换（空库 → 空发现列表，不回退 seed 演示资源）。
    discovery = out.setdefault("discovery", {})
    discovery["resources"] = cards
    return out
