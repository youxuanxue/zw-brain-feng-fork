from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService, ConfirmationRequiredError
from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore


def _service(tmp: str) -> BrainService:
    import os

    os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
    ensure_runtime_schema()
    database_store = DatabaseStore()
    audit_bus.configure_sink(database_store.append_audit_event)
    return BrainService(state_store=StateStore(database_store=database_store))


def test_list_policy_candidates_filters_by_status() -> None:
    with TemporaryDirectory() as tmp:
        service = _service(tmp)
        repo = GovernanceProjectionRepository()
        repo.import_legacy_policy_candidate(
            {
                "legacy_system": "dsp-bsp",
                "legacy_permission_ref": "FUNC_A",
                "legacy_role_ref": "ROLE_BUSIAUDIT",
                "capability_id": "audit.list",
                "surface": "webui",
                "candidate_status": "pending_review",
                "evidence_json": {},
            }
        )
        repo.import_legacy_policy_candidate(
            {
                "legacy_system": "dsp-bsp",
                "legacy_permission_ref": "FUNC_B",
                "legacy_role_ref": "ROLE_ORGAN_MANAGER",
                "capability_id": "request.list",
                "surface": "api",
                "candidate_status": "rejected",
                "evidence_json": {},
            }
        )

        listed = service.invoke_skill(
            "governance.policy_candidate.list",
            {"candidate_status": "pending_review", "role": "ROLE_SYSTEM"},
        )
        assert listed["summary"]["total"] == 1
        assert listed["items"][0]["legacy_permission_ref"] == "FUNC_A"
        assert listed["export_report"]["status_counts"]["pending_review"] == 1


def test_approve_alone_does_not_enable_tenant_policy() -> None:
    with TemporaryDirectory() as tmp:
        service = _service(tmp)
        invoke_trusted(
            service,
            "legacy.bsp.mapping.import",
            {
                "mode": "apply",
                "rows": [
                    {
                        "legacy_permission_ref": "dsp-bsp:zone:publish",
                        "legacy_role_ref": "ROLE_BUSIAUDIT",
                        "capability_id": "zone.publish_topic_projection",
                        "surface": "webui",
                    }
                ],
                "confirmed": True,
            },
            role="ROLE_BUSIAUDIT",
        )
        reviewed = invoke_trusted(
            service,
            "governance.policy_candidate.review",
            {
                "decision": "approve",
                "items": [
                    {
                        "legacy_permission_ref": "dsp-bsp:zone:publish",
                        "capability_id": "zone.publish_topic_projection",
                    }
                ],
                "confirmed": True,
            },
            role="ROLE_SYSTEM",
        )
        assert reviewed["result"]["summary"]["success_count"] == 1
        assert reviewed["audit_id"]

        denied = service.invoke_skill(
            "tenant.policy.evaluate",
            {
                "capability_id": "zone.publish_topic_projection",
                "surface": "webui",
                "role": "ROLE_SYSTEM",
                "role_code": "ROLE_BUSIAUDIT",
            },
        )
        assert denied["allowed"] is False
        assert denied["decision_reason"] == "missing_tenant_policy"


def test_approve_and_apply_enables_tenant_policy_with_audit() -> None:
    with TemporaryDirectory() as tmp:
        service = _service(tmp)
        invoke_trusted(
            service,
            "legacy.bsp.mapping.import",
            {
                "mode": "apply",
                "rows": [
                    {
                        "legacy_permission_ref": "dsp-bsp:zone:publish",
                        "legacy_role_ref": "ROLE_BUSIAUDIT",
                        "capability_id": "zone.publish_topic_projection",
                        "surface": "webui",
                    }
                ],
                "confirmed": True,
            },
            role="ROLE_BUSIAUDIT",
        )
        reviewed = invoke_trusted(
            service,
            "governance.policy_candidate.review",
            {
                "decision": "approve_and_apply",
                "items": [
                    {
                        "legacy_permission_ref": "dsp-bsp:zone:publish",
                        "capability_id": "zone.publish_topic_projection",
                    }
                ],
                "confirmed": True,
            },
            role="ROLE_SYSTEM",
        )
        assert reviewed["audit_id"]
        assert reviewed["result"]["summary"]["applied_policy_count"] == 1
        assert reviewed["result"]["items"][0]["result"] == "approved_and_applied"

        allowed = service.invoke_skill(
            "tenant.policy.evaluate",
            {
                "capability_id": "zone.publish_topic_projection",
                "surface": "webui",
                "role": "ROLE_SYSTEM",
                "role_code": "ROLE_BUSIAUDIT",
            },
        )
        assert allowed["allowed"] is True
        assert allowed["source"] == "tenant_capability_policy"


def test_review_requires_confirmation() -> None:
    with TemporaryDirectory() as tmp:
        service = _service(tmp)
        with pytest.raises(ConfirmationRequiredError):
            invoke_trusted(
                service,
                "governance.policy_candidate.review",
                {
                    "decision": "reject",
                    "items": [{"legacy_permission_ref": "X", "capability_id": "audit.list"}],
                    "confirmed": False,
                },
                role="ROLE_SYSTEM",
            )


def test_reject_blocks_apply() -> None:
    with TemporaryDirectory() as tmp:
        service = _service(tmp)
        invoke_trusted(
            service,
            "legacy.bsp.mapping.import",
            {
                "mode": "apply",
                "rows": [
                    {
                        "legacy_permission_ref": "dsp-bsp:deny",
                        "legacy_role_ref": "ROLE_BUSIAUDIT",
                        "capability_id": "audit.list",
                        "surface": "api",
                    }
                ],
                "confirmed": True,
            },
            role="ROLE_BUSIAUDIT",
        )
        invoke_trusted(
            service,
            "governance.policy_candidate.review",
            {
                "decision": "reject",
                "items": [{"legacy_permission_ref": "dsp-bsp:deny", "capability_id": "audit.list"}],
                "confirmed": True,
            },
            role="ROLE_SYSTEM",
        )
        applied = invoke_trusted(
            service,
            "governance.policy_candidate.review",
            {
                "decision": "apply",
                "items": [{"legacy_permission_ref": "dsp-bsp:deny", "capability_id": "audit.list"}],
                "confirmed": True,
            },
            role="ROLE_SYSTEM",
        )
        assert applied["result"]["items"][0]["result"] == "failed"
        assert applied["result"]["items"][0]["reason"] == "candidate_not_approved"
