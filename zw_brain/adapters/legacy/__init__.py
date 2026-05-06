"""Legacy mysqldump → zw-brain canonical importer.

Entry point: scripts/import_legacy_dumps.py.
Single source of truth for old→new mapping decisions: docs/reconstructs/legacy-import-mapping-v1.md.
Contract:
    - tenant_id="sd-default" for all canonical writes
    - sensitive business fields (name/phone/email) ingested raw; read-side mask layer enforces masking
    - real secrets (password/token/key/connstr) NEVER ingested (filtered at parser/mapper boundary)
    - every row writes LegacyObjectMappingRecord and AdapterRunRecord
    - cross-schema bridges follow the 8-step ID order in the mapping doc §四.1
"""

from zw_brain.adapters.legacy._common import ImportStats
from zw_brain.adapters.legacy.parser import MysqldumpParser, parse_dump_rows
from zw_brain.adapters.legacy.schema_index import LEGACY_DUMPS, dump_path_for, list_dumps
from zw_brain.adapters.legacy.runner import LegacyImportRunner, ParseStats
from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT, LEGACY_SYSTEM_BY_SCHEMA, legacy_system_for

__all__ = [
    "DEFAULT_TENANT",
    "ImportStats",
    "LEGACY_DUMPS",
    "LEGACY_SYSTEM_BY_SCHEMA",
    "LegacyImportRunner",
    "MysqldumpParser",
    "ParseStats",
    "dump_path_for",
    "legacy_system_for",
    "list_dumps",
    "parse_dump_rows",
]
