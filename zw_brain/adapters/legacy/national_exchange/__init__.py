"""国家通道专有写区（数据直达 / national-direct + national-ext-elements）。

§9.5 / 段25：zw-brain 唯一合法写区 = ``zw_brain/adapters/legacy/``。国家通道的
专有持久化（资源网关凭据生命周期等）落在本子包，受同一写禁区豁免。

诚实纪律（承 D47/D50）：未接入客户前凭据 ``not_issued``、密钥字段空，绝不捏造；
受理回执 + ``up_*_id`` 幂等复用既有 ``external_adapter`` 仓，本写区不新增回执/映射表。
"""
from __future__ import annotations

from zw_brain.adapters.legacy.national_exchange.credential_writer import (
    NationalCredentialWriter,
)

__all__ = ["NationalCredentialWriter"]
