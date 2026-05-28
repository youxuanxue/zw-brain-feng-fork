"""ORM record → dict serializers, extracted from BrainService (Phase 1.1).

This package replaces the 30+ ``_X_record_to_dict`` methods that previously
lived on ``BrainService``. Each sub-module owns one aggregate / domain area and
exposes module-level pure functions; ``self`` was never used by the original
methods (only ``_mask`` + ``copy.deepcopy`` + record attributes), so the
extraction is mechanical.

Why this exists:
- The methods are pure ``record → dict`` mappers — no IO, no policy, no state.
  Carrying them on the BrainService god-object made every handler import
  the whole service, inflating the API surface and blocking unit-testability.
- handler call sites switch from ``brain._X_record_to_dict(rec)`` to
  ``from zw_brain.domain.serializers import <aggregate>;
  <aggregate>.X_to_dict(rec)``. No ``self`` shim is kept on BrainService —
  see PR #86 for the anti-pattern this avoids.
- A preflight guard (``scripts/check_brain_no_record_to_dict.py``) prevents
  the methods from being re-introduced on BrainService.

Bucket layout:
    adapter.py       — adapter_run / external_mapping
    catalog.py       — catalog_model / catalog_model_field / catalog_entry
    delivery.py      — delivery_attempt / delivery_evidence / exchange_metric
    governance.py    — tenant/org/region/role/actor projection + policy candidates
    metadata.py      — schema_snapshot / schema_mapping (+ mask/diagnose helpers)
                       / gather_evidence / lineage
    objection.py     — objection / process / evidence / evaluation
    ops_metrics.py   — gateway / metric
    quality.py       — quality
    resource_api.py  — resource_asset / binding / api_test_projection
    topic_package.py — topic_{package,item,visibility,review,evidence,metric}
                       (+ visibility_boundary helper)

Shared infrastructure (``_mask`` etc.) lives in ``_common.py``.
"""
