# Wave: 2
# Twin-F: e3.F9
# Covers: F9 P7 共享专区 / 专题包 — 专题包退出本期（D55/P6）后的策展/发布退役契约
"""F9 curation 退役契约集成测试（D55/P6：专题包退出本期）。

专题包整面退出本期：状态机 handler / repo / seed 数据保留不删，仅去 PERMISSION_ROLES
角色授权与前端入口。原「8 态发布状态机经 ROLE_BUSIAUDIT 真流转绿」因此翻为退役不变量：
策展/发布/审核/policy/evidence 全链 capability 对编制岗（及所有现行业务角色）fail-closed
（invoke_skill 收口为 AccessDeniedError，无人可调），待专题包立项复活时恢复角色授权。
"""
from __future__ import annotations

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.domain.errors import AccessDeniedError
from zw_brain.domain.role_codes import BUSINESS_ROLE_CODES

# 每个测试由 root conftest 的 autouse function-scoped fixture 分到一个空 PG 克隆库；
# 退役锁断言只需 schema（capability 注册 + 策略门），不依赖真实旧平台数据。
EDIT = "ROLE_BUSIAUDIT"

# 退役前曾授权给编制/审核岗的专题包策展链路 capability，现应 fail-closed。
RETIRED_CURATION_CAPABILITIES = (
    "topic.package.create",
    "topic.package.configure",
    "topic.package.submit",
    "topic.package.review",
    "topic.package.publish",
    "topic.package.policy.update",
    "topic.package.evidence.attach",
)


def _new_brain():
    from zw_brain.command.brain import BrainService
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    audit_bus.clear_sink()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=ss)


# 覆盖各 capability input_schema.required 的并集，确保调用越过 schema 校验、抵达策略门，
# 从而真正断言「退役锁」（AccessDeniedError）而非被前置的 schema 校验掩盖。
_SUPERSET_PAYLOAD = {
    "confirmed": True,
    "package_code": "tp-flow-happy",
    "title": "退役锁验证",
    "decision": "approve",
}


@pytest.mark.parametrize("capability", RETIRED_CURATION_CAPABILITIES)
def test_curation_capability_denied_for_edit_role(capability: str) -> None:
    """退役锁：策展/发布链 capability 对原编制/审核岗 ROLE_BUSIAUDIT fail-closed（D55/P6）。"""
    brain = _new_brain()
    with pytest.raises(AccessDeniedError):
        invoke_trusted(brain, capability, dict(_SUPERSET_PAYLOAD), role=EDIT)


@pytest.mark.parametrize("capability", RETIRED_CURATION_CAPABILITIES)
def test_curation_capability_denied_for_all_business_roles(capability: str) -> None:
    """退役锁覆盖全角色：无任何现行业务角色可调专题包策展链 capability（D55/P6）。"""
    brain = _new_brain()
    for role in BUSINESS_ROLE_CODES:
        with pytest.raises(AccessDeniedError):
            invoke_trusted(brain, capability, dict(_SUPERSET_PAYLOAD), role=role)
