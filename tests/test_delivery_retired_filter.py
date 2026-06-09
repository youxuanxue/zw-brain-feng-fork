"""消费侧交付列表（领数据）隐藏规则 + 缺名兜底（2026-06-09 走查）。

业务方裁决：
- 退役类型（folder/url/link，D53② 收敛为 库表/文件/API）历史交付单不显示——保持全局语义一致性。
- 草稿态交付单（存量交换流水线 exchange/recurring_exchange 导入残留、从未激活、含 hex 缺名/重复/
  测试噪声）不显示——正常审批流交付单初始态是 pending，draft 全部是 M0 dump 残留。
- 缺资源名（上游 D11 不伪造）时退可读兜底标签（org_name + 类型），不暴露 hex 交付编号。
仅过滤只读路径、不删存量授权。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zw_brain.domain.services.delivery_service import (
    _delivery_fallback_name,
    delivery_record_hidden_from_consumer,
    delivery_record_is_retired_origin,
)


@dataclass
class _FakeRecord:
    channel: str = ""
    state: str = "granted"
    payload_json: dict[str, Any] | None = None


RETIRED = {"folder-rc", "url-rc"}


# --- 退役类型来源识别 ---


def test_retired_channel_folder_is_origin():
    assert delivery_record_is_retired_origin(_FakeRecord(channel="folder"), RETIRED) is True


def test_retired_resource_code_via_payload_is_origin():
    rec = _FakeRecord(channel="exchange", payload_json={"resource_code": "folder-rc"})
    assert delivery_record_is_retired_origin(rec, RETIRED) is True


def test_retired_raw_res_type_in_grant_is_origin():
    rec = _FakeRecord(channel="exchange", payload_json={"access_grant": {"res_type": "url"}})
    assert delivery_record_is_retired_origin(rec, RETIRED) is True


def test_live_table_is_not_retired_origin():
    rec = _FakeRecord(channel="exchange", payload_json={"resource_code": "table-rc"})
    assert delivery_record_is_retired_origin(rec, RETIRED) is False


# --- 消费视图隐藏（退役 OR 草稿）---


def test_hidden_when_retired_origin():
    assert delivery_record_hidden_from_consumer(_FakeRecord(channel="folder"), RETIRED) is True


def test_hidden_when_draft_state():
    rec = _FakeRecord(channel="exchange", state="draft", payload_json={"resource_code": "table-rc"})
    assert delivery_record_hidden_from_consumer(rec, RETIRED) is True


def test_visible_when_granted_table():
    rec = _FakeRecord(channel="table", state="granted", payload_json={"resource_code": "table-rc"})
    assert delivery_record_hidden_from_consumer(rec, RETIRED) is False


def test_visible_when_pending_file():
    rec = _FakeRecord(channel="file", state="pending", payload_json={"resource_code": "file-rc"})
    assert delivery_record_hidden_from_consumer(rec, RETIRED) is False


# --- 缺名兜底：org + 类型，无 hex ---


def test_fallback_name_uses_org_and_kind_no_hex():
    payload = {"access_grant": {"org_name": "省大数据局", "res_type": "service"}}
    # service → api → 接口服务；不含任何 hex 编号。
    assert _delivery_fallback_name(payload) == "省大数据局 · 接口服务交付任务"


def test_fallback_name_org_only():
    assert _delivery_fallback_name({"access_grant": {"org_name": "省大数据局"}}) == "省大数据局 · 数据交付任务"


def test_fallback_name_empty_payload():
    assert _delivery_fallback_name({}) == "数据交付任务"
