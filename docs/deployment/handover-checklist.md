# zw-brain 客户现场移交 checklist

> 角色权威源：[`docs/approved/zw-brain-roles.md`](../approved/zw-brain-roles.md) | 架构基线：[`docs/approved/zw-brain-architecture.md`](../approved/zw-brain-architecture.md)

> 📍 **你在哪一份 zw-brain 文档？**
> | 你是谁 | 看哪份 |
> | --- | --- |
> | 客户运维 / 实施工程师（部署 + 操作） | [`docs/deployment/sd-default-onboarding.md`](./sd-default-onboarding.md)（0.5-1 工作日 runbook） |
> | 客户验收人 / 签收 | [`docs/deployment/handover-checklist.md`](./handover-checklist.md)（41 项核验签收） |
> | 业务用户 / 7 角色 + M0 试岗 | [`docs/approved/zw-brain-roles.md`](../approved/zw-brain-roles.md)（7 角色权威源 + 各角色旅程任务地图） |
> | 客户老板 / CIO 5 分钟看效果 | `bash scripts/customer_demo_5min.sh`（[demo 剧本](../release-notes/customer-demo-5min.md)） |
>
> **本文件**：`docs/deployment/handover-checklist.md` = 客户验收人 42 项 checkbox 签收依据；不是 runbook（看 onboarding）、不是体验手册（看 README）。

> **客户老板 / CIO 视角**：先看 [`docs/release-notes/customer-demo-5min.md`](../release-notes/customer-demo-5min.md)（5 分钟端到端演示剧本，配套 `scripts/customer_demo_5min.sh`），再来这里逐项签收。

> **用途**：把 `sd-default-onboarding.md` 走完后的 41 项核验全部打勾，
> **作为客户签收 zw-brain 进入生产的唯一依据**。
>
> 每一项都有**怎么验证**和**预期结果**两栏。任一项未通过都不应签收。
>
> 验证脚本统一：`bash scripts/preflight.sh` + `pytest tests/` +
> 部分 curl + 部分 SQL。

---

## 一、环境前置（5 项）

| # | 检查项 | 怎么验证 | 预期 | 业务影响（不过=客户用不了什么） |
| --- | --- | --- | --- | --- |
| 1 | Python 3.13+ | `python3 --version` | 3.13.x | venv 无法创建 → 后续全部失败，系统装不起来 |
| 2 | uv 已装 | `uv --version` | 0.4+ | 依赖锁定失效 → 客户环境与开发环境漂移，难以现场修 bug |
| 3 | venv 已建并装齐依赖 | `.venv/bin/python -c "import zw_brain"` | 不报错 | 进程起不来 → REST / 任何 skill 调用全部 502 |
| 4 | 数据目录可写 | `touch $ZW_BRAIN_DB_PATH.test && rm $_` | 不报错 | M0 迁移落不了库 → 客户旧数据进不来 |
| 5 | mysql 客户端可用（仅客户机房） | `which mysqldump` | 有路径返回 | 客户机房无法一键导出 → M0 数据迁移走不通 |

## 二、数据库初始化（3 项）

| # | 检查项 | 怎么验证 | 预期 | 业务影响（不过=客户用不了什么） |
| --- | --- | --- | --- | --- |
| 6 | schema 初始化成功（用 SQLAlchemy `create_all`，不用 alembic） | `.venv/bin/python -c "from zw_brain.shared.migrate import ensure_runtime_schema; ensure_runtime_schema()"` | 不报错 | schema 不全 → 业务读写报"no such table"，整库不可用 |
| 7 | canonical schema 可写 | （与第 6 项合并） | 不报错 | 同上 |
| 8 | 默认租户 sd-default 生效 | `python -c "from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT; print(DEFAULT_TENANT)"` | `sd-default` | 租户错配 → 数据写到错误 tenant，跨租户隔离失效 |

## 三、配置 / 密钥（5 项）

