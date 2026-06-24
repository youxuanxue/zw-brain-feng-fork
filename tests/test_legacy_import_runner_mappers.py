"""F3 turn 3/4: LegacyImportRunner wires new mappers into migration pipeline."""

from __future__ import annotations

import pytest

from zw_brain.adapters.legacy.mappers.basesubject import BasesubjectMapper
from zw_brain.adapters.legacy.mappers.catalog_metadata import CatalogMetadataMapper
from zw_brain.adapters.legacy.mappers.graph_lineage import GraphLineageMapper
from zw_brain.adapters.legacy.runner import LegacyImportRunner

pytestmark = pytest.mark.no_db


def test_mappers_for_dsp_metaresource_includes_catalog_and_graph_lineage() -> None:
    runner = LegacyImportRunner(tenant_id="sd-default")
    mappers = runner.mappers_for("dsp_metaresource")
    assert len(mappers) == 2
    assert isinstance(mappers[0], CatalogMetadataMapper)
    assert isinstance(mappers[1], GraphLineageMapper)


def test_mappers_for_dsp_basesubject_includes_basesubject_mapper() -> None:
    runner = LegacyImportRunner(tenant_id="sd-default")
    mappers = runner.mappers_for("dsp_basesubject")
    assert len(mappers) == 1
    assert isinstance(mappers[0], BasesubjectMapper)
