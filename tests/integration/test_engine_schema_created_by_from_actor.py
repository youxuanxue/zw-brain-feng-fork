"""created_by 出处不可伪造 — 引擎 schema 草稿落库的 created_by 取自服务端解析的
真实 actor，客户端 payload 里硬串的伪造 created_by 必须被忽略（D11/D47/D55⑤）。

历史裂缝：EnginesAdmin.vue 客户端把 `created_by:'user:gov:ROLE_ORGAN_MANAGER:webui'`
硬串塞进会持久化的审批流/表单草稿出处——出处客户端可伪造，且硬编 ROLE_ORGAN_MANAGER
与「流程表单配置归平台运维员 ROLE_SYSTEM」打架。本测试钉死后端只认服务端 actor。

非 feature-backed：纯后端单元回归，不进 .feature 测量轴（不触发 e2e 重采）。
"""
from __future__ import annotations

from tests._trusted_payload import invoke_trusted

# 每个测试由 root conftest 的 autouse function-scoped fixture 分到一个空 PG 克隆库；
# 草稿落库写进各自隔离克隆，不依赖真实旧平台数据。

# 客户端伪造的出处——后端必须忽略它。后缀 :webui 与服务端 actor_for_role 的
# :{ACTOR_NAMES[role]} 后缀不同，使断言可判别。
FORGED_CREATED_BY = "user:gov:ROLE_ORGAN_MANAGER:webui"
# 配置引擎草稿的合法角色 = 平台运维员（D55⑤）。
CONFIG_ROLE = "ROLE_SYSTEM"


def _new_brain():
    from zw_brain.command.brain import BrainService
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    audit_bus.clear_sink()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=ss), audit_bus, ds


def _expected_actor_prefix() -> str:
    # 服务端 actor_for_role(role) → "user:gov:{role}:{ACTOR_NAMES[role]}"；
    # dev-IAM-bypass 可能追加 "[bypass]" 后缀，故只钉前缀（含 role 段）。
    return f"user:gov:{CONFIG_ROLE}:"


def test_approval_flow_nl_draft_created_by_from_actor_not_payload():
    from zw_brain.domain.approval_flow_schema import ApprovalFlowSchemaRepo
    from zw_brain.shared.db import create_session_factory

    brain, audit_bus, _ = _new_brain()
    try:
        result = invoke_trusted(
            brain,
            "approval_flow.nl_draft",
            {
                "tenant_id": "sd-default",
                "schema_code": "created_by_guard_af_v1",
                "title": "2 级审批",
                "intent_text": "2 级审批流程",
                # 客户端硬串伪造出处——必须被后端忽略。
                "created_by": FORGED_CREATED_BY,
            },
            role=CONFIG_ROLE,
        )
    finally:
        audit_bus.clear_sink()

    assert result["ok"] is True
    schema_id = result["result"]["schema_id"]

    SessionLocal = create_session_factory()
    with SessionLocal() as s:
        record = ApprovalFlowSchemaRepo(s).get(schema_id)

    assert record.created_by != FORGED_CREATED_BY, (
        "客户端伪造的 created_by 不得落库"
    )
    assert record.created_by.startswith(_expected_actor_prefix()), (
        f"created_by 须取服务端解析的真实 actor（{_expected_actor_prefix()}…），"
        f"实际={record.created_by!r}"
    )


def test_approval_flow_nl_draft_no_created_by_in_payload_ok():
    """payload 完全不带 created_by 也应成功——出处不再是必填客户端字段。"""
    from zw_brain.domain.approval_flow_schema import ApprovalFlowSchemaRepo
    from zw_brain.shared.db import create_session_factory

    brain, audit_bus, _ = _new_brain()
    try:
        result = invoke_trusted(
            brain,
            "approval_flow.nl_draft",
            {
                "tenant_id": "sd-default",
                "schema_code": "created_by_guard_af_v2",
                "title": "1 级审批",
                "intent_text": "1 级审批",
            },
            role=CONFIG_ROLE,
        )
    finally:
        audit_bus.clear_sink()

    assert result["ok"] is True
    schema_id = result["result"]["schema_id"]
    SessionLocal = create_session_factory()
    with SessionLocal() as s:
        record = ApprovalFlowSchemaRepo(s).get(schema_id)
    assert record.created_by.startswith(_expected_actor_prefix())


def test_form_schema_nl_draft_created_by_from_actor_not_payload():
    from zw_brain.domain.form_schema import FormSchemaRepo
    from zw_brain.shared.db import create_session_factory

    brain, audit_bus, _ = _new_brain()
    try:
        result = invoke_trusted(
            brain,
            "form_schema.nl_draft",
            {
                "tenant_id": "sd-default",
                "form_code": "created_by_guard_form_v1",
                "title": "极简申请表",
                "intent_text": "申请表：姓名、联系电话",
                "created_by": FORGED_CREATED_BY,
            },
            role=CONFIG_ROLE,
        )
    finally:
        audit_bus.clear_sink()

    assert result["ok"] is True
    schema_id = result["result"]["schema_id"]
    SessionLocal = create_session_factory()
    with SessionLocal() as s:
        record = FormSchemaRepo(s).get(schema_id)

    assert record.created_by != FORGED_CREATED_BY, "客户端伪造的 created_by 不得落库"
    assert record.created_by.startswith(_expected_actor_prefix()), (
        f"created_by 须取服务端真实 actor，实际={record.created_by!r}"
    )


def test_form_schema_nl_draft_no_created_by_in_payload_ok():
    from zw_brain.domain.form_schema import FormSchemaRepo
    from zw_brain.shared.db import create_session_factory

    brain, audit_bus, _ = _new_brain()
    try:
        result = invoke_trusted(
            brain,
            "form_schema.nl_draft",
            {
                "tenant_id": "sd-default",
                "form_code": "created_by_guard_form_v2",
                "title": "极简申请表",
                "intent_text": "申请表：姓名",
            },
            role=CONFIG_ROLE,
        )
    finally:
        audit_bus.clear_sink()

    assert result["ok"] is True
    schema_id = result["result"]["schema_id"]
    SessionLocal = create_session_factory()
    with SessionLocal() as s:
        record = FormSchemaRepo(s).get(schema_id)
    assert record.created_by.startswith(_expected_actor_prefix())
