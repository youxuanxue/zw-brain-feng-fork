---
title: 数据模型参照完整性设计方案（B-高 零外键 / catalog_entry 收录 / 凭据建模 / schema 覆盖）
scope: data-model-referential-integrity
status: approved  # Gate-1 原型设计 + Gate-2 功能实现/效果验收均经产品研发负责人 sign-off（D48，2026-06-03）
date: 2026-06-03
deciders: 海若产品部产品研发负责人（架构决策门）
authors:
  - Claude Opus 4.8 (1M context) — 高级系统架构师（worktree 原型设计）
related_docs:
  - docs/approved/zw-brain-architecture.md
  - docs/approved/zw-brain-data-model.md
  - docs/decisions/e3-f9-topicpackage-business-review-package.md
  - docs/preflight-debt.md
related_prototype: docs/prototypes/data_model_integrity_prototype.py
---

# 数据模型参照完整性设计方案

> 研发阶段：**原型设计**。本文是设计产出 + 可运行 PoC（`docs/prototypes/data_model_integrity_prototype.py`），
> **未改动生产模型为最终态**，停在 `[人工审批]` 门禁前。进入功能实现前需产品研发负责人 sign-off
> 「待人工审批事项」清单中的架构决策。
>
> **本文已经乔布斯审视收敛（2026-06-03）**：原方案的 5 条工程选择题压成「1 个产品保证 + 1 个数据现实确认」，
> 功能开发从完整性方案中剥离，机械守卫升为脊柱。审视全文见 §〇·乔布斯审视。

## 〇·乔布斯审视与收敛（聚焦 / 简洁 / 端到端 / 设计即工作方式 / 精品意识）

原架构方案工程扎实、核实证据可信，但有四处「工程师视角」违背乔布斯哲学，本次按五原则收敛：

1. **聚焦**——原 §三把 `catalog.entry.detail` capability + 目录补录可检索 + 补 UNIQUE 混进"修完整性"。那是 **J1 找数→用数的功能**，不是参照完整性。本方案**只拥有完整性那一半**（删包/删目录时悬挂 ref 的守卫 + package 维度可选 CASCADE）；可检索补录 + 详情页**剥离回 J1 立项**（debt `catalog-entry.debt.yaml` 的 trigger 本就在那）。
2. **简洁**——原 §2.3 把 SQLite「父码非 UNIQUE → FK 建不出」当成选择题抛给负责人。负责人不需要懂 SQLite。**架构层自己收敛**：统一原则 = *每条父子边引用父表 surrogate `id`，子表一律 FK 到 `id`*。C 类边的病根是子表用业务码引用——把引用列改为父 `id`，三类边坍缩成一类，不必给业务码补 UNIQUE 迁就（详见收敛后的 §二）。
3. **端到端**——完整性用「用户看到什么」重述：孤儿子行 = 用户点开交付/目录详情，指向一条已删的审批单/目录 → **死链、幽灵数据**。保证必须**对用户不可见且完整**，不是「12 条 FK + 5 条守卫 + 7 条待定」的拼图。
4. **精品意识**——拒绝「先守卫、UNIQUE 待定」的 27% 覆盖率复发。**要么保证无孤儿，要么不保证**。即便 FK 未全覆盖，CI 孤儿守卫必须对**所有边**生效——保证才完整。故守卫不是审批项 #5，是**方案脊柱**（§六）。

**收敛后负责人只需拍两件事**（不再是 5 条工程选择题）：
- **① 一个产品保证**：「zw-brain 永不留孤儿行——删父级联或拒绝，由系统机制强制，不靠开发者纪律」是否批准为硬约束（机制由架构层定：能建 FK 处 FK+CASCADE，建不出处统一删除编排 + CI 孤儿守卫全边兜底）。
- **② 一个数据现实**：旧平台同租户内 `application_code`/`delivery_code`/`catalog_code` 是否唯一（决定子表引用列收敛到父 `id` 的写入侧改造范围，见 §二·收敛）。

> 缺陷 2（凭据）/ 缺陷 3（schema 覆盖）维持架构师裁决：**记债暂停**，本节不改（见 §四 / §五）。它们是"明确不做并说明"，非本方案主体。

## 〇、结论先行（4 缺陷裁决）

