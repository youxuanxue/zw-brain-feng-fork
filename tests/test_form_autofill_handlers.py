"""阶段3b：表单填报 handler 接线守卫 — request.create 挂 provenance / field.update 锁定 / 提交审计。

承接 form-autofill 方案：
  - request.create 草稿挂 formFields + fieldProvenance（确定性带出 + AI建议 + 人填）。
  - request.field.update 人原地改 → human+locked，此后 autofill/AI 不覆盖；派生字段拒改。
  - request.submit 记 provenance 审计（AI 来源痕迹，不阻断）。
  - reference.{organ,region,dict}.options 选择器读取（只读，不写库）。
"""
from __future__ import annotations

from typing import Any

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.domain.errors import BrainServiceError

_RESOURCE_ID = "res-form-autofill"
_OPERATER = "ROLE_ORGAN_OPERATER"


def _unwrap(result: Any) -> dict[str, Any]:
    if isinstance(result, dict) and "result" in result and isinstance(result["result"], dict):
        return result["result"]
    return result  # type: ignore[return-value]


@pytest.fixture()
def brain(tmp_path, monkeypatch):
    monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(tmp_path / "runtime.db"))
    monkeypatch.setenv("ZW_BRAIN_AUDIT_DB_PATH", str(tmp_path / "audit.db"))

    from zw_brain.command import runtime as runtime_mod
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.audit import store as audit_store_mod

    audit_store_mod.set_default_store(None)
    runtime_mod._service = None
    audit_bus.clear_sink()
    audit_bus.drain()

    service = runtime_mod.get_service()
    service._snapshot["discovery"]["resources"].append(
        {
            "id": _RESOURCE_ID,
            "name": "表单填报测试资源",
            "status": "可复用",
            "provider": "测试部门",
            "repository": {"shared_type": "1"},
        }
    )
    yield service

    runtime_mod._service = None
    audit_bus.clear_sink()
    audit_bus.drain()
    audit_store_mod.set_default_store(None)


def _create_draft(brain, payload_extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"resource_id": _RESOURCE_ID, "confirmed": True, **(payload_extra or {})}
    out = _unwrap(invoke_trusted(brain, "request.create", payload, role=_OPERATER))
    return next(r for r in brain._snapshot["requests"] if r["id"] == out["request_id"])


def _projected_request(rid: str) -> dict[str, Any]:
    """走前端真实路径：从 DB application_record 经 enrich 投影出申请卡（formFields 读时现算）。

    这是 frontend /api/snapshot 看到的形态——比读内存 _snapshot 更真（demo-vs-real：
    内存只存模型 fieldValues+fieldProvenance，formFields 是投影层现算的只读结果）。
    """
    from zw_brain.domain.discovery_snapshot_projection import enrich_requests_snapshot

    projected = enrich_requests_snapshot({"requests": []}, tenant_id="sd-default")
    return next(r for r in projected["requests"] if r["id"] == rid)


def test_create_attaches_form_fields_and_provenance(brain) -> None:
    req = _create_draft(brain, {"purpose": "人填的用途"})
    # 模型（fieldValues + fieldProvenance）持久化在记录上；用户实填 purpose → human。
    prov = req.get("fieldProvenance") or {}
    assert prov.get("purpose", {}).get("source") == "human"
    # 前端真实看到的 formFields 走 DB→投影现算。
    proj = _projected_request(req["id"])
    by_key = {f["key"]: f for f in proj["formFields"]}
    assert by_key["purpose"]["value"] == "人填的用途"
    assert by_key["purpose"]["locked"] is True
    assert by_key["region_name"]["editable"] is False  # 派生字段只读
    assert by_key["apply_domain"]["kind"] == "enum"  # 枚举字段真接入
    assert by_key["apply_domain"]["dictType"] == "data_apply_field"  # 字典带出已挂


def test_create_ai_suggestion_marked_pending(brain) -> None:
    req = _create_draft(brain, {"ai_suggested_fields": {"purpose": "AI 拟的用途"}})
    by_key = {f["key"]: f for f in _projected_request(req["id"])["formFields"]}
    assert by_key["purpose"]["value"] == "AI 拟的用途"
    assert by_key["purpose"]["source"] == "ai_suggested"
    assert by_key["purpose"]["state"] == "ai_pending_confirm"
    assert by_key["purpose"]["stateLabel"] == "AI建议·待确认"


