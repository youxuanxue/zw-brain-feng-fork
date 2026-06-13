"""b1 handler 共享元工具：租户域校验（第二道防线）+ 查询参数指纹。

intake / audit / investigation 三 handler 原各持一份逐字副本
（``_enforce_tenant_scope`` ×3、``_param_hash`` ×2）。``enforce_tenant_scope`` 是
「handler 被未走 invoke_skill 的路径直接调用时」的安全第二道防线，复制粘贴有
「修一处漏两处」风险，故收口到此单源。

刻意不并入的：``_emit_meta_audit`` 三份语义实质不同（默认角色 BUSIAUDIT vs
SECURITY_AUDIT、度量字段 result_count vs summary_length、investigation 多 panel
字段、request_id 来源各异）——属本质差异非偶然重复，强行参数化反成假 DRY，留在各
handler 内更可读。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from zw_brain.domain.policy import DomainAccessDeniedError, tenant_for_role
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id


def enforce_tenant_scope(payload: dict[str, Any], *, capability: str) -> str:
    """单租户 sd-default 模式下 cross-tenant 读必须被拦下。

    ``payload["role"]`` 给出则从 role 推 runtime tenant，否则用全局 runtime
    tenant；无论哪一种，payload 显式声明的 ``tenant_id`` 必须与之相等，否则
    raise ``DomainAccessDeniedError``。preflight ``enforce_manifest_policy`` 同步
    做一次；这里是第二道防线，handler 被未走 invoke_skill 的路径直接调用时也守得住。
    ``capability`` 仅用于错误信息定位（各 handler 传各自能力标识）。
    """
    role = payload.get("role")
    runtime_tenant = tenant_for_role(str(role)) if role else get_runtime_tenant_id()
    requested = payload.get("tenant_id")
    if requested is None or requested == "":
        return runtime_tenant
    requested_str = str(requested)
    if requested_str != runtime_tenant:
        raise DomainAccessDeniedError(
            f"tenant scope violation for {capability}: "
            f"requested={requested_str}, runtime={runtime_tenant}"
        )
    return requested_str


def param_fingerprint(params: dict[str, Any]) -> str:
    """查询参数确定性指纹（排序去空 + sha1），用于元审计 param_hash（不存原始参数值）。

    命名为 fingerprint 而非 param_hash，避免与 ``_emit_meta_audit`` 的同名形参遮蔽。
    """
    serializable = {k: v for k, v in sorted(params.items()) if v is not None and v != ""}
    body = json.dumps(serializable, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(body.encode("utf-8")).hexdigest()