| # | 检查项 | 怎么验证 | 预期 | 业务影响（不过=客户用不了什么） |
| --- | --- | --- | --- | --- |
| 9 | `ZW_BRAIN_DB_PATH` 已设 | `echo $ZW_BRAIN_DB_PATH` | 绝对路径，非默认 | 误用默认路径 → 服务重启数据丢失，没人能签收 |
| 10 | IAF/OIDC 端点可达 | `curl -s "$ZW_BRAIN_IAF_AUTH_SERVER_URL/.well-known/openid-configuration" \| jq .issuer` | 返回 issuer URL | IAM 不通 → 客户业务用户无法登录，整套大脑只有 dev-bypass 可用（生产禁用） |
| 11 | 推理网关密钥引用配置 | `echo $ZW_BRAIN_INFERENCE_API_KEY_REF` | 非空，且不是明文（应以 `arn:` 或 `vault:` 开头） | 推理密钥缺/明文 → LLM 类 skill 全部失败 或 密钥泄露被合规警告 |
| 12 | Blockchain anchor 端点配置（可选） | `echo $ZW_BRAIN_BLOCKCHAIN_ENDPOINT` | 非空 或 显式留 mock-chain | 未显式 mock-chain → audit 异步锚定无目标，安全审计员 督查证据链断 |
| 13 | 无明文密钥泄露到代码库 | `grep -rE '(password\|api_key)=.{8,}' --include="*.py" --include="*.json" /opt/zw-brain` | 仅命中 `*_REF` 引用、不出现真实值 | 明文密钥 → 立即合规高危事件，必须 rotation + 强制下架，签收作废 |

## 四、preflight 全段全过（1 项 — 这一项覆盖整个机械规约层）

| # | 检查项 | 怎么验证 | 预期 | 业务影响（不过=客户用不了什么） |
| --- | --- | --- | --- | --- |
| 14 | preflight 全段通过 | `bash scripts/preflight.sh 2>&1 \| tail -3` | `=== preflight: PASS (common + project stages) ===` | 机械规约层断 → 任何 PR 不能 merge，hotfix 链路瘫痪 |

子段以 `scripts/preflight.sh` 实际执行为准（段号有跳号/子段，不以固定计数承诺，运行 `bash scripts/preflight.sh` 看实际输出）。代表性子段含：branch naming / dev-rules 同步 / agent contract drift / user-story alignment / approved-doc invariants / doc stats sync / audit-must-block / blockchain-async / fixture-pii / no-direct-llm / external-refs / ui-spec-b / legacy-mappers / iam-doc-freshness / no-legacy-role-codes / no-retired-features 等。子段编号与覆盖项随脚本演进，以脚本输出为准。

## 五、客户现场一键导出（4 项）

| # | 检查项 | 怎么验证 | 预期 | 业务影响（不过=客户用不了什么） |
| --- | --- | --- | --- | --- |
| 15 | customer_export.sh dry-run 跑通（仿真） | `bash scripts/customer_export.sh --from-dir=old/10示例数据 --output-dir=.data/export-dryrun/B-test --batch-id=B-test --tenant=sd-default --force` | 17 file_count，total_rows > 800K，redaction_summary 含 phone/email/addr/secret | 一键导出脚本本身坏 → 客户机房落不出可消费的脱敏包 |
| 16 | 真实库 dump 成功 | `ZW_BRAIN_DB_PASSWORD=*** bash scripts/customer_export.sh --db-host=... ...` | manifest.json 文件存在 + verify ok | mysql 连接/权限/编码失败 → 客户旧库一行数据进不来 |
| 17 | 列级脱敏生效 | `grep -c '<REDACTED:PHONE>' /data/legacy-imports/B-*/dump-dsp_bsp-*.sql` | 数千行（视 dsp_bsp 体量） | 脱敏未触发 → PII 进 canonical 表，立即合规高危事件，签收作废 |
| 18 | crc32 / sha256 校验 ok | `python scripts/customer_export.py verify --batch-dir=/data/legacy-imports/B-*` | `{"ok": true, "failures": []}` | hash 不一致 → 不知道导出件是否被传输污染，迁移不可信 |

## 六、M0 端到端（5 项）

