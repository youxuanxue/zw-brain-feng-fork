"""Audit event persistent store (SQLite-backed, sync, fail-fast).

Goal-id e4-b1-agentruntime F1。落在 zw_brain/shared/audit/store.py 而不是
复用 shared/database_store.py 的目的是：

  1. 审计是 D4 强约束「不允许无审计落库」的硬熔断点，需要一条
     独立、最小依赖、不被业务 schema 演进牵连的写路径。
  2. shared/database_store.py 上面挂了 15+ 业务 repository，引入循环依赖
     会让 audit.* skill / 推理 client 的纯净测试很难拉起。
  3. store.py 的 sqlite 文件支持独立查询/回放/dashboards（F2 / F3 会消费
     `index.query`），不污染主库 schema。

线上 runtime 把 database_store.append_audit_event 配为 sink；这里的 store 在
非 runtime 上下文（单测、CLI 工具、批量回放）下提供同等保证。

D4 收口位（架构 §6.4 / §8.4）：
  - 写失败必须 raise AuditWriteError（绝不 try/except: pass）
  - audit_class 三级正规化：write-critical / write-normal / read-sensitive
    （映射策略见 docs/audit-class-normalization.md）
  - 区块链锚定通过可插拔 post_persist_hook 异步执行（E6 / M0 落地），
    外链 down 不阻塞业务但要排队 outbox
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# audit_class 三级正规化（docs/audit-class-normalization.md）
# ---------------------------------------------------------------------------

CANONICAL_AUDIT_CLASSES: tuple[str, ...] = (
    "write-critical",
    "write-normal",
    "read-sensitive",
)

# 历史 manifest 实际取值 → 3 级正规化。
# 未列出 / 未知值 → "read-sensitive"（防御性兜底；store 同时把原值写到
# payload[original_audit_class]，不丢信息）。
_AUDIT_CLASS_MAP: dict[str, str] = {
    "write-critical": "write-critical",
    "write-normal": "write-normal",
    "write-default": "write-normal",
    "adapter-write": "write-critical",
    "external-execution": "write-critical",
    "read-sensitive": "read-sensitive",
    "read-default": "read-sensitive",
    "read-normal": "read-sensitive",
    "read-trace": "read-sensitive",
    "read": "read-sensitive",
}


def normalize_audit_class(raw: str | None) -> str:
    """把契约层 audit_class 收敛到 3 级正规化值。

    None / 空串 / 未知值都归类为 "read-sensitive"。详见 ADR
    docs/audit-class-normalization.md。
    """
    if not raw:
        return "read-sensitive"
    return _AUDIT_CLASS_MAP.get(raw, "read-sensitive")


# ---------------------------------------------------------------------------
# exceptions
# ---------------------------------------------------------------------------


class AuditWriteError(RuntimeError):
    """审计落库失败硬熔断（D4 一票否决）。"""


# ---------------------------------------------------------------------------
# storage path
# ---------------------------------------------------------------------------


_DEFAULT_AUDIT_DB_ENV = "ZW_BRAIN_AUDIT_DB_PATH"


def default_audit_db_path() -> Path:
    """默认 audit.db 路径：env 覆盖 > XDG > ~/.local。

    生产部署可通过 ZW_BRAIN_AUDIT_DB_PATH 指向运维挂载的 volume，单测
    用 in-memory (":memory:") 或临时文件目录。
    """
    explicit = os.environ.get(_DEFAULT_AUDIT_DB_ENV)
    if explicit:
        return Path(explicit)
    home = Path.home() / ".local" / "share" / "zw-brain"
    return home / "audit.db"


# ---------------------------------------------------------------------------
# AuditEvent (mirror of zw_brain.shared.audit.AuditEvent — duplicated here
# to keep store.py importable without circular dep)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StoredAuditEvent:
    """从 SQLite 回读出的事件结构。

    与 __init__.AuditEvent 字段对齐，但是 frozen 且 occurred_at 一定是 datetime。
    """

    request_id: str
    actor: str
    skill_id: str
    tenant_id: str
    audit_class: str
    event_type: str
    phase: str
    occurred_at: datetime
    payload: dict[str, Any]


# ---------------------------------------------------------------------------
# AuditStore
# ---------------------------------------------------------------------------


# `post_persist_hook` 签名：拿到已正规化的 StoredAuditEvent，返回 None；
# 错误由 store 自己 swallow（不影响业务落库；hook 是 E6 区块链锚定的入口，
# 详见架构 D4 「区块链锚定通过可插拔 adapter 异步执行」）。
PostPersistHook = Callable[[StoredAuditEvent], None]


class AuditStore:
    """同步、可重入、按需建表的 SQLite 审计 store。"""

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS audit_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            actor TEXT NOT NULL,
            skill_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            audit_class TEXT NOT NULL,
            event_type TEXT NOT NULL,
            phase TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            outcome TEXT,
            has_error INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS ix_audit_event_request_id ON audit_event(request_id);
        CREATE INDEX IF NOT EXISTS ix_audit_event_actor_time ON audit_event(actor, occurred_at);
        CREATE INDEX IF NOT EXISTS ix_audit_event_skill_time ON audit_event(skill_id, occurred_at);
        CREATE INDEX IF NOT EXISTS ix_audit_event_tenant_time ON audit_event(tenant_id, occurred_at);
        CREATE INDEX IF NOT EXISTS ix_audit_event_class_time ON audit_event(audit_class, occurred_at);
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        post_persist_hook: PostPersistHook | None = None,
    ) -> None:
        if path is None:
            path = default_audit_db_path()
        # ":memory:" 是 sqlite3 内存模式；其他都视为文件路径
        self._path_repr = str(path)
        if self._path_repr != ":memory:":
            p = Path(self._path_repr)
            p.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # 用单连接 + lock 保证 in-memory 模式下数据可见性（多连接 in-memory
        # 各自独立）；文件模式下也避免高频建连。
        self._conn = sqlite3.connect(
            self._path_repr,
            check_same_thread=False,
            isolation_level=None,  # autocommit；我们手动控制事务边界
        )
        self._conn.executescript(self._SCHEMA)
        self._migrate_materialized_columns()
        self._post_persist_hook = post_persist_hook

    # -------- write path --------

    def _migrate_materialized_columns(self) -> None:
        """outcome/has_error 物化列迁移 + 一次性回填（存量审计库）。

        异常扫描此前在查询时对每行 payload（实测累积库平均 ~68KB、极值 17MB）做
        json_extract——0604 试用「查审计 9 秒」的最终根因。物化为真实列后查询零
        JSON 解析；回填只在升级后首次打开时发生一次。
        """
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(audit_event)")}
        altered = False
        if "outcome" not in cols:
            self._conn.execute("ALTER TABLE audit_event ADD COLUMN outcome TEXT")
            altered = True
        if "has_error" not in cols:
            self._conn.execute(
                "ALTER TABLE audit_event ADD COLUMN has_error INTEGER NOT NULL DEFAULT 0"
            )
            altered = True
        if altered:
            self._conn.execute(
                "UPDATE audit_event SET "
                "outcome = json_extract(payload_json, '$.outcome'), "
                "has_error = (json_extract(payload_json, '$.error') IS NOT NULL)"
            )
            self._conn.commit()

    def append(self, event: StoredAuditEvent | AuditEventLike) -> StoredAuditEvent:
        """同步写一条事件，失败 raise AuditWriteError。

        入参可以是 StoredAuditEvent 或 __init__.AuditEvent（duck-typed：只要
        有 request_id/actor/skill_id 三个必填属性即可）。

        正规化策略：
          - audit_class 走 normalize_audit_class
          - 原 audit_class 写到 payload[original_audit_class]
          - occurred_at 若缺省，置当前 UTC
          - tenant_id 缺省 → "sd-default"（与 runtime_tenant 一致；store 不
            直接 import runtime_tenant 以避免循环依赖）
        """
        request_id = getattr(event, "request_id", "") or ""
        actor = getattr(event, "actor", "") or ""
        skill_id = getattr(event, "skill_id", "") or ""
        if not request_id or not actor or not skill_id:
            raise AuditWriteError(
                "audit_event missing required fields (request_id/actor/skill_id)"
            )
        phase = getattr(event, "phase", "") or ""
        raw_payload = getattr(event, "payload", None) or {}
        if not isinstance(raw_payload, dict):
            raise AuditWriteError("audit_event payload must be a dict")
        payload = dict(raw_payload)

        raw_audit_class = getattr(event, "audit_class", None) or payload.get("audit_class")
        normalized = normalize_audit_class(raw_audit_class)
        if raw_audit_class and raw_audit_class != normalized:
            payload.setdefault("original_audit_class", raw_audit_class)

        tenant_id = getattr(event, "tenant_id", None) or payload.get("tenant_id") or "sd-default"
        event_type = getattr(event, "event_type", None) or payload.get("event_type") or "capability_call"
        occurred_at = getattr(event, "occurred_at", None) or datetime.now(UTC)
        if not isinstance(occurred_at, datetime):
            raise AuditWriteError("audit_event occurred_at must be a datetime")

        stored = StoredAuditEvent(
            request_id=request_id,
            actor=actor,
            skill_id=skill_id,
            tenant_id=tenant_id,
            audit_class=normalized,
            event_type=event_type,
            phase=phase,
            occurred_at=occurred_at,
            payload=payload,
        )

        try:
            payload_text = json.dumps(payload, default=str, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise AuditWriteError(f"audit_event payload not JSON-serializable: {exc}") from exc

        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO audit_event(
                        request_id, actor, skill_id, tenant_id, audit_class,
                        event_type, phase, occurred_at, payload_json,
                        outcome, has_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stored.request_id,
                        stored.actor,
                        stored.skill_id,
                        stored.tenant_id,
                        stored.audit_class,
                        stored.event_type,
                        stored.phase,
                        stored.occurred_at.isoformat(),
                        payload_text,
                        payload.get("outcome") if isinstance(payload.get("outcome"), str) else None,
                        1 if payload.get("error") is not None else 0,
                    ),
                )
            except sqlite3.Error as exc:
                # 写失败硬熔断（D4）。绝不 swallow。
                raise AuditWriteError(f"audit store write failed: {exc}") from exc

        if self._post_persist_hook is not None:
            # 区块链锚定钩子，错误吞掉避免阻塞业务（D4 「外链 down 不阻塞业务」），
            # 但需要 stderr 留痕便于排查。E6 / M0 实装时建议同时写 anchor_outbox。
            try:
                self._post_persist_hook(stored)
            except Exception as exc:  # noqa: BLE001  # D4 「外链 down 不阻塞」明确允许此处不再 raise
                import sys
                print(
                    f"[audit-store] post_persist_hook raised (non-fatal, will retry async): {exc}",
                    file=sys.stderr,
                )
        return stored

    # -------- read path --------

    def query(
        self,
        *,
        actor: str | None = None,
        skill_id: str | None = None,
        tenant_id: str | None = None,
        audit_class: str | None = None,
        request_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 200,
    ) -> list[StoredAuditEvent]:
        """按常用维度查询审计事件，按 occurred_at 升序返回。

        F2 audit.event.query / audit.event.replay capability 会基于这个接口
        实装。F1 仅暴露 Python 调用。
        """
        clauses: list[str] = []
        params: list[Any] = []
        if actor is not None:
            clauses.append("actor = ?")
            params.append(actor)
        if skill_id is not None:
            clauses.append("skill_id = ?")
            params.append(skill_id)
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if audit_class is not None:
            clauses.append("audit_class = ?")
            params.append(normalize_audit_class(audit_class))
        if request_id is not None:
            clauses.append("request_id = ?")
            params.append(request_id)
        if since is not None:
            clauses.append("occurred_at >= ?")
            params.append(since.isoformat())
        if until is not None:
            clauses.append("occurred_at <= ?")
            params.append(until.isoformat())

        sql = "SELECT request_id, actor, skill_id, tenant_id, audit_class, event_type, phase, occurred_at, payload_json FROM audit_event"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY occurred_at ASC, id ASC"
        if limit and limit > 0:
            sql += " LIMIT ?"
            params.append(int(limit))

        with self._lock:
            rows: Iterable[tuple] = list(self._conn.execute(sql, params))

        out: list[StoredAuditEvent] = []
        for row in rows:
            (
                request_id_v,
                actor_v,
                skill_id_v,
                tenant_id_v,
                audit_class_v,
                event_type_v,
                phase_v,
                occurred_at_v,
                payload_json_v,
            ) = row
            try:
                payload = json.loads(payload_json_v) if payload_json_v else {}
            except json.JSONDecodeError:
                payload = {"_corrupt_payload": True, "raw": payload_json_v}
            out.append(
                StoredAuditEvent(
                    request_id=request_id_v,
                    actor=actor_v,
                    skill_id=skill_id_v,
                    tenant_id=tenant_id_v,
                    audit_class=audit_class_v,
                    event_type=event_type_v,
                    phase=phase_v,
                    occurred_at=datetime.fromisoformat(occurred_at_v),
                    payload=payload,
                )
            )
        return out

    def query_outcome_rows(
        self,
        *,
        tenant_id: str | None = None,
        audit_class: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 10000,
    ) -> list[tuple[str, str, str, str, str, str | None, int]]:
        """轻量行查询 — (request_id, actor, skill_id, tenant_id, phase, outcome, has_error)。

        异常扫描（audit.event.anomaly）三条规则只消费这五个字段；此前走 ``query()``
        把上万条 payload 全量 ``json.loads``（实测 10k 行 ≈ 2.4s，且随审计累积线性
        恶化——0604 试用「查审计页 9 秒」根因）。outcome 用 SQLite ``json_extract``
        在 SQL 侧取出，**不水合 payload**，扫描成本回到毫秒级。
        """
        clauses: list[str] = []
        params: list[Any] = []
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if audit_class is not None:
            clauses.append("audit_class = ?")
            params.append(normalize_audit_class(audit_class))
        if since is not None:
            clauses.append("occurred_at >= ?")
            params.append(since.isoformat())
        if until is not None:
            clauses.append("occurred_at <= ?")
            params.append(until.isoformat())
        sql = (
            "SELECT request_id, actor, skill_id, tenant_id, phase, "
            "outcome, has_error FROM audit_event"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY occurred_at ASC, id ASC"
        if limit and limit > 0:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self._lock:
            return list(self._conn.execute(sql, params))

    def count(self) -> int:
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) FROM audit_event")
            return int(cur.fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -------- introspection --------

    @property
    def path(self) -> str:
        return self._path_repr


# ---------------------------------------------------------------------------
# default store singleton (lazy)
# ---------------------------------------------------------------------------


_default_store: AuditStore | None = None
_default_store_lock = threading.Lock()


def get_default_store() -> AuditStore:
    """Lazy 单例。"""
    global _default_store
    with _default_store_lock:
        if _default_store is None:
            _default_store = AuditStore()
        return _default_store


def set_default_store(store: AuditStore | None) -> None:
    """主要供测试用：替换或清空 default store。"""
    global _default_store
    with _default_store_lock:
        if _default_store is not None and _default_store is not store:
            try:
                _default_store.close()
            except Exception:  # noqa: BLE001
                pass
        _default_store = store


# Duck-typed protocol marker for `append()` 入参；不强制 import 避免循环依赖。
AuditEventLike = Any  # type: ignore[assignment]