| 缺陷 | 级别 | 裁决 | 一句话 |
| --- | --- | --- | --- |
| 1 零外键约束 | B-高 | **已落地（M1 FK + M3 守卫）；C 类 honest 降级守卫兜底** | A 类 12 + B 类 5（复合）= 17 条边已建 FK + ON DELETE CASCADE（M1）。C 类 9 条边（含 [06-03 amendment] 补 catalog_item/delivery_subscription.resource_code 两条原裸奔软引用边）经 M2 写入侧核实：父行写子时不保证存在（实证 receipt 父可缺位）→ NOT-NULL FK 不可行、nullable FK 零强制收益，**honest 降级为 M3 孤儿守卫登记边兜底**（§2.5；覆盖=常量登记边集合非 schema 全反射）。 |
| 4 catalog_entry 引用完整性 | B-中 | **设计-only 待审批（已聚焦）** | 本方案**只管完整性**：删包/删目录时悬挂 ref 走应用层守卫（多态 ref 无法单建 SQL FK）。**可检索补录 + `catalog.entry.detail` 详情页剥离回 J1 立项**，不在本方案。 |
| 2 凭据未建模为实体 | B-中 | **记债暂停（上游缺供 + 业务待确认，D47.a）** | 真凭据在网关域 `dsp_service.api_service_app.SECRET`、与 apply_id 无绑定供数；只产出 schema-readiness 设计，**禁实现、禁捏造**。 |
| 3 resource_schema_mapping 覆盖率 27% | B-中 | **记债暂停（上游缺供）** | 已核实读路径桥接就绪、补数自动放大，**无需改码**，等上游补 schema dump。 |

---

## 一、现状核实证据（只读探索）

### 1.1 共同事实

- `zw_brain/domain/models.py`：**71 张表，metadata ForeignKey 命中 = 0**（`.venv/bin/python` 反射 `Base.metadata` 实测，grep `ForeignKey` 亦 0）。
- ORM = SQLAlchemy 2.0（`Mapped` / `mapped_column`），后端默认 SQLite（`sqlite:///.data/zw_brain.db`，可经 `ZW_BRAIN_DATABASE_URL` 覆盖）。
- `zw_brain/shared/db.py:46` 已在每条 SQLite 连接上 `PRAGMA foreign_keys=ON` —— **开关已开，但没有任何 FK 可约束**，故"形同虚设"属实。
- schema 由 `zw_brain/shared/migrate.py` 的 `Base.metadata.create_all` / `drop_all`（**alembic 已删，D23**）管理 = **drop & recreate 模型**。这对加 FK 是**有利前提**：无需写迁移脚本，改 ORM 列定义即生效；但**已部署库**只有重建才会拾取新约束（与 memory「seed fresh-db-only」一致）。

### 1.2 父子边的真实分类（决定 FK 可行性）

用 `Base.metadata` 反射枚举「子表引用列 → 父表目标列 + 目标是否 UNIQUE」，得三类边：

**A 类 — 父 PK 边（12 条，可直接 FK + ON DELETE CASCADE）**

子表引用列指向父表 `id`（PK 天然唯一）：

| 子表.列 | → 父.PK | 删除策略建议 |
| --- | --- | --- |
| `approval_step.approval_case_id` | `approval_case.id` | CASCADE |
| `approval_decision.step_id` | `approval_step.id` | CASCADE |
| `objection_evidence.objection_id` | `objection_case.id` | CASCADE |
| `objection_process.objection_id` | `objection_case.id` | CASCADE |
| `objection_evaluation.objection_id` | `objection_case.id` | CASCADE |
| `form_section.form_schema_id` | `form_schema.id` | CASCADE |
| `form_field.form_schema_id` | `form_schema.id` | CASCADE |
| `form_validator.form_schema_id` | `form_schema.id` | CASCADE |
| `approval_flow_node.schema_id` | `approval_flow_schema.id` | CASCADE |
| `approval_flow_selection_rule.schema_id` | `approval_flow_schema.id` | CASCADE |
| `approval_flow_branch.schema_id` | `approval_flow_schema.id` | CASCADE |
| `recommendation_rule_clause.rule_id` | `recommendation_rule.id` | CASCADE |

**B 类 — 业务码边，父码 UNIQUE（topic_package 系，5 条，可 FK 但需复合 FK）**

`topic_package` 上有 `UniqueConstraint(tenant_id, package_code)`；下列子表用单列 `package_code` 引用：
`topic_package_item` / `topic_package_visibility` / `topic_package_review_record` /
`topic_package_evidence` / `topic_package_metric_projection`。
→ FK 目标必须匹配 UNIQUE 列集，故需建**复合 FK `(tenant_id, package_code) → topic_package(tenant_id, package_code)`**（子表两列均已存在），可 CASCADE。

**C 类 — 业务码边，父码非 UNIQUE（不补 UNIQUE 则 FK 建不出）**

| 子表.列 | → 父.列 | 父目标 UNIQUE？ |
| --- | --- | --- |
| `delivery_receipt.delivery_code` | `delivery_task.delivery_code` | ❌ 无 |
| `delivery_attempt.delivery_code` | `delivery_task.delivery_code` | ❌ 无 |
| `delivery_subscription.delivery_code` | `delivery_task.delivery_code` | ❌ 无 |
| `delivery_execution_evidence.delivery_code` | `delivery_task.delivery_code` | ❌ 无 |
| `delivery_task.application_code` | `application_record.application_code` | ❌ 无 |
| `approval_case.application_code` | `application_record.application_code` | ❌ 无 |
| `catalog_entry_version.catalog_code` | `catalog_entry.catalog_code` | ❌ 无 |

