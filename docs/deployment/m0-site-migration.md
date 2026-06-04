# M0 客户现场迁移与验收：一次性迁得清，再让旧平台退场

## 这一页解决什么事

这是 zw-brain 的开箱切换体验，不是一个长期角色。客户现场要从旧平台一键导出真实数据，迁移到 zw-brain，并在验收时证明旧目录、资源、元数据、申请、审批、授权、质量、血缘都被承接；M0 是唯一处理迁移执行、批量导入、对象映射完整性、重跑、回滚和验收移交的页面。迁移完成后，日常工作交给 2 核心旅程（J1 找数→用数 / J2 挂数→维数）+ B1 后台支撑面（B1.1 合规与运营 / B1.2 接入扩展中心）下的 7 角色（详见 `docs/approved/zw-brain-roles.md`），不保留运行时双轨。

## 前置假设（基线对齐）

- **schema 全新创建**：M0 在 `Base.metadata.drop_all + create_all` 重建后的空 canonical 上跑（基线 §9.6）；alembic 不进入产品基线。如客户现场上一轮迁移留有持久化目录，需经客户授权清空后再启 M0 迁移。
- **单租户**：所有 record 注入 `tenant_id="sd-default"`（基线 §8.2）。
- **模型调用边界**：M0 不调用 LLM；若 mapper 后续启用 schema 描述补全等 AI 能力，必须走 `shared/inference/client` 经集团推理平台（基线 §3.4 / preflight 段 10）。
- **外部依赖**：IAF IAM（认证）/ 集团数据治理中心 / 集团数据安全中心 / 集团运维监控 / 区块链 adapter 均为外部依赖；M0 不复造（基线 §3.4）。
- **产品形态**：M0 不打包大屏 / 指挥中心 / 演示页面入口（基线 §1.3）。
- **实施界面 = CLI（by design）**：M0 现场实施走命令行（`scripts/import_legacy_dumps.py import <schema>` / `verify` 等）；**不建独立浏览器实施面**。用户 2026-05-25 确认「M0 不需要 web 页面」，故 M0「12 步主旅程浏览器可视化」（原 e6-platform-m0 AC3）**非缺口**，不再作为待办跟踪。

## 你手上拿到的真实输入

- 旧平台导出包：目录、目录项、资源、资源字段、元数据快照、申请、审批、授权、质量、血缘、审计流转。
- 结构依据：`old/12-datastructure/*` 中的旧表结构。
- 脱敏样例：`old/10示例数据/*` 中可用于演示和验收的样例。
- 用户角色 / 权限承接 baseline manifest：`tests/fixtures/m0-sd-default/{iaf-binding,role-mapping,capability-mapping}-manifest.json`（基于 `old/10示例数据/dump-dsp_bsp-202604271139.sql` 构造，由 `scripts/build_m0_sd_default_fixtures.py` 幂等生成；M0 实施现场可调整后回流）。`iaf-binding-manifest.json` 中 `iaf_sub` 字段是 `iaf-sd-<sha1>` **占位**，必须经 IAM 团队批量注入后由 `scripts/ingest_iam_sub_backfill.py` 替换为真实 IAM directory sub。e2e 验证：`tests/test_bsp_sd_default_real_dump_e2e.py`。
- 迁移状态：待导出、导出完成、脱敏通过、导入中、迁移待核验、迁移通过、迁移回滚。
- 核验证据：`legacy_object_mapping`、导入批次号、schema 快照、目录项-资源字段绑定、quality projection、lineage projection、审计回执。
- 旧→新状态映射：旧 `dump-dsp_catalog` 中目录状态为 `草稿(0)/待审核(1)/审批通过(2)/审批驳回(3)/已发布(4)/下线(5)` 六档 + 独立 `revoke_status` 字段，M0 必须把这些映射到新平台 `draft/pending_review/approved_pending_publish/active/suspended/revoked`，并对没有旧值的扩展态 `changing` 做"无旧值"标记，以 catalog3-metadata3 重构方案 §八 为基线。
- 单租户单省锚定：所有迁入目录、资源、申请、授权、组织、区划默认 `tenant_id=sd-default`、`region_code=370000000000`（山东省）；上级通道下发的跨省目录单独标 `external_channel_origin`，不与 sd-default canonical 混淆。

