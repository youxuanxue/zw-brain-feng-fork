"""R-008 单一事实源：zw-brain 角色码与显示名（D23 retrofit）.

所有需要"6 ROLE_* + admin/system"集合的地方都从此模块导入，避免基线附录 C
明确禁止的"控制面多处手维护投影"。

下游消费者（必须从本文件导入而非自行硬编码）：
- zw_brain.domain.policy.ACTOR_NAMES (权限矩阵权威源)
- zw_brain.entry.rest.server._DEV_IAM_BYPASS_ROLES
- zw_brain.domain.web_snapshot_redaction
- 前端：通过 export_agent_contract.py 生成的 OpenAPI enum（system.snapshot.role）派生

（alembic 0009 旧消费者已在 v4.1 R15 删除 alembic 时一并清理）

未直接消费但需保持同步（测试 test_role_codes_alignment.py 验证）：
- zw-brain-web/js/app.js ROLE_NAMES
- zw-brain-web/js/pages.js roleLabel / ROLE_HERO
"""
from __future__ import annotations

# 6 个业务角色 + 2 个系统角色
# 顺序约定：业务高频角色在前（OPERATER → MANAGER → BUSIAUDIT），低频在后（SECURITY → SYSTEM）
BUSINESS_ROLE_CODES: tuple[str, ...] = (
    "ROLE_ORGAN_OPERATER",
    "ROLE_ORGAN_MANAGER",
    "ROLE_BUSIAUDIT",
    "ROLE_SECURITY_ADMIN",
    "ROLE_SECURITY_AUDIT",
    "ROLE_SYSTEM",
)

# 系统角色（不分配给人）
SYSTEM_ROLE_CODES: tuple[str, ...] = (
    "admin",   # 平台实施工程师（M0 验收监控）
    "system",  # IAM 自动写
)

# 所有合法角色码（CHECK 约束与启动检查的白名单）
ALL_ROLE_CODES: tuple[str, ...] = BUSINESS_ROLE_CODES + SYSTEM_ROLE_CODES

# 角色显示名（中文，UI 展示）
ROLE_DISPLAY_NAMES_ZH: dict[str, str] = {
    "ROLE_ORGAN_OPERATER": "部门操作员",
    "ROLE_ORGAN_MANAGER": "部门管理员",
    "ROLE_BUSIAUDIT": "业务运营员",
    "ROLE_SECURITY_ADMIN": "安全管理员",
    "ROLE_SECURITY_AUDIT": "安全审计员",
    "ROLE_SYSTEM": "平台运维员",
    "admin": "实施工程师",
    "system": "系统",
}

# 角色层级（manager 隐式包含 operater 权限）
ROLE_HIERARCHY: dict[str, frozenset[str]] = {
    "ROLE_ORGAN_MANAGER": frozenset({"ROLE_ORGAN_OPERATER"}),
}

# 标签位：依附 ROLE_ORGAN_MANAGER；仅基础主题分类相关 2 项权限
# R-014 fix: 此处仅保留标签位描述；启动校验在 enforce_manifest_policy 中实现
TAG_LEAD_DEPT = "tag_lead_dept"

# 历史用户角色码（R1-R8）— 仅用于启动检查兜底
# D23 retrofit (2026-05-19) 一次性退役
LEGACY_ROLE_CODES: frozenset[str] = frozenset(
    {"r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"}
)
