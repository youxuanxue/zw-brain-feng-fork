"""Quality serializer — quality_evidence record.

Extracted from ``BrainService._quality_record_to_dict`` (Phase 1.1).
"""
from __future__ import annotations

import copy
from typing import Any


def quality_to_dict(record: Any) -> dict[str, Any]:
    source_ref = record.source_ref or record.quality_ref
    generated_at = record.generated_at.isoformat()
    return {
        "quality_ref": record.quality_ref,
        "target_type": record.target_type,
        "target_ref": record.target_ref,
        "quality_status": record.quality_status,
        "score": record.score,
        "evidence_json": copy.deepcopy(record.evidence_json),
        "source_ref": source_ref,
        "generated_at": generated_at,
        "projection_only": True,
        "evidence": {"source_ref": source_ref, "generated_at": generated_at, "projection_only": True},
    }