## 一条主旅程

> **认证职责分界**（基线 §1.4 / G1 / G7）：zw-brain **不**写 IAF IAM 的密码 / 用户表 / token；IAM 账号开通是 IAM 团队职责。zw-brain 只做两件事：（a）输出"开通清单 csv"给 IAM 团队；（b）接收 IAM 回填的真实 sub 后替换 manifest 占位。step 0a / 0b 处理 A 线传送带（认证信息）；step 1–12 处理 B 线（业务身份 / 角色 / 权限 / 目录 / 资源等）。

0a. 跑 `uv run python scripts/export_iam_provisioning_request.py --dump <客户 dump 路径>` 把 `iaf-binding-manifest.json` + dump 派生为脱敏 csv（默认落 `tests/fixtures/m0-sd-default/iam-provisioning-request.csv`），把该 csv + 客户 HR 提供的**明文**花名册（明文不入仓）一起交给 IAM 团队批量开通账号；本轮补迁可加 `--diff <上次 csv>` 只产出增量行。

0b. IAM 团队按 csv 在 IAF directory 注入账号后，回填一份 `legacy_user_id,iaf_sub[,binding_status]` 的 csv 交给 zw-brain 实施工程师，跑 `uv run python scripts/ingest_iam_sub_backfill.py <回填 csv>`（可加 `--dry-run` 预演不写盘）。脚本机械门禁：`not_found_in_manifest>0` → 退出码 1；仍有 `iaf-sd-` 占位 sub → 退出码 2；仅退出码 0 才落库。落库后 `binding_status=iam_account_missing` 计数即"IAM 未开通"用户数；必须为 0（或经客户授权显式接受残缺）才进入 step 1。

1. 在客户现场发起一键导出，按目录、资源、元数据、申请审批、授权、质量、血缘和审计流转生成同一批次的脱敏导出包。
2. 先做完整性检查：关键旧表、主外键、目录 ID、资源 ID、目录项 ID、字段 ID、申请 ID、审批流转是否能被识别。
3. 对导出包做敏感信息扫描，只保留目录名、组织名、区域名、状态名、字段口径和脱敏证据引用。
4. 执行批量导入，生成 `legacy_object_mapping`，让每个旧目录、旧资源、旧字段、旧申请和旧审批都能回指来源对象。
5. 核验 `医疗救助信息`、`医保码信息`、`异地就医统筹区开通信息` 等高频目录是否进入 `catalog_entry` 和 `catalog_item`。
6. 核验库表、文件、文件夹、链接、API/接口资源是否进入 `resource_asset` 与 `resource_channel_binding`。
7. 核验元数据采集结果是否形成 `resource_schema_snapshot`，字段中文注释、格式、主键、空值、安全级别、加密要求是否可见。
8. 核验目录项与资源字段是否形成 `resource_schema_mapping`，避免“目录能看到但资源交不了”。
9. 对目录迁移审核做抽样：旧 `草稿(0)`、`待审核(1)`、`审批通过(2)`、`审批驳回(3)`、`已发布(4)`、`下线(5)` 及 `revoke_status` 撤销等状态能否映射为 zw-brain 的状态机和审计回执。
10. 生成搜索、共享专题、质量、血缘、运营统计等 projection，并记录投影状态与失败摘要。
11. 让部门管理员（`ROLE_ORGAN_MANAGER`，提供方部门）、业务运营员（`ROLE_BUSIAUDIT`，主管部门）、安全审计员（`ROLE_SECURITY_AUDIT`）分别抽查资源证据、目录运营入口和合规断链，形成验收结论。
12. 验收通过后关闭迁移模式，把后续资源维护（J2）、目录发布（J2 + `ROLE_BUSIAUDIT`）、审批授权（J1）和合规督查（**B1.1 合规与运营后台支撑面**，仅管理员/审计员，**不在普通用户主导航内**——基线 §5.1）移交给对应 7 角色（详见 `docs/approved/zw-brain-roles.md`）。

