"""J1 供需对接三态状态机。

状态定义：
  1. pending_response — 需求已登记，等待提供方部门管理员响应
  2. responded        — 提供方已确认提供 / 拒绝提供 / 退回补正
  3. closed           — 需求已关闭

BR 聚合（Business Requirement meta 合并）独立于 demand response status：BR 自身存
application_record kind='business_requirement'，含 application_ids 列表 + merge_reason
等 meta-only 字段；原始 demand 的 response_status 不会被合并改写。
"""

from __future__ import annotations

DEMAND_STATUS_PENDING_RESPONSE = "pending_response"
DEMAND_STATUS_RESPONDED = "responded"
DEMAND_STATUS_CLOSED = "closed"

ALL_DEMAND_STATUSES: tuple[str, ...] = (
    DEMAND_STATUS_PENDING_RESPONSE,
    DEMAND_STATUS_RESPONDED,
    DEMAND_STATUS_CLOSED,
)

ALLOWED_DEMAND_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    DEMAND_STATUS_PENDING_RESPONSE: frozenset({DEMAND_STATUS_RESPONDED}),
    DEMAND_STATUS_RESPONDED: frozenset({DEMAND_STATUS_CLOSED}),
    DEMAND_STATUS_CLOSED: frozenset(),
}


class SupplyDemandStatusError(ValueError):
    pass


def assert_status_transition(current: str, next_status: str) -> None:
    allowed = ALLOWED_DEMAND_STATUS_TRANSITIONS.get(current, frozenset())
    if next_status not in allowed:
        raise SupplyDemandStatusError(
            f"invalid supply-demand status transition: {current} -> {next_status}"
        )
