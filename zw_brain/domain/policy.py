from __future__ import annotations

from typing import Any

from zw_brain.domain.role_codes import (
    LEGACY_ROLE_CODES as _LEGACY_ROLE_CODES,
)
from zw_brain.domain.role_codes import (  # R-008 单一来源
    ROLE_DISPLAY_NAMES_ZH,
    ROLE_HIERARCHY,
)
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

# R-008: ACTOR_NAMES 从 role_codes.ROLE_DISPLAY_NAMES_ZH 派生，不再手维护
ACTOR_NAMES: dict[str, str] = dict(ROLE_DISPLAY_NAMES_ZH)

# R-014 fix: 标签位运行时校验在 enforce_manifest_policy 实现；集合定义在 LEAD_DEPT_TAG_PERMISSIONS
LEAD_DEPT_TAG_PERMISSIONS: frozenset[str] = frozenset({
    "catalog.lead_dept_topic_review.execute",
    "catalog.lead_dept_topic_revoke.execute",
})

# 权限分配规则（D23 retrofit 后）：
# - 发现/查看类  → ORGAN_OPERATER + ORGAN_MANAGER + BUSIAUDIT + SECURITY_AUDIT（只读放开）
# - 编制/提交类  → ORGAN_OPERATER（MANAGER 通过 ROLE_HIERARCHY 隐式获得）
# - 审批/审核类  → ORGAN_MANAGER + BUSIAUDIT（部门审 + 平台复核）
# - 发布/撤回类  → BUSIAUDIT（主管部门最终发布权）
# - 数据安全策略 → SECURITY_ADMIN
# - 审计/存证   → SECURITY_AUDIT
# - 运维/网关   → ROLE_SYSTEM
PERMISSION_ROLES = {
    # 基础导航与系统快照（所有业务角色可见）
    "workbench.view.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT", "ROLE_SECURITY_ADMIN", "ROLE_SYSTEM", "admin"},
    "system.snapshot.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT", "ROLE_SECURITY_ADMIN", "ROLE_SYSTEM", "admin"},
    "system.schema_info.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT", "ROLE_SECURITY_ADMIN", "ROLE_SYSTEM", "admin"},

    # J1 找数→用数：检索/详情/列表
    "data.search.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    # F6 P2 搜索上下文助手 — 同 data.search 4 角色 read 权限
    "search.intent.parse.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    # 平台文档问答（内置 zw-platform-guide Agent）
    "platform.docs.search.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT", "ROLE_SECURITY_ADMIN", "ROLE_SYSTEM"},
    "platform.docs.read.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT", "ROLE_SECURITY_ADMIN", "ROLE_SYSTEM"},
    # F7 P3 申请草拟助手 — 申请人 read，便于草稿阶段获取建议
    "application.draft.suggest.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    # F7 P3 审批依据助手 — 审批人 + 主管部门 + 审计员 read
    "approval.evidence.summarize.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    # F8 P4 状态解释助手 — 同 delivery.view 4 角色 read
    "delivery.status.explain.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "catalog.resource_view.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "catalog.resource.list.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "request.list.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    "request.view.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    "approval.view.execute": {"ROLE_ORGAN_MANAGER"},
    "delivery.list.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "delivery.view.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "provider.view.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},

    # B1.1 异议/审计/合规
    "governance.dispute_list.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "governance.dispute_view.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "governance.iam_overview.execute": {"ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "governance.policy_candidate.list.execute": {"ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "governance.policy_candidate.review.execute": {"ROLE_BUSIAUDIT"},
    "audit.replay_evidence_chain.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "audit.list.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    # F4 5 类投影状态聚合（业务运营员 / 安全审计员 看投影 pipeline 健康度）
    "projection.status.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    # F2: 正规化审计事件流的查询 + 回放面（安全审计员 / 主管部门 / 系统）
    "audit.event.query.execute": {"ROLE_SECURITY_AUDIT", "ROLE_BUSIAUDIT", "ROLE_SYSTEM"},
    "audit.event.replay.execute": {"ROLE_SECURITY_AUDIT", "ROLE_BUSIAUDIT", "ROLE_SYSTEM"},
    # F3-backend: B1.1 4 panel 后端 capability + 调查摘要助手
    "audit.event.statistics.execute": {"ROLE_SECURITY_AUDIT", "ROLE_BUSIAUDIT", "ROLE_SYSTEM"},
    "audit.event.anomaly.execute": {"ROLE_SECURITY_AUDIT", "ROLE_BUSIAUDIT", "ROLE_SYSTEM"},
    "audit.event.accountability.execute": {"ROLE_SECURITY_AUDIT", "ROLE_BUSIAUDIT", "ROLE_SYSTEM"},
    "assistant.investigation_summary.execute": {"ROLE_SECURITY_AUDIT", "ROLE_BUSIAUDIT", "ROLE_SYSTEM"},

    # 区划只读
    "zone.list.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "zone.view.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 能力包注册（平台运营侧）
    "package.list.execute": {"ROLE_BUSIAUDIT"},
    "package.view.execute": {"ROLE_BUSIAUDIT"},
    # F4 B1.2 intake：rollback / 暴露矩阵 / trust_level 升降（BUSIAUDIT 主管 +
    # SECURITY_ADMIN 数据安全；SYSTEM 给运维自动回滚）
    "package.rollback.execute": {"ROLE_BUSIAUDIT", "ROLE_SECURITY_ADMIN", "ROLE_SYSTEM"},
    "package.exposure.matrix.query.execute": {"ROLE_BUSIAUDIT", "ROLE_SECURITY_ADMIN", "ROLE_SECURITY_AUDIT", "ROLE_SYSTEM"},
    "package.trust_level.update.execute": {"ROLE_BUSIAUDIT", "ROLE_SECURITY_ADMIN"},

    # J1 申请：发起 → 审 → 授权
    "request.create.execute": {"ROLE_ORGAN_OPERATER"},
    "request.submit.execute": {"ROLE_ORGAN_OPERATER"},
    "approval.case.decide.execute": {"ROLE_ORGAN_MANAGER"},
    "approval.review_decide.execute": {"ROLE_ORGAN_MANAGER"},
    "supplement.submit.execute": {"ROLE_ORGAN_OPERATER"},
    "summary.confirm.execute": {"ROLE_ORGAN_MANAGER"},
    "backflow.confirm.execute": {"ROLE_ORGAN_MANAGER"},
    "delivery.reconcile_receipt.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "delivery.trigger_recovery.execute": {"ROLE_ORGAN_MANAGER"},
    "service.publish_or_suspend.execute": {"ROLE_ORGAN_MANAGER"},

    # 运维侧网关/调用监控
    "ops.gateway.heartbeat.ingest.execute": {"ROLE_ORGAN_MANAGER", "ROLE_SECURITY_AUDIT"},
    "ops.gateway.log.anchor.execute": {"ROLE_ORGAN_MANAGER", "ROLE_SECURITY_AUDIT"},
    "ops.service.invocation.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "ops.service.report.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # API 资源全生命周期
    "resource.api.register.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "resource.api.change.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "resource.api.submit_review.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    # R-007 fix: 审核类权限保留交叉审（仅 BUSIAUDIT）
    "resource.api.review.execute": {"ROLE_BUSIAUDIT"},
    # R-001 fix: r6 (映射到 ROLE_ORGAN_MANAGER) 是提供方部门管理员，应保留对自家 API 资源的发布权
    "resource.api.publish.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "resource.api.withdraw.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "resource.api.revoke.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "resource.api.test.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "resource.api.policy.update.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},

    # 目录浏览/搜索
    "catalog.group.query.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "catalog.share_zone.query.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "catalog.model.query.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "catalog.model.field.query.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "catalog.entry.query.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "catalog.browse.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 目录编制（J2 挂数→维数）
    "catalog.entry.create.execute": {"ROLE_ORGAN_OPERATER"},  # MANAGER 通过 hierarchy 获得
    "catalog.entry.update.execute": {"ROLE_ORGAN_OPERATER"},
    "catalog.entry.create_draft.execute": {"ROLE_ORGAN_OPERATER"},
    "catalog.entry.submit_review.execute": {"ROLE_ORGAN_OPERATER"},
    # F1 (E2 J2 3-layer)：放开给 ROLE_ORGAN_MANAGER（部门待审 stage）+ ROLE_BUSIAUDIT（平台待审 stage）。
    # stage-aware 判定在 handlers/j1/catalog_entry.py::_review_catalog_entry：MANAGER 只能从 pending_review
    # → pending_platform_review；BUSIAUDIT 只能从 pending_platform_review → approved_pending_publish
    # （旧单步直达 pending_review→approved_pending_publish 作为兼容路径暂留）。
    # 评审流引擎（D25）上线后由节点定义角色，届时整体收回到 PERMISSION_ROLES 显式映射。
    "catalog.entry.review.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    # R-001 fix: r6 (映射到 ROLE_ORGAN_MANAGER) 是提供方部门管理员，应保留对自家目录的发布权
    "catalog.entry.publish.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "catalog.entry.withdraw.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "catalog.resource.bind.execute": {"ROLE_ORGAN_OPERATER"},
    # F3 (E2 J2)：发布前重复率检测，read-only 非硬拦。发布链路上 OPERATER 编目 / MANAGER
    # 部门审 / BUSIAUDIT 平台审三个角色都该看到提醒。SECURITY_AUDIT 不直接发布，归
    # objection.case.* 异议侧；catalog.browse.execute 已开放给审计员，无需重复授权。
    "catalog.duplicate.check.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},

    # 资源资产
    "resource.asset.query.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "resource.asset.submit_review.execute": {"ROLE_ORGAN_OPERATER"},
    # 库表 / 文件 物化资源挂接（提交侧）— OPERATER 创建草稿；复核/发布沿用 resource.asset.* 角色门
    "resource.mount.table.prepare.execute": {"ROLE_ORGAN_OPERATER"},
    "resource.mount.file.prepare.execute": {"ROLE_ORGAN_OPERATER"},
    # R-007 fix: 审核类权限保留交叉审（仅 BUSIAUDIT）
    "resource.asset.review.execute": {"ROLE_BUSIAUDIT"},
    # R-001 fix: r6 (映射到 ROLE_ORGAN_MANAGER) 是提供方部门管理员，应保留对自家资源的发布权
    "resource.asset.publish.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},

    # 申请受理（资源端）
    "application.resource.submit.execute": {"ROLE_ORGAN_OPERATER"},
    # D-7 align (G1.2): 无条件共享审批 = 资源提供部门管理员单步通过；前端
    # ZW_PAGE_ACCESS.reviewDetail + .feature 头标已同步收敛到 ROLE_ORGAN_MANAGER。
    "application.resource.review.execute": {"ROLE_ORGAN_MANAGER"},
    # j1-approval-conditional 有条件共享两步审批：
    #   第一步部门审 = 提供方部门管理员；resubmit（补件重提）由申请人 OPERATER 发起，
    #   两动作共用 application.dept_approve.execute，运行时 self_approval / R11 方向 /
    #   applicant 校验在 ConditionalApprovalService + policy guard 内做细粒度门控。
    "application.dept_approve.execute": {"ROLE_ORGAN_MANAGER", "ROLE_ORGAN_OPERATER"},
    #   第二步平台复核 = 省大数据局业务运营员（数据主管部门合规复核权）。
    "application.platform_approve.execute": {"ROLE_BUSIAUDIT"},
    "delivery.access.grant.execute": {"ROLE_ORGAN_MANAGER"},
    # J1 凭据签发 — 审批通过自动触发；手工补签由审批人/主管部门触发
    "credential.issue.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    # J1 凭据查询 — 申请人 P4 凭据领取页 + 审批人 / 主管部门 / 审计员
    "credential.query.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    # F5 凭据三语调用样例渲染 — 收敛到 credential 自然生命周期角色（principle of least privilege；
    # 样例含 app_secret 明文，审计角色 BUSIAUDIT / SECURITY_AUDIT 通过 credential.query 元数据
    # + audit_event 验证签发，不需要 copy-paste 样例）。MANAGER 通过 ROLE_HIERARCHY 继承获得。
    "credential.sample.render.execute": {"ROLE_ORGAN_OPERATER"},

    # 元数据查询（开放给运营/审计）
    "metadata.schema.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "metadata.catalog_item.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "metadata.lineage.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "metadata.gather.evidence.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "ops.catalog.statistics.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "ops.catalog.quality.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 目录/模型 upsert（J2 主线）
    # PR #60 后修复：BUSIAUDIT 主管部门作为平台运营方，需要直接管理目录（特别是审计/合规视角的目录管理）
    "catalog.manage_entry.execute": {"ROLE_ORGAN_OPERATER", "ROLE_BUSIAUDIT"},
    "catalog.model.upsert.execute": {"ROLE_ORGAN_OPERATER"},
    "catalog.schema.mapping.upsert.execute": {"ROLE_ORGAN_OPERATER"},
    "metadata.schema.snapshot.upsert.execute": {"ROLE_ORGAN_OPERATER"},
    "metadata.gather.evidence.upsert.execute": {"ROLE_ORGAN_OPERATER"},
    "metadata.lineage.upsert.execute": {"ROLE_ORGAN_OPERATER", "ROLE_SECURITY_AUDIT"},
    "ops.catalog.quality.upsert.execute": {"ROLE_ORGAN_OPERATER", "ROLE_SECURITY_AUDIT"},
    # PR #60 后修复：BUSIAUDIT 主管部门需要直接管理资产
    "resource.manage_asset.execute": {"ROLE_ORGAN_OPERATER", "ROLE_BUSIAUDIT"},

    # 共享专题/能力包
    "zone.publish_topic_projection.execute": {"ROLE_BUSIAUDIT"},
    "package.review_decide.execute": {"ROLE_BUSIAUDIT"},
    "capability.package.register.execute": {"ROLE_BUSIAUDIT"},
    "capability.version.submit.execute": {"ROLE_BUSIAUDIT"},
    "capability.version.review.execute": {"ROLE_BUSIAUDIT"},
    "capability.exposure.configure.execute": {"ROLE_BUSIAUDIT"},
    "tenant.capability.enable.execute": {"ROLE_BUSIAUDIT"},
    "tenant.capability.disable.execute": {"ROLE_BUSIAUDIT"},
    "registry.artifact.export.execute": {"ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "package.register_version.execute": {"ROLE_BUSIAUDIT"},
    "package.apply_tenant_policy.execute": {"ROLE_BUSIAUDIT"},
    "package.configure_exposure.execute": {"ROLE_BUSIAUDIT"},

    # E3 Wave-2 三引擎 — 审批流模板入库（项目级管理员）
    "approval_flow.schema.commit.execute": {"ROLE_ORGAN_MANAGER"},
    # E3 Wave-2 三引擎 — 审批流 NL 草稿 + 三步流程（项目级管理员）
    "approval_flow.nl_draft.execute": {"ROLE_ORGAN_MANAGER"},
    "approval_flow.schema.promote_to_preview.execute": {"ROLE_ORGAN_MANAGER"},
    "approval_flow.schema.revert_to_draft.execute": {"ROLE_ORGAN_MANAGER"},
    # E3 Wave-2 三引擎 — 表单模板入库（项目级管理员）
    "form_schema.commit.execute": {"ROLE_ORGAN_MANAGER"},
    # E3 Wave-2 三引擎 — 表单 NL 草稿 + 三步流程（项目级管理员）
    "form_schema.nl_draft.execute": {"ROLE_ORGAN_MANAGER"},
    "form_schema.promote_to_preview.execute": {"ROLE_ORGAN_MANAGER"},
    "form_schema.revert_to_draft.execute": {"ROLE_ORGAN_MANAGER"},
    # E3 Wave-2 三引擎 — 推荐规则入库（项目级管理员）+ J1 申请前置目录推荐（用户面）
    "recommendation.rule.commit.execute": {"ROLE_ORGAN_MANAGER"},
    "recommendation.similar_catalog.suggest.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},

    # 合规 / 风险事件（SECURITY_AUDIT 主面）
    "compliance.investigate_case.execute": {"ROLE_SECURITY_AUDIT"},
    "compliance.signal.ingest.execute": {"ROLE_SECURITY_AUDIT"},
    "risk.event.ingest.execute": {"ROLE_SECURITY_AUDIT"},
    "compliance.rule.configure.execute": {"ROLE_SECURITY_AUDIT"},
    "compliance.case.open.execute": {"ROLE_SECURITY_AUDIT"},
    "compliance.case.assign.execute": {"ROLE_SECURITY_AUDIT"},
    "compliance.case.resolve.execute": {"ROLE_SECURITY_AUDIT"},
    "compliance.case.close.execute": {"ROLE_SECURITY_AUDIT"},
    "compliance.case.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "compliance.metric.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 数据标准/数据安全（SECURITY_ADMIN 主面，部分共享给 BUSIAUDIT）
    # PR #60 后修复：SECURITY_AUDIT 审计读取数据标准建议是合规场景刚需
    "standard.asset.recommend.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_ADMIN", "ROLE_SECURITY_AUDIT"},
    "security.scan.result.sync.execute": {"ROLE_SECURITY_ADMIN", "ROLE_SECURITY_AUDIT"},

    # adapter 健康
    "adapter.health.probe.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 异议（合规 + 部门 + 平台）
    "objection.case.create.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "objection.case.submit.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "objection.case.accept.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "objection.case.reject.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "objection.case.assign.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "objection.case.reply.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "objection.case.review.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "objection.case.evaluate.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "objection.case.escalate.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "objection.case.close.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "objection.case.query.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "demand.register.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "demand.phase.advance.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "demand.list.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "objection.process.query.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "objection.metric.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 国家平台 adapter
    "adapter.national.catalog.pull.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "adapter.national.resource.pull.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "adapter.national.catalog.report.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "adapter.national.resource.report.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "adapter.national.application.submit.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "adapter.national.application.receive.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "adapter.national.application.reconcile.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "adapter.national.delivery.receipt.sync.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "adapter.national.objection.sync.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "adapter.national.topic.report.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # adapter 级联消费
    "adapter.cascade.consume.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "adapter.cascade.replay.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "adapter.cascade.health.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "adapter.external.mapping.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 租户策略
    "tenant.policy.evaluate.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 组织/Actor projection（IAM 同步）
    "org.projection.sync.execute": {"ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "actor.projection.sync.execute": {"ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT", "system"},

    # 旧 BSP / sharezone 映射导入
    "legacy.bsp.mapping.import.execute": {"ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "legacy.sharezone.mapping.import.execute": {"ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # M0 实施工程师专用（admin 主用；BUSIAUDIT/SECURITY_AUDIT 验收日代看）
    "legacy.migration.status.query.execute": {"admin", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 反向编目（J2）— ROLE_ORGAN_MANAGER + ROLE_BUSIAUDIT 主导（OPERATER 通过 ROLE_HIERARCHY 隐式获得 suggest/create）
    "catalog.entry.reverse_draft.suggest.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "catalog.entry.reverse_draft.create.execute": {"ROLE_ORGAN_MANAGER"},
    "catalog.entry.reverse_draft.confirm.execute": {"ROLE_BUSIAUDIT"},
    "catalog.entry.reverse_draft.reject.execute": {"ROLE_BUSIAUDIT"},

    # schema 发现 — 反向编目入口；提供方部门管理员 + 平台主管部门可拉取候选 schema
    "metadata.schema.discover.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},

    # 质量规则与任务（D27 #14：仅旁路；不进 J1/J2 主线）
    "quality.rule.upsert.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "quality.task.run.execute": {"ROLE_ORGAN_MANAGER"},
    "quality.task.replay.execute": {"ROLE_ORGAN_MANAGER"},

    # 数据直达（D27 #13：国家平台流程，独立子旅程）
    "direct_access.catalog.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "direct_access.delivery.list.execute": {"ROLE_ORGAN_MANAGER", "ROLE_SECURITY_AUDIT"},

    # 需求资源派发 / 任务移交
    "require.resource.dispatch.execute": {"ROLE_BUSIAUDIT"},
    "require.task.handoff.execute": {"ROLE_BUSIAUDIT"},

    # 交付替换/取消 / 订阅终止
    "delivery.replace_or_cancel.execute": {"ROLE_ORGAN_MANAGER"},
    "subscription.terminate.execute": {"ROLE_ORGAN_MANAGER"},

    # 专题包（共享专区）
    "topic.package.create.execute": {"ROLE_BUSIAUDIT"},
    "topic.package.configure.execute": {"ROLE_BUSIAUDIT"},
    "topic.package.submit.execute": {"ROLE_BUSIAUDIT"},
    "topic.package.review.execute": {"ROLE_BUSIAUDIT"},
    "topic.package.publish.execute": {"ROLE_BUSIAUDIT"},
    "topic.package.policy.update.execute": {"ROLE_BUSIAUDIT"},
    "topic.package.subscribe.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "topic.package.evidence.attach.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "topic.package.query.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "topic.package.metric.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 交付回执 / exchange
    "delivery.receipt.ingest.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "ops.exchange.statistics.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "ops.exchange.diagnose.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "delivery.exchange.plan.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "delivery.exchange.start.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "delivery.exchange.publish.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "delivery.exchange.stop.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},

    # 申请授权（grant）
    "application.grant.approve.execute": {"ROLE_ORGAN_MANAGER"},
    "application.grant.renew.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    # j1-credential-revoke 决策 A（已签字 docs/decisions/j1-credential-revoke-semantics-*）：
    # 撤回 = 业务运营员合规驱动 + 申请人本人主动放弃（owner 校验在 handler）；暂停 = 业务运营员。
    # 收回 MANAGER（提供方部门管理员不直接撤回，SPEC 负向场景）。
    "application.grant.suspend.execute": {"ROLE_BUSIAUDIT"},
    "application.grant.revoke.execute": {"ROLE_BUSIAUDIT", "ROLE_ORGAN_OPERATER"},

    # 服务评价
    "service.rating.submit.execute": {"ROLE_ORGAN_OPERATER"},

    # 工单（合规/督查侧）
    "ops.ticket.create.execute": {"ROLE_SECURITY_AUDIT"},
    "ops.ticket.close.execute": {"ROLE_SECURITY_AUDIT"},
    "ops.shift_handover.submit.execute": {"ROLE_SECURITY_AUDIT"},

    # 需求登记（D27 #6 智能推荐前置，下期实施）
    "require.intent.submit.execute": {"ROLE_ORGAN_OPERATER"},
    "require.intent.refine.execute": {"ROLE_ORGAN_OPERATER"},
    "require.intent.review.execute": {"ROLE_ORGAN_MANAGER"},
    "require.resource.match.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 订阅管理 / 应急熔断
    "delivery.subscription.manage.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "system.toggle_outage.execute": {"ROLE_SYSTEM", "ROLE_SECURITY_AUDIT"},

    # 标签位（依附 ORGAN_MANAGER + tag_lead_dept）— D27 #11 处置
    "catalog.lead_dept_topic_review.execute": {"ROLE_ORGAN_MANAGER"},  # 运行时再校验 tag_lead_dept
    "catalog.lead_dept_topic_revoke.execute": {"ROLE_ORGAN_MANAGER"},
}


class DomainAccessDeniedError(PermissionError):
    pass


def assert_no_legacy_role_codes() -> None:
    """启动时检查：任何 r1-r8 字面值出现即抛错（D23 retrofit 兜底）。"""
    offenders: list[str] = []
    for role in ACTOR_NAMES:
        if role.lower() in _LEGACY_ROLE_CODES:
            offenders.append(f"ACTOR_NAMES key={role!r}")
    for permission, roles in PERMISSION_ROLES.items():
        for role in roles:
            if role.lower() in _LEGACY_ROLE_CODES:
                offenders.append(f"PERMISSION_ROLES[{permission!r}] contains {role!r}")
    if offenders:
        raise ValueError(
            "D23: R1-R8 角色码已退役，policy.py 不允许出现 r1-r8 字面值；"
            f"违例：{offenders}"
        )


def resolve_role(payload_role: object, fallback_role: str) -> str:
    role = str(payload_role or fallback_role)
    if role not in ACTOR_NAMES:
        raise DomainAccessDeniedError(f"unknown role: {role}")
    return role


def filter_product_role_codes(role_codes: list[str] | tuple[str, ...] | None) -> list[str]:
    """IAF / 旧 BSP 投影中的角色码只保留产品白名单（D23 + 阶段 D）。"""
    return [str(item) for item in (role_codes or []) if str(item) in ACTOR_NAMES]


def actor_for_role(role: str) -> str:
    if role not in ACTOR_NAMES:
        raise DomainAccessDeniedError(f"unknown role: {role}")
    return f"user:gov:{role}:{ACTOR_NAMES[role]}"


def tenant_for_role(role: str) -> str:
    if role not in ACTOR_NAMES:
        raise DomainAccessDeniedError(f"unknown role: {role}")
    return get_runtime_tenant_id()


def _expand_with_hierarchy(role: str) -> set[str]:
    """展开角色层级：MANAGER 隐式包含 OPERATER 的所有权限"""
    expanded = {role}
    inherits = ROLE_HIERARCHY.get(role, set())
    for inherited in inherits:
        expanded.add(inherited)
        expanded.update(_expand_with_hierarchy(inherited))
    return expanded


def permissions_for_role(role: str) -> set[str]:
    if role not in ACTOR_NAMES:
        raise DomainAccessDeniedError(f"unknown role: {role}")
    effective_roles = _expand_with_hierarchy(role)
    return {
        permission
        for permission, roles in PERMISSION_ROLES.items()
        if roles & effective_roles
    }


def enforce_manifest_policy(skill_id: str, manifest: dict[str, Any], role: str, payload: dict[str, Any]) -> None:
    tenant_scope = manifest.get("tenant_scope")
    if tenant_scope == "tenant":
        requested_tenant = payload["tenant_id"] if "tenant_id" in payload else tenant_for_role(role)
        if requested_tenant != tenant_for_role(role):
            raise DomainAccessDeniedError(f"tenant scope violation for {skill_id}: {requested_tenant}")

    # C1 fix (security): permission enforcement runs against the *resolved* role for
    # EVERY capability that declares ``permissions`` — read-only or write, role key in
    # the original payload or not. The previous `if not side_effects and "role" not in
    # payload: return` escape conflated "caller omitted a role key" with "trusted
    # internal call", so a low-privilege bearer/CLI/MCP/A2A caller could read sensitive
    # SECURITY_AUDIT/BUSIAUDIT capabilities (e.g. audit.event.query) just by NOT sending
    # a role — the resolved fallback role's permissions were never checked. The boundary
    # responsibility is now sharp: the *entry layer* must derive `role` from the verified
    # identity (cookie BFF: build_trusted_skill_payload; bearer/CLI: identity-derived
    # role stamped into payload), and this enforce step never skips for permissioned caps.
    #
    # Capabilities with NO declared permissions are public-by-design; for them the
    # permission set is empty and the check below is a no-op, so behavior is unchanged.
    required_permissions = set(manifest.get("permissions", []))
    if required_permissions:
        missing_permissions = sorted(required_permissions - permissions_for_role(role))
        if missing_permissions:
            raise DomainAccessDeniedError(
                f"role {role} lacks permissions for {skill_id}: {', '.join(missing_permissions)}"
            )

    # Confirmation gate runs *after* permission enforcement: an unauthorized caller must
    # be denied (403), never handed a "needs confirmation" envelope it could use to probe
    # capability existence. Authorized-but-unconfirmed writes still short-circuit here so
    # the confirmation round-trip (→ 409 ConfirmationRequired) is preserved for them.
    if manifest.get("human_confirmation_required") and not bool(payload.get("confirmed")):
        return

    # R-014 fix: 标签位运行时校验 — tag_lead_dept 标记的权限只允许持有该标签的 actor 调用。
    # actor.tags 通过 payload.actor_tags 传入（IAM session 或上层注入）；未传时默认无标签。
    # F1 fix: actor_tags 必须是 dict；非 dict 类型（str/list/None/...）等同于"无标签"，拒绝。
    # F2 fix: 严格只接受 bool True 作为"持有标签"；字符串 "true"/"1"/"false" 等都不算（避免 IAM
    # 误传字符串造成 Python truthiness 误判）。
    tagged_permissions = required_permissions & LEAD_DEPT_TAG_PERMISSIONS
    if tagged_permissions:
        raw_tags = payload.get("actor_tags")
        actor_tags = raw_tags if isinstance(raw_tags, dict) else {}
        if actor_tags.get("tag_lead_dept") is not True:
            raise DomainAccessDeniedError(
                f"skill {skill_id} requires tag_lead_dept=True (bool); "
                f"actor lacks the tag — needed for permissions: {', '.join(sorted(tagged_permissions))}"
            )


class SelfApprovalNotAllowedError(DomainAccessDeniedError):
    """Raised when an actor tries to approve their own application (J1 conditional)."""


class ApprovalDirectionError(DomainAccessDeniedError):
    """Raised when a department manager outside the providing org tries to act (R11)."""


def enforce_self_approval_guard(applicant_org_code: object, actor_org_code: object) -> None:
    """Reject self-approval: the applicant org cannot approve its own request.

    J1 有条件审批 Scenario 6. The legacy platform never enforced this (省大数据局
    既申请又自审 × 4 真数据 anomaly, documented in the conditional pytest); the new
    brain enforces it at the policy layer. Empty / unknown orgs do not match
    (cannot prove a self-approval), so they pass — direction is enforced separately.
    """
    applicant = str(applicant_org_code or "")
    actor = str(actor_org_code or "")
    if applicant and actor and applicant == actor:
        raise SelfApprovalNotAllowedError("self_approval_not_allowed")


def enforce_dept_approval_direction(owner_org_code: object, actor_org_code: object) -> None:
    """Reject a department manager whose org ≠ the resource's providing org (R11).

    Scenario 5: 提供方部门外的 ORGAN_MANAGER 不能审批此申请。Direction is computed
    from owner_org_code; an unknown owner cannot be matched and is therefore rejected
    (fail-closed: a request with no resolvable provider org is not actionable by any
    department manager).
    """
    owner = str(owner_org_code or "")
    actor = str(actor_org_code or "")
    if not owner or owner != actor:
        raise ApprovalDirectionError(
            f"approval_direction_mismatch: owner_org_code={owner!r} actor_org_code={actor!r}"
        )


def can_dept_manager_see_request(owner_org_code: object, actor_org_code: object) -> bool:
    """R11 visibility: a department manager only sees requests for resources their
    org provides. Used by the '我作为提供方' queue filter (no-permission = invisible).
    """
    owner = str(owner_org_code or "")
    actor = str(actor_org_code or "")
    return bool(owner) and owner == actor


# 模块加载时立即检查；任何 r1-r8 残留导致 import 失败（fail-fast）
assert_no_legacy_role_codes()
