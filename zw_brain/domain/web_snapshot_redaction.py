"""Web UI snapshot redaction — align server-side preload with shell / ZW_PAGE_ACCESS.

Full runtime state remains in :meth:`zw_brain.command.brain.BrainService.snapshot` for
DB sync and tests; only ``system.snapshot`` / ``GET /api/snapshot`` serve this shape.
"""

from __future__ import annotations

import copy
from typing import Any

# D23 (2026-05-19): R1-R8 退役。Mirrors zw-brain-web/js/pages.js `window.ZW_PAGE_ACCESS` — update both when nav roles change.
# 角色码（D55/P16 安全管理员退役后 5 业务角色）：ROLE_ORGAN_OPERATER / ROLE_ORGAN_MANAGER / ROLE_BUSIAUDIT / ROLE_SECURITY_AUDIT / ROLE_SYSTEM
# D55/P17：安全审计员非数据使用方（v5 无找数据），收敛纯只读监督者后退出找数据预载。
_DISCOVERY = frozenset({"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"})
# ROLE_BUSIAUDIT：j1-credential-revoke 决策 A —— 业务运营员合规收回/暂停授权需在 P3 申请详情
# 操作，故须能预载 requests（与 productShellNav「办共享申请」shell 对齐）；否则 shell 进得去但
# 申请列表/详情空（lookupRequest → 未找到该申请），合规撤回入口不可达。
_REQUEST = frozenset({"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"})
# D55/P18：安全审计员退出领数据（delivery_tasks 快照裁剪对齐）
_DELIVERY = frozenset({"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"})
# provider snapshot 是 "shell + sub-key" 两层鉴权：
#   _PROVIDER_FULL：见全部 sub-keys（catalogs + 各 reviewer/responder 待办）。
#   _PROVIDER_PARTIAL：只看 _PROVIDER_PARTIAL_KEYS 列出的 sub-keys（J2 在线编制 OPERATER 视角）。
#   其他 role：整个 provider dict empty。
# 与 zw-brain-web/src/lib/pageAccess.ts ROUTE_ROLE_OVERRIDES 对齐：
# MANAGER/BUSIAUDIT 进所有 /provider/inbox/*；MANAGER 也可进 /provider/wizard/inline-catalog + reverse-catalog（D55/P11·P14）；
# OPERATER 进 /provider + /provider/wizard/inline-catalog（D55/P11）
# + /provider/wizard/api-service，wizard 提交后 P5Provider/列表展示「我的目录」「我的 API 服务」，
# 故 OPERATER 需 catalogs + services（D54 GATE-1：代理服务注册 = 部门操作员 + 部门管理员；
# 操作员注册后须能看到并提交自己的 API 服务草稿）。
# 另需 resources：T9 供数侧「资源管理清单」只读浏览岗位含部门操作员（业务方 2026-06-09——操作员=
# 挂接/编制者也需看本部门已挂接资源跟踪状态），故操作员 snapshot 须带 provider.resources（只读，
# 无行内管理动作；与 requestFlowRoles.PROVIDER_ASSET_VIEWER_ROLES 对齐）。
_PROVIDER_FULL = frozenset({"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"})
_PROVIDER_PARTIAL = frozenset({"ROLE_ORGAN_OPERATER"})
_PROVIDER_PARTIAL_KEYS = frozenset({"catalogs", "services", "resources"})
# 查审计页 shell（disputes / alerts / tickets / knowledge_articles 等合规运营内容）。
# 异议 / 合规 capability 角色由 S5 流处理；此 shell-preload 集本流不收窄（仅审计日志另拆 _AUDIT_LOG）。
# ROLE_SECURITY_ADMIN 随安全管理员本期退役而移除（D55/P16）。
_COMPLIANCE = frozenset(
    {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT", "ROLE_SYSTEM"}
)
# 审计日志 / 证据回放 / 审计事件面（audit_events / audit_ai）—— 查审计拆分（D55/P8·P9，Wave1-S3）：
# 收窄到「业务运营员 + 安全审计员」。部门管理员 / 平台运维员退审计日志，不再预载。
# 与后端 audit.event.* / audit.list / audit.replay_evidence_chain 角色集 + compliance-ops nav 一致。
_AUDIT_LOG = frozenset({"ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"})
_ZONES = frozenset({"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"})
_CAPABILITY = frozenset({"ROLE_BUSIAUDIT", "ROLE_SYSTEM"})
# api_resources 预载（外部系统 / 代理服务 API 面）——本流不动。
_OPS = frozenset({"ROLE_BUSIAUDIT", "ROLE_SYSTEM"})
# 服务调用监控（gateway_runtime_statuses / service_invocation_metrics）—— 查审计拆分（D55/P8）：
# 平台运维员保留服务调用监控（v5），管理员 / 审计只读。与后端 ops.service.report.query.execute +
# service-ops nav 角色门一致。
_SERVICE_OPS = frozenset({"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT", "ROLE_SYSTEM"})

_EMPTY_DISCOVERY: dict[str, Any] = {
    "zones": [],
    "resources": [],
    "catalogTree": [],
    "aiCopilot": {
        "summary": "",
        "missingQuestions": [],
        "nextActions": [],
        "evidence": [],
    },
}

_EMPTY_PROVIDER: dict[str, Any] = {
    "overview": [],
    "catalogs": [],
    "resources": [],
    "services": [],
    "field_decisions": [],
    "hookup_reviews": [],
    "demand_matches": [],
    "objection_cases": [],
    "aiGovernance": {
        "summary": "",
        "priorities": [],
        "draft": "",
        "evidence": [],
    },
}

_EMPTY_AUDIT_AI: dict[str, Any] = {"summary": "", "evidence": []}


def redact_webui_snapshot(full: dict[str, Any], role: str) -> dict[str, Any]:
    """Deep-copy *full* and clear collections the given Web UI role must not preload."""
    out = copy.deepcopy(full)
    if role not in _DISCOVERY:
        out["discovery"] = copy.deepcopy(_EMPTY_DISCOVERY)
    if role not in _REQUEST:
        out["requests"] = []
        out["approvals"] = []
    if role not in _DELIVERY:
        out["delivery_tasks"] = []
    if role in _PROVIDER_FULL:
        pass  # 保留完整 provider 视图
    elif role in _PROVIDER_PARTIAL:
        # 仅保留 _PROVIDER_PARTIAL_KEYS 列出的 sub-keys，其余清空到 _EMPTY_PROVIDER 默认。
        current = out.get("provider") or {}
        partial = copy.deepcopy(_EMPTY_PROVIDER)
        for key in _PROVIDER_PARTIAL_KEYS:
            if key in current:
                partial[key] = current[key]
        out["provider"] = partial
    else:
        out["provider"] = copy.deepcopy(_EMPTY_PROVIDER)
    if role not in _COMPLIANCE:
        out["disputes"] = []
        out["alerts"] = []
        out["tickets"] = []
        out["knowledge_articles"] = []
    # 审计日志面单独收窄（D55/P8·P9）：管理员 / 运维员虽进合规 shell，但不预载审计事件 / AI 摘要。
    if role not in _AUDIT_LOG:
        out["audit_events"] = []
        out["audit_ai"] = copy.deepcopy(_EMPTY_AUDIT_AI)
    if role not in _ZONES:
        out["zones"] = []
    if role not in _CAPABILITY:
        out["capability_packages"] = []
    if role not in _OPS:
        out["api_resources"] = []
    # 服务调用监控（D55/P8）：平台运维员 + 业务运营员 + 管理员/审计只读可预载网关运行 / 调用统计。
    if role not in _SERVICE_OPS:
        out["gateway_runtime_statuses"] = []
        out["service_invocation_metrics"] = []
    return out