## 工作队列卡片

| 工作队列 | 何时进 | 谁批 | 何时出 | 留在哪 |
| --- | --- | --- | --- | --- |
| IAM 账号注入 | step 0a 导出清单 → IAM 团队开通 → step 0b 回填 | M0 实施人 + IAM 团队 + 客户授权 | `iam_account_missing` 计数清零或客户显式接受残缺 | `iam-provisioning-request.csv` + IAM 回填 csv + 更新后的 `iaf-binding-manifest.json` |
| 一键导出 | 客户现场启动迁移、补迁批次 | M0 实施人 + 客户授权 | 导出完成、脱敏通过 | 导出包 + 脱敏回执 |
| 批量导入 | 导出包已脱敏 | M0 实施人 | 批次成功或停在缺口报告 | import batch + `legacy_object_mapping` |
| 对象映射核验 | 批次导入完成 | M0 实施人 + `ROLE_ORGAN_MANAGER` + `ROLE_BUSIAUDIT` 抽样 | 旧对象逐一回指或缺口列出 | mapping evidence + 缺口清单 |
| 目录迁移审核 | 旧目录 `草稿(0)/待审核(1)/审批通过(2)/审批驳回(3)/已发布(4)/下线(5)` + `revoke_status` 进入新平台 | M0 + `ROLE_BUSIAUDIT` 抽样 | 状态映射可解释、目录可发现 | migration review + audit |
| schema 快照与挂接核验 | 元数据采集结果导入 | M0 + `ROLE_ORGAN_MANAGER` 抽样 | 字段中文注释、敏感级别、挂接绑定齐全 | `resource_schema_snapshot` + `resource_schema_mapping` |
| 申请审批授权历史核验 | 旧申请/审批/授权导入 | M0 + `ROLE_BUSIAUDIT` 抽样 | 历史责任链可追溯，当前授权重新按策略生效 | `application_record` / `approval_case` / `delivery_task` 摘要 |
| 投影生成 | canonical 写入完成 | M0 自动 + 失败摘要 | 搜索/共享/质量/血缘/统计 projection 状态可见 | projection status + 失败摘要 |
| 合规与断链抽查 | 投影完成 | `ROLE_SECURITY_AUDIT` 抽样 | 绕行模式、来源缺口、断链全部记录 | ops issue projection + 整改清单 + **B1.1 合规与运营 panel** |
| 验收移交 | 所有抽样通过、缺口闭环或被接受 | 客户验收人 + M0 实施人 | 关闭迁移模式、移交 7 角色 | 验收回执 + 移交清单 |
| 缺口补迁 | 验收后发现漏迁 | M0 + 客户授权 | 新批次回指旧对象 | 补迁批次回执 |
| 回滚 | 批次失败或验收驳回 | M0 + 客户授权 | 批次冻结、按幂等规则重跑或回滚 | 回滚审计 + 影响清单 |

## 关键判断点

| 你看到什么 | 该怎么判断 | 系统证据 |
| --- | --- | --- |
| 旧对象无法生成映射 | 不能算迁移完成 | `legacy_object_mapping` 缺口报告 |
| 旧目录已发布但新平台不可发现 | 先查目录状态和 projection，不要求重新导入 | `catalog_entry.status`、search projection status |
| 目录项没有资源字段绑定 | 不能说“可交付” | `resource_schema_mapping` 缺口 |
| 资源已导入但 schema 缺字段注释 | 不能直接发布为高质量资产 | `resource_schema_snapshot`、quality projection |
| 申请审批历史缺授权结果 | 只能作为历史证据，不能伪造当前授权 | `approval_case`、`delivery_task.access_grant_snapshot` |
| 质量或血缘投影失败 | 迁移事实可以保留，但验收需记录断链 | quality / lineage projection status |
| 批量导入部分成功 | 冻结批次，按幂等规则重跑或回滚 | import batch receipt、audit event |

