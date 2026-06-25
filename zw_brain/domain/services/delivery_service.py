"""DeliveryService — delivery task lifecycle + projection helpers.

Owns: delivery task projection from records, grant evidence, due hints,
attempt recording, task id derivation, by-id / by-request card lookups
（Action D：DB 单一事实源，经 CardSession）。

"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from zw_brain.domain.errors import NotFoundError
from zw_brain.domain.resource_kind import canonical_resource_kind
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID
from zw_brain.shared.sensitive_mask import mask_default as _mask

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService
    from zw_brain.command.deps import DomainPorts


def _delivery_resource_kind(res_type: Any, channel: Any = None) -> str | None:
    """交付资源类型归一（D53 收敛 库表/文件/API），驱动 F3 操作分流 + F4 文件下载。

    存量 data_apply_authrization 多无 per-grant res_type → 用交付渠道 channel 兜底推导
    （channel 即编码了交付形态：table/db/exchange→库表、file/folder→文件、service/api→接口），
    否则 resourceKind=None、前端「查看授权 / 下载 / 交换任务」永不分流。仍推不出→None
    （前端回落「查看授权」通用入口，0611 业务口径确认单 §B 方案 B）。
    """
    for raw in (res_type, channel):
        if not raw:
            continue
        kind = canonical_resource_kind(raw)
        if kind:
            return kind
        if str(raw).strip().lower() in {"db", "exchange", "recurring_exchange"}:
            return "table"
    return None


# 退役资源类型（D53② 收敛为「库表/文件/API」）：folder/url/link 在类型退役前导入的存量交付单
# 不进消费视图（交付列表）。全局语义一致——退役类型不在任何消费面以历史交付单形态泄漏
# （业务方 2026-06-09 确认：交付列表历史「文件夹/链接资源」交付单不显示）。数据保留（只读路径过滤、
# 不删存量授权），按资源资产「原始 kind」识别（payload 多无 per-grant res_type，canonical 已折叠为
# file/api 故不能靠投影后的 kind 反推）。
RETIRED_RESOURCE_KINDS = {"folder", "url", "link"}


def delivery_record_is_retired_origin(record: Any, retired_codes: set[str]) -> bool:
    """该交付记录的底层资源是否为退役类型（folder/url/link）来源。"""
    channel = str(getattr(record, "channel", "") or "").strip().lower()
    if channel in RETIRED_RESOURCE_KINDS:
        return True
    payload = getattr(record, "payload_json", None) or {}
    code = payload.get("resource_code") or payload.get("resource_id")
    if code and code in retired_codes:
        return True
    grant = payload.get("access_grant") or {}
    raw = str(payload.get("resource_kind") or grant.get("res_type") or "").strip().lower()
    return raw in RETIRED_RESOURCE_KINDS


def delivery_record_hidden_from_consumer(record: Any, retired_codes: set[str]) -> bool:
    """消费侧交付列表（领数据）应隐藏该记录：
    ① 退役类型（folder/url/link）来源——见 delivery_record_is_retired_origin；
    ② 草稿态——存量交换流水线（exchange/recurring_exchange）导入残留、从未激活，非真实可领交付
       （正常审批流交付单初始态是 pending，不存在 draft；草稿态全部是 M0 dump 残留，含 hex 缺名单/
       重复/测试目录噪声，2026-06-09 走查确认不显示）。只读路径过滤、不删存量授权。
    """
    if delivery_record_is_retired_origin(record, retired_codes):
        return True
    return str(getattr(record, "state", "") or "").strip().lower() == "draft"


# 缺资源名（上游 D11 不伪造）时的可读兜底：用真实 access_grant 字段拼标签，不暴露 hex 交付编号。
_DELIVERY_KIND_LABELS = {"table": "库表", "file": "文件", "api": "接口服务"}


def _delivery_fallback_name(payload: dict[str, Any]) -> str:
    grant = payload.get("access_grant") or {}
    org = str(grant.get("org_name") or "").strip()
    kind = _delivery_resource_kind(payload.get("resource_kind") or grant.get("res_type"), None)
    base = f"{_DELIVERY_KIND_LABELS.get(kind or '', '')}交付任务" if kind in _DELIVERY_KIND_LABELS else "数据交付任务"
    return f"{org} · {base}" if org else base


@dataclass(frozen=True)
class DeliveryService:
    """Delivery task lifecycle + projection (P4 delivery)."""

    brain: BrainService
    ports: DomainPorts

    # --- Projection from delivery record ---

    def task_from_record(
        self,
        request_id: str,
        store: Any,
        *,
        context: Any | None = None,
        record: Any | None = None,
    ) -> dict[str, Any] | None:
        """Build delivery task dict from a delivery record + payload + boundaries.

        ``record`` 由调用方预取直传时跳过任何查找（N+1 消除：list_delivery_tasks
        已一次性取全部 records，逐条投影时无需每条再全表扫 list_tasks）。
        """
        if record is None:
            if context is not None:
                record = context.delivery_by_appcode.get(request_id)
            else:
                # 旧实现按 (delivery_code OR application_code) 全表扫 next(...)；
                # 改成两次索引 get（先 delivery_code 再 application_code），保 OR 语义、去全表扫。
                record = store.delivery_repo.get_task(request_id, tenant_id=_DEFAULT_TENANT_ID)
                if record is None:
                    record = store.delivery_repo.get_task_by_application_code(request_id, tenant_id=_DEFAULT_TENANT_ID)
        if record is None:
            return None
        payload = record.payload_json or {}
        grant = _mask(copy.deepcopy(payload.get("access_grant") or {}))
        return {
            "id": record.delivery_code,
            "requestId": record.application_code,
            # F2：resource_name 缺供（上游 D11 不伪造资源名）时退可读兜底标签，不再把 hex 编号
            # 拼进名称（编号列已单独展示 id），避免「<hex> 交付任务」的乱码观感（2026-06-09 走查）。
            "name": payload.get("resource_name") or _delivery_fallback_name(payload),
            "channel": record.channel,
            # F3（6.5#9）+ F4：交付侧资源类型，供前端按类型分流操作——API=「查看授权」、
            # 文件=「下载」、库表=「交换任务」语系（0611 §B 方案 B）。收敛口径同 D53（folder/url→file、service→api）；
            # 优先 payload.resource_kind（F4 导入时已落），回落 access_grant.res_type，再以 channel 兜底推导
            # （见 _delivery_resource_kind）。（渠道/时间/编号白话化由前端 formatChannel/formatTime/shortId 承接。）
            "resourceKind": _delivery_resource_kind(payload.get("resource_kind") or grant.get("res_type"), record.channel),
            "status": record.state,
            "owner": "审批承接 → 交付执行",
            "updatedAt": record.updated_at.isoformat(),
            "note": "真实旧平台授权导入生成的交付边界。",
            "history": [
                {"time": record.created_at.strftime("%m-%d %H:%M"), "state": record.state, "detail": "授权边界已从 data_apply_authrization 导入。"}
            ],
            "aiSummary": {
                "summary": "已导入真实旧平台授权边界，交付侧按字段范围、频次和授权期回放。",
                "nextAction": "核对交付范围和续期缺口，不新增超出审批意见的授权。",
                "cause": "授权来自 data_apply_authrization，并可回指 legacy_object_mapping。",
                "impact": "通过、退回或驳回都能在审计链路中追溯到责任节点。",
            },
            "backflow": {
                "candidateObject": payload.get("resource_name") or record.delivery_code,
                "candidateFields": [],
                "status": "不适用",
                "note": "本任务来自既有授权回放；不把无真实续期行伪造成回流或续期成功。",
            },
            "accessGrantSnapshot": grant,
            "authorizationBoundary": self.authorization_boundary(grant),
            "r2Review": _mask(copy.deepcopy(payload.get("r2_review") or {})),
            "grantBoundary": _mask(copy.deepcopy(payload.get("grant_boundary") or {})),
            "supplementBoundary": _mask(copy.deepcopy(payload.get("supplement_boundary") or {})),
            "nonGrantBoundary": _mask(copy.deepcopy(payload.get("non_grant_boundary") or {})),
            "renewalBoundary": payload.get("renewal_boundary") or "真实 data_apply_renewal 无行；不伪造续期成功路径。",
            "repository": {"delivery_code": record.delivery_code, "application_code": record.application_code, "channel": record.channel},
            # DB-only 交付（M0 dump granted）也带 receipts，与内存快照 task 行为一致
            # （修真 bug：旧实现该路径产出的 task 无 receipts 键，前端拿不到回执）。
            "receipts": self.receipts_for(store.delivery_repo, record.delivery_code),
        }

    @staticmethod
    def receipts_for(delivery_repo: Any, delivery_code: str) -> list[dict[str, Any]]:
        """单一事实源：交付回执记录 → dict 投影。

        brain.list_delivery_tasks（列表态）与 handlers/j1/delivery._get_delivery_task
        （详情态）共用，避免同一投影复制两份手同步（R-001）。
        """
        return [
            {
                "receiptType": item.receipt_type,
                "receiptNo": item.receipt_no,
                "receiptStatus": item.receipt_status,
                "payload": copy.deepcopy(item.payload_json),
            }
            for item in delivery_repo.list_receipts(delivery_code)
        ]

    def grant_evidence(self, delivery: dict[str, Any] | None) -> dict[str, Any]:
        """Compact grant evidence for the approval review screen."""
        if not delivery:
            return {"state": "pending", "accessGrant": {}}
        return {"state": delivery.get("status"), "accessGrant": copy.deepcopy(delivery.get("accessGrantSnapshot") or {})}

    def due_hint(self, delivery: dict[str, Any] | None) -> str:
        """Human-readable due-by-X hint from delivery grant snapshot."""
        grant = (delivery or {}).get("accessGrantSnapshot") or {}
        limit_day = grant.get("limit_day")
        return f"授权 {limit_day} 天内有效" if limit_day else "按审批授权边界执行"

    def authorization_boundary(self, grant: dict[str, Any]) -> dict[str, Any]:
        """Authorization boundary projection from grant snapshot."""
        return {
            "limitDays": grant.get("limit_day"),
            "resourceType": grant.get("res_type"),
            "applyStatus": grant.get("apply_status"),
            "renewalSourceRows": 0,
            "renewalPolicy": "真实 data_apply_renewal 无行；不伪造续期成功路径。",
        }

    # --- File download (F4：文件资源下载，zw-brain 内自闭环) ---

    def record_file_download(self, payload: dict[str, Any], skill_id: str) -> dict[str, Any]:
        """文件资源下载：产签名下载链接 + 落下载日志（对齐旧 resource_file_download_log）。

        zw-brain 内自闭环（不依赖外部交换底座）：从交付任务解析文件名/访问路径，派生一个
        有时效的签名下载链接（self-issued），并把 file_link/file_name/file_size/download_time/
        downloaded_by 作为一条 ``file_download`` 回执落库——既是下载凭证、又是审计锚。

        诚实（D11）：文件元信息（名/大小）来自交付任务 payload，缺则 None；签名链接是
        zw-brain 自签的受控下载地址，非伪造的外部直链。
        """
        from zw_brain.shared import clock  # noqa: PLC0415

        role = str(payload.get("role") or self.ports.current_role("ROLE_ORGAN_OPERATER"))
        confirmed = bool(payload.get("confirmed"))
        task_id = str(payload["task_id"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            task = self.by_id(task_id)  # 命中快照或回 DB；不存在抛 NotFoundError
            task_payload = (task or {})
            file_name = payload.get("file_name") or task_payload.get("name") or f"{task_id}.dat"
            file_size = payload.get("file_size")
            download_time = clock.now_datetime()
            # 自签受控下载链接：带 task / audit 锚，平台侧凭此校验授权后放行（非外部直链）。
            file_link = f"/api/delivery/{task_id}/file/{audit_id}/download"
            delivery_repo = self.ports.delivery_repo
            receipt = delivery_repo.append_receipt(
                {
                    "delivery_code": task_id,
                    "receipt_type": "file_download",
                    "receipt_no": audit_id,
                    "receipt_status": "issued",
                    "payload_json": {
                        "file_link": file_link,
                        "file_name": file_name,
                        "file_size": file_size,
                        "download_time": download_time,
                        "downloaded_by": actor,
                    },
                }
            )
            self.ports.append_audit_feed(skill_id, task_id, "ok", actor)
            return {
                "task_id": task_id,
                "file_link": file_link,
                "file_name": file_name,
                "file_size": file_size,
                "download_time": download_time,
                "receipt_id": receipt.id,
                "audit_id": audit_id,
            }

        return self.ports.write(skill_id, role, confirmed, payload, mutation)

    # --- Attempt recording (write path) ---

    def record_attempt(
        self,
        payload: dict[str, Any],
        skill_id: str,
        state: str,
        attempt_kind: str,
    ) -> dict[str, Any]:
        """Record a delivery attempt (publish / pause / replay / stop / retry)."""
        from zw_brain.shared import clock  # noqa: PLC0415

        role = str(payload.get("role") or self.ports.current_role("ROLE_ORGAN_OPERATER"))
        confirmed = bool(payload.get("confirmed"))
        task_id = str(payload["task_id"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            task = self.by_id(task_id)
            delivery_repo = self.ports.delivery_repo
            attempt = delivery_repo.upsert_attempt({"attempt_code": payload.get("attempt_id") or f"{task_id}:{attempt_kind}:{audit_id}", "delivery_code": task_id, "subscription_code": payload.get("subscription_id"), "attempt_kind": attempt_kind, "state": state, "executor_ref": payload.get("executor_ref"), "evidence_ref": audit_id, "payload_json": payload.get("plan") or payload})
            task["updatedAt"] = clock.now_datetime()
            task.setdefault("history", []).append({"time": clock.now_short_time(), "state": f"交换交付{state}", "detail": str(payload.get("reason") or payload.get("mode") or attempt_kind)})
            delivery_repo.add_execution_evidence({"evidence_ref": audit_id, "delivery_code": task_id, "attempt_code": attempt.attempt_code, "executor_kind": "builtin_exchange", "executor_ref": payload.get("executor_ref"), "evidence_kind": attempt_kind, "result_status": state, "payload_json": payload})
            delivery_repo.upsert_exchange_metric({"metric_scope": "delivery", "delivery_code": task_id, "resource_code": payload.get("resource_id") or task.get("resourceId"), "subscription_code": payload.get("subscription_id"), "status": state, "success_count": 1 if state in {"published", "running", "planned"} else 0, "failed_count": 1 if state == "stopped" else 0, "summary_json": {"skill_id": skill_id, "state": state}})
            self.ports.append_audit_feed(skill_id, task_id, "ok", actor)
            return {"task_id": task_id, "attempt_code": attempt.attempt_code, "state": attempt.state, "audit_id": audit_id}

        return self.ports.write(skill_id, role, confirmed, payload, mutation)

    # --- Card lookups (Action D: DB 单一事实源，经 CardSession) ---

    def task_id_for_request(self, request_id: str) -> str:
        """Derive delivery task id from request id（``DLV-`` 前缀）。

        Action D：申请 id 收敛为不透明 hex，``REQ-``→``DLV-`` 文本替换不再适用；
        统一前缀派生（存量 ``REQ-*`` 单沿用历史 ``DLV-REQ-…`` 不受影响——本函数
        只在新建交付时铸号）。
        """
        return f"DLV-{request_id}"

    def by_id(self, task_id: str) -> dict[str, Any]:
        """Delivery task by task_id; raises NotFoundError when absent.

        运行时交付卡经 CardSession 载入（payload_json 卡 + 权威 state 列覆盖，
        闭包就地变更由 flush 落库）；legacy 导入交付走 task_from_record
        只读合成投影（不进会话、不被回写——与退役前「DB 单变更丢失」语义
        一致，历史导入交付的在线动作由 UI 门控）。
        """
        card = self.brain._card_session.get_delivery(task_id)
        if card is not None:
            return card
        store = getattr(getattr(self.brain, "_state_store", None), "database_store", None)
        if store is not None:
            task = self.task_from_record(task_id, store)
            if task is not None:
                return task
        raise NotFoundError(task_id)

    def maybe_by_id(self, task_id: str) -> dict[str, Any] | None:
        """Snapshot delivery task by task_id; returns None when absent."""
        try:
            return self.by_id(task_id)
        except NotFoundError:
            return None

    def by_request_id(self, request_id: str) -> dict[str, Any] | None:
        """Delivery task by application/request id; None when absent.

        运行时交付卡经 CardSession（按 application_code 索引）；legacy 导入
        交付回 task_from_record 只读合成。DB 是唯一真相。
        """
        card = self.brain._card_session.get_delivery_by_request(request_id)
        if card is not None:
            return card
        store = getattr(getattr(self.brain, "_state_store", None), "database_store", None)
        if store is not None:
            return self.task_from_record(request_id, store)
        return None
