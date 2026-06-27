"""CardSession — Action D 写路径单源化的 per-dispatch 卡片会话。

Action D（j1-runtime-write-path-dual-track 收账）把申请 / 审批 / 交付三聚合的
唯一事实源收口到 DB（``application_record`` / ``approval_case`` / ``delivery_task``
的 payload 列），内存快照的 ``requests`` / ``approvals`` / ``delivery_tasks``
三键整体退役。处理器保留「先查卡、闭包内就地改卡」的既有写法，本会话承担
持久化语义：

- **查找**：``get_*`` 从 DB 载入 payload 卡（权威 status 列覆盖 payload 内
  status），登记进 identity map 并记录 load 指纹；同一 dispatch 内重复查找
  返回同一 dict 实例（处理器在 ``deps.write`` 括号外预取、闭包内变更的
  既有形态因此继续成立）。
- **新建**：``add_*`` 登记空指纹卡（必脏），与变更卡一起在写括号末尾落库。
- **落库**：``flush()``（PersistMiddleware 写路径调用）只 upsert 指纹变化的
  卡；申请卡落库时配对刷新 approval_case（与退役前 sync_aggregate_tables
  镜像循环的 request+approval 配对语义一致），随后清空会话。
- **纪元**：顶层 ``invoke_skill`` 进入时清空（防上一次 dispatch 的卡跨期
  陈旧），flush 后清空；嵌套 dispatch（如审批后自动签发凭据）复用同一
  会话，由最外层括号清。

运行时单 vs 导入单的判别是机械的：legacy 导入 payload 一律带 ``kind``
（apply / require / apply_grant / …），运行时卡从不带——导入单保持只读合成
投影（``record_to_request`` / ``task_from_record``），不进会话、不被回写。
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from typing import Any

from zw_brain.domain.application_dedupe import dedupe_application_records
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID


def is_runtime_request_payload(payload: dict[str, Any] | None) -> bool:
    """运行时申请卡判别：legacy 导入 payload 一律带 ``kind``，运行时卡从不带。"""
    return bool(payload) and "kind" not in payload


def is_runtime_delivery_payload(payload: dict[str, Any] | None) -> bool:
    """运行时交付卡判别：运行时卡带 ``requestId``（创建时落）且无 legacy ``kind``。"""
    return bool(payload) and "kind" not in payload and "requestId" in payload


def _fingerprint(card: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(card, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


class CardSession:
    """Per-dispatch identity map over 申请 / 审批 / 交付卡（DB 单一事实源）。"""

    def __init__(self, store_getter: Callable[[], Any]) -> None:
        self._store = store_getter
        # kind → {entity_id: (card, load_fingerprint)}；新建卡指纹为 ""（必脏）。
        self._requests: dict[str, tuple[dict[str, Any], str]] = {}
        self._approvals: dict[str, tuple[dict[str, Any], str]] = {}
        self._deliveries: dict[str, tuple[dict[str, Any], str]] = {}

    # --- 查找（载入 + 登记） -------------------------------------------------

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        """运行时申请卡；导入单 / 不存在 → None（调用方走只读合成兜底）。"""
        tracked = self._requests.get(request_id)
        if tracked is not None:
            return tracked[0]
        store = self._store()
        if store is None:
            return None
        record = store.application_repo.get_record(request_id, tenant_id=_DEFAULT_TENANT_ID)
        if record is None or not is_runtime_request_payload(record.payload_json):
            return None
        card = copy.deepcopy(record.payload_json)
        card["status"] = record.status  # status 列权威（update_status 类写者只写列）
        self._requests[request_id] = (card, _fingerprint(card))
        return card

    def get_approval(self, request_id: str) -> dict[str, Any] | None:
        """运行时审批卡（approval_case.decision_payload_json）；legacy case → None。"""
        tracked = self._approvals.get(request_id)
        if tracked is not None:
            return tracked[0]
        store = self._store()
        if store is None:
            return None
        case = store.approval_repo.get_case(request_id, tenant_id=_DEFAULT_TENANT_ID)
        if case is None or getattr(case, "legacy_id", None) or not case.decision_payload_json:
            return None
        card = copy.deepcopy(case.decision_payload_json)
        card.setdefault("id", case.application_code)
        self._approvals[request_id] = (card, _fingerprint(card))
        return card

    def get_delivery(self, task_id: str) -> dict[str, Any] | None:
        """运行时交付卡（delivery_task.payload_json，按 delivery_code）；legacy → None。"""
        tracked = self._deliveries.get(task_id)
        if tracked is not None:
            return tracked[0]
        store = self._store()
        if store is None:
            return None
        record = store.delivery_repo.get_task(task_id, tenant_id=_DEFAULT_TENANT_ID)
        return self._track_delivery_record(record)

    def get_delivery_by_request(self, request_id: str) -> dict[str, Any] | None:
        """运行时交付卡（按 application_code）；legacy → None。"""
        for card, _ in self._deliveries.values():
            if card.get("requestId") == request_id:
                return card
        store = self._store()
        if store is None:
            return None
        record = store.delivery_repo.get_task_by_application_code(request_id, tenant_id=_DEFAULT_TENANT_ID)
        return self._track_delivery_record(record)

    def _track_delivery_record(self, record: Any) -> dict[str, Any] | None:
        if record is None or not is_runtime_delivery_payload(record.payload_json):
            return None
        card = copy.deepcopy(record.payload_json)
        card["status"] = record.state  # state 列权威
        self._deliveries[str(record.delivery_code)] = (card, _fingerprint(card))
        return card

    def list_runtime_requests(self) -> list[dict[str, Any]]:
        """全部运行时申请卡（只读副本，**不登记**），创建时间倒序。

        供 ``RequestsView.list_all``（在办去重 / 草稿重入检查）等列表态消费；
        变更必须经 ``get_request`` 取登记卡。
        """
        store = self._store()
        if store is None:
            return []
        cards: list[tuple[Any, dict[str, Any]]] = []
        records = [
            record
            for record in store.application_repo.list_records(tenant_id=_DEFAULT_TENANT_ID)
            if is_runtime_request_payload(record.payload_json)
        ]
        for record in dedupe_application_records(records):
            card = copy.deepcopy(record.payload_json)
            card["status"] = record.status
            cards.append((record.created_at, card))
        cards.sort(key=lambda pair: str(pair[0] or ""), reverse=True)
        return [card for _, card in cards]

    # --- 新建（登记必脏卡） ---------------------------------------------------

    def add_request(self, card: dict[str, Any]) -> None:
        self._requests[str(card["id"])] = (card, "")

    def add_approval(self, card: dict[str, Any]) -> None:
        self._approvals[str(card["id"])] = (card, "")

    def add_delivery(self, card: dict[str, Any]) -> None:
        self._deliveries[str(card["id"])] = (card, "")

    # --- 落库 / 纪元 ----------------------------------------------------------

    def flush(self) -> None:
        """脏卡落库（指纹变化才 upsert），随后清空会话。

        申请卡落库时配对刷新 approval_case（current_status / 步骤投影随
        申请状态走），保持与退役前镜像循环一致的配对语义。
        """
        store = self._store()
        if store is None:
            self.clear()
            return
        flushed_approval_ids: set[str] = set()
        for request_id, (card, loaded) in self._requests.items():
            if _fingerprint(card) == loaded:
                continue
            store.application_repo.upsert_from_request(card, tenant_id=_DEFAULT_TENANT_ID)
            approval = self._paired_approval(store, request_id)
            store.approval_repo.upsert_from_request_and_approval(card, approval, tenant_id=_DEFAULT_TENANT_ID)
            flushed_approval_ids.add(request_id)
        for request_id, (card, loaded) in self._approvals.items():
            if request_id in flushed_approval_ids or _fingerprint(card) == loaded:
                continue
            request = self._paired_request(store, request_id)
            store.approval_repo.upsert_from_request_and_approval(request, card, tenant_id=_DEFAULT_TENANT_ID)
        for _task_id, (card, loaded) in self._deliveries.items():
            if _fingerprint(card) == loaded:
                continue
            store.delivery_repo.upsert_from_delivery(card, tenant_id=_DEFAULT_TENANT_ID)
        self.clear()

    def _paired_approval(self, store: Any, request_id: str) -> dict[str, Any]:
        tracked = self._approvals.get(request_id)
        if tracked is not None:
            return tracked[0]
        case = store.approval_repo.get_case(request_id, tenant_id=_DEFAULT_TENANT_ID)
        if case is not None and not getattr(case, "legacy_id", None) and case.decision_payload_json:
            return dict(case.decision_payload_json)
        return {}

    def _paired_request(self, store: Any, request_id: str) -> dict[str, Any]:
        tracked = self._requests.get(request_id)
        if tracked is not None:
            return tracked[0]
        record = store.application_repo.get_record(request_id, tenant_id=_DEFAULT_TENANT_ID)
        if record is not None:
            return {
                "id": request_id,
                "status": record.status,
                "applicant": record.applicant_name,
                "applicantDept": record.applicant_org,
            }
        return {"id": request_id, "status": "pending", "applicant": "", "applicantDept": ""}

    def clear(self) -> None:
        self._requests.clear()
        self._approvals.clear()
        self._deliveries.clear()