> **关键发现**：`delivery_task.delivery_code` / `application_record.application_code` / `catalog_entry.catalog_code`
> 当前**只 `index=True`，无 UNIQUE**。PoC case B 实测：目标列非 UNIQUE 时 SQLite 在首次写入即报
> `foreign key mismatch`，FK **根本建不出来**。这是 C 类边 FK 化的**前置阻塞**。

### 1.3 缺陷 4 现状（F9 多态引用 + catalog_entry）

- `topic_package_item` 是**多态引用**：`ref_type ∈ {catalog_entry, resource, bs_resource, ...}` + `ref_id`（`zw_brain/adapters/legacy/mappers/{catalog_metadata,topic_package,basesubject}.py` 三处写入不同 ref_type）。
- 读路径桥接已存在：`catalog_service.topic_projection_cards*` 用 `ref_type/ref_id` 反查（`list_packages_referencing`），`catalog_service.py:139` 显式 `if record.ref_type == "catalog_entry"`。
- **debt 实证**（`docs/preflight-debt.md` 2026-05-30「F9 专题包引用目录未录入 catalog_entry 主表」）：F9 三标杆引用的 5 个目录（医疗救助 / 医保码 / 异地就医统筹区·定点机构·经办机构）**不在 `catalog_entry` 主表** → `catalog.entry.query` 搜不到、**无 `catalog.entry.detail` 能力**（已确认 dispatch 表只有 `catalog.entry.query`，无 detail）→ P2 召回卡「查看详情」422、P7 目录项只能纯文本。
- 此外 `catalog_entry` 自身**无 `(tenant_id, catalog_code)` UNIQUE**，而 `get_entry(catalog_code)` 当作单条读 —— 收录方案必须同时补此 UNIQUE 让详情页 key 确定。

### 1.4 缺陷 2 现状（凭据）

- `zw_brain/adapters/legacy/mappers/exchange.py:697-704`：legacy granted 分支已按 **D47 诚实化** —— `credential=None` + `credential_status="not_issued"`，**不捏造 AK-DEMO**。
- canonical 库**只存 `credential_status` 标记**（在 grant snapshot JSON 里），无 `apply_id↔service↔app` 链路实体。
- 真凭据在网关域 `dsp_service.api_service_app.SECRET`，导入时 `service.py:37 APP_DROP_FIELDS={SECRET,...}` 在行边界丢弃（不入 canonical），且与 `apply_id` 无绑定供数。**= 上游缺供 + 业务待确认（D47.a）**。

### 1.5 缺陷 3 现状（schema 覆盖 27%）

- 读路径桥接：`catalog_service.enrich_detail`（models 详情）调 `list_schema_mappings(catalog_code=...)` 渲染 `detail["fieldBindings"]` / `fieldBindingSummary`；`request_service.build_*_context` / `provider_service` 同样从 `metadata_evidence_repo.list_schema_mappings` 取，**全部按现有行渲染**。
- **核实结论**：无任何「覆盖率门槛」「写死 27% 名单」的代码分支；mapping 行多一条，详情页字段绑定就多一条。**补数（seed/upstream dump）即自动放大，无需改码**——现状属实。

---

## 二、缺陷 1 设计方案（零外键 → 参照完整性）

### 2.1 设计目标与权衡（FK vs 应用层守卫）

| 维度 | SQL FK + ON DELETE | 应用层删除编排守卫 |
| --- | --- | --- |
| 插入期参照完整性 | ✅ DB 强制（PoC case A 实测拒绝 ghost 父引用） | ⚠️ 仅在写经过 repo 时有效，裸 SQL/旁路无保护 |
| 删父级联 | ✅ CASCADE 自动（PoC 孤儿=0） | 需手写「先删子再删父」编排，易漏 |
| 适用前提 | 父目标列必须 UNIQUE/PK | 无前提，但靠纪律 |
| 跨 ORM 可移植 | SQLite/PG 一致语义 | 与库无关 |
| 历史脏数据 | 重建库时若已有孤儿会**建表/插入失败**，需先清理 | 容忍存量孤儿 |

**裁决取向**：A 类 + B 类（共 17 条边）走 **SQL FK + ON DELETE CASCADE**（DB 兜底最强、与已开的 `PRAGMA foreign_keys=ON` 对齐）；C 类边因父码非 UNIQUE，**二选一交业务/负责人定**（见 §2.3）。

### 2.2 A 类 + B 类落地路径（FK + CASCADE）