## 异常分支

- **IAM 回填 csv 含 manifest 不存在的 `legacy_user_id`**：`ingest_iam_sub_backfill.py` 退出码 1，不落库；修正 typo 或换 manifest 后重跑 step 0b。
- **IAM 团队回填漏了用户 / 未在 directory 开通**：`ingest_iam_sub_backfill.py` 校验通过后落库，仍扫到任何 `iaf-sd-<sha1>` 占位 sub 残留即退出码 2，无逃生口。先与客户确认这些用户是否本期不开通；若是则在 backfill csv 把这些 `legacy_user_id` 行的 `iaf_sub` 留空（ingest `_classify` 会自动把 `binding_status` 转 `iam_account_missing` 并清空占位 sub），重跑 ingest 即可通过；若非则催 IAM 团队补开通后重跑 step 0b。占位 sub 有**两道闸门**：ingest 落库前扫描（exit 2）+ `legacy.bsp.mapping.import` 的 governance mapper 把 `iaf-sd-` 前缀视同未注入并 fail-closed 为 `iam_account_missing`（不写 active binding / 不泄漏占位 sub 进 `external_actor_id`）。即便侥幸进入 canonical，IAF directory 无对应 sub 也会让 OIDC 验签失败、用户无法登录。
- **存量用户首登产生两套用户数据（历史脏数据修复）**：修复前的登录链路对存量用户首次 IAM 登录会按真实 `sub` 另插一行（`source_ref='iaf:claims'`）、不 rekey 原 legacy 行 → 同一人在 `actor_projection` 留下两行（一行 legacy user_id 键含完整 profile+绑定，一行登录薄行只有 claims 字段）。页面用薄行+token 角色照常工作，肉眼看不出，但库里是两套数据。**代码侧根因已修复**（登录/重导入统一走 `claim_legacy_actor_by_iaf`：sub 优先、辅助字段唯一命中即就地 rekey 存量行并搬移 binding+mapping，多命中 fail-closed 403 `actor_identity_ambiguous`，不认领 disabled 行）；**存量脏数据用一次性脚本清**：
  1. **先备份库**（`cp zw_brain.db zw_brain.db.bak-<日期>` 或 `pg_dump`）。
  2. 预演：`uv run python scripts/repair_actor_identity_duplicates.py --db-url <库URL> --dry-run --json-report /tmp/repair.json` —— 打印 `planned_rekey / unmatched / ambiguous` 计数；退出码 0=无双行/全可合并，1=有 unmatched 或 ambiguous（需人工核对 username/phone/email），2=apply 抛错。
  3. 人工审 `/tmp/repair.json`：`detail.unmatched`（薄行匹配不到存量行——多半是 account/phone/email 对不上，人工确认是否同一人）与 `detail.ambiguous`（薄行命中多条存量行——绝不自动合并，人工裁决）。
  4. 执行：`... --apply`（删薄行→把存量行 rekey 到 sub，单行收口）。脚本删除经 `delete_actor_row(source_ref_guard='iaf:claims')` 守卫，只能删登录薄行、永不误删 legacy 行。
  5. 复核：再跑一次 `--dry-run`，期望 `thin_rows=0 planned_rekey=0`（幂等）；并核对 `actor_projection` 行数下降量 == `deleted_thin`、被认领行的 `external_actor_id` 已是真实 sub 且 `binding` 完整。
  > unmatched/ambiguous 不阻断已成功合并的行；它们只是需要人工跟进的尾巴，处理完再单独重跑即可。
