"""国家资源网关凭据建模 — 诚实化 + FK 守卫（D50/C2，承 D47/D48）.

权威：docs/decisions/national-platform-access-D50.md §三（数据模型）。
核实：
  - credential_status 默认 "not_issued"，state_appkey/state_sid 默认 None（绝不捏造）；
  - 干净库含 application_id FK → application_record.id 且 ON DELETE CASCADE；
  - NationalCredentialWriter.upsert_pending 不捏造密钥；删父级联删凭据。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import text

from zw_brain.adapters.legacy.national_exchange import NationalCredentialWriter
from zw_brain.domain.models import (
    ApplicationRecord,
    NationalResourceCredentialRecord,
)
from zw_brain.shared import db as db_module
from zw_brain.shared.migrate import ensure_runtime_schema


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "national_credential.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()
        yield db_path
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


def _make_application(session, *, code: str = "APP-NAT-1") -> ApplicationRecord:
    app = ApplicationRecord(
        tenant_id="sd-default",
        application_code=code,
        status="submitted",
        applicant_name="测试申请人",
        applicant_org="测试单位",
        payload_json={},
    )
    session.add(app)
    session.flush()
    return app


def test_credential_defaults_not_issued_no_fabrication(temp_db: Path) -> None:
    """ORM 默认值：not_issued + 密钥字段 None（承 D47，绝不捏造）。"""
    SessionLocal = db_module.create_session_factory()
    with SessionLocal() as s:
        app = _make_application(s)
        record = NationalResourceCredentialRecord(
            tenant_id="sd-default",
            application_id=app.id,
        )
        s.add(record)
        s.commit()
        fetched = s.get(NationalResourceCredentialRecord, record.id)
        assert fetched is not None
        assert fetched.credential_status == "not_issued"
        assert fetched.state_appkey is None
        assert fetched.state_sid is None
        assert fetched.state_url is None


def test_writer_upsert_pending_never_fabricates(temp_db: Path) -> None:
    """写区 upsert_pending：状态 not_issued、密钥保持空；二次 upsert 幂等不造密钥。"""
    SessionLocal = db_module.create_session_factory()
    with SessionLocal() as s:
        app = _make_application(s)
        s.commit()
        app_id = app.id

    writer = NationalCredentialWriter()
    rec = writer.upsert_pending(application_id=app_id, gateway_url="https://gw.example/api")
    assert rec.credential_status == "not_issued"
    assert rec.state_appkey is None
    assert rec.state_sid is None

    # 幂等：再次 upsert 同申请 → 仍一条、仍 not_issued、仍无密钥。
    again = writer.upsert_pending(application_id=app_id, up_apply_id="UP-123")
    assert again.id == rec.id
    assert again.credential_status == "not_issued"
    assert again.state_appkey is None
    assert again.up_apply_id == "UP-123"


def test_clean_schema_has_application_fk_cascade(temp_db: Path) -> None:
    """干净库：national_resource_credential.application_id FK → application_record.id, CASCADE。"""
    SessionLocal = db_module.create_session_factory()
    with SessionLocal() as s:
        rows = list(s.execute(text("PRAGMA foreign_key_list(national_resource_credential)")))
    # PRAGMA cols: id, seq, table, from, to, on_update, on_delete, match
    fks = [(r[2], r[3], r[4], r[6]) for r in rows]
    match = [t for t in fks if t[0] == "application_record" and t[1] == "application_id"]
    assert match, f"application_id 应有 FK → application_record.id，实测 {fks}"
    assert match[0][2] == "id"
    assert match[0][3] == "CASCADE", f"FK 应 ON DELETE CASCADE，实测 {match[0][3]}"


def test_delete_application_cascades_credential(temp_db: Path) -> None:
    """删申请单 → 级联删凭据（孤儿=0，DB 强制）。"""
    SessionLocal = db_module.create_session_factory()
    with SessionLocal() as s:
        app = _make_application(s)
        s.add(NationalResourceCredentialRecord(tenant_id="sd-default", application_id=app.id))
        s.commit()
        app_id = app.id

    with SessionLocal() as s:
        s.delete(s.get(ApplicationRecord, app_id))
        s.commit()

    with SessionLocal() as s:
        remaining = s.execute(
            text(
                "SELECT COUNT(*) FROM national_resource_credential WHERE application_id = :a"
            ),
            {"a": app_id},
        ).scalar()
        assert remaining == 0