1. **改 ORM 列定义**（功能实现阶段，非本期）：
   - A 类：`approval_case_id: Mapped[str] = mapped_column(String(36), ForeignKey("approval_case.id", ondelete="CASCADE"), index=True)`（12 条同形）。
   - B 类（复合 FK）：在 `topic_package_*` 五表 `__table_args__` 加
     `ForeignKeyConstraint(["tenant_id","package_code"], ["topic_package.tenant_id","topic_package.package_code"], ondelete="CASCADE")`。
2. **schema 生效**：因走 `Base.metadata.create_all`，干净库重建即带 FK；**已部署库需重建**（与 D23 drop&recreate 哲学、memory「fresh-db-only」一致）。
3. **存量孤儿清理前置**：重建前跑一次孤儿扫描（见 §五守卫脚本可复用为一次性体检），有孤儿先在 legacy adapter 侧补父或删子，否则建库插入会被新 FK 拒。

> PoC `case_a_fk_cascade()` 已证明：插入守卫拒 ghost 父引用 + 删父级联删子 + 孤儿=0。

### 2.3 C 类边 —— 收敛为「子表引用列锚到父 `id`」（不再二选一）

> **乔布斯收敛**：原方案把「补 UNIQUE+FK vs 应用层守卫」当选择题抛给负责人，本质是把 SQLite
> 限制外泄成产品决策。架构层统一定方向——**C 类边的病根是子表用业务码（`delivery_code`/
> `application_code`/`catalog_code`）引用父表，而非父 `id`**。把引用列收敛到父 `id`，C 类即变为 A 类，
> FK+CASCADE 直接可建，**无需给业务码补 UNIQUE**。

- **统一方案**：`delivery_receipt`/`delivery_attempt`/… 的 `delivery_code` 引用 → 增 `delivery_task_id`（FK→`delivery_task.id`，CASCADE）；`delivery_task.application_code`/`approval_case.application_code` → `application_record_id`（FK→`application_record.id`）；`catalog_entry_version.catalog_code` → `catalog_entry_id`（FK→`catalog_entry.id`）。业务码列**保留**作可读自然键（仅 index，不参与参照完整性）。
- **写入侧前提（= 收敛后唯一的数据现实确认项）**：legacy 导入/运行时写子行时须能拿到父 `id`。父先入库取 `id` 再写子是标准次序；**需在功能实现阶段核 mapper 写入次序**确认成本。若个别边父 `id` 在写子时不可得（跨系统异步落地），该边降级为「§六孤儿守卫全边兜底」——保证不破。
- **为何不补 UNIQUE 迁就**：补 `(tenant_id, code)` UNIQUE 依赖"旧平台同租户 code 唯一"这个未证假设，且把自然键钉成强约束会绑死后续多租户/编码演进。锚到 surrogate `id` 是更精品的解，不赌数据假设。

> **兜底保证（精品意识）**：无论某条边最终走 FK 还是降级守卫，**§六 CI 孤儿守卫对全部父子边生效**——FK 覆盖不到的边由守卫兜底，"无孤儿"是完整保证，不是部分覆盖。

### 2.4 写禁区约束遵守（§9.5 / 段 25）

本方案的 schema 变更（加 FK/UNIQUE）属**模型定义层**，不引入新的 add/commit/merge/delete/裸 SQL DML 写入口；删除编排守卫若实现，落在既有 repo 删除路径（非新建写入口），且 legacy 写仍限 `zw_brain/adapters/legacy/`。功能实现阶段需复跑段 25 确认。

### 2.5 功能实现阶段·M2 写入侧核实结论（C 类边 honest 降级）

> **本节是功能实现阶段对 §2.3 写入侧前提的真实核实产出**，按任务「核实写入次序可行性…honest 降级、不硬凑」执行。结论：**C 类边全部 honest 降级为「§六 M3 孤儿守卫登记边兜底」，不加 NOT-NULL `*_id` FK**。下列证据支撑该裁决（非纪律松懈，是机制诚实）。
>
> **[2026-06-03 amendment · D48 补边 + 措辞收敛]** 上帝视角 review 指出守卫自称"全边/全部父子边"实为闭枚举（彼时 A12+B5+C7=24 边），≥2 条真实软引用边裸奔。处置（产品研发负责人 sign-off）：
> - **补边**：`catalog_item.resource_code → resource_asset.resource_code`、`delivery_subscription.resource_code → resource_asset.resource_code` 两条原裸奔软引用边纳入 `C_CLASS_EDGES`（干净 seed 实证 0 孤儿）；C 类 7→9 条。
> - **措辞收敛**：守卫覆盖 = **常量登记边集合**（单一事实源 = `check_orphan_rows.py` 的 `*_EDGES`，**非 schema 自动反射**），全文"全边"语义统一为"登记边兜底"——承诺不再超出实现。新增父子边须在此登记方被覆盖。
> - **刻意排除**：`objection_case.related_application_id` 系无 live deref 的松散可选标注（legacy mapper 恒写 `None`、command/services 无任何 join 消费方），**不构成参照边**；强行纳入 = 虚构系统并不维护的约束，故不加（诚实的反方向亦是不诚实）。
> - **防回潮测试待补**：补边正确性当前由 preflight 段67 每次提交实跑兜底（实证 0 孤儿）；但"边被悄摘"只能由单测捕获。该回归测试归属 `negative-and-guardrails.feature`（已 `# Pytest:` 引 `test_data_model_referential_integrity.py`），加测会改其内容指纹需 `--with-e2e` 全栈重采，**留待下次 CI 重采时随该 feature 一并落入**（不在本地 PR-A 强加，避免无 node_modules 环境伪绿）。

