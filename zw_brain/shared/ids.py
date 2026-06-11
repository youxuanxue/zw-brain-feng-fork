"""Project ID generators — application codes + audit event IDs.

- ``new_audit_id()``: stateless — date + HHMMSS + microsecond suffix. The
  microsecond resolution keeps audit events within a millisecond burst unique.
- ``new_application_code()``: opaque ``uuid4().hex`` — Action D 写路径单源化
  后，运行时申请与 legacy 导入申请共用同一 id 形态（``application_record.
  application_code`` 不透明编码）。演示时代的 ``REQ-YYYY-MM-DD-NNNN`` 序列
  （靠扫描内存快照取当日最大号）随快照一并退役；存量 REQ-* 行作为历史
  application_code 继续可读，不再新铸。

ID format contracts baked into audit feed UI:
- ``AE-`` prefix is what audit-feed grep filters expect.
- 交付任务 id 由 ``delivery_service.task_id_for_request`` 派生（``DLV-`` 前缀）。
"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4


def new_audit_id() -> str:
    return f"AE-{datetime.now():%Y-%m-%d-%H%M%S%f}"


def new_application_code() -> str:
    return uuid4().hex
