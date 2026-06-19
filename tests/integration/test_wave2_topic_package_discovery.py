# Wave: 2
# Twin-F: e3.F9
# Covers: F9 P7 共享专区 / 专题包 — 专题包退出本期（D55/P6）后的退役契约
"""F9 专题包退役契约集成测试（D55/P6：专题包退出本期）。

专题包整面退出本期：保 capability 静态注册 + seed 数据不删库，仅去 PERMISSION_ROLES
角色授权与前端入口。本测试因此从「query/subscribe/metric 真链路绿」翻为「退役不变量」：

  1) 退役锁有效：每个 topic.package.* capability 经 `invoke_trusted`（模拟 BFF 验证后路径）
     对所有现行业务角色都 fail-closed（DomainAccessDeniedError），无人可调。
  2) 数据/注册保留：seed_snapshot.json 的 3 山东标杆专题包数据仍在（保数据不删库，
     守 D11 真数据 + D55/P6「保留 capability 注册与数据」），待数据安全中心外的专题包
     立项复活时可直接恢复角色授权。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.domain.errors import AccessDeniedError
from zw_brain.domain.role_codes import BUSINESS_ROLE_CODES

# invoke_skill 把 domain 层 DomainAccessDeniedError 收口为 errors.AccessDeniedError（→403），
# 故退役锁的可观测异常是 AccessDeniedError（D55/P6 fail-closed 契约）。
# 每个测试由 root conftest 的 autouse function-scoped fixture 分到一个空 PG 克隆库；
# 退役锁断言只需 schema，seed 数据留存断言读 seed_snapshot.json 文件、不碰 DB。

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED = REPO_ROOT / "zw_brain" / "domain" / "seed_snapshot.json"
BENCHMARKS = ("tp-yiliao-jiuzhu", "tp-yibao-code", "tp-yidi-jiuyi")

# 退役前曾授权的 topic.package.* capability（含 zone.publish_topic_projection），现应全员 fail-closed。
RETIRED_TOPIC_PACKAGE_CAPABILITIES = (
    "topic.package.create",
    "topic.package.configure",
    "topic.package.submit",
    "topic.package.review",
    "topic.package.publish",
    "topic.package.policy.update",
    "topic.package.subscribe",
    "topic.package.evidence.attach",
    "topic.package.query",
    "topic.package.metric.query",
    "zone.publish_topic_projection",
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
    "package_code": "tp-yiliao-jiuzhu",
    "decision": "approve",
    "zone_id": "business",
}


@pytest.mark.parametrize("capability", RETIRED_TOPIC_PACKAGE_CAPABILITIES)
def test_topic_package_capability_denied_for_all_business_roles(capability: str) -> None:
    """退役锁：专题包 capability 对所有现行业务角色 fail-closed（D55/P6）。

    manifest 仍声明 permissions，但 PERMISSION_ROLES 不再授予任何角色 →
    enforce_manifest_policy 对每个角色都拒绝（invoke_skill 收口为 AccessDeniedError，无人可调）。
    """
    brain = _new_brain()
    for role in BUSINESS_ROLE_CODES:
        with pytest.raises(AccessDeniedError):
            invoke_trusted(brain, capability, dict(_SUPERSET_PAYLOAD), role=role)


def test_seed_topic_package_data_retained() -> None:
    """保数据不删库（D55/P6 + D11）：seed_snapshot.json 3 山东标杆专题包数据仍在，
    待复活时可直接恢复角色授权。"""
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    by_code = {p["package_code"]: p for p in seed.get("topic_packages", [])}
    for code in BENCHMARKS:
        assert code in by_code, f"{code} 标杆专题包 seed 数据缺失（退役应保数据不删库）"
    # 异地就医专题包详情仍引用真 catalog_entry（守 D11 真数据）。
    z3 = by_code["tp-yidi-jiuyi"]
    refs = {it["ref_id"] for it in z3["items"]}
    assert refs and all(ref.startswith("basic-elem:") for ref in refs)