- **导出缺表或缺字段**：停止导入该批次，输出缺口清单；不猜测旧结构，也不手工补造来源。
- **字段枚举无法识别**：保留原始枚举摘要，进入迁移待核验，不直接映射为 active 状态。
- **schema 冲突**：同一旧资源多版本字段不一致时，保留版本快照，默认只激活通过核验的稳定版本。
- **旧对象重复**：生成候选合并关系，交给 `ROLE_BUSIAUDIT`（业务运营员）做目录合并或专题入口整理，不在迁移脚本里静默去重。
- **敏感数据命中**：导入批次失败，保留脱敏错误摘要，不写入 canonical model。
- **投影生成失败**：业务事实不回滚，记录 projection 失败摘要并交给 `ROLE_SECURITY_AUDIT` 督查断链。
- **客户现场执行器失败**：保留批次号、失败阶段和回执，允许重跑；禁止半手工导入绕过审计。
- **验收后发现漏迁**：用新批次补迁并回指旧对象，不重新打开运行时兼容入口。
- **推理网关不可达**：若 mapper 启用 AI 辅助能力（schema 描述补全等），调用走 `shared/inference/client` 失败时降级为只迁结构、不补语义，记录"未补 AI 字段"摘要进验收报告；不直连第三方 LLM 绕过基线 §3.4。
- **区块链 anchor 异步失败**：进 `anchor_outbox` 重试队列，**不阻塞迁移**（基线 §3.4 / D4 区块链 adapter 异步执行 + 外链 down 不阻塞业务）。

## 成功判据

- 每个关键旧目录、旧目录项、旧资源、旧字段、旧申请、旧审批、旧授权都有 `legacy_object_mapping`。
- 高频目录能被 `ROLE_ORGAN_OPERATER`（部门操作员，J1 发起）搜索、理解、申请；审批边界能被 `ROLE_ORGAN_MANAGER`（部门管理员）判断；资源证据能被 `ROLE_ORGAN_MANAGER` 维护；目录入口能被 `ROLE_BUSIAUDIT`（业务运营员）运营；断链能被 `ROLE_SECURITY_AUDIT`（安全审计员）抽查。
- 旧平台的批量导入、目录迁移审核、资源注册迁移、元数据采集快照、质量检测、血缘关系和审计流转都有新平台承接位置。
- 失败批次可重跑、可回滚、可解释；没有绕过审计的手工补库。
- 迁移结束后，客户不再需要旧平台运行时能力来完成日常目录、资源、申请、授权和交付。

## 旧平台能力在这里怎么落地

| 旧平台能力 | zw-brain 表达 | 验收感知 |
| --- | --- | --- |
| 一键导出、批量导入 | import batch + `legacy_object_mapping` | 每个旧对象都能回指来源 |
| 目录迁移审核 | migration review + `approval_case` 摘要 | 旧状态进入可审计迁移结论 |
| 目录维护、发布、撤回 | `catalog_entry` / `catalog_entry_version` | 目录能被发现、版本能回放 |
| 资源注册迁移 | `resource_asset` / `resource_channel_binding` | 表、文件、文件夹、链接、API 都有统一资产表达 |
| 元数据采集结果 | `resource_schema_snapshot` | 字段、格式、主键、空值、安全级别可核验 |
| 资源挂接 | `resource_schema_mapping` | 目录项能解释到资源字段 |
| 申请审批授权历史 | `application_record` / `approval_case` / `delivery_task` 摘要 | 历史责任链可追溯，当前授权重新按策略生效 |
| 质量检测与规则 | quality projection | 验收时知道哪些目录/字段仍有质量风险 |
| 血缘与关系图谱 | lineage projection | 能解释来源去向和影响范围 |
| 审计流转 | audit event / receipt | 每次导入、核验、重跑、回滚都有证据 |
| 国家目录通道 | `legacy_object_mapping` + 外部通道 adapter 摘要 | 上级通道目录与本地目录的对接记录可回放 |
| 开放目录 / 资源开放配置 | `legacy_object_mapping` 覆盖 `catalog-front /open/catalog-config`、`/open/catalog-publish`、`/open/resource-config`、`/open/resource-config-examine`、`/open/resource-publish`、`/open/relative-desensitize-data`、`/open/desensitize-data-examine` | 开放与脱敏审核记录都纳入验收，不留运行时双轨 |
| 安全前端策略 | `legacy_object_mapping` 覆盖 `datasecurity-front` 的脱敏 / 加密 / 敏感识别 / 风险规则等关键策略对象 | 验收时确认字段安全证据被新平台承接 |