**核实事实（只读探索 git grep + 读码）**：

1. **C 类子写不在 legacy mapper，而在 domain 仓储层**：`delivery_receipt/attempt/subscription/evidence` 由 `zw_brain/domain/repositories/delivery.py` 的 `append_receipt/upsert_attempt/upsert_subscription/add_execution_evidence` 写入；`catalog_entry_version` 由 `zw_brain/domain/repositories/catalog.py:create_entry_version` 写入。这些方法**只接收业务码**（`delivery_code`/`catalog_code`），**不加载父行、不持有父 `id`**。（§2.3 原假设「在 legacy mapper 回填」与代码现实不符——写散落 legacy mapper + command handler + domain service 三处。）
2. **父行在写子时不保证存在**：`command/handlers/j1/delivery.py:41` 用 `maybe_by_id(task_id)` 取 task，**返回 None 仍无条件写 receipt（:47）**——证明 receipt 的父 `delivery_task` 行可不存在。`catalog_entry_version` 的父 `catalog_entry` 同理常缺位（正是缺陷 4 debt：F9 引用目录未录入主表）。`approval_case.application_code` 键控、不加载 `application_record`，迁入的审批单常无对应申请行。
3. **业务码与 id 存在既有混用**：`command/handlers/j1/application_grant.py:53` 把 `delivery_task.id` 作为 `delivery_code` 传入 `add_execution_evidence`——`delivery_code` 字段在不同调用点既装业务码又装 id。清理这层混用属行为重构，非纯完整性改造，本期不授权。

**裁决理由（精品意识：要么真保证，要么不假装）**：

- 父不保证存在 → **NOT-NULL `*_id` FK 不可行**（会拒绝合法的「父行未落地」子写，改变运行时语义，属未授权的行为变更）。
- **Nullable `*_id` FK 多数为 NULL → 不产生任何被强制的完整性**（NULL FK 不被 DB 约束），只增 schema 噪声 + 七处写点改造，**零完整性收益**——是 cargo-cult convergence，违背简洁/精品。
- §六 已明确：**FK 覆盖不到的边由 M3 孤儿守卫全边兜底**，「无孤儿」保证完整。故 C 类边走守卫兜底是**方案内既定路径**，非缺口。

**结论**：原 7 条 C 类边（4 delivery 子→delivery_task、delivery_task→application_record、approval_case→application_record、catalog_entry_version→catalog_entry）**不加 FK，业务码列保留作可读自然键**，参照完整性由 §六 M3 `check_orphan_rows.py` 对**登记边** `NOT EXISTS` 扫孤儿兜底。M3 守卫的边定义已含这 7 条；[06-03 amendment] 另补 catalog_item/delivery_subscription.resource_code 两条，C 类共 9 条。

> **真正消解 C 类孤儿的上游解（记债，不在本期）**：清理 `delivery_code` 装 id 的混用 + 让父行先落地是「写入次序治理」立项，承接 `j1-legacy-record-actionability`（D47.b）同源的运行时实体解析债。本期不做、不捏造 FK。

### 2.6 功能实现阶段·M5 真库孤儿体检结论（多态码豁免 + 真孤儿清理）

> **本节是 M5 对真实 seed 库（drop&recreate + 真实 legacy dump 导入）跑 `check_orphan_rows.py` 的实证产出。** 真库暴露三类 C 类「孤儿」，逐类诚实裁决——证明 §2.5 降级判断正确（NOT-NULL FK 会拒合法导入），并把守卫边精确收敛到真该有父的子集。

**真库首扫发现（drop&recreate 后，导入前 `check_orphan_rows` 报）**：

