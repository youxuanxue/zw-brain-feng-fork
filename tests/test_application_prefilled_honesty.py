# Wave: 1
# Journey: J1
# Pages: P3 申请草拟 / U-3 凭据签发
# Consumer-faces: API (ApplicationService.prefilled_fields)
# Roles: ROLE_ORGAN_OPERATER (申请人)
# Trace:
#   zw_brain/domain/services/application_service.py prefilled_fields
#   CLAUDE.md D11（业务数据禁 Mock，一律真实库回归）
"""禁 Mock 守卫：J1 申请材料预填行绝不向用户展示捏造的企业/法人数据。

历史事故：prefilled_fields() 写死一家虚构企业（山东云启…/假统一社会信用代码/
假法定代表人）当作「已预填」，会在真实凭据签发流里向用户展示捏造的业务数据。
本测试断言：
  1. 预填行只带出真实请求字段（来自目录元数据）；
  2. 取值诚实留空 + 「请填写」提示，不再有任何写死的企业取值；
  3. source 指向真实可得的目录证据，不再是泛化「已带出」。
"""
from __future__ import annotations

from zw_brain.domain.services.application_service import ApplicationService

# 这些方法是纯函数（不触 self.brain），可直接构造做纯单测，无需 seed DB。
SVC = ApplicationService(brain=None)  # type: ignore[arg-type]

# 退役的捏造取值——任何一处出现即视为回潮。
FABRICATED_MARKERS = {
    "山东云启科技有限公司",
    "91370000MA3XXXXXX1",
    "李某某",
    "已带出",
}


def _all_text(rows: list[dict]) -> str:
    return "\n".join(f"{r.get('label','')}|{r.get('value','')}|{r.get('source','')}" for r in rows)


def test_prefilled_fields_carry_real_field_labels_with_empty_honest_values() -> None:
    resource = {
        "id": "RSRC-001",
        "repository": {"catalogCode": "370000308004000000/000001"},
    }
    requested = [
        {"item_code": "F001", "title": "统一社会信用代码"},
        {"item_code": "F002", "title": "企业名称"},
        {"item_code": "F003", "title": "法定代表人"},
    ]
    rows = SVC.prefilled_fields(resource, requested)

    # 逐条带出真实请求字段标题。
    assert [r["label"] for r in rows] == ["统一社会信用代码", "企业名称", "法定代表人"]
    # 取值一律诚实留空 + 请填写提示，绝不捏造。
    for r in rows:
        assert r["value"] == "", f"预填取值必须留空，发现捏造取值: {r}"
        assert r.get("placeholder") == "请填写"
        assert r.get("state") == "待填写"
        # source 指向真实目录字段证据（含 catalogCode），不是泛化占位。
        assert "共享目录字段" in r["source"]
        assert "370000308004000000/000001" in r["source"]


def test_prefilled_fields_never_emit_fabricated_company_data() -> None:
    # 即便字段标题恰好命中历史 samples 字典的 key，也绝不回填捏造取值。
    resource = {"id": "RSRC-X", "repository": {"catalogCode": "C-X"}}
    requested = [
        {"item_code": "F1", "title": "统一社会信用代码"},
        {"item_code": "F2", "title": "企业名称"},
        {"item_code": "F3", "title": "法定代表人"},
        {"item_code": "F4", "title": "成立日期"},
        {"item_code": "F5", "title": "注册资本"},
    ]
    rows = SVC.prefilled_fields(resource, requested)
    blob = _all_text(rows)
    for marker in FABRICATED_MARKERS:
        assert marker not in blob, f"捏造数据回潮: {marker!r} 出现在预填行"


def test_prefilled_fields_falls_back_to_resource_fields_when_no_requested() -> None:
    resource = {"id": "R", "repository": {}, "fields": ["字段甲", "字段乙"]}
    rows = SVC.prefilled_fields(resource, None)
    assert [r["label"] for r in rows] == ["字段甲", "字段乙"]
    assert all(r["value"] == "" for r in rows)


def test_prefilled_fields_caps_at_five() -> None:
    requested = [{"item_code": f"F{i}", "title": f"字段{i}"} for i in range(8)]
    rows = SVC.prefilled_fields({"id": "R", "repository": {}}, requested)
    assert len(rows) == 5
