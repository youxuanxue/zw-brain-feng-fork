"""Audit event persistent store (PostgreSQL-backed, sync, fail-fast).

Goal-id e4-b1-agentruntime F1。落在 zw_brain/shared/audit/store.py 而不是
复用 shared/database_store.py 的目的是：

  1. 审计是 D4 强约束「不允许无审计落库」的硬熔断点，需要一条
     独立、最小依赖、不被业务 schema 演进牵连的写路径。
  2. shared/database_store.py 上面挂了 15+ 业务 repository，引入循环依赖
     会让 audit.* capability / 推理 client 的纯净测试很难拉起。
  3. store 用一条独立 PG schema（默认 ``audit``）承载审计表，支持独立
     查询/回放/dashboards（F2 / F3 会消费 ``index.query``），不与主库的业务
     ORM 表（public schema）schema 演进绑定。

PG 迁移（全盘去 SQLite）：
  - 原生 sqlite3 → raw psycopg（不进 ORM，守 D4 去耦合 + 避循环依赖）；
  - 审计表落同一 PG 实例的独立 ``audit`` schema（连接复用主库 DSN，
    从 ``get_database_url()`` 解析 host/port/db/user/password）；
  - ``INTEGER PRIMARY KEY AUTOINCREMENT`` → ``BIGINT GENERATED ALWAYS AS IDENTITY``；
    ``?`` 占位 → ``%s``；``PRAGMA table_info`` → ``information_schema.columns``；
    ``json_extract(col,'$.k')`` → ``(payload_json::jsonb)->>'k'``；
  - 公共 API 签名一字不改（``AuditStore`` / ``StoredAuditEvent`` /
    ``AuditWriteError`` / ``get_default_store`` / ``set_default_store`` /
    ``query`` / ``query_outcome_rows`` / ``count`` / ``append``）。``path`` 入参
    保留（不破签名）但不再派生 schema——审计永远落同一条 ``audit`` schema，
    测试隔离交给 per-test PG 库克隆（conftest CREATE DATABASE TEMPLATE，每测一条
    空 audit schema）。需要并存多条 schema 的运维场景可显式传 ``schema=``。

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
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.conninfo import make_conninfo
from sqlalchemy.engine import make_url

from zw_brain.shared.db import get_database_url

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
# storage location（PG schema，env 覆盖）
# ---------------------------------------------------------------------------


# 环境变量：审计 schema 名显式覆盖（可选）。给值即用作 schema 名字面量
# （不做 sha1 派生、不当文件路径解释）；不给则用默认 ``audit``。env 名 only，
# 不引用值。
_AUDIT_SCHEMA_ENV = "ZW_BRAIN_AUDIT_DB_PATH"

# 默认审计 schema。与主库业务 ORM 表（public）物理隔离，schema 演进互不牵连。
# 审计永远落这一条 schema；测试隔离交给 per-test PG 库克隆（每测一条空 schema）。
_DEFAULT_AUDIT_SCHEMA = "audit"


def _default_audit_schema() -> str:
    """默认审计 schema 名：env 显式覆盖 > 固定 ``audit``。"""
    return os.environ.get(_AUDIT_SCHEMA_ENV) or _DEFAULT_AUDIT_SCHEMA


# ---------------------------------------------------------------------------
# AuditEvent (mirror of zw_brain.shared.audit.AuditEvent — duplicated here
# to keep store.py importable without circular dep)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StoredAuditEvent:
    """从审计库回读出的事件结构。

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


def _audit_dsn() -> str:
    """审计连接 DSN：复用主库 DSN（同一 PG 实例），连接库即主业务库。

    审计表落该库下的独立 ``audit`` schema（与 public 业务表物理隔离），所以
    连接本身不需要单独的库——只需要一条到同实例的 psycopg 连接，建/用 schema
    由 store 自己管。从 ``get_database_url()`` 解析为 libpq DSN（去掉 SQLAlchemy
    方言前缀 ``+psycopg``）。
    """
    url = get_database_url()
    sa_url = make_url(url)
    backend = sa_url.get_backend_name()
    if backend != "postgresql":
        # 全盘去 SQLite 后，审计库必须落 PG。非 PG（如残留 sqlite 测试 URL）
        # 直接熔断——审计绝不静默降级到一条不被 D4 守护的旁路。
        raise AuditWriteError(
            f"audit store requires a PostgreSQL backend, got dialect '{backend}'"
        )
    kwargs: dict[str, Any] = {}
    if sa_url.host:
        kwargs["host"] = sa_url.host
    if sa_url.port:
        kwargs["port"] = sa_url.port
    if sa_url.database:
        kwargs["dbname"] = sa_url.database
    if sa_url.username:
        kwargs["user"] = sa_url.username
    if sa_url.password:
        kwargs["password"] = sa_url.password
    # make_conninfo 负责把含特殊字符（空格/单引号/反斜杠）的值正确转义，
    # 不再手工空格 join key=value（特殊字符会破坏 DSN 解析）。
    return make_conninfo(**kwargs)