| 边 | 孤儿数 | 子码形态 | 性质 | 裁决 |
| --- | --- | --- | --- | --- |
| `approval_case.application_code → application_record` | 170 | **全 `resource-review:*`** | 多态主体码——资源评审单（非申请单），设计上无 application_record 父 | **守卫豁免前缀 `resource-review:`**（非孤儿，不清理） |
| `delivery_execution_evidence.delivery_code → delivery_task` | 10 | **全 `materialize:*`** | 多态主体码——物化作业 id（非交付任务），无 delivery_task 父 | **守卫豁免前缀 `materialize:`** |
| `delivery_attempt.delivery_code → delivery_task` | 16 | 10 `materialize:*` + 6 纯码 | materialize 同上；6 纯码是**真孤儿**（父 subscribe_job 在 dump 被删/缺位，全指向同一失踪 delivery_code） | materialize 豁免；**6 真孤儿删子清理** |

**关键证据**：A/B 类 17 条 FK 边在真库导入时**孤儿=0**（FK + import 顺序天然成立）；C 类「孤儿」要么是多态码（合法、非孤儿）、要么是真上游缺父（删子）。**无一条是「该 FK 却没 FK」**——印证 §2.5「C 类不是真 FK 边」。

**裁决与落地**：

1. **多态码豁免（不是孤儿，禁清理）**：`check_orphan_rows.py` 的 C 类边加可选豁免前缀；`approval_case`(`resource-review:`)、`delivery_attempt`/`delivery_execution_evidence`(`materialize:`)。把完整性主张**精确收敛到真该有本边父行的子集**——诚实（不假装全列都该有父），也不漏报（纯码仍校验）。
2. **真孤儿删子（写在 legacy）**：`zw_brain/adapters/legacy/mappers/pipelines.py:_sweep_orphan_attempts`——导入**末尾**（此刻所有 subscribe_job 已落库，避开「executor 在 dump 里早于 subscribe_job」的行序陷阱）一次性删 `delivery_code` 非 materialize、且 `delivery_task` 查无父的 attempt；warn-level 审计记录进 `error_summary`（不静默），**删子不补造假 task**（D11 禁捏造）。写在 §9.5 合法写区（段 25 通过）。
3. **结果**：清理后真库 `check_orphan_rows.py` **孤儿=0、退出码 0**（M5 验收证据 `.testing/acceptance/data-model-referential-integrity/evidence.json`）。

> **上游真因（记债）**：6 真孤儿的根因 = legacy dump 里 subscribe_job 行缺失但其 executor 行仍在。删子是本期诚实兜底；真修要上游补齐 subscribe_job 供数或确认其 deliberate 删除语义——归「写入次序/供数治理」立项（同 §2.5 上游解）。

---

## 三、缺陷 4 设计方案（catalog_entry 收录 + ref 完整性）

### 3.1 多态 ref 的 FK 限制（事实约束）

`topic_package_item.ref_id` 多态（同列指向 catalog_entry / resource / bs_resource…），**单列无法建 SQL FK**（FK 必须指向单一确定父表）。这是结构性限制，PoC case 4 已据此走应用层守卫路线。

### 3.2 范围切分（聚焦：完整性留本方案，功能剥离回 J1）

> **乔布斯收敛**：原 §3.2 把"建能力 + 补录可检索 + 详情页"混进完整性方案 = 范围蔓延。按聚焦原则切开：

| 事项 | 性质 | 归属 |
| --- | --- | --- |
| 删包/删目录时悬挂 `ref` 的处置守卫 | **参照完整性** | ✅ **本方案**（§3.3） |
| package 维度删除级联（随 §2.2 B 类复合 FK） | **参照完整性** | ✅ **本方案** |
| 被引目录补录进 `catalog_entry`（可检索） | 产品功能 | ➡️ **J1 立项**（debt `catalog-entry.debt.yaml` trigger） |
| 新增 `catalog.entry.detail` capability + 补 `(tenant_id,catalog_code)` UNIQUE + 详情页 | 产品功能 | ➡️ **J1 立项** |

本方案不建能力、不补录、不动 dispatch 表——那是"用数"功能，走 J1 找数→用数立项（D40/D43 链路），与 P2 召回卡/P7 详情页的产品验收绑定。本方案只保证：**无论目录录没录入主表，删除动作都不留悬挂引用**。

### 3.3 ref 完整性方案（无 FK 时的替代，本方案核心）

