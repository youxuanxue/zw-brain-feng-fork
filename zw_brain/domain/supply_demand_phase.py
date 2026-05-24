"""J1 供需对接 6 步状态机（plan e1-j1-journey F4）.

阶段定义（与 feature j1-supply-demand-meta-merge.feature 对齐）:
  1. gap_discovered      — 用户在 P2 找不到资源
  2. registered          — 登记需求（application_record kind='demand'）
  3. recommend_failed    — 智能推荐失败 (Wave 1 规则匹配未命中；AI 推荐归 E3 Wave 2)
  4. manual_registered   — 转人工需求登记 (BUSIAUDIT 介入)
  5. provider_responded  — 部门响应（提供方反馈）
  6. subscribed          — 完成订阅（端到端订阅生效）

REGISTERED → PROVIDER_RESPONDED 跳过 recommend_failed/manual_registered 路径保留：
真实业务中规则匹配命中即可直接发提供方，不必经人工补登。

BR 聚合（Business Requirement meta 合并）独立于 6 步 phase：BR 自身存
application_record kind='business_requirement'，含 application_ids 列表 + merge_reason
等 meta-only 字段；原始 demand 的 phase / status 不会被合并改写。
"""

from __future__ import annotations

PHASE_GAP_DISCOVERED = "gap_discovered"
PHASE_REGISTERED = "registered"
PHASE_RECOMMEND_FAILED = "recommend_failed"
PHASE_MANUAL_REGISTERED = "manual_registered"
PHASE_PROVIDER_RESPONDED = "provider_responded"
PHASE_SUBSCRIBED = "subscribed"

ALL_PHASES: tuple[str, ...] = (
    PHASE_GAP_DISCOVERED,
    PHASE_REGISTERED,
    PHASE_RECOMMEND_FAILED,
    PHASE_MANUAL_REGISTERED,
    PHASE_PROVIDER_RESPONDED,
    PHASE_SUBSCRIBED,
)

ALLOWED_PHASE_TRANSITIONS: dict[str, frozenset[str]] = {
    PHASE_GAP_DISCOVERED: frozenset({PHASE_REGISTERED}),
    PHASE_REGISTERED: frozenset({PHASE_RECOMMEND_FAILED, PHASE_PROVIDER_RESPONDED}),
    PHASE_RECOMMEND_FAILED: frozenset({PHASE_MANUAL_REGISTERED}),
    PHASE_MANUAL_REGISTERED: frozenset({PHASE_PROVIDER_RESPONDED}),
    PHASE_PROVIDER_RESPONDED: frozenset({PHASE_SUBSCRIBED}),
    PHASE_SUBSCRIBED: frozenset(),
}


class SupplyDemandPhaseError(ValueError):
    pass


def assert_phase_transition(current: str, next_phase: str) -> None:
    allowed = ALLOWED_PHASE_TRANSITIONS.get(current, frozenset())
    if next_phase not in allowed:
        raise SupplyDemandPhaseError(
            f"invalid supply-demand phase transition: {current} -> {next_phase}"
        )
