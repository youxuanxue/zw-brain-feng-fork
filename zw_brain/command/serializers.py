"""Re-export shim for legacy ``zw_brain.command.serializers`` import path.

The canonical home for serializers is ``zw_brain.domain.serializers`` (Action D
R-021: serializers are pure dict↔record conversions — domain knowledge, not
command-layer artifacts). This shim preserves backward compat for handlers /
helpers that still import via the old path; new code MUST use
``from zw_brain.domain.serializers import X``.

This file is intentionally a single line: re-export the module namespace so
``from zw_brain.command.serializers import catalog as catalog_ser`` keeps working.
"""
from zw_brain.domain.serializers import *  # noqa: F401,F403
from zw_brain.domain.serializers import (  # noqa: F401
    adapter,
    catalog,
    delivery,
    governance,
    metadata,
    objection,
    ops_metrics,
    quality,
    resource_api,
    topic_package,
)