- **应用层 ref 解析守卫**（**已落地 M4**）：`zw_brain/domain/serializers/topic_package.py:effective_ref_status()` 纯函数——对 `ref_type=catalog_entry` 的 item，校验 `ref_id` 在 `catalog_entry` 命中；悬挂引用降级为诚实信号 `ref_status="dangling"`（复用现成列，不假装可达）+ `ref_resolvable=False`。**只读派生、不写库**（无新写入口，§9.5），始终与主表现状一致、无漂移。`CatalogRepository.present_catalog_codes()` 单查询取命中集合避免 N+1。**触发面仅 `topic_package_service.detail_to_dict()`（topic.package 详情序列化）**——全仓只有它传 `present_catalog_codes`；其余 list/query 路径不传（`present_catalog_codes=None` → 原样返回、不臆断）。PoC `dangling_catalog_refs()` 精确报出悬挂引用，M3 守卫机械兜底。
  > **现状与局限（2026-06-03 产品研发负责人本地走查实证）**：`ref_status=dangling` 是**数据层只读派生就绪信号**，且**仅在 `detail_to_dict` 路径计算**。当前 webui / 5 消费面**无任何 surface 调用该详情路径**（P7 走 `topic.package.query` list 路径，不传 `present_catalog_codes` → 不降级），故此信号**对用户不可见**——P7 目录项一律纯文本、无跳转链接、悬挂与可达**无视觉区分**。这是 **by design**：用户可见的悬挂呈现 + 可点目录详情**同属 J1**（detail/可检索剥离 J1，design §3.2）。**M4 交付边界 = 完整性数据就绪**（`ref_status` 字段为 J1 备好 + FK + 段67 守卫），**非用户侧可见功能**，不应被描述为用户侧诚实信号。
  > **刻意未做（剥离回 J1）**：`catalog.entry.detail` capability / 目录补录可检索 / 详情页。
- **删包编排**：无 FK → 删 `topic_package` 不级联 `topic_package_item`（除非 §2.2 B 类复合 FK 同时落地，则 package 维度可 CASCADE）。删被引**目录**（catalog_entry）天然不级联 item（多态），需应用层守卫把残留 item 标 `ref_status` 失效（item 已有 `ref_status` 列，现成承接点）。

> PoC case 4 已证明：收录后 catalog_entry 命中 + 守卫精确报悬挂 + 删父不级联（需编排）。

---

## 四、缺陷 2 设计方案（凭据 schema-readiness，禁实现）

> **裁决：记债暂停（D47.a 已记，上游缺供 + 业务待确认）。本期禁实现、禁捏造任何 per-grant 凭据/AK。**

仅产出「若上游打通 `apply_id↔service↔app` 供数，canonical 该如何承接」的 schema-readiness 草图（**不写代码、不建表**）：

- 候选实体 `access_credential`（**仅设计草图**）：`tenant_id` / `apply_id`（→ application_record）/ `service_ref`（→ 网关 service）/ `app_ref`（→ api_service_app）/ `credential_status`（issued/not_issued/revoked）/ `issued_at` / `source_ref`。
- **真 SECRET 不入 canonical**：延续 `service.py` APP_DROP_FIELDS 行边界丢弃；canonical 只存**状态 + 指针**（与 D36 `_API_KEY_REF` 指针/字面区分同源哲学），真凭据留网关域。
- **上游缺供阻塞**：`data_apply_authrization` 无 per-grant 凭据，`api_service_app.SECRET` 与 `apply_id` 无绑定供数 → 即便建表也无数据可填，且会诱发捏造。故**不建**。

**暂停记录**：等业务确认「J1 凭据取网关 SECRET 口径 + `apply_id↔service↔app` 绑定供数」（D47.a），再立项承接。

---

## 五、缺陷 3 核实结论（schema 覆盖 27%，禁改码）

> **裁决：记债暂停（上游缺供）。读路径桥接就绪、补数自动放大，无需代码改动。**

- 已核实（§1.5）：`enrich_detail` / `request_service` / `provider_service` 均按现有 `resource_schema_mapping` 行渲染 `fieldBindings`，**无覆盖率门槛、无写死名单**。
- 结论：**无需改码**；27%→更高覆盖靠上游补 schema dump（seed/legacy）即自动放大。
- 对齐既有 debt：`docs/preflight-debt.md` 已登记同类「上游缺供、补数即修」模式（如 update_cycle 73/75）。
- **活账本已登记**：`.testing/debt/resource-schema-keying-reconcile.debt.yaml`（`kind: external`，trigger = 数据/业务侧在上游补 `dsp_metaresource→catalog` 列级 link，补齐后桥接自动放大、无需改码）。本设计**不新增债、不改其 assert**。

> 补充：缺陷 4 亦已在活账本 `.testing/debt/catalog-entry.debt.yaml`（`kind: external`）登记，trigger = 立项「F9 引用目录录入主表 + 目录详情页」。本设计是其 trigger 的**设计承接**，进入实现前仍待 §七审批。

---

## 六、机械反向防御 —— 方案脊柱（D21 段 / 防回潮）

> **乔布斯收敛**：守卫不是审批附属项，是这个产品保证**唯一可信的兑现方式**——"无孤儿"靠机制强制、不靠开发者纪律（设计即工作方式）。FK 覆盖到的边由 DB 兜底，FK 覆盖不到的边由孤儿守卫兜底，**两者合起来才是完整保证**（精品意识：不留 27% 缺口）。
> 注：守卫**接进 `scripts/preflight.sh` 主路径仍需负责人审批段号**（对齐 D46.c「立规则不预先强加守卫」）；本 worktree 不私自接入。脊柱指的是它在方案中的地位，不是绕过审批。

