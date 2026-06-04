#!/usr/bin/env python3
"""C9 e2e 造数：注入一条「请求国家级数据」的待转报申请（national-direct 子旅程）。

用途：national_channel.spec.ts「待转报队列」真实 UI 断言需要一条
``channel_class=='national'`` 且处于 ``dept_approved``（本级审核通过、待业务运营员
转报国家平台）的申请。该状态组合**无法**经 in-memory request API 造出
（``_create_request`` 写内存快照而非 DB apply 记录；``dept_approve`` 要求 DB 记录在
``submitted``→``dept_approved``），故此处直接 upsert 一条确定性 DB apply 记录，
口径与 record_to_request 透出的 ``channelClass`` 完全一致（payload_json["channel_class"]）。

幂等：同 application_code 重复执行只更新。针对 ``ZW_BRAIN_DB_PATH`` 指向的库。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zw_brain.domain.repositories.application import ApplicationRepository  # noqa: E402
from zw_brain.shared.db import ensure_parent_dir  # noqa: E402
from zw_brain.shared.migrate import upgrade  # noqa: E402

# A_7001 = SPEC（national-direct.feature §scenario 2）里「来自部门X 的申请国家级数据」样例。
NATIONAL_APPLY_CODE = os.environ.get("ZW_E2E_NATIONAL_APPLY_CODE", "A_7001_E2E_NATIONAL")
TENANT_ID = "sd-default"


def seed() -> str:
    ensure_parent_dir()
    upgrade()  # idempotent create_all（裸 DB 时建表；已建库 no-op）
    repo = ApplicationRepository()
    request = {
        "id": NATIONAL_APPLY_CODE,
        # dept_approved = 本级审核通过、待业务运营员转报国家平台（platformReview 队列阶段）。
        "status": "dept_approved",
        "applicant": "部门X 经办人",
        "applicantDept": "部门X",
        "kind": "apply",  # list_requests 仅拾取 kind=='apply' 的 DB 记录
        "channel_class": "national",  # 国家通道真实信号（record_to_request → channelClass）
        "resource_name": "国家级人口基础数据（e2e 待转报样例）",
        "purpose": "申请国家级数据用于跨省核验（C9 待转报 e2e 样例）",
    }
    repo.upsert_from_request(request, tenant_id=TENANT_ID)
    return NATIONAL_APPLY_CODE


if __name__ == "__main__":
    code = seed()
    print(f"[seed-national-escalate] upserted dept_approved national apply: {code}", flush=True)
