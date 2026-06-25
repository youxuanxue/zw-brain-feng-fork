"""dsp_pipelines.meta_database → datasource_endpoint_projection（脱敏，不含明文密钥）。"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zw_brain.adapters.legacy._common import ImportStats, coerce_int, finish_run, schema_from_dump_name
from zw_brain.adapters.legacy.parser import MysqldumpParser
from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT, legacy_system_for
from zw_brain.domain.repositories.datasource_endpoint import DatasourceEndpointRepository, infer_data_partition
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository


def _secret_ref(db_id: str, encrypted_password: str | None) -> str | None:
    if not encrypted_password:
        return None
    digest = hashlib.sha256(f"{db_id}:{encrypted_password}".encode()).hexdigest()
    return f"legacy-secret:{digest[:32]}"


def _host_ref(host: str | None, port: int | None) -> str | None:
    if not host:
        return None
    return f"host:{host}:{port or 0}"


def _connectivity_status(is_connect: Any, is_del: Any) -> str:
    if coerce_int(is_del, 0) == 1:
        return "deleted"
    return "connected" if coerce_int(is_connect, 0) == 1 else "disconnected"


class DatasourceEndpointMapper:
    HANDLED_TABLES = {"meta_database"}
    ADAPTER_SLUG = "legacy.datasource_endpoint.import"

    def __init__(self, *, tenant_id: str = DEFAULT_TENANT):
        self.tenant_id = tenant_id
        self.repo = DatasourceEndpointRepository()
        self.adapter_repo = ExternalAdapterRepository()

    def import_dump(self, dump_path: Path) -> ImportStats:
        schema = schema_from_dump_name(dump_path.name)
        legacy_system = legacy_system_for(schema)
        stats = ImportStats(schema=schema, dump_path=dump_path)
        started_at = datetime.now(UTC)

        for table, row in MysqldumpParser(dump_path).iter_rows():
            if table not in self.HANDLED_TABLES:
                stats.skip(table)
                continue
            try:
                self._map_meta_database(row, legacy_system)
                stats.bump(table)
            except KeyError as exc:
                stats.bump(table, "errors")
                key = f"{table}.missing_field:{exc.args[0]}"
                stats.skipped[key] = stats.skipped.get(key, 0) + 1

        finish_run(
            self.adapter_repo,
            stats,
            adapter_slug=self.ADAPTER_SLUG,
            dump_path=dump_path,
            started_at=started_at,
            tenant_id=self.tenant_id,
        )
        return stats

    def _map_meta_database(self, row: dict[str, Any], legacy_system: str) -> None:
        db_id = str(row["db_id"])
        host = row.get("db_ip")
        port_raw = row.get("db_port")
        port = coerce_int(port_raw, 0) if port_raw not in (None, "") else None
        payload = {
            "endpoint_id": db_id,
            "connection_ref": f"{legacy_system}:meta_database:{db_id}",
            "display_name": row.get("db_display_name") or row.get("db_name") or db_id,
            "db_name": row.get("db_name") or "",
            "db_type": row.get("db_type") or "mysql",
            "host_ref": _host_ref(str(host) if host else None, port),
            "host_display": str(host) if host else None,
            "port": port,
            "org_code": row.get("org_code"),
            "org_name": row.get("org_name"),
            "contact_name": row.get("db_linkname"),
            "contact_phone": row.get("db_linkphone"),
            "node_id": row.get("node_id"),
            "node_name": row.get("node_name"),
            "remark": row.get("db_desc"),
            "secret_ref": _secret_ref(db_id, row.get("db_passwd")),
            "metadata_database_id": db_id,
            "connectivity_status": _connectivity_status(row.get("is_connect"), row.get("is_del")),
            "source_ref": f"{legacy_system}:meta_database:{db_id}",
            "summary_json": {
                "legacy_system": legacy_system,
                "jdbc_type": row.get("jdbc_type"),
                "region_code": row.get("region_code"),
                "import_kind": "legacy_meta_database",
            },
        }
        payload["data_partition"] = infer_data_partition(payload)
        self.repo.upsert_endpoint(payload, tenant_id=self.tenant_id)
