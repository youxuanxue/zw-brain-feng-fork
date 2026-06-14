---
title: alembic 迁移回归 + 冷启动不再 DROP（反转 D23 二次升级 / drop_all+create_all 退役）
scope: alembic-migration-reintroduction
status: approved  # 架构门：反转 D23「alembic 整体删除 / 冷启动 drop&recreate」，产品研发负责人 sign-off 已签（薛娇 2026-06-14；D28 GATE 元规则不适用——本条属架构/数据安全门，非角色/流程/状态机；账本 .testing/signoff/alembic-migration-reintroduction.signoff.yaml）
date: 2026-06-14
deciders: 海若产品部产品研发负责人（架构 + 数据安全门）
authors:
  - Claude Opus 4.8 (1M context) — 乔布斯式产品专家 + 高级系统架构师（worktree 设计与实现）
related_docs:
  - docs/approved/zw-brain-architecture.md   # §9.6 schema 生命周期（drop_all+create_all 基线）
  - docs/deployment/docker-image-deployment.md
  - docs/deployment/sd-default-onboarding.md
  - docs/deployment/m0-site-migration.md
  - docs/decisions/data-model-referential-integrity-design.md   # D48：永不留孤儿行；schema 强一致性同源诉求
related_code:
  - zw_brain/shared/migrate.py        # ensure_runtime_schema / run_migrations / stamp_baseline_if_legacy / reset_and_upgrade
  - alembic/env.py + alembic/versions/*_baseline.py
  - tests/test_alembic_migration_d58.py
reverses:
  - D23  # GATE-1.1：「alembic 整体删除（全新项目不背历史兼容，drop&recreate）」
---

# alembic 迁移回归 + 冷启动不再 DROP

> 研发阶段：**设计 + 实现（一个 PR / 多 commit）**，停在 `[人工审批]` 门禁前。
> D23（2026-05-20 二次升级）当年把 alembic 整体删除、schema 生命周期定为
> `Base.metadata.drop_all + create_all`：**任何 schema 漂移即 DROP 全表重建**。理由是
> "全新项目不背历史兼容"。本方案**反转这条 approved 基线决策** —— 一旦有**生产试用
> 数据**，"漂移即 DROP" 就是数据丢失风险，必须用 alembic 向前迁移取代。属**架构 + 数据
> 安全门**，须产品研发负责人 sign-off 才进 D-编号、相关测试才由 InTest 转 Done。

## 〇·乔布斯审视与收敛（聚焦 / 简洁 / 端到端 / 设计即工作方式 / 精品意识）

D23 的 `drop_all+create_all` 在"全新项目、库里没数据"时是**对的简洁**。问题出在它不区分
"空库"和"有真实试用数据的存量库"——同一条代码路径，对前者是无害重建，对后者是**静默清库**。

按五原则收敛：

1. **聚焦** —— 真正要保护的是**生产试用库的数据**。不追求 alembic 列级完美 diff、不引入复杂
   迁移链。本期 baseline 只需 `upgrade=建全部 75 表`（== `create_all`）、`downgrade=drop 全部`，
   把"漂移即 DROP"这条数据丢失路径堵死。
2. **简洁** —— 不把"SQLite 能不能 ALTER""autogenerate 漏不漏列"抛给运维。架构层自己收敛成
   **四态分支**（空库 / 已纳管 / 存量库 / 真漂移），运维只需知道"存量库永不被 DROP"。
3. **端到端** —— 覆盖三种真实部署形态：开发态（仓根 alembic.ini）、wheel 安装态（force-include 到
   `zw_brain/_migrations/`）、迁移批 `--reset-db`（显式重置）。三态都能定位 alembic、行为一致。
4. **设计即工作方式** —— 破坏性重置**不再是默认路径**，而是**显式开关**：`reset_and_upgrade()`
   闸在 `ZW_BRAIN_ALLOW_SCHEMA_RESET=1` 之后（仿 `DevBypassInProductionError` 的 M5 fail-closed
   姿态）。想清库必须显式承认，手滑不会清库。
5. **精品意识** —— **拒启优于清库**。生产模式检测到真实漂移、且无迁移可向前应用时，
   `ensure_runtime_schema()` **raise `SchemaDriftError` 拒绝启动**，把问题暴露给运维（补迁移
   或显式 reset），绝不静默 DROP。要么安全迁移，要么诚实拒启，没有第三种。

**负责人只需拍两件事**：
- **① 反转 D23**：是否批准把 schema 生命周期从 `drop_all+create_all` 改为 alembic
  forward-migration（baseline stamp → upgrade head），存量库零 DDL、绝不 DROP。
- **② fail-closed 姿态**：是否接受"真实漂移无迁移可上 → 拒启而非清库"、"破坏性重置须显式
  `ZW_BRAIN_ALLOW_SCHEMA_RESET=1`"作为本期数据安全上限。

---

## 一·背景与真实锚定

- D23（CLAUDE.md 决策索引 / 2026-05-20 二次升级）："旧 R1-R8 角色矩阵退役 → ……二次升级：
  **alembic 整体删除**（全新项目不背历史兼容，drop&recreate）+ policy 启动检查 + grep 双兜底"。
- 配套硬约束：preflight 段 20 `no-retired-features` 守卫含 5 条 anti-alembic 正则
  （`from/import alembic`、`alembic upgrade/config/command`），防 alembic 回潮。
- `zw_brain/shared/migrate.py` `ensure_runtime_schema()` 原实现：校验 `REQUIRED_TABLES` /
  `REQUIRED_COLUMNS`，**不齐即 `reset_and_upgrade()`（drop 全表 + create_all）**。
- 触发反转的真实风险：项目已进入**生产试用**（MEMORY: `sd-default` 单租户、真实库回归、
  customer_acceptance 走查），库里是脱敏后的真实业务数据。任何一次模型 schema 不向后兼容
  变更（加列/改列）都会触发 reset → **整库清空**。D48（参照完整性"永不留孤儿行")已表明项目
  对数据安全的强诉求；"漂移即 DROP"与之同源冲突。

---

## 二·核心架构决策：alembic forward-migration 四态分支

`ensure_runtime_schema()` 重写为四态（`zw_brain/shared/migrate.py`），**绝不再调
`reset_and_upgrade()`**：

| 库状态 | 判据 | 动作 |
| --- | --- | --- |
| **已纳管** | 有 `alembic_version` 表 | `run_migrations()`（`alembic upgrade head`，幂等续迁） |
| **空库** | 无版本表 + 除 `alembic_version` 外无任何业务表 | `run_migrations()`（建全部 75 表） |
| **存量库** | 无版本表 + 有数据 + schema 与当前模型一致 | `stamp_baseline_if_legacy()`（`alembic stamp <baseline>`，**零 DDL、保数据**）→ `upgrade head` |
| **真漂移** | 无版本表 + 有数据 + schema 与模型**不一致** | **raise `SchemaDriftError` 拒启**（绝不 DROP；正确路径=补迁移再 upgrade head） |

- `BASELINE_REVISION = 77da8251e66d`（`alembic/versions/*_baseline.py`）：对空临时库 autogenerate，
  `upgrade=create 全部 75 表`、`downgrade=drop 全部`，与 `Base.metadata.create_all` 等价（实测
  upgrade head 后表集合 == `Base.metadata.tables`，76 含 `alembic_version`）。SQLite 细节不追列级
  完美 diff（任务注记），baseline 只保 create/drop 全表语义。
- `_schema_matches_baseline()` 复用既有 `REQUIRED_TABLES` / `REQUIRED_COLUMNS` 反射校验判定
  "存量库 schema 是否与模型一致"，从而安全区分"可 stamp 的存量库"与"真漂移"。

## 三·破坏性重置：显式开关 + M5 fail-closed

- `reset_and_upgrade()`（`drop_all` + `alembic upgrade head`）**保留**，但闸在
  `ZW_BRAIN_ALLOW_SCHEMA_RESET=1` 之后；否则 raise `SchemaResetForbiddenError`（仿
  `DevBypassInProductionError` 的 M5 fail-closed 姿态）。
- 唯一仍合法的显式重置入口 = 迁移批 `migration_batch.py --reset-db` 路径：该路径在调用前
  显式 `os.environ["ZW_BRAIN_ALLOW_SCHEMA_RESET"] = "1"`（开发态 rebuild / M0 全新现场）。
- 自动冷启动路径（`runtime.py:69` 的 `ensure_runtime_schema()`）**永不**触达 reset。

## 四·部署形态兼容（三态都能定位 alembic）

- **开发态**：`alembic.ini` + `alembic/` 在仓根；`alembic` CLI 与 `migrate.py` 都用仓根。
- **wheel 安装态**（生产 docker，`uv pip install *.whl` 后从 site-packages 跑 `zw-brain-rest`）：
  `pyproject.toml` `force-include` 把 `alembic.ini`/`alembic/` 打到 `zw_brain/_migrations/`；
  `migrate._resolve_alembic_paths()` **优先 package 内、回落仓根**，两端 `run_migrations()` 都能定位。
  （实测 wheel 内含 `zw_brain/_migrations/{alembic.ini,alembic/env.py,alembic/versions/*_baseline.py}`。）
- `alembic>=1.13` 已加入 `pyproject.toml` `dependencies`（运行时依赖，非 dev-only）。

## 五·守卫与文档同步

- preflight 段 20 `no-retired-features`：**移除** 5 条 anti-alembic 正则（alembic 回归，反转 D23）；
  K12 dashboard 退役守卫**保留不动**。`/alembic/` 加入 `RETIRED_SKIP`（迁移工件不参与回潮扫描）。
- 部署文档（`docker-image-deployment` / `sd-default-onboarding` / `m0-site-migration`）：把
  "drop_all+create_all / alembic 不进入产品基线"改写为"alembic baseline stamp → upgrade head；
  存量库不 DROP；破坏性重置仅显式开关"。
- CLAUDE.md 决策索引补 D58 一行（≤900 字符，指针指本文）；"已退役资产禁回潮"速查里 alembic
  从退役清单移出（K12 大屏 / R1-R8 角色矩阵仍在）。

## 六·验证（隔离临时库）

`tests/test_alembic_migration_d58.py` 7 测全绿（main `.venv` py3.13 + alembic 1.18）：
(a) 空库 `ensure_runtime_schema` → 全部 75 表 + `alembic_version` 建好；
(b) 灌真实数据的存量库（无版本表）→ stamp baseline 后**数据仍在**、版本号 = baseline；
(c) prod 模式 `reset_and_upgrade()` 无 ALLOW env → raise `SchemaResetForbiddenError`；
    + 显式 ALLOW env → 真 drop&rebuild 不报错；
(d) `upgrade head` / `ensure_runtime_schema` 幂等（重复调用表集合不变、不动已有数据）；
补：真漂移（无版本表 + 有数据 + schema 不一致）→ raise `SchemaDriftError`、数据原封不动。

---

## 七·待人工审批事项（产品研发负责人 sign-off 清单）

1. **反转 D23**：schema 生命周期从 `drop_all+create_all` 改为 alembic forward-migration
   （baseline stamp → upgrade head），存量库零 DDL、绝不 DROP。（架构 + 数据安全门）
2. **fail-closed 姿态**：真实漂移无迁移可上 → 拒启（`SchemaDriftError`）而非清库；破坏性重置
   `reset_and_upgrade()` 须显式 `ZW_BRAIN_ALLOW_SCHEMA_RESET=1`（M5 fail-closed）。
3. **baseline 口径**：本期 baseline 只保 create/drop 全表语义（不追 SQLite 列级完美 diff）；后续
   真正的 schema 演进逐条加 alembic 向前迁移。
4. **依赖与打包**：`alembic>=1.13` 入运行时依赖，迁移工件随 wheel 打包到 `zw_brain/_migrations/`。

> 签字落 `.testing/signoff/alembic-migration-reintroduction.signoff.yaml`（`decision_only: true`，
> `covers: []` —— 本条不抬任何 `.feature` 状态，是架构/数据安全的产品判断）。登记为 D58
> （CLAUDE.md 决策索引）。