1. **孤儿扫描守卫（缺陷 1，可机械化）**：`scripts/check_orphan_rows.py`（**已落地，接 preflight 段 67**）——对 A/B/C 三类边逐条 `NOT EXISTS` 扫孤儿子行，>0 即 FAIL。**自建干净 seed 库**（临时目录 drop&recreate + `DatabaseStore().initialize()`）扫，CI 可跑、便宜、不需真库、不污染本地；`--db-path` 可对真实 seed 库做一次性体检（M5 用）。既作 FK 化前的**存量体检**，也作 FK 未覆盖的 C 类登记边（9 条，§2.5 amendment 后）的**唯一长期兜底**。
2. **FK 回潮守卫（缺陷 1，可机械化）**：`check_orphan_rows.py` 内置 `len([fk …]) >= 22` 断言（A 类 12 + B 类复合 10），防 FK 被悄悄摘掉退回字符串引用。
3. **catalog_entry 可达性守卫（缺陷 4，可机械化）**：`check_orphan_rows.py` 扫 `topic_package_item(ref_type=catalog_entry)` 的 `ref_id` 是否都在 `catalog_entry`（按 tenant+catalog_code）命中；悬挂引用 → FAIL（防「引用了却没录入主表」回潮）。
4. **凭据捏造防回潮（缺陷 2，已存在）**：D47 段 66 已守 granted 分支禁捏造凭据；本方案不新增，沿用。

可运行 PoC：`docs/prototypes/data_model_integrity_prototype.py`（`.venv/bin/python` 跑，退出码 0 = 全过），证明 case A/B/4 三条设计路径成立并暴露真实约束。

---

## 七、待人工审批事项（收敛后：1 产品保证 + 2 落地确认）

> **乔布斯收敛**：原 5 条工程选择题（FK vs 守卫、补不补 UNIQUE…）已收回架构层。负责人只拍产品级保证 + 必要的落地现实，不在 SQLite 机制间做选择。

1. **【产品保证 / 核心】** 批准硬约束：**「zw-brain 永不留孤儿行——删父级联或拒绝，由系统机制强制」**。机制由架构层定（能 FK 处 FK+CASCADE；C 类边引用列收敛到父 `id`；FK 覆盖不到处由 §六 CI 孤儿守卫全边兜底）。→ 批准即授权进入功能实现。
2. **【落地确认 a】** 已部署库 FK 化生效 = **drop&recreate**（与 D23 一致，干净库重建带 FK）是否接受 + 重建前一次性存量孤儿清理策略（清理落 `zw_brain/adapters/legacy/`）。
3. **【落地确认 b】** §六孤儿/FK 回潮守卫**接入 `scripts/preflight.sh` 的段号分配**（D46.c：立规则需负责人确认才接段）。

> **不再需要负责人定的（已收回架构层）**：C 类边走 FK 还是守卫、补不补 UNIQUE —— 统一为"引用列锚到父 `id`"，详见 §2.3。
> **已剥离出本方案（→ J1 立项）**：`catalog.entry.detail` capability + 目录补录可检索 + 详情页 —— 那是"用数"功能，不是完整性，归 J1 找数→用数（debt trigger 已在）。

## 八、待业务确认 / 上游缺供事项

1. **缺陷 2 凭据建模**（D47.a）：`apply_id↔service↔app` 绑定供数口径 + J1 凭据取网关 SECRET 口径 —— 上游缺供，业务待确认，本期**不建表**。
2. **缺陷 3 schema 覆盖**：73% 资源源 dump 无 schema 列级映射 —— 上游补数即自动放大，**等数据**。
3. ~~C 类边 code 唯一性~~ **（收敛后消解）**：原本要确认 `application_code`/`delivery_code`/`catalog_code` 同租户唯一以建 UNIQUE+FK——§2.3 已收敛为「引用列锚到父 `id`」，不再依赖 code 唯一假设。**剩余确认降级为技术内部项**：功能实现阶段核 legacy mapper 写入次序（父先入库取 `id` 再写子），非业务决策。

## 九、本期刻意未做（诚实声明）

- **未改生产 `models.py`**：保持原型/设计层，避免在审批前把生产模型改成最终态（流程门禁要求）。
- **未接守卫进 `scripts/preflight.sh` 主路径**：守卫为「提议」，立规则不预先强加守卫（对齐 D46.c），待审批后再接段并分配段号。
- **未触碰缺陷 2/3 代码**：仅只读核实 + 文档化，遵 D47.a / 上游缺供 / D11 禁 Mock 禁捏造。
- **未对真实库做 FK 体检**：PoC 用独立缩比 metadata 证明设计，未在真 `.data/zw_brain.db` 跑孤儿扫描（避免污染本地库、且真库孤儿体检属功能实现阶段）。
