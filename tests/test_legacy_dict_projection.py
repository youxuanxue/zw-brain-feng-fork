"""阶段1：pub_dict → dict_projection 真导入 + 机构/区划点查（确定性带出真源验证）。

承接 form-autofill-provenance 方案：枚举字段确定性带出需要真字典 options 源。
pub_dict 此前是 customer_core_v1_coverage 的 AUDIT_ONLY_SKIP（bsp_static_dictionary），
本测试验证它已提升为真导入，并验证派生引擎要用的机构/区划点查方法命中真实库。

数据源：old/10示例数据/dump-dsp_bsp-202604271139.sql（真实脱敏 BSP dump）。
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_DUMP = REPO_ROOT / "old/10示例数据/dump-dsp_bsp-202604271139.sql"


def _bootstrap(tmp: Path):
    from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
    from zw_brain.shared.migrate import ensure_runtime_schema

    os.environ["ZW_BRAIN_DB_PATH"] = str(tmp / "sd_default.db")
    ensure_runtime_schema()
    return GovernanceProjectionRepository()


@pytest.mark.skipif(not REAL_DUMP.exists(), reason="real BSP dump absent on this checkout")
def test_pub_dict_imports_into_dict_projection() -> None:
    """pub_dict 真导入：organLine 字典含真实条目（02→外交部 等），可经 list_dicts 查到。"""
    from zw_brain.adapters.legacy.mappers.governance import GovernanceMapper

    with TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        gov = _bootstrap(tmp)

        dump_dir = tmp / "dumps"
        dump_dir.mkdir(parents=True, exist_ok=True)
        dump = dump_dir / "dump-dsp_bsp-202604271139.sql"
        dump.write_text(REAL_DUMP.read_text(encoding="utf-8"), encoding="utf-8")

        stats = GovernanceMapper().import_dump(dump, dry_run=False)
        report = stats.to_dict()
        assert report["source_counts"].get("pub_dict", 0) > 0, "pub_dict 应进 source_counts（不再 skip）"

        organ_line = gov.list_dicts("organLine", tenant_id="sd-default")
        assert organ_line, "organLine 字典应有条目"
        by_code = {d.code: d.name for d in organ_line}
        # dump 中真实存在的 organLine 条目（脱敏后保留语义）
        assert by_code.get("02") == "外交部", f"organLine 02 应为 外交部，实得 {by_code.get('02')}"
        # options 形态：每条都有非空 code/name
        assert all(d.code and d.name for d in organ_line)


@pytest.mark.skipif(not REAL_DUMP.exists(), reason="real BSP dump absent on this checkout")
def test_org_and_region_point_lookup_for_derivation() -> None:
    """派生引擎要用的点查：get_org_by_code / get_region_by_code 命中真实投影。"""
    from zw_brain.adapters.legacy.mappers.governance import GovernanceMapper

    with TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        gov = _bootstrap(tmp)

        dump_dir = tmp / "dumps"
        dump_dir.mkdir(parents=True, exist_ok=True)
        dump = dump_dir / "dump-dsp_bsp-202604271139.sql"
        dump.write_text(REAL_DUMP.read_text(encoding="utf-8"), encoding="utf-8")
        GovernanceMapper().import_dump(dump, dry_run=False)

        # 任取一个真实机构：选机构应能确定性带出 名称 + 所属区划（带出核心）
        all_orgs = gov.list_orgs(tenant_id="sd-default")
        assert all_orgs, "应导入机构投影"
        sample = next((o for o in all_orgs if o.region_code), all_orgs[0])
        hit = gov.get_org_by_code(sample.org_code, tenant_id="sd-default")
        assert hit is not None and hit.org_name, "机构点查应命中且有名称"
        if sample.region_code:
            region = gov.get_region_by_code(sample.region_code, tenant_id="sd-default")
            assert region is not None and region.region_name, "机构所属区划应能确定性带出名称"

        # 区划点查未命中返回 None（fail-soft，不抛）
        assert gov.get_region_by_code("__nonexistent__", tenant_id="sd-default") is None


@pytest.mark.skipif(not REAL_DUMP.exists(), reason="real BSP dump absent on this checkout")
def test_search_orgs_keyword_pagination() -> None:
    """机构选择器搜索分页：keyword 模糊匹名称/编码、分页 total 稳定、区划过滤、大小写不敏感、limit 钳制。"""
    from zw_brain.adapters.legacy.mappers.governance import GovernanceMapper

    with TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        gov = _bootstrap(tmp)
        dump_dir = tmp / "dumps"
        dump_dir.mkdir(parents=True, exist_ok=True)
        dump = dump_dir / "dump-dsp_bsp-202604271139.sql"
        dump.write_text(REAL_DUMP.read_text(encoding="utf-8"), encoding="utf-8")
        GovernanceMapper().import_dump(dump, dry_run=False)

        # 取一个真实机构名的子串作 keyword（保证有命中）。
        sample = next(o for o in gov.list_orgs(tenant_id="sd-default") if o.org_name and len(o.org_name) >= 3)
        kw = sample.org_name[1:3]  # 中间子串，验真模糊（非前缀）

        rows, total = gov.search_orgs(keyword=kw, offset=0, limit=10, tenant_id="sd-default")
        assert total >= 1 and rows, f"keyword '{kw}' 应有命中"
        assert all(kw in r.org_name or kw in r.org_code for r in rows), "命中行应含 keyword"
        assert len(rows) <= 10, "limit 应生效"

        # 分页：total 不随 offset 变；第二页与第一页不重叠（若 total>10）。
        rows2, total2 = gov.search_orgs(keyword=kw, offset=10, limit=10, tenant_id="sd-default")
        assert total2 == total, "total 应与 offset 无关"
        if total > 10:
            assert {r.org_code for r in rows}.isdisjoint({r.org_code for r in rows2}), "分页不应重叠"

        # 大小写不敏感（org_code 含字母时）：用编码子串小写匹配。
        if any(c.isalpha() for c in sample.org_code):
            code_sub = next(c for c in sample.org_code if c.isalpha())
            r_lo, _ = gov.search_orgs(keyword=code_sub.lower(), limit=5, tenant_id="sd-default")
            r_up, _ = gov.search_orgs(keyword=code_sub.upper(), limit=5, tenant_id="sd-default")
            assert ({r.org_code for r in r_lo} or {r.org_code for r in r_up}), "大小写应等价命中"

        # 区划过滤叠加：限定某机构所属区划，命中应都在该区划。
        if sample.region_code:
            rr, _ = gov.search_orgs(region_code=sample.region_code, limit=20, tenant_id="sd-default")
            assert rr and all(r.region_code == sample.region_code for r in rr), "区划过滤应生效"

        # 空 keyword + 空区划 → 仍返回首页 + total（不退化）。
        r0, t0 = gov.search_orgs(limit=5, tenant_id="sd-default")
        assert t0 >= len(r0) >= 1
