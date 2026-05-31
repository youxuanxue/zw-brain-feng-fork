"""DeliveryService — delivery task lifecycle + projection helpers.

Owns: delivery task projection from records, grant evidence, due hints,
attempt recording, task id derivation, by-id / by-request snapshot lookups.

"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from zw_brain.domain.errors import NotFoundError
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID
from zw_brain.shared.sensitive_mask import mask_default as _mask

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService



@dataclass(frozen=True)
class DeliveryService:
    """Delivery task lifecycle + projection (P4 delivery)."""

    brain: BrainService

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
            "name": payload.get("resource_name") or f"{record.delivery_code} 交付任务",
            "channel": record.channel,
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

        role = str(payload.get("role", self.brain._ui_state["role"]))
        confirmed = bool(payload.get("confirmed"))
        task_id = str(payload["task_id"])

        def mutation(audit_id: str, actor: str) -> dict[str, Any]:
            task = self.by_id(task_id)
            delivery_repo = self.brain._delivery_repo()
            attempt = delivery_repo.upsert_attempt({"attempt_code": payload.get("attempt_id") or f"{task_id}:{attempt_kind}:{audit_id}", "delivery_code": task_id, "subscription_code": payload.get("subscription_id"), "attempt_kind": attempt_kind, "state": state, "executor_ref": payload.get("executor_ref"), "evidence_ref": audit_id, "payload_json": payload.get("plan") or payload})
            task["updatedAt"] = clock.now_datetime()
            task.setdefault("history", []).append({"time": clock.now_short_time(), "state": f"交换交付{state}", "detail": str(payload.get("reason") or payload.get("mode") or attempt_kind)})
            delivery_repo.add_execution_evidence({"evidence_ref": audit_id, "delivery_code": task_id, "attempt_code": attempt.attempt_code, "executor_kind": "builtin_exchange", "executor_ref": payload.get("executor_ref"), "evidence_kind": attempt_kind, "result_status": state, "payload_json": payload})
            delivery_repo.upsert_exchange_metric({"metric_scope": "delivery", "delivery_code": task_id, "resource_code": payload.get("resource_id") or task.get("resourceId"), "subscription_code": payload.get("subscription_id"), "status": state, "success_count": 1 if state in {"published", "running", "planned"} else 0, "failed_count": 1 if state == "stopped" else 0, "summary_json": {"skill_id": skill_id, "state": state}})
            self.brain._append_audit_feed(skill_id, task_id, "ok", actor)
            return {"task_id": task_id, "attempt_code": attempt.attempt_code, "state": attempt.state, "audit_id": audit_id}

        return self.brain._mutate(skill_id, role, confirmed, payload, mutation)

    # --- Snapshot lookups ---

    def task_id_for_request(self, request_id: str) -> str:
        """Derive delivery task id from request id (REQ- → DLV-)."""
        return request_id.replace("REQ-", "DLV-", 1)

    def by_id(self, task_id: str) -> dict[str, Any]:
        """Snapshot delivery task by task_id; raises NotFoundError when absent."""
        for item in self.brain._snapshot["delivery_tasks"]:
            if item["id"] == task_id:
                return item
        raise NotFoundError(task_id)

    def maybe_by_id(self, task_id: str) -> dict[str, Any] | None:
        """Snapshot delivery task by task_id; returns None when absent."""
        try:
            return self.by_id(task_id)
        except NotFoundError:
            return None

    def by_request_id(self, request_id: str) -> dict[str, Any] | None:
        """Delivery task by application/request id; None when absent.

        先查内存快照（demo/seed 即时态），未命中再回 DB（task_from_record）。
        修真 bug：DB 导入的交付（如 M0 dump 的 granted 授权）不在内存快照基底里，
        旧实现只读 brain._snapshot 漏查 → credential.query 抛 NotFoundError → P4 凭据页 422。
        DB 是真相（system.snapshot 也用 brain.list_delivery_tasks() 回源），与之同源。
        """
        for item in self.brain._snapshot["delivery_tasks"]:
            if item["requestId"] == request_id:
                return item
        store = getattr(getattr(self.brain, "_state_store", None), "database_store", None)
        if store is not None:
            return self.task_from_record(request_id, store)
        return None
