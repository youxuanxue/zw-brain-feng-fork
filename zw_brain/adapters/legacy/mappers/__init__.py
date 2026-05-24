"""Per-aggregate mappers from legacy mysqldump rows → zw-brain canonical / projection.

Each mapper:
    - declares which legacy tables it handles (HANDLED_TABLES)
    - exposes `import_dump(dump_path)` returning ImportStats
    - writes LegacyObjectMappingRecord for every canonical / projection row it lands
    - writes one AdapterRunRecord per run (idempotent by dump basename)
    - filters real secrets (password / token / key / connstr) at the row boundary —
      business-visible sensitive fields (name / phone / email / address) per
      [2026-05-06] policy override pass through and are masked at read time.

Bridging order (legacy-import-mapping-v1.md §四.1):
    1. governance  (pub_organ / pub_region / pub_user / pub_role)
    2. catalog_metadata  (rc_resource → ResourceAsset, then data_catalog → CatalogEntry)
    3. exchange  (data_require → Application, then data_apply → Application + Approval + Delivery)
    4. objection  (data_objection)
    5. topic_package  (data_example — 共享专题案例)
    6. basesubject  (basesubject_info / bs_resource / schema_info — 主题库主线，F3 turn 2 漏做补齐)
    7. service  (api_service_*)
    8. connect  (dc_*)
    9. projections  (monitor / perform — only summaries)
"""

from zw_brain.adapters.legacy._common import ImportStats
from zw_brain.adapters.legacy.mappers.basesubject import BasesubjectMapper
from zw_brain.adapters.legacy.mappers.catalog_metadata import CatalogMetadataMapper
from zw_brain.adapters.legacy.mappers.connect import ConnectMapper
from zw_brain.adapters.legacy.mappers.exchange import ExchangeMapper
from zw_brain.adapters.legacy.mappers.governance import GovernanceMapper
from zw_brain.adapters.legacy.mappers.objection import ObjectionMapper
from zw_brain.adapters.legacy.mappers.pipelines import PipelinesMapper
from zw_brain.adapters.legacy.mappers.projections import MonitorMapper, PerformMapper
from zw_brain.adapters.legacy.mappers.service import ServiceMapper
from zw_brain.adapters.legacy.mappers.topic_package import TopicPackageMapper

__all__ = [
    "BasesubjectMapper",
    "CatalogMetadataMapper",
    "ConnectMapper",
    "ExchangeMapper",
    "GovernanceMapper",
    "ImportStats",
    "MonitorMapper",
    "ObjectionMapper",
    "PerformMapper",
    "PipelinesMapper",
    "ServiceMapper",
    "TopicPackageMapper",
]
