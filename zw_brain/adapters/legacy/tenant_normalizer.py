"""Tenant + legacy_system normalization for legacy importer.

Per [2026-05-06] memory project_default_tenant_sd: single tenant `sd-default` while in
trial. Legacy schema → legacy_system grouping per legacy-import-mapping-v1.md §四.3.
"""
from __future__ import annotations

DEFAULT_TENANT = "sd-default"

LEGACY_SYSTEM_BY_SCHEMA: dict[str, str] = {
    # catalog plan §1.3 合流：catalog + metaresource → 'dsp-catalog3'
    "dsp_catalog": "dsp-catalog3",
    "dsp_metaresource": "dsp-catalog3",
    # exchange plan §1.3 合流：require + pipelines → 'dsp-exchange'
    "dsp_require": "dsp-exchange",
    "dsp_pipelines": "dsp-exchange",
    # objection
    "dsp_handling": "dsp-objection",
    # dataservice
    "dsp_service": "dsp-dataservice",
    # sharezone (example + basesubject)
    "dsp_example": "dsp-sharezone",
    "dsp_basesubject": "dsp-sharezone",
    # IAM / org / region projection source
    "dsp_bsp": "dsp-bsp",
    # external mapping (data-connect uses ExternalObjectMappingRecord, not LegacyObjectMapping;
    # legacy_system here is informational only)
    "dsp_connect": "dsp-data-connect",
    "dsp_block": "dsp-blockchain",
    # compliance/ops candidates
    "dsp_monitor": "compliance-ops",
    "dsp_perform": "compliance-ops",
    # not imported (listed for completeness; runner skips them)
    "dsp_message": "dsp-message",
    "dsp_pdf": "dsp-pdf",
    "dsp_app_center": "dsp-app-center",
    "data_resource": "data-resource",
}


def legacy_system_for(schema: str) -> str:
    """Return the legacy_system label for a given schema dump name."""
    return LEGACY_SYSTEM_BY_SCHEMA.get(schema, schema)