def _quote_ident(name: str) -> str:
    """安全引用 PG 标识符（schema 名是固定常量或显式注入，此处双引号转义兜底）。"""
    return '"' + name.replace('"', '""') + '"'


class AuditStore:
    """同步、可重入、按需建 schema/表的 PostgreSQL 审计 store。

    每个 store 绑定一条独立 PG schema（默认 ``audit``）。表与索引在 schema 内
    定义（``<schema>.audit_event``）。所有读写走单条 ``psycopg`` 连接 +
    ``threading.Lock`` 串行化（与历史单连接 + 单 lock 语义一致，避免高频建连，
    并让并发线程看到一致视图）。
    """

    # 表与索引 DDL（PG 方言）。``{schema}`` 在 __init__ 里以安全引用替换；
    # 分条执行（psycopg 一条 execute 跑一条 DDL，不用 sqlite executescript）。
    _DDL_TABLE = """
        CREATE TABLE IF NOT EXISTS {schema}.audit_event (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
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
        )
    """
    _DDL_INDEXES = (
        "CREATE INDEX IF NOT EXISTS ix_audit_event_request_id ON {schema}.audit_event(request_id)",
        "CREATE INDEX IF NOT EXISTS ix_audit_event_actor_time ON {schema}.audit_event(actor, occurred_at)",
        "CREATE INDEX IF NOT EXISTS ix_audit_event_skill_time ON {schema}.audit_event(skill_id, occurred_at)",
        "CREATE INDEX IF NOT EXISTS ix_audit_event_tenant_time ON {schema}.audit_event(tenant_id, occurred_at)",
        "CREATE INDEX IF NOT EXISTS ix_audit_event_class_time ON {schema}.audit_event(audit_class, occurred_at)",
    )

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        schema: str | None = None,
        post_persist_hook: PostPersistHook | None = None,
    ) -> None:
        # path 仅作内省锚（不破 API、不再派生 schema）；审计永远落 ``audit`` schema。
        self._path_repr = str(path) if path is not None else _default_audit_schema()
        # schema 名：显式 schema 注入（运维/测试 hook）> env/默认。
        self._schema = schema if schema is not None else _default_audit_schema()
        self._qschema = _quote_ident(self._schema)
        self._lock = threading.Lock()
        try:
            self._conn = psycopg.connect(_audit_dsn(), autocommit=True)
        except psycopg.Error as exc:
            raise AuditWriteError(f"audit store connect failed: {exc}") from exc
        try:
            self._init_schema()
            self._migrate_materialized_columns()
        except psycopg.Error as exc:
            # 建 schema/表失败即审计不可用 → 硬熔断（D4）。
            raise AuditWriteError(f"audit store schema init failed: {exc}") from exc
        self._post_persist_hook = post_persist_hook

    # -------- schema / table bootstrap --------

    def _init_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self._qschema}")
            cur.execute(self._DDL_TABLE.format(schema=self._qschema))
            for ddl in self._DDL_INDEXES:
                cur.execute(ddl.format(schema=self._qschema))

    # -------- write path --------

    def _migrate_materialized_columns(self) -> None:
        """outcome/has_error 物化列迁移 + 一次性回填（存量审计库）。

        历史上异常扫描在查询时对每行 payload（实测累积库平均 ~68KB、极值 17MB）做
        json 解析——0604 试用「查审计 9 秒」的最终根因。物化为真实列后查询零
        JSON 解析；回填只在升级后首次发现列缺失时发生一次。

        PG 翻译：``PRAGMA table_info`` → ``information_schema.columns``；
        ``json_extract(payload_json,'$.k')`` → ``(payload_json::jsonb)->>'k'``。
        新建表已含 outcome/has_error 两列（见 _DDL_TABLE），此处主要兜底纳管的
        存量 schema（无这两列时补列 + 回填）。
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = 'audit_event'",
                (self._schema,),
            )
            cols = {row[0] for row in cur.fetchall()}
            altered = False
            if "outcome" not in cols:
                cur.execute(
                    f"ALTER TABLE {self._qschema}.audit_event ADD COLUMN outcome TEXT"
                )
                altered = True
            if "has_error" not in cols:
                cur.execute(
                    f"ALTER TABLE {self._qschema}.audit_event "
                    "ADD COLUMN has_error INTEGER NOT NULL DEFAULT 0"
                )
                altered = True
            if altered:
                cur.execute(
                    f"UPDATE {self._qschema}.audit_event SET "
                    "outcome = (payload_json::jsonb)->>'outcome', "
                    "has_error = CASE WHEN (payload_json::jsonb) ? 'error' "
                    "AND (payload_json::jsonb)->'error' <> 'null'::jsonb "
                    "THEN 1 ELSE 0 END"
                )

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
                    f"""
                    INSERT INTO {self._qschema}.audit_event(
                        request_id, actor, skill_id, tenant_id, audit_class,
                        event_type, phase, occurred_at, payload_json,
                        outcome, has_error
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            except psycopg.Error as exc:
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
            clauses.append("actor = %s")
            params.append(actor)
        if skill_id is not None:
            clauses.append("skill_id = %s")
            params.append(skill_id)
        if tenant_id is not None:
            clauses.append("tenant_id = %s")
            params.append(tenant_id)
        if audit_class is not None:
            clauses.append("audit_class = %s")
            params.append(normalize_audit_class(audit_class))
        if request_id is not None:
            clauses.append("request_id = %s")
            params.append(request_id)
        if since is not None:
            clauses.append("occurred_at >= %s")
            params.append(since.isoformat())
        if until is not None:
            clauses.append("occurred_at <= %s")
            params.append(until.isoformat())

        sql = (
            "SELECT request_id, actor, skill_id, tenant_id, audit_class, "
            f"event_type, phase, occurred_at, payload_json FROM {self._qschema}.audit_event"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY occurred_at ASC, id ASC"
        if limit and limit > 0:
            sql += " LIMIT %s"
            params.append(int(limit))

        with self._lock:
            try:
                rows: Iterable[tuple] = list(self._conn.execute(sql, params))
            except psycopg.Error as exc:
                raise AuditWriteError(f"audit store query failed: {exc}") from exc

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

        异常扫描（audit.event.anomaly）三条规则只消费这五个字段；历史上走 ``query()``
        把上万条 payload 全量 ``json.loads``（实测 10k 行 ≈ 2.4s，且随审计累积线性
        恶化——0604 试用「查审计页 9 秒」根因）。outcome/has_error 是物化真实列，
        **不水合 payload**，扫描成本回到毫秒级。
        """
        clauses: list[str] = []
        params: list[Any] = []
        if tenant_id is not None:
            clauses.append("tenant_id = %s")
            params.append(tenant_id)
        if audit_class is not None:
            clauses.append("audit_class = %s")
            params.append(normalize_audit_class(audit_class))
        if since is not None:
            clauses.append("occurred_at >= %s")
            params.append(since.isoformat())
        if until is not None:
            clauses.append("occurred_at <= %s")
            params.append(until.isoformat())
        sql = (
            "SELECT request_id, actor, skill_id, tenant_id, phase, "
            f"outcome, has_error FROM {self._qschema}.audit_event"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY occurred_at ASC, id ASC"
        if limit and limit > 0:
            sql += " LIMIT %s"
            params.append(int(limit))
        with self._lock:
            try:
                # has_error 在 PG 是 INTEGER 列，回读已是 int；保持与历史 tuple
                # 形态一致（第 7 位为 int），下游 pipeline_ops 失败谓词不变。
                return list(self._conn.execute(sql, params))
            except psycopg.Error as exc:
                raise AuditWriteError(f"audit store query_outcome_rows failed: {exc}") from exc

    def count(self) -> int:
        with self._lock:
            try:
                cur = self._conn.execute(
                    f"SELECT COUNT(*) FROM {self._qschema}.audit_event"
                )
                return int(cur.fetchone()[0])
            except psycopg.Error as exc:
                raise AuditWriteError(f"audit store count failed: {exc}") from exc

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -------- introspection --------

    @property
    def path(self) -> str:
        return self._path_repr

    @property
    def schema(self) -> str:
        """绑定的 PG schema 名（PG 后端下的真实落点；测试/运维内省用）。"""
        return self._schema


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
