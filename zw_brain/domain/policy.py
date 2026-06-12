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
# - 审计/存证   → SECURITY_AUDIT
# （数据安全策略原属 SECURITY_ADMIN；D55/P16 安全管理员本期退役，散权见各条注释）
# - 运维/网关   → ROLE_SYSTEM
PERMISSION_ROLES = {
    # 基础导航与系统快照（所有业务角色可见）
    "workbench.view.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT", "ROLE_SYSTEM", "admin"},
    "system.snapshot.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT", "ROLE_SYSTEM", "admin"},
    "system.schema_info.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT", "ROLE_SYSTEM", "admin"},

    # J1 找数→用数：检索/详情/列表
    # D55/P17：安全审计员非数据使用方（旧平台 v5 安全审计员无找数据菜单），Wave 1/S5 收敛纯只读
    # 监督者后退出找数据全链（data.search / search.intent.parse / catalog.resource_view / .list）。
    "data.search.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    # F6 P2 搜索上下文助手 — 同 data.search read 权限
    "search.intent.parse.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    # 平台文档问答（内置 zw-platform-guide Agent）
    "platform.docs.search.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT", "ROLE_SYSTEM"},
    "platform.docs.read.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT", "ROLE_SYSTEM"},
    # F7 P3 申请草拟助手 — 申请人侧 read（草稿阶段建议）。0605 复审：业务运营员退申请人
    # 身份（D55/P7）后不再草拟申请，去 BUSIAUDIT。
    "application.draft.suggest.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    # F7 P3 审批依据助手 — 审批人 + 主管部门 + 审计员 read
    "approval.evidence.summarize.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    # F8 P4 状态解释助手 — 同 delivery.view 口径（D55/P13：领数据回归操作员+管理员）
    "delivery.status.explain.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    # D55/P17：找数据详情/列表随安全审计员退出找数据而去 SECURITY_AUDIT。
    "catalog.resource_view.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "catalog.resource.list.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "request.list.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    "request.view.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    # D55/P21：审批/受理详情对受理人（业务运营员）+ 部门审核人（部门管理员）皆可见——
    # 无条件由业务运营员受理即终；有条件先业务运营员受理、后部门管理员审核，两级皆看详情。
    "approval.view.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    # D55/P13：领数据回归部门操作员+部门管理员（反转 D53/F1 收窄）；P18 安全审计员退领数据
    "delivery.list.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    "delivery.view.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    "provider.view.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},

    # B1.1 异议/审计/合规
    "governance.dispute_list.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "governance.dispute_view.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    # 身份治理归平台运维员（D55/P4，Wave1-S1）：IAM 治理 = 平台运维员独有。
    "governance.iam_overview.execute": {"ROLE_SYSTEM"},
    "governance.policy_candidate.list.execute": {"ROLE_SYSTEM"},
    "governance.policy_candidate.review.execute": {"ROLE_SYSTEM"},
    # 查审计拆分（D55/P8·P9，Wave1-S3）：审计日志/证据回放面收窄到「业务运营员 + 安全审计员」。
    # 部门管理员（MANAGER）退审计日志（P9）；平台运维员（SYSTEM）退审计日志、保服务调用监控（P8）。
    "audit.replay_evidence_chain.execute": {"ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "audit.list.execute": {"ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    # F4 5 类投影状态聚合（投影 pipeline 健康度）——非审计日志面，本流不动（D55/P8·P9）。
    "projection.status.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    # F2: 正规化审计事件流的查询 + 回放面（安全审计员 / 业务运营员）。
    # 平台运维员（SYSTEM）退审计事件面（D55/P8），不再随审计日志可见。
    "audit.event.query.execute": {"ROLE_SECURITY_AUDIT", "ROLE_BUSIAUDIT"},
    "audit.event.replay.execute": {"ROLE_SECURITY_AUDIT", "ROLE_BUSIAUDIT"},
    # F3-backend: B1.1 4 panel 后端 capability + 调查摘要助手
    "audit.event.statistics.execute": {"ROLE_SECURITY_AUDIT", "ROLE_BUSIAUDIT"},
    "audit.event.anomaly.execute": {"ROLE_SECURITY_AUDIT", "ROLE_BUSIAUDIT"},
    "audit.event.accountability.execute": {"ROLE_SECURITY_AUDIT", "ROLE_BUSIAUDIT"},
    "assistant.investigation_summary.execute": {"ROLE_SECURITY_AUDIT", "ROLE_BUSIAUDIT"},

    # 区划只读
    "zone.list.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "zone.view.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 能力包 / 外部系统接入（D55/P2：外部系统收归平台运维员独有，业务运营员退出——
    # 0609 已签裁决的能力面补漏：P2 当时只改了导航 + redaction，package.* 数据能力漏收，
    # 致 B1.2 外部系统页对唯一可达角色（ROLE_SYSTEM）整面 403、前端静默回落 fixture 假数据）
    "package.list.execute": {"ROLE_SYSTEM"},
    "package.view.execute": {"ROLE_SYSTEM"},
    # F4 B1.2 intake：rollback / 暴露矩阵 / trust_level 升降
    # 注：原含 SECURITY_ADMIN（数据安全），随安全管理员本期退役而去除（D55/P16）；
    # 后 D55/P2 收权，BUSIAUDIT 全部退出外部系统能力面。
    "package.rollback.execute": {"ROLE_SYSTEM"},
    # 暴露矩阵查询：UI 面已随 D52.c 退役，能力保留给协议面（MCP/CLI）；安全审计员只读保留（D55/P22 只读不受限）。
    "package.exposure.matrix.query.execute": {"ROLE_SECURITY_AUDIT", "ROLE_SYSTEM"},
    "package.trust_level.update.execute": {"ROLE_SYSTEM"},

    # J1 申请：发起 → 审 → 授权
    # D57④（feedback-0611-gate）：管理员申请人身份照 v5 保留（「我的申请 = 管理员 + 操作员」）。
    # MANAGER 此前经 ROLE_HIERARCHY 隐式放行（REST 200）而前端 gate 已砍 → 口径漂移；
    # 收口劈叉：显式登记 MANAGER，与前端 ACTION_ROLE_GATES set-equal（行为零变更，hierarchy 本就放行）。
    "request.create.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    "request.submit.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    # 表单填报（form-autofill）：原地修订与创建同口径（操作员发起/编辑草稿）；
    # 参照选择器为只读带出，放开给填表/审查角色（同 catalog 只读类口径）。
    "request.field.update.execute": {"ROLE_ORGAN_OPERATER"},
    "request.draft.ai_suggest.execute": {"ROLE_ORGAN_OPERATER"},
    "reference.organ.options.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "reference.region.options.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "reference.dict.options.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    # D55/P21：无条件共享受理即终 = 业务运营员（受理=初级审核）。这两个 entry key 与
    # application.resource.review 同走 _review_request → review_application_record 的单步受理
    # 路径，角色随之 ROLE_ORGAN_MANAGER → ROLE_BUSIAUDIT（受理即终；有条件两级走 dept/platform
    # _approve 两 key，不经此路径）。
    "approval.case.decide.execute": {"ROLE_BUSIAUDIT"},
    "approval.review_decide.execute": {"ROLE_BUSIAUDIT"},
    "supplement.submit.execute": {"ROLE_ORGAN_OPERATER"},
    "summary.confirm.execute": {"ROLE_ORGAN_MANAGER"},
    "backflow.confirm.execute": {"ROLE_ORGAN_MANAGER"},
    # 0605 复审收口：交付对账/下载 = 领数据动作，口径同 delivery.list/view（操作员+管理员）。
    # 业务运营员无交付场景（D53⑥ 原话）且已退申请人身份（D55/P7），去 BUSIAUDIT 残留；
    # 安全审计员已退（D55/P18）。
    "delivery.reconcile_receipt.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    "delivery.file.download.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    "delivery.trigger_recovery.execute": {"ROLE_ORGAN_MANAGER"},
    "service.publish_or_suspend.execute": {"ROLE_ORGAN_MANAGER"},

    # 运维侧网关/调用监控
    # D55/G2（安全审计员纯只读收尾）：网关心跳上报 / 日志存证是写动作，归平台运维员
    # （v5 网关节点管理 = 平台运维员）；安全审计员退出全部写键。
    "ops.gateway.heartbeat.ingest.execute": {"ROLE_SYSTEM"},
    "ops.gateway.log.anchor.execute": {"ROLE_SYSTEM"},
    # 服务调用监控（D55/P8 拆分 → D57⑥ 收窄）：全局监控面（service-ops 导航 + report.query）=
    # 平台运维员 + 业务运营员（v5 服务调用日志口径）；部门管理员、安全审计员退出全局监控
    # （shipped「管理员/审计只读保留」注释是无签字孤证，按已签矩阵收窄）。
    # invocation.query 保留 MANAGER：D57⑥ 明文「管理员看自家资源被调用情况保留在 P4Credential
    # 凭据门内」（v5 资源订阅含任务监控=操作员+管理员），该能力唯一前端面即 P4 凭据页调用记录段。
    # 「自家」是系统机制非注释承诺：handler 侧按会话机构 server-side scope（provider_org 匹配 ∨
    # 资源属本机构注册资产；无机构上下文/查别家资产 fail-closed 拒），REST/CLI 直调同受限——
    # 见 handlers/b1/ops_service._scope_invocations_for_manager。
    "ops.service.invocation.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SYSTEM"},
    "ops.service.report.query.execute": {"ROLE_BUSIAUDIT", "ROLE_SYSTEM"},

    # API 资源全生命周期 —— 角色口径以旧平台角色菜单 v5 + D54 GATE-1 为准（产品研发负责人 2026-06-08 sign-off，
    # .testing/signoff/feedback-0605-acceptance-gate.signoff.yaml）：
    #   注册 / 编辑 / 提交审核 = 部门操作员 + 部门管理员（业务运营员退出注册——其职责是「融合服务受理」≠ 服务注册）；
    #   审核 / 发布 / 下线 / 撤销 / 策略 = 部门管理员（v5「融合服务审核 = 部门管理员」）；
    #   测试 = 注册方自测（操作员 + 管理员）。
    # 撤回此前 R-007（review 交叉审给 BUSIAUDIT）与 R-001 的 BUSIAUDIT 旁路：D54 收口业务运营员
    # 完全退出 API 资源生命周期（MANAGER 仍保留对自家 API 资源的发布权——R-001 的本意被新口径保留）。
    "resource.api.register.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    "resource.api.change.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    "resource.api.submit_review.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    "resource.api.review.execute": {"ROLE_ORGAN_MANAGER"},
    "resource.api.publish.execute": {"ROLE_ORGAN_MANAGER"},
    "resource.api.withdraw.execute": {"ROLE_ORGAN_MANAGER"},
    "resource.api.revoke.execute": {"ROLE_ORGAN_MANAGER"},
    "resource.api.test.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    "resource.api.policy.update.execute": {"ROLE_ORGAN_MANAGER"},

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
    # D57⑤（feedback-0611-gate，回收 R-001 保留）：目录发布权严格 v5「目录发布 = 业务运营员」。
    # R-001 当时给 MANAGER 的「仅自家目录发布权」无签字背书、且"仅自家"限定后端从未实现——
    # 既偏离 v5 又未兑现自身限定的中间态，按 D57⑤ 回收；管理员职责定格在「审核」一级（部门审）。
    "catalog.entry.publish.execute": {"ROLE_BUSIAUDIT"},
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
    # D55/G1（撤回 R-007 交叉审）：照旧平台角色菜单 v5「资源挂接审核 / 资源审核 = 部门管理员」校正，
    # 挂接资产审核归部门管理员（docx 部门管理员待办明文含「资源发布审核」）。
    "resource.asset.review.execute": {"ROLE_ORGAN_MANAGER"},
    # D57⑤ 同口径机械延伸（feedback-0611-gate）：v5「资源发布 = 业务运营员」，与目录发布同构——
    # R-001 给 MANAGER 的资源发布保留同样无签字且"仅自家"未实现，一并回收（#251 R3 发布队列 UI
    # 已门控仅 BUSIAUDIT，本次把 policy 对齐到同口径、收口 UI 窄于 policy 的分歧）。
    "resource.asset.publish.execute": {"ROLE_BUSIAUDIT"},

    # 申请受理（资源端）
    "application.resource.submit.execute": {"ROLE_ORGAN_OPERATER"},
    # D55/P21（受理/审核两级，改 D49 关联）：无条件共享 = 业务运营员受理即终（受理=初级审核，
    # 单步即终）。受理是平台级动作（业务运营员是省大数据局平台方），不适用 self_approval / R11
    # 方向 guard（无提供方部门方向概念）。资源类受理入口 key 不改名（API surface 稳定，D33 先例），
    # 仅迁移角色 ROLE_ORGAN_MANAGER → ROLE_BUSIAUDIT。
    "application.resource.review.execute": {"ROLE_BUSIAUDIT"},
    # D55/P21 有条件共享两级（stage 顺序对调，改 D49 关联）：受理（第一级）→ 部门审核（第二级）。
    #   第二级=部门审核 = 提供方部门管理员（复用 application.dept_approve.execute key，状态机
    #   dept_approved → granted/rejected）；resubmit（补件重提）由申请人 OPERATER 发起，两动作
    #   共用本 key，运行时 self_approval / R11 方向 / applicant 校验在 ConditionalApprovalService
    #   + policy guard 内做细粒度门控（self/方向 guard 保留在本部门审核级）。
    "application.dept_approve.execute": {"ROLE_ORGAN_MANAGER", "ROLE_ORGAN_OPERATER"},
    #   第一级=受理 = 省大数据局业务运营员（初级审核，复用 application.platform_approve.execute
    #   key，状态机 submitted → dept_approved/rejected）。受理是平台级动作，不适用方向 guard。
    "application.platform_approve.execute": {"ROLE_BUSIAUDIT"},
    "delivery.access.grant.execute": {"ROLE_ORGAN_MANAGER"},
    # J1 凭据签发 — 审批通过自动触发；手工补签由审批人/主管部门触发
    "credential.issue.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    # J1 凭据查询 — 申请人 P4 凭据领取页 + 审批人 / 主管部门 / 审计员
    # D55/P18：安全审计员退出凭据查询（领数据口径统一）
    "credential.query.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
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
    "catalog.manage_entry.execute": {"ROLE_ORGAN_OPERATER"},
    "catalog.model.upsert.execute": {"ROLE_ORGAN_OPERATER"},
    "catalog.schema.mapping.upsert.execute": {"ROLE_ORGAN_OPERATER"},
    "metadata.schema.snapshot.upsert.execute": {"ROLE_ORGAN_OPERATER"},
    "metadata.gather.evidence.upsert.execute": {"ROLE_ORGAN_OPERATER"},
    # D55/P22：安全审计员收敛纯只读，移除谱系/质量 upsert 写权（保留 OPERATER 编制侧）。
    "metadata.lineage.upsert.execute": {"ROLE_ORGAN_OPERATER"},
    "ops.catalog.quality.upsert.execute": {"ROLE_ORGAN_OPERATER"},
    # PR #60 后修复：BUSIAUDIT 主管部门需要直接管理资产
    "resource.manage_asset.execute": {"ROLE_ORGAN_OPERATER"},

    # 共享专题/能力包
    # 专题包退出本期（D55/P6），保留 capability 注册与数据，仅去角色授权与入口。
    # zone.publish_topic_projection（发布专题投影）属专题包链路，随之退出；manifest 仍声明
    # permissions，PERMISSION_ROLES 不再授予任何角色 → enforce_manifest_policy 对所有调用方
    # fail-closed（无人可调），数据与注册保留待复活。
    # "zone.publish_topic_projection.execute": {"ROLE_BUSIAUDIT"},  # 退出本期（D55/P6）
    # 外部系统/能力包生命周期全链收归平台运维员（D55/P2 能力面补漏，同上）。
    "package.review_decide.execute": {"ROLE_SYSTEM"},
    "capability.package.register.execute": {"ROLE_SYSTEM"},
    "capability.version.submit.execute": {"ROLE_SYSTEM"},
    "capability.version.review.execute": {"ROLE_SYSTEM"},
    "capability.exposure.configure.execute": {"ROLE_SYSTEM"},
    "tenant.capability.enable.execute": {"ROLE_SYSTEM"},
    "tenant.capability.disable.execute": {"ROLE_SYSTEM"},
    "registry.artifact.export.execute": {"ROLE_SYSTEM", "ROLE_SECURITY_AUDIT"},
    "package.register_version.execute": {"ROLE_SYSTEM"},
    "package.apply_tenant_policy.execute": {"ROLE_SYSTEM"},
    "package.configure_exposure.execute": {"ROLE_SYSTEM"},

    # E3 Wave-2 三引擎 — 审批流模板入库（平台运维员；D55/P3 反转 D49 配置角色：项目级管理员→平台运维员）
    "approval_flow.schema.commit.execute": {"ROLE_SYSTEM"},
    # E3 Wave-2 三引擎 — 审批流 NL 草稿 + 三步流程（平台运维员）
    "approval_flow.nl_draft.execute": {"ROLE_SYSTEM"},
    "approval_flow.schema.promote_to_preview.execute": {"ROLE_SYSTEM"},
    "approval_flow.schema.revert_to_draft.execute": {"ROLE_SYSTEM"},
    # E3 Wave-2 三引擎 — 表单模板入库（平台运维员）
    "form_schema.commit.execute": {"ROLE_SYSTEM"},
    # E3 Wave-2 三引擎 — 表单 NL 草稿 + 三步流程（平台运维员）
    "form_schema.nl_draft.execute": {"ROLE_SYSTEM"},
    "form_schema.promote_to_preview.execute": {"ROLE_SYSTEM"},
    "form_schema.revert_to_draft.execute": {"ROLE_SYSTEM"},
    # E3 Wave-2 三引擎 — 推荐规则入库（平台运维员）+ J1 申请前置目录推荐（用户面）
    "recommendation.rule.commit.execute": {"ROLE_SYSTEM"},
    "recommendation.similar_catalog.suggest.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},

    # 合规 / 风险事件 — 合规调查/风险处置写权随安全管理员退役 + 安全审计员收敛纯只读而本期退役
    # （D55/P22）。这些写 capability 原 {SECURITY_AUDIT} 独有；安全审计员转纯只读后无人承做，
    # 按 Wave 0 topic.package 模式退役：PERMISSION_ROLES 移除该 key + manifest product_scope.status
    # 置 deferred → enforce_manifest_policy 对全角色 fail-closed（无人可调），保注册保数据待
    # 数据安全中心立项恢复。retired keys（PERMISSION_ROLES 不再授予任何角色）：
    #   compliance.investigate_case / compliance.signal.ingest / risk.event.ingest /
    #   compliance.rule.configure / compliance.case.open / compliance.case.assign /
    #   compliance.case.resolve / compliance.case.close
    # 保留只读（安全审计员可读合规态，不动）：compliance.case.query / compliance.metric.query。
    "compliance.case.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "compliance.metric.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 数据标准/数据安全（原 SECURITY_ADMIN 主面；D55/P16 安全管理员退役，散权随之收口）
    # PR #60 后修复：SECURITY_AUDIT 审计读取数据标准建议是合规场景刚需
    # standard.asset.recommend：去 SECURITY_ADMIN 后仍剩 MANAGER+BUSIAUDIT+SECURITY_AUDIT，未变空。
    "standard.asset.recommend.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    # security.scan.result.sync：原 {SECURITY_AUDIT}；D55/P22 安全审计员收敛纯只读后无人承做，
    # 随数据安全中心退役（PERMISSION_ROLES 移除 key + manifest 置 deferred，全角色 fail-closed）。

    # adapter 健康
    "adapter.health.probe.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 异议（业务运营员 + 部门管理员/操作员）
    # D55/P22：安全审计员收敛纯只读，移除异议全部写动作（create/submit/accept/reject/assign/
    # reply/review/evaluate/escalate/close 各去 SECURITY_AUDIT，去后非空）；保留 objection.case.query
    # / objection.process.query / objection.metric.query 只读（审计可读异议态，不动）。
    # D55/P7：业务运营员退申请人身份（「处理别人申请≠提申请」）。提异议=用户侧动作，
    # 业务运营员退出 create/submit；保留处置侧 accept/reject/assign/reply/review/evaluate/
    # escalate/close + query（受理/处置异议是业务运营员核心职责）。
    "objection.case.create.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    "objection.case.submit.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    "objection.case.accept.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "objection.case.reject.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "objection.case.assign.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "objection.case.reply.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "objection.case.review.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "objection.case.evaluate.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "objection.case.escalate.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "objection.case.close.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "objection.case.query.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    # D55/P7：登记需求=申请人动作，业务运营员退出 demand.register（退申请人身份）。
    "demand.register.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    # demand.phase.advance / demand.list 保留业务运营员：需求汇总是运营员核心职责，工作台
    # 「待汇总需求」深链依赖之；去掉会空其汇总工作面（乔布斯决策：保留，与 P7 字面「去 demand.list」
    # 相左，按最优职责口径——汇总≠提需求）。
    "demand.phase.advance.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "demand.list.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "objection.process.query.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},
    "objection.metric.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 国家平台 adapter
    # D55/G2：安全审计员从全部 adapter.national.* 退出（纯只读；这批 deferred 不可调，移除残留授权防回潮，manifest status 不动）。
    "adapter.national.catalog.pull.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "adapter.national.resource.pull.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "adapter.national.catalog.report.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "adapter.national.resource.report.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "adapter.national.application.submit.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "adapter.national.application.receive.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "adapter.national.application.reconcile.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "adapter.national.delivery.receipt.sync.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "adapter.national.objection.sync.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "adapter.national.topic.report.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    # 国家扩展要素编制（D50/C5，J2 子旅程）：部门管理员编制 + 业务运营员主管审核（SPEC 角色）。
    "catalog.national_ext_elem.compile.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    # 国家直达转报（D50/C6，J1 子旅程）：仅业务运营员转报本级申请到国家平台（SPEC 角色）。
    "application.escalate_national.execute": {"ROLE_BUSIAUDIT"},

    # adapter 级联消费 / 外部映射（permission-matrix-0610 复审收归）：
    # 外部系统类能力照 D55/P2 收归平台运维员（integration-admin shell 已仅 SYSTEM）；
    # consume/replay 是写动作，安全审计员纯只读（D55/P22）不得持有。
    # cascade.* manifest=deferred:wave-3（不可调，移除残留授权防回潮，照 D55/G2 先例
    # manifest status 不动）；external.mapping.query=live，无前端 CTA、调用面在后台。
    "adapter.cascade.consume.execute": {"ROLE_SYSTEM"},
    "adapter.cascade.replay.execute": {"ROLE_SYSTEM"},
    "adapter.cascade.health.query.execute": {"ROLE_SYSTEM"},
    "adapter.external.mapping.query.execute": {"ROLE_SYSTEM"},

    # 租户策略
    "tenant.policy.evaluate.execute": {"ROLE_ORGAN_MANAGER", "ROLE_SECURITY_AUDIT", "ROLE_SYSTEM"},

    # 组织/Actor projection（IAM 同步）
    # D55/P22：安全审计员收敛纯只读，移除 projection 同步写权（保留 BUSIAUDIT / system）。
    "org.projection.sync.execute": {"ROLE_BUSIAUDIT"},
    "actor.projection.sync.execute": {"ROLE_BUSIAUDIT", "system"},

    # 旧 BSP / sharezone 映射导入
    # D55/P22：安全审计员收敛纯只读，移除 legacy 映射导入写权（保留 BUSIAUDIT）。
    "legacy.bsp.mapping.import.execute": {"ROLE_BUSIAUDIT"},
    "legacy.sharezone.mapping.import.execute": {"ROLE_BUSIAUDIT"},

    # M0 实施工程师专用（admin 主用；BUSIAUDIT/SECURITY_AUDIT 验收日代看）
    "legacy.migration.status.query.execute": {"admin", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 反向编目（J2）— 部门操作员 + 部门管理员发起，BUSIAUDIT 审核（v5 旧平台口径，D55/P14）
    "catalog.entry.reverse_draft.suggest.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
    "catalog.entry.reverse_draft.create.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    "catalog.entry.reverse_draft.confirm.execute": {"ROLE_BUSIAUDIT"},
    "catalog.entry.reverse_draft.reject.execute": {"ROLE_BUSIAUDIT"},

    # schema 发现 — 反向编目入口；操作员 + 管理员 + 业务运营员可拉取候选 schema（D55/P14）
    "metadata.schema.discover.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},

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
    # D55/P13：订阅终止加操作员（领数据回归操作员+管理员）
    "subscription.terminate.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},

    # 专题包（共享专区）退出本期（D55/P6）：保留 capability 注册与数据，仅去角色授权与入口。
    # 各 manifest 仍声明对应 permission，但 PERMISSION_ROLES 不再授予任何角色 →
    # enforce_manifest_policy 对所有调用方 fail-closed（无人可调）。下线整面、保数据不删库，
    # 待专题包复活时恢复以下角色映射。
    # "topic.package.create.execute": {"ROLE_BUSIAUDIT"},  # 退出本期（D55/P6）
    # "topic.package.configure.execute": {"ROLE_BUSIAUDIT"},  # 退出本期（D55/P6）
    # "topic.package.submit.execute": {"ROLE_BUSIAUDIT"},  # 退出本期（D55/P6）
    # "topic.package.review.execute": {"ROLE_BUSIAUDIT"},  # 退出本期（D55/P6）
    # "topic.package.publish.execute": {"ROLE_BUSIAUDIT"},  # 退出本期（D55/P6）
    # "topic.package.policy.update.execute": {"ROLE_BUSIAUDIT"},  # 退出本期（D55/P6）
    # "topic.package.subscribe.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},  # 退出本期（D55/P6）
    # "topic.package.evidence.attach.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},  # 退出本期（D55/P6）
    # "topic.package.query.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},  # 退出本期（D55/P6）
    # "topic.package.metric.query.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},  # 退出本期（D55/P6）

    # 交付回执 / exchange
    # D55/G2：回执登记是写动作，安全审计员退出（纯只读）。
    "delivery.receipt.ingest.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"},
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

    # 工单 / 巡检（运维侧）
    # D55/P22·P23：安全审计员收敛纯只读，工单创建/关闭与值班巡检改派平台运维员（ROLE_SYSTEM）。
    "ops.ticket.create.execute": {"ROLE_SYSTEM"},
    "ops.ticket.close.execute": {"ROLE_SYSTEM"},
    "ops.shift_handover.submit.execute": {"ROLE_SYSTEM"},

    # 需求登记（D27 #6 智能推荐前置，下期实施）
    "require.intent.submit.execute": {"ROLE_ORGAN_OPERATER"},
    "require.intent.refine.execute": {"ROLE_ORGAN_OPERATER"},
    "require.intent.review.execute": {"ROLE_ORGAN_MANAGER"},
    "require.resource.match.execute": {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"},

    # 订阅管理 / 应急熔断
    # D55/P13：订阅管理回归操作员+管理员（去 BUSIAUDIT，加 OPERATER，Wave1-S4）
    "delivery.subscription.manage.execute": {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"},
    # D55/P22：应急熔断为写操作，安全审计员收敛纯只读后退出，归平台运维员（Wave1-S5）。
    "system.toggle_outage.execute": {"ROLE_SYSTEM"},

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
