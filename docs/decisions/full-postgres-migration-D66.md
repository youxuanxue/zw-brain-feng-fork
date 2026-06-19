# D66 — 全盘迁移 PostgreSQL，彻底移除 SQLite

- **日期**：2026-06-19
- **scope**：`full-postgres-migration`
- **门类**：架构 + 数据安全门（反转 D58 的 sqlite-coexist 立场）
- **签字**：产品研发负责人（`.testing/signoff/full-postgres-migration.signoff.yaml`，decision_only）
- **PR**：#301

## 背景 / 根因

zw-brain 此前运行时**默认 SQLite**（`.data/zw_brain.db`），PG 仅经 `ZW_BRAIN_DATABASE_URL` 可选支持、且不装驱动。D58 把冷启动 `drop_all` 换成 alembic forward-migration 时，仍保留 SQLite 作为开发/测试后端（双方言共存）。

要上生产，双方言共存有两个不可接受的后果：
1. **测量假象**：测试套件证明 SQLite，发布运行的是 PG——CI 绿 ≠ PG 能跑（撞 D11「真实库回归」精神）。
2. **真实缺陷被掩盖**：SQLite 忽略 `VARCHAR(N)` 长度约束，PG 强制——存量数据里的越长字段在 SQLite 上静默通过、到 PG 即截断报错。

## 裁决

**全盘单引擎 PostgreSQL，彻底移除 SQLite。单一引擎 = 测试即生产引擎。**

### 子决策锚点
- **D66.a 运行时 PG-only**：`get_database_url()` 仅 `ZW_BRAIN_DATABASE_URL > DEFAULT_PG_URL`；对 `sqlite://` URL 与 `ZW_BRAIN_DB_PATH` 双 **fail-closed raise**——SQLite 旋钮永不静默存活（不是「忽略」，是「拒绝」）。
- **D66.b 审计库去-sqlite3**：`shared/audit/store.py` 原生 `sqlite3` → raw psycopg，落**同一 PG 实例的独立 `audit` schema**（守 D4 审计写硬约束 + 去 ORM 耦合 + 避循环依赖）；删 path→schema 派生 / `:memory:` 死抽象。
- **D66.c 测试基建模板克隆**：`conftest.py` autouse fixture 给每个测试一个 `CREATE DATABASE … TEMPLATE` 空克隆隔离库；`tests/_pg_realistic.py` 提供真实数据模板克隆 fixture（承接旧 `require_real_seed` 跳过语义）；惰性 durable 审计 sink + 重置缓存 service（修 reject 路径 D4）。
- **D66.d 防回潮守卫**：`scripts/check_no_sqlite.py`（针对**实际使用**非注释提及：`import sqlite3` / `sqlite://` / 设 `ZW_BRAIN_DB_PATH` / 拷贝 `.db`）+ preflight 段 74；故意提及加 `# sqlite-allow:`。
- **D66.e PROD BLOCKER 修复**：`binding_code` `String(64)→128`（旧平台复合码 65–73 字符；models.py 4 列 + baseline 迁移 4 列同步）——这是 PG 揪出、SQLite 一直掩盖的真实数据截断缺陷。
- **D66.f CI 全 PG**：`test` / `legacy-import-smoke` / `e2e-measurement` 各加 `postgres:16` service；`pg-smoke` 折并。
- **say-no**：审计库不再保留 sqlite `:memory:` 兜底；不保留任何「SQLite 快速档」opt-in（删 `ZW_BRAIN_DB_PATH` sqlite 分支、`check_db_bloat.py`/`db-vacuum.sh` 等 sqlite-文件专用脚本）。

## 生产数据来源
全新库，数据 = `old/10示例数据` 下 MySQL dump，经既有 `import_legacy_dumps.py` legacy-import 直灌 PG（无存量 SQLite 要搬）。

## 验证（真 PostgreSQL）
- 全量 pytest 套件多轮 `PYTEST_EXIT=0 / 0 失败`（rebase 后 + 全仓清剿后）。
- legacy-import `old/10示例数据` 真 dump 灌 PG：verify 0 未解析 / 0 冲突、零截断；realistic 模板 catalog 1222 / application 258 / topic_package 113。
- 真 Playwright 走查 live PG 部署：**123 业务流通过**；webui `twin_browser_pages` **13 passed**（权威 `--with-e2e`，ci-scoped 产物）。
- `check_no_sqlite` 0 残留 / 936 文件；ruff 全过；preflight PASS。

## 影响面
- 本地/CI 跑测试从此**强依赖 PG 在线**（`docker compose up -d postgres`）——零依赖 sqlite 快速档的能力消失，是「全 PG」的既定代价。
- 对运行产品行为：单引擎 PG；流程/状态机/角色语义零变更（纯后端引擎切换 + 测试基建）。