> **关联**：本节 5 项是对 [`sd-default-onboarding.md` §5 批量导入 + 验证（M0.2-M0.4）](./sd-default-onboarding.md#5-批量导入--验证m02-m04) 的核验。runbook 在那里看，本表的 exit code / 期望输出是验收签收依据。

| # | 检查项 | 怎么验证 | 预期 | 业务影响（不过=客户用不了什么） |
| --- | --- | --- | --- | --- |
| 19 | 批量导入跑通 | `bash scripts/customer_acceptance_up.sh` | 写 `.data/customer-acceptance/migration-report.json` 且 status=succeeded | 迁移不通 → 客户旧数据进不来，大脑空跑 |
| 20 | `legacy_object_mapping` 一对一回指 | `sqlite3 $ZW_BRAIN_DB_PATH "SELECT COUNT(*), SUM(mapping_status='mapped') FROM legacy_object_mapping"` | total > 0 且 mapped 比例 ≥ 95% | mapping 断 → 安全审计员 督查无法溯源到旧对象，合规证据链不完整 |
| 21 | M0 验收 status query 11 卡片 | `curl -s /api/skills/legacy.migration.status.query?role=ROLE_BUSIAUDIT \| jq '.work_queue_cards \| length'` | `11` | 卡片缺失 → 业务运营员 看不到验收进度，无法签收 M0 |
| 22 | P0 WebUI 页面渲染 | 浏览器访问 `#/migration-acceptance` | 11 张卡片 + totals + canonical/legacy 分布表 | 页面不渲染 → 实施工程师无法证明迁移完成，签收没视觉证据 |
| 23 | 显式回滚 dry-run 可调 | `python -m zw_brain.entry.legacy_migration.rollback --tenant=sd-default --legacy-system=dsp_catalog --dry-run` | 返回 scanned 数 + audit_id=null | 回滚链路坏 → 迁移如果半途出错无法干净退回，业务无 rollback plan |

## 七、M0 + 7 角色 e2e 契约（10 项 — W5.2 全部）

| # | 检查项 | 怎么验证 | 预期 | 业务影响（不过=客户用不了什么） |
| --- | --- | --- | --- | --- |
| 24 | M0 验收 status query | pytest test_01 | pass | M0 验收契约断 → 客户无法证明迁移完成 |
| 25 | ROLE_ORGAN_OPERATER 需求登记 | pytest test_02 | pass | ROLE_ORGAN_OPERATER 主旅程断 → 业务专班无法在生产里发起复用申请 |
| 26 | 提供方部门→部门管理员部门审→业务运营员平台审 反向编目两级闭环（D57⑧） | pytest tests/test_wave1_j2_pipeline.py -k reverse_two_level | pass，confirm 后 lifecycle_status=pending_platform_review、平台审后 approved_pending_publish | 反向编目两级审核断 → 新资源进不了目录候选池 |
| 27 | 审批人 分级授权审批 | pytest test_04 | pass | 审批人 审批断 → 申请进了系统但永远 pending，无法授权交付 |
| 28 | 提供方部门 检测规则 + 任务 | pytest test_05 | pass | 检测规则断 → 字段质量问题无法被发现 |
| 29 | ROLE_ORGAN_OPERATER 接派发任务（基层补差场景） | pytest test_06 | pass | 基层补差派单断 → 基层归口部门拿不到预填任务，基层补录走不通 |
| 30 | ROLE_ORGAN_OPERATER 异常回传（村社区基层场景） | pytest test_07 | pass | 末端异常回传断 → 末端异常无路径回流，数据治理断头 |
| 31 | ROLE_BUSIAUDIT 异议四子流程 | pytest test_08 | pass，evaluate 成功 | ROLE_BUSIAUDIT 异议断 → 申请方与提供方分歧无仲裁路径 |
| 32 | 安全审计员 审计 + 直达督查 | pytest test_09 | pass | 安全审计员 督查断 → 合规问题无法独立核查，巡检失效 |
| 33 | audit 链覆盖 12 个核心 skill | pytest test_10 | pass，no missing | 审计漏写 skill → 部分操作不可回放，合规盲区 |

一键跑全部：`.venv/bin/python -m pytest tests/ -q` → 26 passed + 1 deselected（slow_infra）。
> 上表 24-33 项 e2e 用例的 pytest 实施由 Wave 0/1 实施 PR 接力（设计源 = `.testing/waves/wave-{0,1}/features/*.feature`，详见 `.testing/cleanup-plan.md` 删除映射）；当前移交以"现场按 .feature 顺序人工跑通 + audit_event 表回放"为等价验收路径。

## 八、WebUI M0 + 7 角色浏览（6 项）

| # | 检查项 | 怎么验证 | 预期 | 业务影响（不过=客户用不了什么） |
| --- | --- | --- | --- | --- |
| 34 | ROLE_ORGAN_OPERATER P1 工作台显示 API 凭据卡 + 需求登记 | 切角色 ROLE_ORGAN_OPERATER，进 `#/workbench` | 底部出现"我的 API 凭据"和"需求登记前置"两栏 | 工作台缺关键卡 → 业务专班看不到自己的凭据和入口 |
| 35 | 审批人 P3 reviewDetail 有分级授权策略 form | 切 ROLE_ORGAN_MANAGER，进 `#/request-flow/review/REQ-2026-04-25-0011` | 看到 5 字段策略表（档位/脱敏/频次/有效期/级联） | 审批人 审批表单缺字段 → 无法设置授权边界，审批失效 |
| 36 | 提供方部门 P5 4 张工作流卡 + 反向编目向导可点 | 切 ROLE_ORGAN_MANAGER，进 `#/provider` | 看到 4 张 提供方部门 工作流卡；点反向编目能进 `#/provider/wizard/reverse-catalog` | 提供方部门 工作面缺 → 提供方无法发起反向编目，新资源进不了目录 |
| 37 | 业务运营员 P5 3 张收件箱 + 字段口径裁决可点 | 切 ROLE_BUSIAUDIT，进 `#/provider` | 看到 3 张 业务运营员 卡（标题含 "N 条待我裁决"） | 业务运营员 收件箱缺 → 目录管理员看不到待裁决项，目录运营停摆 |
| 38 | ROLE_SECURITY_AUDIT B1.1 绕行督查 panel | 切 ROLE_SECURITY_AUDIT，进 `#/compliance-ops`（B1.1 合规与运营后台支撑面 literal 路由，仅管理员/审计员；**不在 8 页面普通用户主导航内**——基线 §5.2 = P1-P5/P7 + B1.1/B1.2 共 8 页面） | 底部出现 安全审计员 直达交付清单 + 异议绕行可疑 | B1.1 督查面缺 → 合规绕行无法被发现，督查抓瞎 |
| 39 | ROLE_ORGAN_OPERATER P3 任务过滤 + 异常回传（基层场景） | 切 ROLE_ORGAN_OPERATER，进 `#/request-flow` | 列表只剩 supplementing/need-fix 状态；右上角有"异常回传"链接 | 基层任务过滤错乱 → 基层归口部门看不清自己该做哪些，基层补录混乱 |

## 九、审计 + 合规收口（3 项）

| # | 检查项 | 怎么验证 | 预期 | 业务影响（不过=客户用不了什么） |
| --- | --- | --- | --- | --- |
| 40 | 写 skill 全部产生 audit_event | 客户机房按主旅程实跑一遍（M0 迁移 + `bash scripts/customer_demo_5min.sh` 5 段 curl + 7 角色 WebUI 各点 1-2 个真实业务对象）后查 `sqlite3 $ZW_BRAIN_DB_PATH "SELECT COUNT(DISTINCT skill_id) FROM audit_event"` | ≥ 12（覆盖 W5.2 关键 skill）。zw-brain 是全新项目，单一 canonical DB 走 `$ZW_BRAIN_DB_PATH`（默认 `.data/zw_brain.db`）；e2e 测试用 isolated TemporaryDirectory 仅供单测隔离，不参与本项验收计数 | 审计漏写 → 合规证据链断 → 安全审计员 督查抓瞎，签收作废 |
| 41 | blockchain anchor 队列正常（或可达） | `sqlite3 $ZW_BRAIN_DB_PATH "SELECT COUNT(*) FROM anchor_outbox WHERE delivered=0"` | 0 或 < 100（未投递队列正在异步处理；mock-chain 配置下应该 = 0）。**区块链 adapter 异步执行、外链 down 不阻塞业务**（基线 §3.4 / D4）；anchor 失败不阻断主流程，进 `anchor_outbox` 重试 | anchor 大量未投递 → 区块链证据缺失，对外可信度证明不足 |
| 42 | AgentRuntime AGENT.yaml 注册抽查（按需） | 若客户启用外部 Agent 接入，B1.2 管理员对已注册 `AGENT.yaml` 做 1-2 条抽查（基线 §8.2 + §8.4）：`trust_level` 默认 `untrusted`、`provider` 指向集团推理平台 gateway、`tenant_id=sd-default`、`auth_policy != none` | 抽查通过；否则降级 `untrusted` 或下线 | 外部 Agent 越权调用 → 主旅程被绕过，审计断链 |

---

## 移交完成签名页

```
□ 客户验收人          ____________  日期 _________
□ M0 实施人           ____________  日期 _________
□ zw-brain 产品负责人  ____________  日期 _________

附件：
□ migration-report.json
□ verify-report.json
□ `pytest tests/ -q` 输出（26 passed + 1 deselected）+ `.testing/waves/wave-{0,1}/features/` 现场人工 walkthrough 记录
□ WebUI M0 + 7 角色浏览验收截图（每岗位 ≥ 1 张）
□ preflight 全段 PASS（段数以 `bash scripts/preflight.sh` 实际输出为准）
```

---

## 移交后保修

| 项目 | 保修内容 | 责任方 |
| --- | --- | --- |
| zw-brain 核心 | 主旅程 M0 + 7 角色 e2e 通过；bug fix 7×24 | zw-brain 团队 |
| 推理网关 | 集团统一推理平台 SLA（基线 §3.4 / preflight 段 10） | 集团推理团队 |
| IAM/OIDC | IAF IAM 认证权威源；客户 IT 部门维护 | 客户 IT / IAF |
| Blockchain anchor | 视客户是否启用；异步 adapter，外链 down 不阻塞业务 | 客户 / mock-chain 默认本地 |
| 集团数据治理中心 | 数据清洗 / 质量 / 血缘（基线 §3.4，本平台不复造） | 集团数据治理团队 |
| 集团数据安全中心 | 数据分类分级 / 敏感识别 / 脱敏 / 密钥（基线 §3.4） | 集团数据安全团队 |
| 集团运维监控平台 | 运行监控 / 告警 / 巡检（旧 dsp_monitor 50 表的外部依赖；本平台不复造） | 集团运维团队 |
| 旧库导出兼容性 | 仅承诺 sd-default 17 个 dsp_* schema；新增旧库需 PR | zw-brain 团队 |

## 加固建议（生产环境）

1. **`ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH=0`** 关闭岗位切换，强制走 IAM 角色映射
2. **`ZW_BRAIN_MASK_ROLE=external`** 默认外部脱敏；只在审计回放岗位用 `internal_admin`
3. 数据库换 PostgreSQL：首次切换至**空** PG 库时，把 `ZW_BRAIN_DATABASE_URL` 指向 PG，首次启动 `ensure_runtime_schema()` 自动建表（基线 §9.6 全新项目原则）；**若 PG 库已含 zw-brain 数据，必须先备份再决定是否重置，不可在生产数据存在时直接清空**。alembic 不进入产品基线；首客户上线 + 首次生产 schema 变更后再启 alembic baseline
4. 反向代理统一 TLS 终结 + WAF
5. `customer_export.sh` 的 `ZW_BRAIN_DB_PASSWORD` 走 Vault / KMS，不走文件
6. **`ZW_BRAIN_DEV_IAM_BYPASS` 必须未设置或为 `0`**（MEMORY `dev-iam-bypass debt`，prod guard 延后至首客户部署；目前依赖部署文档 + 运维 checklist 兜底）