def test_field_update_locks_against_reautofill(brain) -> None:
    req = _create_draft(brain, {"ai_suggested_fields": {"purpose": "AI 初稿"}})
    rid = req["id"]
    out = _unwrap(invoke_trusted(brain, "request.field.update",
                                 {"request_id": rid, "field": "purpose", "value": "人最终定稿"}, role=_OPERATER))
    by_key = {f["key"]: f for f in out["formFields"]}
    assert by_key["purpose"]["value"] == "人最终定稿"
    assert by_key["purpose"]["source"] == "human"
    assert by_key["purpose"]["locked"] is True
    # 真 DB 持久化（demo-vs-real 约定：mutation 守卫须验真库，不只内存快照）——
    # 经 enrich 投影从 application_record 现算，确认 human/locked 落库可见。
    pj = {f["key"]: f for f in _projected_request(rid)["formFields"]}
    assert pj["purpose"]["value"] == "人最终定稿"
    assert pj["purpose"]["source"] == "human" and pj["purpose"]["locked"] is True


def test_ai_suggest_fills_empty_as_pending(brain, monkeypatch) -> None:
    """AI 建议填充：空可建议字段标 ai_suggested·待确认；人已填字段不被覆盖。"""
    monkeypatch.setenv("ZW_BRAIN_INFERENCE_MODE", "mock")
    req = _create_draft(brain)
    rid = req["id"]
    # 先人填 use_reason（应被 AI 保护）
    invoke_trusted(brain, "request.field.update", {"request_id": rid, "field": "use_reason", "value": "人填理由"}, role=_OPERATER)
    out = _unwrap(invoke_trusted(brain, "request.draft.ai_suggest", {"request_id": rid}, role=_OPERATER))
    by_key = {f["key"]: f for f in out["formFields"]}
    # 至少一个可建议字段（purpose）转为 AI 建议·待确认
    ai_fields = [k for k, f in by_key.items() if f["source"] == "ai_suggested"]
    assert ai_fields, f"应有 AI 建议字段，实得 {[(k, f['source']) for k, f in by_key.items()]}"
    # 人填的 use_reason 不被 AI 覆盖
    assert by_key["use_reason"]["source"] == "human"


def test_ai_suggest_rejected_for_non_applicant(brain) -> None:
    # 审计类角色(BUSIAUDIT)不在申请发起线、不继承 operator → 无权 AI 建议填充。
    # （MANAGER 经 ROLE_HIERARCHY 继承 operator 提交类权限，有权——故用 BUSIAUDIT 验拒绝。）
    req = _create_draft(brain)
    with pytest.raises(BrainServiceError):
        invoke_trusted(brain, "request.draft.ai_suggest", {"request_id": req["id"]}, role="ROLE_BUSIAUDIT")


def test_field_update_rejects_derived_field(brain) -> None:
    req = _create_draft(brain)
    rid = req["id"]
    with pytest.raises(BrainServiceError):
        invoke_trusted(brain, "request.field.update",
                       {"request_id": rid, "field": "region_name", "value": "乱填"}, role=_OPERATER)


def test_field_update_rejects_unknown_field(brain) -> None:
    req = _create_draft(brain)
    with pytest.raises(BrainServiceError):
        invoke_trusted(brain, "request.field.update",
                       {"request_id": req["id"], "field": "nonexistent", "value": "x"}, role=_OPERATER)


def test_submit_records_provenance_audit(brain) -> None:
    req = _create_draft(brain, {"ai_suggested_fields": {"purpose": "AI 拟", "use_reason": "AI 因"}})
    rid = req["id"]
    invoke_trusted(brain, "request.submit", {"request_id": rid, "confirmed": True}, role=_OPERATER)
    req2 = next(r for r in brain._snapshot["requests"] if r["id"] == rid)
    audit = req2.get("submitProvenanceAudit") or {}
    assert "purpose" in audit.get("ai_suggested_fields", [])
    assert audit.get("ai_unconfirmed_count", 0) >= 1  # 未经人确认的 AI 字段计数（不阻断）


def test_reference_dict_options_shape(brain) -> None:
    # temp 库无 dump 导入 → options 为空，但调用不报错、形状正确（真数据覆盖在 test_field_derivation）。
    out = _unwrap(invoke_trusted(brain, "reference.dict.options", {"dict_type": "organLine"}, role=_OPERATER))
    assert out["kind"] == "dict" and out["dict_type"] == "organLine"
    assert isinstance(out["options"], list)


def test_reference_dict_options_requires_type(brain) -> None:
    with pytest.raises(BrainServiceError):
        invoke_trusted(brain, "reference.dict.options", {}, role=_OPERATER)


def test_reference_organ_options_shape(brain) -> None:
    # temp 库无 dump → 空,但调用不报错、形状正确(按区划过滤+limit DB 层,不捞全表)。
    # 入参 reference_region_code 刻意避开框架注入的 actor org_code/region_code 上下文键。
    out = _unwrap(invoke_trusted(brain, "reference.organ.options", {"reference_region_code": "370000000000"}, role=_OPERATER))
    assert out["kind"] == "organ" and isinstance(out["options"], list)


def test_reference_region_options_shape(brain) -> None:
    out = _unwrap(invoke_trusted(brain, "reference.region.options", {"parent_code": "000000000000"}, role=_OPERATER))
    assert out["kind"] == "region" and isinstance(out["options"], list)
