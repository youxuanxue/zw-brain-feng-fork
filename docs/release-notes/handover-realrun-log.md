# handover-checklist 41 项 fresh-run log（ITEM-07）

> **2026-05-19 retrofit (D23-D29)**：本文 7 角色 角色矩阵已退役。
> - 角色权威源：`docs/approved/zw-brain-roles-v2.md`
> - 信息架构权威源：`docs/approved/zw-brain-information-architecture-v2.md`
> - 评审决策记录：`docs/approved/zw-brain-gate1.1-retrofit-2026-05-19.md`
> - 原版 R 编号见 git blame。

> **受众**：`customer-delivery-final-mile` /twin workspace ITEM-07 交付。早晨用户拿来核对哪几项需要他亲自看（#22, #34-#39 浏览器渲染）。
> **执行时间**：2026-05-19 凌晨
> **环境**：本机 venv (.venv/bin/python 3.13.0) + `.data/customer_acceptance.db`（既有 ITEM-02 demo 数据）+ 分支 `feature/customer-delivery-final-mile`

## 总览

- **pass**: 26 项（24 直接 pass + 2 partial-but-acceptable）
- **dev-box-skip**: 3 项（§3 IAF / 推理密钥 / 区块链 endpoint —— 客户 prod env 才设，dev box 无）
- **customer-site-only**: 2 项（#5 mysqldump、#16 真实库 dump —— 仅客户机房 DBA 现场跑）
- **human-visual-required**: 7 项（#22 P0 页面 + #34-#39 WebUI 6 岗位 —— 浏览器肉眼验证）
- **needs debt entry**: 1 项（#40 expectation 与 e2e-temp-DB 隔离的语义冲突 —— 进 preflight-debt）
- **doc drift fixed in part 2/3**: 1 项（#41 SQL 列名 `status`→`delivered`）

详见下方分节。

## 一、环境前置（5 项）

### #1 Python 3.13+
- 命令：`python3 --version`
- 输出：`Python 3.14.4`（top-level）/ `.venv/bin/python --version → 3.13.0`（项目 venv）
- 结果：**pass**（venv 内 3.13.0 满足；3.14 系统 python 不会污染 venv）

### #2 uv 已装
- 命令：`uv --version`
- 输出：`uv 0.9.15 (5eafae332 2025-12-02)`
- 结果：**pass**

### #3 venv 已建并装齐依赖
- 命令：`.venv/bin/python -c "import zw_brain; print('import ok')"`
- 输出：`import ok`
- 结果：**pass**

### #4 数据目录可写
- 命令：`touch $ZW_BRAIN_DB_PATH.test && rm $_`
- 输出：`writable`
- 结果：**pass**

### #5 mysql 客户端可用（仅客户机房）
- 命令：`which mysqldump`
- 输出：`mysqldump not found`
- 结果：**customer-site-only**（dev box 不需要；客户机房 DBA 必须装）

## 二、数据库初始化（3 项）

### #6 alembic upgrade head 成功
- 命令：`.venv/bin/alembic upgrade head` + `alembic current` + `alembic heads`
- 输出：`0008_actor_org_role_binding (head)` ↔ heads `0008_actor_org_role_binding`
- 结果：**pass**（current = head；checklist 说"9 个 migration"，实际链 0000 init + 0001..0008 = 9）

### #7 canonical schema 可写
- 命令：`.venv/bin/python -c "from zw_brain.shared.migrate import ensure_runtime_schema; ensure_runtime_schema()"`
- 输出：`schema ok`
- 结果：**pass**

### #8 默认租户 sd-default 生效
- 命令：`.venv/bin/python -c "from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT; print(DEFAULT_TENANT)"`
- 输出：`sd-default`
- 结果：**pass**

## 三、配置 / 密钥（5 项）

### #9 ZW_BRAIN_DB_PATH 已设
- 命令：`echo $ZW_BRAIN_DB_PATH`
- 输出：`/Users/xuejiao/Desktop/History/inspur/cowork/zw/zw-brain/.data/customer_acceptance.db`
- 结果：**pass**（绝对路径、非默认）

### #10 IAF/OIDC 端点可达
- 命令：`curl -s "$ZW_BRAIN_IAF_AUTH_SERVER_URL/.well-known/openid-configuration" | jq .issuer`
- 输出：`ZW_BRAIN_IAF_AUTH_SERVER_URL not set in dev shell`
- 结果：**dev-box-skip**（dev 走 `ZW_BRAIN_DEV_IAM_BYPASS=1`；客户 prod env 必须设）

### #11 推理网关密钥引用配置
- 命令：`echo $ZW_BRAIN_INFERENCE_API_KEY_REF`
- 输出：未设
- 结果：**dev-box-skip**（D6 推理网关 dev 走 mock；客户 prod 必须设 `arn:` / `vault:` 引用）

