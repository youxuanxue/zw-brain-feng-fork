"""alembic env — D58（反转 D23；docs/decisions/alembic-migration-reintroduction-D58.md）.

target_metadata = Base.metadata（zw_brain.shared.db.Base）；URL 取
zw_brain.shared.db.get_database_url()（ZW_BRAIN_DATABASE_URL 注入），
绝不从 alembic.ini 读硬编码连接串（配置走环境变量）。offline + online 都配。

注意：导入 zw_brain.domain.models 是**必需副作用** —— 它把全部 75 张表注册到
Base.metadata，否则 autogenerate / create_all 只看到空 metadata。

后端 PG-only：alembic 直接对 PostgreSQL 跑原生 ALTER，不需要 SQLite 的 batch 重建模式。
"""
from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

# 副作用导入：注册全部 ORM 表到 Base.metadata（不可删，删了 autogenerate 看不到表）。
import zw_brain.domain.models  # noqa: F401
from alembic import context
from zw_brain.shared.db import Base, get_database_url

config = context.config

# 运行时注入真实 URL（环境变量优先），覆盖 alembic.ini 的空 sqlalchemy.url。
config.set_main_option("sqlalchemy.url", get_database_url())

# disable_existing_loggers=False 关键：默认 True 会在每次迁移（含 ensure_runtime_schema
# 经 command.upgrade 加载本 env）把进程内已存在的 zw_brain.* logger 全部 disabled，
# 污染后续测试 / 运行时日志（capture_zw_logs 捕获不到 → StopIteration）。迁移只需 alembic
# 自己的格式化器，绝不该殃及他人 logger。
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """以 URL（不建连接）方式生成 SQL —— offline 模式。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """建连接后跑迁移 —— online 模式。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
