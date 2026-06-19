"""阶段2：field_derivation 确定性派生引擎单测（纯逻辑，fake reference）。

覆盖治理口径：派生权威/级联/重算/覆盖人填/空触发清理但保护人直选值。
"""
from __future__ import annotations

from zw_brain.domain.services.field_derivation import (
    SOURCE_AI,
    SOURCE_DERIVED,
    SOURCE_EMPTY,
    SOURCE_HUMAN,
    apply_human_edit,
    derive,
    orchestrate_fill,
)


class _FakeReference:
    """机构/区划真源的内存替身。"""

    ORGANS = {
        "11370000MB284651XL": {"org_name": "省大数据局", "region_code": "370000000000", "region_name": "山东省"},
    }
    REGIONS = {
        "370000000000": {"region_name": "山东省", "parent_region_code": "000000000000"},
        "370100000000": {"region_name": "济南市", "parent_region_code": "370000000000"},
    }

    def organ(self, org_code, *, tenant_id="sd-default"):
        return ({"org_code": org_code, **self.ORGANS[org_code]} if org_code in self.ORGANS else None)

    def region(self, region_code, *, tenant_id="sd-default"):
        return ({"region_code": region_code, **self.REGIONS[region_code]} if region_code in self.REGIONS else None)


REF = _FakeReference()


def test_select_organ_derives_name_and_region() -> None:
    """选机构 → 带出 机构名 + 所属区划码 + 区划名（带出核心，级联一次完成）。"""
    values, prov = derive({"organ_code": "11370000MB284651XL"}, {}, reference=REF, tenant_id="sd-default")
    assert values["organ_name"] == "省大数据局"
    assert values["region_code"] == "370000000000"
    assert values["region_name"] == "山东省"  # 级联：organ→region_code→region_name
    for f in ("organ_name", "region_code", "region_name"):
        assert prov[f]["source"] == SOURCE_DERIVED
        assert prov[f]["locked"] is False


def test_change_region_directly_rederives_name() -> None:
    """人不经机构、直选区划码 → 派生区划名；区划码本身是 human（保留）。"""
    values, prov = derive(
        {"region_code": "370100000000"},
        {"region_code": {"source": SOURCE_HUMAN, "locked": True}},
        reference=REF,
        tenant_id="sd-default",
    )
    assert values["region_name"] == "济南市"
    assert prov["region_name"]["source"] == SOURCE_DERIVED
    assert prov["region_code"]["source"] == SOURCE_HUMAN  # 人直选的码不被动


def test_derivation_overrides_human_value_on_derived_target() -> None:
    """派生权威：选机构后，机构带出的区划覆盖人此前手填的区划（不受人锁约束）。"""
    values, prov = derive(
        {"organ_code": "11370000MB284651XL", "region_code": "999999999999", "region_name": "乱填的"},
        {"region_code": {"source": SOURCE_HUMAN, "locked": True}, "region_name": {"source": SOURCE_HUMAN, "locked": True}},
        reference=REF,
        tenant_id="sd-default",
    )
    assert values["region_code"] == "370000000000"
    assert values["region_name"] == "山东省"
    assert prov["region_code"]["source"] == SOURCE_DERIVED  # 派生夺回所有权


def test_human_field_untouched_by_derivation() -> None:
    """派生只动它声明的 target；无关 human 字段（purpose）原样不动。"""
    values, prov = derive(
        {"organ_code": "11370000MB284651XL", "purpose": "用于审批"},
        {"purpose": {"source": SOURCE_HUMAN, "locked": True}},
        reference=REF,
        tenant_id="sd-default",
    )
    assert values["purpose"] == "用于审批"
    assert prov["purpose"]["source"] == SOURCE_HUMAN


def test_empty_trigger_clears_derived_but_protects_human() -> None:
    """清空机构 → 回收曾派生的字段；但人直选的 region_code 不被清。"""
    # 先选机构得到一组派生值
    values, prov = derive({"organ_code": "11370000MB284651XL"}, {}, reference=REF, tenant_id="sd-default")
    # 再清空机构
    values["organ_code"] = ""
    values, prov = derive(values, prov, reference=REF, tenant_id="sd-default")
    assert values["organ_name"] == ""
    assert values["region_code"] == ""
    assert values["region_name"] == ""
    assert prov["region_code"]["source"] == SOURCE_EMPTY

    # 对照：人直选 region_code（human）即使无机构，清机构也不清它
    v2, p2 = derive(
        {"organ_code": "", "region_code": "370100000000"},
        {"region_code": {"source": SOURCE_HUMAN, "locked": True}},
        reference=REF,
        tenant_id="sd-default",
    )
    assert v2["region_code"] == "370100000000"  # human 直选不被空机构清掉
    assert v2["region_name"] == "济南市"  # 仍据 human 的区划码派生名称


def test_unknown_organ_does_not_fabricate() -> None:
    """未知机构码 → 不捏造，派生字段清空（诚实，D11）。"""
    values, prov = derive({"organ_code": "NOSUCHORG"}, {}, reference=REF, tenant_id="sd-default")
    assert values["organ_name"] == ""
    assert values["region_code"] == ""
    assert prov["organ_name"]["source"] == SOURCE_DERIVED  # 标记为派生但值为空（已尝试带出、无源）


