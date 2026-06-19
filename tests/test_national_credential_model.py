"""国家资源网关凭据建模 — 诚实化 + FK 守卫（D50/C2，承 D47/D48）.

权威：docs/decisions/national-platform-access-D50.md §三（数据模型）。
核实：
  - credential_status 默认 "not_issued"，state_appkey/state_sid 默认 None（绝不捏造）；
  - 干净库含 application_id FK → application_record.id 且 ON DELETE CASCADE；
  - NationalCredentialWriter.upsert_pending 不捏造密钥；删父级联删凭据。

PG-only：库由根 conftest 的 autouse fixture 提供（每测一个 CREATE DATABASE …
TEMPLATE 克隆的、已 alembic upgrade head 的空 PG 库），测试只需走
create_session_factory()/get_database_url() 即落到隔离的迁移后 PostgreSQL schema。
库供给与隔离全由 conftest 接管。
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from zw_brain.adapters.legacy.national_exchange import NationalCredentialWriter
from zw_brain.domain.models import (
    ApplicationRecord,
    NationalResourceCredentialRecord,
)
from zw_brain.shared import db as db_module


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


def test_credential_defaults_not_issued_no_fabrication() -> None:
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


def test_writer_upsert_pending_never_fabricates() -> None:
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


def test_clean_schema_has_application_fk_cascade() -> None:
    """干净库：national_resource_credential.application_id FK → application_record.id, CASCADE。"""
    engine = db_module.create_session_factory().kw["bind"]
    fks = inspect(engine).get_foreign_keys("national_resource_credential")
    # 方言无关：每条 fk = {'constrained_columns','referred_table',
    #   'referred_columns','options': {'ondelete': ...}}。
    match = [
        fk
        for fk in fks
        if fk["referred_table"] == "application_record"
        and fk["constrained_columns"] == ["application_id"]
    ]
    assert match, f"application_id 应有 FK → application_record.id，实测 {fks}"
    assert match[0]["referred_columns"] == ["id"]
    ondelete = (match[0].get("options") or {}).get("ondelete")
    assert ondelete == "CASCADE", f"FK 应 ON DELETE CASCADE，实测 {ondelete}"


def test_delete_application_cascades_credential() -> None:
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
