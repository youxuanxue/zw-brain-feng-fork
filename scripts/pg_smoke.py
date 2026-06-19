#!/usr/bin/env python3
"""真 PostgreSQL 冲烟：证「默认 PG 后端」真能被 alembic 建表 + seed 驱动。

为什么存在：默认后端切到 PG 后（zw_brain/shared/db.py DEFAULT_PG_URL），单测/CI 仍跑
SQLite——若不另起一条真 PG 道，发布运行的 PG 路径将从未被任何测量触达（测量假象，
撞 D11 真库回归）。本脚本对一个真实 PG 实例跑端到端最小闭环：

  1. ensure_runtime_schema() → alembic upgrade head（建全部 ORM 表 + alembic_version）；
  2. 反射出的表集合 ⊇ Base.metadata 全表（schema 与模型一致，非硬编码 75）；
  3. DatabaseStore().load_runtime_state() 在空库返回非空 seed（seed_snapshot 落得进 PG）。

任一不满足即非零退出。连接来自 get_database_url()——调用方须先把 ZW_BRAIN_DATABASE_URL
指向 PG（CI 由 postgres service 注入；本地 `docker compose up -d postgres` 后留空即默认 PG）。
"""
from __future__ import annotations

import sys

from sqlalchemy import create_engine, inspect

# 副作用导入：把全部 ORM 表注册进 Base.metadata（否则 metadata 为空，断言失真）。
import zw_brain.domain.models  # noqa: F401
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.db import Base, get_database_url
from zw_brain.shared.migrate import ensure_runtime_schema


def main() -> int:
    url = get_database_url()
    if not url.startswith(("postgresql://", "postgresql+")):
        print(f"[pg-smoke] FAIL: 解析出的 DB URL 不是 PostgreSQL：{url.split('@')[-1]}", file=sys.stderr)
        print("[pg-smoke] hint: 设 ZW_BRAIN_DATABASE_URL 指向 PG，或本地 docker compose up -d postgres 后留空 env", file=sys.stderr)
        return 2

    print(f"[pg-smoke] target: {url.split('@')[-1]} (psycopg)")

    # 1. 建 schema（真 alembic upgrade head 对 PG）。
    ensure_runtime_schema()
    print("[pg-smoke] ok: ensure_runtime_schema() 完成（alembic upgrade head）")

    # 2. 反射表集合 ⊇ ORM metadata 全表 + alembic_version 在位。
    engine = create_engine(url, future=True)
    try:
        actual = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    expected = set(Base.metadata.tables.keys())
    missing = expected - actual
    if missing:
        print(f"[pg-smoke] FAIL: PG 缺 {len(missing)} 张 ORM 表，例如 {sorted(missing)[:5]}", file=sys.stderr)
        return 1
    if "alembic_version" not in actual:
        print("[pg-smoke] FAIL: alembic_version 表缺失（未 stamp/upgrade）", file=sys.stderr)
        return 1
    print(f"[pg-smoke] ok: {len(expected)} 张 ORM 表全部建立 + alembic_version 在位")

    # 3. seed 能落进 PG（空库 load 返回非空快照）。
    state, _ui = DatabaseStore().load_runtime_state()
    if not state:
        print("[pg-smoke] FAIL: load_runtime_state() 返回空，seed 未落 PG", file=sys.stderr)
        return 1
    print(f"[pg-smoke] ok: seed 落库，runtime_state 含 {len(state)} 个顶层键")

    print("[pg-smoke] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
