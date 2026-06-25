from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from zw_brain.domain.services.delivery_service import DeliveryService
from zw_brain.domain.services.request_service import RequestService

pytestmark = pytest.mark.no_db


@dataclass
class _FakePorts:
    delivery: dict[str, Any] | None = None
    writes: list[dict[str, Any]] = field(default_factory=list)
    audit_events: list[tuple[str, str, str, str]] = field(default_factory=list)
    issued_credentials: list[tuple[str, str, str]] = field(default_factory=list)
    delivery_repo: Any = None

    def write(self, skill_id, role, confirmed, payload, mutation):
        self.writes.append(
            {"skill_id": skill_id, "role": role, "confirmed": confirmed, "payload": payload}
        )
        return mutation("AUD-port", "actor-port")

    def append_audit_feed(self, event_type, target, result, actor):
        self.audit_events.append((event_type, target, result, actor))

    def current_role(self, default):
        return default

    def actor_for_role(self, role):
        return f"actor:{role}"

    def issue_credential_on_approval(self, request_id, role, actor):
        self.issued_credentials.append((request_id, role, actor))

    def delivery_by_request_id(self, request_id):
        return self.delivery


class _FakeRequestService(RequestService):
    def __init__(
        self,
        *,
        ports: _FakePorts,
        request: dict[str, Any],
        approval: dict[str, Any],
    ) -> None:
        object.__setattr__(self, "brain", None)
        object.__setattr__(self, "ports", ports)
        object.__setattr__(self, "_request", request)
        object.__setattr__(self, "_approval", approval)

    def by_id(self, request_id: str) -> dict[str, Any]:
        return self._request

    def approval_by_id(self, request_id: str) -> dict[str, Any]:
        return self._approval


class _FakeReceipt:
    id = "receipt-port"


class _FakeDeliveryRepo:
    def __init__(self) -> None:
        self.receipts: list[dict[str, Any]] = []

    def append_receipt(self, payload: dict[str, Any]) -> _FakeReceipt:
        self.receipts.append(payload)
        return _FakeReceipt()


class _FakeDeliveryService(DeliveryService):
    def __init__(
        self,
        *,
        ports: _FakePorts,
        task: dict[str, Any],
    ) -> None:
        object.__setattr__(self, "brain", None)
        object.__setattr__(self, "ports", ports)
        object.__setattr__(self, "_task", task)

    def by_id(self, task_id: str) -> dict[str, Any]:
        return self._task


def test_request_approve_uses_domain_ports() -> None:
    delivery = {
        "status": "pending",
        "updatedAt": "",
        "note": "",
        "history": [],
        "aiSummary": {},
        "backflow": {},
        "accessGrantSnapshot": {},
    }
    ports = _FakePorts(delivery=delivery)
    request = {
        "status": "pending",
        "chainAnchor": "",
        "timeline": [],
        "aiStatus": {},
    }
    approval = {}
    service = _FakeRequestService(ports=ports, request=request, approval=approval)

    result = service.approve("REQ-port", "ROLE_REVIEWER", True)

    assert result == {"request_id": "REQ-port", "status": "supplementing"}
    assert ports.writes == [
        {
            "skill_id": "approval.review_decide",
            "role": "ROLE_REVIEWER",
            "confirmed": True,
            "payload": {"request_id": "REQ-port", "decision": "approve_reuse"},
        }
    ]
    assert ports.audit_events == [("request.approve", "REQ-port", "ok", "actor-port")]
    assert ports.issued_credentials == [
        ("REQ-port", "ROLE_REVIEWER", "actor:ROLE_REVIEWER")
    ]
    assert request["status"] == "supplementing"
    assert delivery["status"] == "supplementing"


def test_delivery_file_download_uses_domain_ports_repo_and_write() -> None:
    repo = _FakeDeliveryRepo()
    ports = _FakePorts(delivery_repo=repo)
    service = _FakeDeliveryService(ports=ports, task={"name": "port.csv"})

    result = service.record_file_download(
        {"task_id": "DLV-port", "role": "ROLE_CONSUMER", "confirmed": True},
        "delivery.file.download",
    )

    assert ports.writes[0]["skill_id"] == "delivery.file.download"
    assert ports.audit_events == [
        ("delivery.file.download", "DLV-port", "ok", "actor-port")
    ]
    assert repo.receipts[0]["delivery_code"] == "DLV-port"
    assert repo.receipts[0]["receipt_no"] == "AUD-port"
    assert repo.receipts[0]["payload_json"]["file_name"] == "port.csv"
    assert result["file_link"] == "/api/delivery/DLV-port/file/AUD-port/download"
