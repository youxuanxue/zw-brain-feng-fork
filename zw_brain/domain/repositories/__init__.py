from __future__ import annotations

from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.application import ApplicationRepository
from zw_brain.domain.repositories.approval import ApprovalRepository
from zw_brain.domain.repositories.delivery import DeliveryRepository
from zw_brain.domain.repositories.capability_package import CapabilityPackageRepository
from zw_brain.domain.repositories.gateway_runtime import GatewayRuntimeRepository
from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.domain.repositories.service_invocation import ServiceInvocationMetricRepository

__all__ = [
    "CatalogRepository",
    "ApplicationRepository",
    "ApprovalRepository",
    "DeliveryRepository",
    "CapabilityPackageRepository",
    "GatewayRuntimeRepository",
    "LegacyObjectMappingRepository",
    "ObjectionRepository",
    "ResourceApiRepository",
    "ServiceInvocationMetricRepository",
]