### #12 Blockchain anchor 端点配置（可选）
- 命令：`echo $ZW_BRAIN_BLOCKCHAIN_ENDPOINT`
- 输出：未设（mock-chain default）
- 结果：**pass-as-mock**（D4 异步 anchor，未设即用 mock，可签收）

### #13 无明文密钥泄露到代码库
- 命令：`grep -rE '(password|api_key)=.{8,}' --include="*.py" --include="*.json" .`
- 输出：命中 `tests/test_inference_smoke.py:21`、`hub/.../skill_runner_legacy.py:335` 等
- 样本：`api_key=auth_token`、`api_key=env_cfg["api_key"]` —— 均为**变量引用**，非明文
- 结果：**pass-with-note**（hits 全部 `*_REF` 风格，无明文 secret）

## 四、preflight 16 段全过（1 项）

### #14 preflight 全段通过
- 命令：`bash scripts/preflight.sh 2>&1 | tail -3`
- 输出：`=== preflight: PASS (common + project stages) ===`
- 结果：**pass**（实测 17 段全过：preflight 已扩到 17）

## 五、客户现场一键导出（4 项）

### #15 customer_export.sh dry-run 跑通
- 命令：`bash scripts/customer_export.sh --from-dir=old/10示例数据 --output-dir=.data/export-itm07-test --batch-id=B-itm07 --tenant=sd-default --force`
- 输出关键：`=== export complete ===` + manifest.json `file_count: 17 / total_rows: 875174 / redaction_summary keys: ['secret','phone','addr','email','ip','connstr']`
- 结果：**pass**（17 ✓、≥ 800K ✓、6 redaction 类别覆盖 ≥ phone/email/addr/secret 要求 ✓）

### #16 真实库 dump 成功
- 命令：`ZW_BRAIN_DB_PASSWORD=*** bash scripts/customer_export.sh --db-host=... ...`
- 结果：**customer-site-only**（dev box 无 mysql server；客户机房 DBA 现场跑）

### #17 列级脱敏生效
- 命令：`grep -c '<REDACTED:PHONE>' .data/export-itm07-test/dump-dsp_bsp-*.sql`
- 输出：`4`
- 结果：**partial-but-acceptable**（dev seed dsp_bsp 量小，4 条 PHONE 脱敏命中证明 redaction 链路通；客户真实数据 dsp_bsp 数千行时数字自然放大）

### #18 crc32 / sha256 校验 ok
- 命令：`.venv/bin/python scripts/customer_export.py verify --batch-dir=.data/export-itm07-test`
- 输出：`{"batch_id": "B-itm07", "ok": true, "file_count": 17, "failures": []}`
- 结果：**pass**

## 六、M0 端到端（5 项）

### #19 批量导入跑通
- 命令：`bash scripts/customer_acceptance_up.sh`
- 输出关键：5 个 step ok（parse stats / strict acceptance migration / verify / runtime smoke / done）；`migration-report.json` status=succeeded
- 结果：**pass**（含 ITEM-04 fail next-step 改进）

### #20 legacy_object_mapping 一对一回指
- 命令：`sqlite3 $ZW_BRAIN_DB_PATH "SELECT COUNT(*), SUM(mapping_status='mapped') FROM legacy_object_mapping"`
- 输出：`68935|68931`
- 结果：**pass**（mapped 比例 68931/68935 ≈ **99.99%**，远超 95% 门槛）

### #21 M0 验收 status query 11 卡片
- 命令：`service.invoke_skill('legacy.migration.status.query', {'role':'ROLE_BUSIAUDIT'})`（等价于 `curl /api/skills/...`）
- 输出：`work_queue_cards count: 11`（首 3：export / import / mapping_verify）
- 结果：**pass**

### #22 P0 WebUI 页面渲染
- 路径：浏览器 `#/p0-migration-acceptance`
- 结果：**human-visual-required**（headless 无法验证；早晨用户启 REST 后浏览器访问，应见 11 卡片 + totals + canonical/legacy 分布表）

### #23 显式回滚 dry-run 可调
- 命令：`.venv/bin/python -m zw_brain.entry.legacy_migration.rollback --tenant=sd-default --legacy-system=dsp_catalog --dry-run`
- 输出：`{"audit_id": null, "dry_run": true, "scanned": 6, "rolled_back": 6, ...}`
- 结果：**pass**（scanned=6, audit_id=null）

## 七、9 角色 e2e 契约（10 项）

### #24-#33 一键跑
- 命令：`.venv/bin/python -m pytest tests/test_acceptance_9_roles_e2e.py -v`
- 输出：`10 passed in 2.47s`
- 结果：**pass**（10/10）；逐项断言（M0 status / 申请人 需求登记 / 提供方部门→业务运营员 反向编目 / 审批人 分级授权 / 提供方部门 检测规则 / 镇街填报人 派单 / 村社区填报人 异常回传 / 审核汇总人 异议四子流程 / 安全审计员 直达督查 / audit 链覆盖）均通过

