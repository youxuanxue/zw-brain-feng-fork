"""F4 文件资源下载（delivery.file.download）— 产受控下载链接 + 落下载日志，zw-brain 内自闭环。

对齐旧 resource_file_download_log（file_link/file_name/file_size/download_time/downloaded_by）。
不依赖外部交换底座。同时回归交付任务 resourceKind 投影（供 P4 文件分流）。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.shared import audit as audit_bus
from zw_brain.shared import db as db_module
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

TENANT = "sd-default"
MANAGER = "ROLE_ORGAN_MANAGER"


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "delivery_file_download.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()
        yield db_path
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


def _seed_file_delivery(store: DatabaseStore, delivery_code: str) -> None:
    store.delivery_repo.upsert_from_delivery(
        {
            "id": delivery_code,
            "requestId": f"app-{delivery_code}",
            "status": "granted",
            "channel": "file",
            "name": "产品使用报告.docx",
            "resource_kind": "file",
            "note": "文件类交付任务",
        },
        tenant_id=TENANT,
    )


@pytest.fixture()
def brain(temp_db: Path) -> BrainService:
    ds = DatabaseStore()
    ds.initialize()
    audit_bus.configure_sink(ds.append_audit_event)
    _seed_file_delivery(ds, "DLV-FILE-1")
    return BrainService(state_store=StateStore(database_store=ds))


def test_file_download_produces_link_and_log(brain: BrainService) -> None:
    res = invoke_trusted(
        brain,
        "delivery.file.download",
        {"task_id": "DLV-FILE-1", "file_name": "产品使用报告.docx", "file_size": "17869", "confirmed": True},
        role=MANAGER,
    )["result"]
    # 受控下载链接（自签，带 task + audit 锚），非外部直链。
    assert res["file_link"].startswith("/api/delivery/DLV-FILE-1/file/")
    assert res["file_link"].endswith("/download")
    assert res["file_name"] == "产品使用报告.docx"
    assert res["file_size"] == "17869"
    assert res["download_time"]
    # 下载日志落库为 file_download 回执（下载凭证 + 审计锚）。
    receipts = brain._delivery_repo().list_receipts("DLV-FILE-1")
    dl = [r for r in receipts if r.receipt_type == "file_download"]
    assert len(dl) == 1
    payload = dl[0].payload_json
    assert payload["file_name"] == "产品使用报告.docx"
    assert payload["file_size"] == "17869"
    assert payload["downloaded_by"]


def test_delivery_task_projects_resource_kind_file(brain: BrainService) -> None:
    """交付任务投影出 resourceKind=file，供 P4 文件分流（显「下载」）。"""
    tasks = brain.list_delivery_tasks()
    target = next((t for t in tasks if t["id"] == "DLV-FILE-1"), None)
    assert target is not None
    assert target["resourceKind"] == "file"


def test_file_download_unknown_task_raises(brain: BrainService) -> None:
    from zw_brain.domain.errors import NotFoundError

    with pytest.raises(NotFoundError):
        invoke_trusted(
            brain,
            "delivery.file.download",
            {"task_id": "DLV-MISSING", "confirmed": True},
            role=MANAGER,
        )