# ---- orchestrate_fill：身份带出 + 派生 + AI 建议（只填空、不覆盖人填） ----

def test_orchestrate_fill_ai_fills_empty_only() -> None:
    values, prov = orchestrate_fill(
        {"purpose": "", "use_reason": "人已填的理由"},
        {"use_reason": {"source": SOURCE_HUMAN, "locked": True}},
        reference=REF,
        tenant_id="sd-default",
        ai_suggestions={"purpose": "AI 拟的用途", "use_reason": "AI 想覆盖但不行"},
    )
    assert values["purpose"] == "AI 拟的用途"
    assert prov["purpose"]["source"] == SOURCE_AI
    assert prov["purpose"]["state"] == "ai_pending_confirm"
    # 人填的 use_reason 不被 AI 覆盖
    assert values["use_reason"] == "人已填的理由"
    assert prov["use_reason"]["source"] == SOURCE_HUMAN


def test_orchestrate_fill_identity_bring_out() -> None:
    values, prov = orchestrate_fill(
        {"purpose": "x"},
        {},
        reference=REF,
        tenant_id="sd-default",
        actor_org={"org_code": "11370000MB284651XL", "org_name": "省大数据局"},
    )
    assert values["applicant_org"] == "省大数据局"
    assert prov["applicant_org"]["source"] == SOURCE_DERIVED


def test_orchestrate_fill_ai_never_overrides_derived() -> None:
    # use_region 同时是 AI 可建议字段；若已被派生占据则 AI 不得覆盖
    values, prov = orchestrate_fill(
        {"organ_code": "11370000MB284651XL"},
        {},
        reference=REF,
        tenant_id="sd-default",
        ai_suggestions={"region_name": "AI 想改区划名"},  # region_name 是 derived，应被拒
    )
    assert values["region_name"] == "山东省"
    assert prov["region_name"]["source"] == SOURCE_DERIVED


def test_apply_human_edit_locks_against_reautofill() -> None:
    # 人改 purpose → 锁定；再跑 orchestrate_fill 的 AI 不再覆盖
    values, prov = orchestrate_fill({"purpose": ""}, {}, reference=REF, tenant_id="sd-default",
                                    ai_suggestions={"purpose": "AI 第一次"})
    assert prov["purpose"]["source"] == SOURCE_AI
    values, prov = apply_human_edit(values, prov, "purpose", "人最终定稿", actor="user-1",
                                    reference=REF, tenant_id="sd-default")
    assert values["purpose"] == "人最终定稿"
    assert prov["purpose"]["source"] == SOURCE_HUMAN and prov["purpose"]["locked"] is True
    # 再次 autofill：人锁字段不被 AI 覆盖
    values, prov = orchestrate_fill(values, prov, reference=REF, tenant_id="sd-default",
                                    ai_suggestions={"purpose": "AI 第二次想覆盖"})
    assert values["purpose"] == "人最终定稿"


def test_apply_human_edit_on_trigger_rederives() -> None:
    # 人改 organ_code（trigger）→ region 重派生
    values, prov = apply_human_edit({}, {}, "organ_code", "11370000MB284651XL", actor="u",
                                    reference=REF, tenant_id="sd-default")
    assert values["region_code"] == "370000000000"
    assert values["region_name"] == "山东省"
    assert prov["organ_code"]["source"] == SOURCE_HUMAN  # trigger 本身是人选的
    assert prov["region_name"]["source"] == SOURCE_DERIVED  # 带出的是派生


# ---- 真数据集成：ReferenceService + derive 在真导入库上跑通 ----
from pathlib import Path  # noqa: E402
from tempfile import TemporaryDirectory  # noqa: E402

import pytest  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REAL_DUMP = _REPO_ROOT / "old/10示例数据/dump-dsp_bsp-202604271139.sql"


@pytest.mark.skipif(not _REAL_DUMP.exists(), reason="real BSP dump absent on this checkout")
def test_derive_on_real_imported_org() -> None:
    """对真导入的某机构跑派生：选机构 → 带出真实名称 + 所属区划。"""
    from zw_brain.adapters.legacy.mappers.governance import GovernanceMapper
    from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
    from zw_brain.domain.services.reference_service import ReferenceService
    from zw_brain.shared.migrate import ensure_runtime_schema

    with TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        # conftest autouse fixture already supplies an isolated empty PG clone.
        ensure_runtime_schema()
        dump_dir = tmp / "dumps"
        dump_dir.mkdir(parents=True, exist_ok=True)
        dump = dump_dir / "dump-dsp_bsp-202604271139.sql"
        dump.write_text(_REAL_DUMP.read_text(encoding="utf-8"), encoding="utf-8")
        GovernanceMapper().import_dump(dump, dry_run=False)

        gov = GovernanceProjectionRepository()
        ref = ReferenceService(repo=gov)
        sample = next((o for o in gov.list_orgs(tenant_id="sd-default") if o.region_code), None)
        assert sample is not None, "真库应有带 region_code 的机构"

        values, prov = derive({"organ_code": sample.org_code}, {}, reference=ref, tenant_id="sd-default")
        assert values["organ_name"], "应带出真实机构名称"
        assert values["region_code"] == sample.region_code, "应带出机构所属区划码"
        assert prov["organ_name"]["source"] == SOURCE_DERIVED
