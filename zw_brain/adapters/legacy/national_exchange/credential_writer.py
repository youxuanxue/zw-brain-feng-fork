"""国家资源网关凭据写区（national_resource_credential）。

对应真实库 ``dc_resource_api_auth_info``。**诚实纪律（承 D47/D50）是脊柱**：

- 新建凭据默认 ``credential_status="not_issued"``、``state_appkey/state_sid=None``；
  本期无真实国家端点可联调，未签发即如实留空，**绝不捏造**密钥/服务标识。
- 仅在国家平台真实签发后（``mark_issued``）才落 ``state_*``；调用方须传入真实值，
  本写区不生成任何占位密钥。

写 token（session.add/commit）仅因本文件位于唯一合法写区 ``adapters/legacy/`` 而合法
（§9.5 / 段25）。父聚合 ``application_id`` 删父级联删凭据（D48，FK 在模型层声明）。
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT
from zw_brain.domain.models import NationalResourceCredentialRecord
from zw_brain.shared.db import create_session_factory


def _now() -> datetime:
    return datetime.now(UTC)


class NationalCredentialWriter:
    """国家资源凭据的唯一写入口（一次性迁移 + 签发态迁移）。"""

    def upsert_pending(
        self,
        *,
        application_id: str,
        up_apply_id: str | None = None,
        gateway_url: str | None = None,
        tenant_id: str = DEFAULT_TENANT,
    ) -> NationalResourceCredentialRecord:
        """登记/更新一条凭据，状态固定 ``not_issued``、密钥字段保持空。

        用于上报意图落地：记录「该申请单已进入国家通道、待国家平台签发凭据」，
        密钥（state_appkey/state_sid）此刻天然缺失——不捏造，等真实签发。
        """
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(NationalResourceCredentialRecord).where(
                    NationalResourceCredentialRecord.tenant_id == tenant_id,
                    NationalResourceCredentialRecord.application_id == application_id,
                )
            ).scalar_one_or_none()
            if record is None:
                record = NationalResourceCredentialRecord(
                    tenant_id=tenant_id,
                    application_id=application_id,
                    up_apply_id=up_apply_id,
                    gateway_url=gateway_url,
                    credential_status="not_issued",
                )
                session.add(record)
                session.flush()
            else:
                if up_apply_id is not None:
                    record.up_apply_id = up_apply_id
                if gateway_url is not None:
                    record.gateway_url = gateway_url
                record.updated_at = _now()
            session.commit()
            return session.execute(
                select(NationalResourceCredentialRecord).where(
                    NationalResourceCredentialRecord.id == record.id
                )
            ).scalar_one()

    def mark_issued(
        self,
        *,
        application_id: str,
        state_url: str,
        state_appkey: str,
        state_sid: str,
        tenant_id: str = DEFAULT_TENANT,
    ) -> NationalResourceCredentialRecord:
        """国家平台真实签发后落凭据。**只接受真实值**——本期无端点，故实际不会被调用，
        但保留以使凭据生命周期完整（issued/revoked），且明确「捏造无入口」。
        """
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            record = session.execute(
                select(NationalResourceCredentialRecord).where(
                    NationalResourceCredentialRecord.tenant_id == tenant_id,
                    NationalResourceCredentialRecord.application_id == application_id,
                )
            ).scalar_one_or_none()
            if record is None:
                record = NationalResourceCredentialRecord(
                    tenant_id=tenant_id,
                    application_id=application_id,
                )
                session.add(record)
            record.state_url = state_url
            record.state_appkey = state_appkey
            record.state_sid = state_sid
            record.credential_status = "issued"
            record.updated_at = _now()
            session.commit()
            return session.execute(
                select(NationalResourceCredentialRecord).where(
                    NationalResourceCredentialRecord.id == record.id
                )
            ).scalar_one()
