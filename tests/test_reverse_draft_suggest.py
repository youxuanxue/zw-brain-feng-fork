from __future__ import annotations

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.state_store import StateStore

TENANT = "sd-default"


def _brain() -> BrainService:
    ds = DatabaseStore()
    ds.initialize()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=StateStore(database_store=ds))


def test_reverse_draft_suggest_resolves_catalog_source_ref_to_resource_schema() -> None:
    catalog_code = "reverse-cat-001"
    resource_code = "reverse-res-001"
    source_ref = "dsp-catalog3:data_catalog:LEGACY-CAT-001"
    catalog = CatalogRepository()
    catalog.upsert_from_resource(
        {
            "id": catalog_code,
            "name": "法人登记注册基本信息",
            "status": "active",
            "provider": "11370000MB284651XL",
            "source_ref": source_ref,
            "legacy_object_ref": "LEGACY-CAT-001",
        },
        tenant_id=TENANT,
    )
    resources = ResourceApiRepository()
    resources.upsert_asset(
        {
            "resource_code": resource_code,
            "title": "法人登记注册基本信息",
            "resource_kind": "table",
            "lifecycle_status": "active",
            "catalog_code": catalog_code,
            "owner_org_id": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )
    metadata = MetadataEvidenceRepository()
    metadata.upsert_schema_snapshot(
        {
            "snapshot_ref": f"{resource_code}:db_meta_column:tyshxydm",
            "resource_code": resource_code,
            "binding_code": resource_code,
            "schema_json": {"column_name": "tyshxydm", "comment": "统一社会信用代码", "format": "varchar"},
        },
        tenant_id=TENANT,
    )
    metadata.upsert_schema_snapshot(
        {
            "snapshot_ref": f"{resource_code}:db_meta_column:lxr",
            "resource_code": resource_code,
            "binding_code": resource_code,
            "schema_json": {"column_name": "lxr", "comment": "联系人", "format": "varchar"},
        },
        tenant_id=TENANT,
    )

    result = invoke_trusted(
        _brain(),
        "catalog.entry.reverse_draft.suggest",
        {"schema_ref": source_ref},
        role="ROLE_ORGAN_MANAGER",
    )

    assert result["found"] is True
    assert result["resource_code"] == resource_code
    assert result["coverage"]["total"] == 2
    fields = {row["field_en"]: row["field_cn"] for row in result["fields"]}
    assert fields["tyshxydm"] == "统一社会信用代码"
    assert fields["lxr"] == "联系人"