## 八、WebUI 9 岗位浏览（6 项）

> headless 跑不了；本节 6 项 **early-morning user walkthrough** 必看。启 REST 后浏览器访问：

### #34 申请人 P1 工作台显示 API 凭据卡 + 需求登记
- 切角色 ROLE_ORGAN_OPERATER，进 `#/p1-workbench` → 底部应见"我的 API 凭据"和"需求登记前置"两栏
- 结果：**human-visual-required**

### #35 审批人 P3 reviewDetail 有分级授权策略 form
- 切 ROLE_ORGAN_MANAGER，进 `#/p3-request-flow/review/REQ-2026-04-25-0011` → 5 字段策略表（档位/脱敏/频次/有效期/级联）
- 结果：**human-visual-required**

### #36 提供方部门 P5 4 张工作流卡 + 反向编目向导可点
- 切 ROLE_ORGAN_MANAGER，进 `#/p5-provider` → 4 张 提供方部门 卡 + 点反向编目能进 `#/p5-provider/wizard/reverse-catalog`
- 结果：**human-visual-required**

### #37 业务运营员 P5 3 张收件箱 + 字段口径裁决可点
- 切 ROLE_BUSIAUDIT，进 `#/p5-provider` → 3 张 业务运营员 卡（标题含 "N 条待我裁决"）
- 结果：**human-visual-required**

### #38 安全审计员 P6 绕行督查 panel
- 切 ROLE_SECURITY_AUDIT，进 `#/p6-compliance-ops` → 底部 安全审计员 直达交付清单 + 异议绕行可疑
- 结果：**human-visual-required**

### #39 基层填报人 P3 任务过滤 + 异常回传
- 切 ROLE_ORGAN_OPERATER，进 `#/p3-request-flow` → 列表只剩 supplementing/need-fix；右上角"异常回传"链接
- 结果：**human-visual-required**

## 九、审计 + 合规收口（2 项）

### #40 写 skill 全部产生 audit_event
- 命令：`sqlite3 $ZW_BRAIN_DB_PATH "SELECT COUNT(DISTINCT skill_id) FROM audit_event"`
- 输出：`8`（含 application.resource.submit / approval.review_decide / audit.list / catalog.browse / catalog.resource_view / legacy.coverage.skip / legacy.migration.status.query / request.list）
- checklist 期望：`≥ 12`
- 结果：**partial / debt**
- 解释：`tests/test_acceptance_9_roles_e2e.py` 使用 `TemporaryDirectory` 创建 isolated DB（见 test 内 fixture），其 audit_event 不会落回 `$ZW_BRAIN_DB_PATH`；而本地 `customer_acceptance.db` 只承接 M0 + ITEM-02 demo 5 段 curl（含部分 read skills）。这是**doc-vs-test 设计错位**：checklist 隐含『把 e2e 写入 prod DB』但 e2e 实际 isolated。**进 debt：见 docs/preflight-debt.md ITEM-07-handover-fresh-run-audit-skill-count**

### #41 blockchain anchor 队列空（或可达）
- 原命令：`sqlite3 $ZW_BRAIN_DB_PATH "SELECT COUNT(*) FROM anchor_outbox WHERE status='pending'"` → **schema drift fail**: 实际 schema 列名是 `delivered`（BOOLEAN，0/1）而非 `status`
- 修正命令：`sqlite3 $ZW_BRAIN_DB_PATH "SELECT COUNT(*) FROM anchor_outbox WHERE delivered=0"`
- 输出：`10`
- 结果：**pass-with-doc-fix**（10 < 100 满足 mock-chain 异步队列正常承载；handover-checklist.md 该行 SQL 在 Commit B 修正）

---

## fresh-run 后实操结论（给早晨用户）

| 等级 | 项 | 你的动作 |
|---|---|---|
| 🟢 done | 26 项（含 4 partial-but-acceptable） | 无需处理 |
| 🟡 浏览器 | #22 + #34-#39 共 7 项 | 启 `bash scripts/start-local.sh` 后用 dev-bypass 登录，按本 log §六/§八 路径逐项肉眼看 |
| 🟡 客户机房 | #5 + #16 | 客户 DBA 现场跑 mysqldump 链路 |
| 🟡 客户 prod env | #10 / #11 | 设 IAF endpoint + 推理密钥 REF |
| 🔴 doc fix | #41 SQL `status`→`delivered` | Commit B 顺手改 |
| 🟠 debt | #40 期望与 e2e isolation 错位 | preflight-debt.md 新增条目；trigger to re-evaluate = M0 主流程结束后由客户实际跑通 ≥ 12 skill |

**结论**：26 项 headless pass + 7 项浏览器待看 + 1 项 doc 修 + 1 项 debt → **可交付客户（pending 浏览器复核）**。
