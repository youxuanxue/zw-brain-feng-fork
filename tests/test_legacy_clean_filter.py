"""`--only-clean` 判据与 mapper 联动（clean_filter + runner 透传）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from zw_brain.adapters.legacy.clean_filter import SkipUnclean, is_clean_record
from zw_brain.adapters.legacy.mappers.catalog_metadata import CatalogMetadataMapper
from zw_brain.adapters.legacy.mappers.exchange import ExchangeMapper
from zw_brain.adapters.legacy.migration_batch import MigrationOptions, _base_report
from zw_brain.adapters.legacy.runner import LegacyImportRunner

pytestmark = pytest.mark.no_db


@pytest.mark.parametrize(
    ("kind", "record", "expected_clean", "expected_reason"),
    [
        ("catalog", {"name": "人口基础信息目录", "id": "cata-001", "provider": "11370000MB284651XL"}, True, ""),
        ("catalog", {"name": "测试目录", "id": "cata-t", "provider": "org-1"}, False, "catalog.bad_name"),
        ("catalog", {"name": "cata-001", "id": "cata-001", "provider": "org-1"}, False, "catalog.bad_name"),
        ("catalog", {"name": "有效目录", "id": "cata-002", "provider": ""}, False, "catalog.no_provider"),
        ("resource", {"name": "法人登记信息", "id": "res-001"}, True, ""),
        ("resource", {"name": "1234567890123456", "id": "res-bare"}, False, "resource.bad_name"),
        ("resource", {"name": "demo资源", "id": "res-d"}, False, "resource.bad_name"),
        (
            "application",
            {
                "resourceId": "res-1",
                "resource_name": "婚姻状况",
                "applicantDept": "省教育厅",
                "use_item": "统计分析",
            },
            True,
            "",
        ),
        (
            "application",
            {"resourceId": "", "resource_name": "婚姻状况", "applicantDept": "省教育厅"},
            False,
            "application.no_resource_ref",
        ),
        (
            "application",
            {"resourceId": "res-1", "resource_name": "测试资源", "applicantDept": "省教育厅", "use_item": "正常用途"},
            False,
            "application.bad_resource_name",
        ),
        (
            "application",
            {"resourceId": "res-1", "resource_name": "婚姻状况", "applicantDept": "unknown", "use_item": "正常用途"},
            False,
            "application.placeholder_dept",
        ),
        (
            "application",
            {"resourceId": "res-1", "resource_name": "婚姻状况", "applicantDept": "省教育厅", "use_item": "测试"},
            False,
            "application.dirty_use_item",
        ),
    ],
    ids=[
        "catalog_ok",
        "catalog_test_name",
        "catalog_name_equals_code",
        "catalog_no_provider",
        "resource_ok",
        "resource_bare_id_name",
        "resource_demo_marker",
        "application_ok",
        "application_no_resource",
        "application_bad_resource_name",
        "application_placeholder_dept",
        "application_dirty_use_item",
    ],
)
def test_is_clean_record(kind: str, record: dict, expected_clean: bool, expected_reason: str) -> None:
    clean, reason = is_clean_record(kind, record)
    assert clean is expected_clean
    assert reason == expected_reason


def test_skip_unclean_carries_reason() -> None:
    exc = SkipUnclean("catalog.bad_name")
    assert exc.reason == "catalog.bad_name"
    assert str(exc) == "catalog.bad_name"


def test_migration_report_records_only_clean_flag() -> None:
    options = MigrationOptions(dumps_dir=Path("/tmp/dumps"), only_clean=True)
    report = _base_report(options)
    assert report["only_clean"] is True


def test_legacy_import_runner_passes_only_clean_to_business_mappers() -> None:
    runner = LegacyImportRunner(tenant_id="sd-default", only_clean=True)
    catalog_mapper = runner.mappers_for("dsp_catalog")[0]
    exchange_mappers = [m for m in runner.mappers_for("dsp_require") if isinstance(m, ExchangeMapper)]
    assert isinstance(catalog_mapper, CatalogMetadataMapper)
    assert catalog_mapper.only_clean is True
    assert len(exchange_mappers) == 1
    assert exchange_mappers[0].only_clean is True


def test_exchange_mapper_skips_child_when_parent_apply_filtered() -> None:
    mapper = ExchangeMapper(tenant_id="sd-default", only_clean=True)
    mapper._filtered_apply_ids.add("apply-dirty-1")
    with pytest.raises(SkipUnclean) as excinfo:
        mapper._map_data_apply_course({"id": "course-1", "apply_id": "apply-dirty-1", "status": 0}, "dsp-require")
    assert excinfo.value.reason == "application.parent_filtered"
