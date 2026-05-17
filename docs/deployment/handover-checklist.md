# zw-brain 客户现场移交 checklist

> **用途**：把 `sd-default-onboarding.md` 走完后的 41 项核验全部打勾，
> **作为客户签收 zw-brain 进入生产的唯一依据**。
>
> 每一项都有**怎么验证**和**预期结果**两栏。任一项未通过都不应签收。
>
> 验证脚本统一：`bash scripts/preflight.sh` + `pytest tests/` +
> 部分 curl + 部分 SQL。

---

## 一、环境前置（5 项）

| # | 检查项 | 怎么验证 | 预期 |
| --- | --- | --- | --- |
| 1 | Python 3.13+ | `python3 --version` | 3.13.x |
| 2 | uv 已装 | `uv --version` | 0.4+ |
| 3 | venv 已建并装齐依赖 | `.venv/bin/python -c "import zw_brain"` | 不报错 |
| 4 | 数据目录可写 | `touch $ZW_BRAIN_DB_PATH.test && rm $_` | 不报错 |
| 5 | mysql 客户端可用（仅客户机房） | `which mysqldump` | 有路径返回 |

## 二、数据库初始化（3 项）

| # | 检查项 | 怎么验证 | 预期 |
| --- | --- | --- | --- |
| 6 | alembic upgrade head 成功 | `.venv/bin/alembic upgrade head` | 9 个 migration 全过 |
| 7 | canonical schema 可写 | `python -c "from zw_brain.shared.migrate import ensure_runtime_schema; ensure_runtime_schema()"` | 不报错 |
| 8 | 默认租户 sd-default 生效 | `python -c "from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT; print(DEFAULT_TENANT)"` | `sd-default` |

## 三、配置 / 密钥（5 项）

| # | 检查项 | 怎么验证 | 预期 |
| --- | --- | --- | --- |
| 9 | `ZW_BRAIN_DB_PATH` 已设 | `echo $ZW_BRAIN_DB_PATH` | 绝对路径，非默认 |
| 10 | IAF/OIDC 端点可达 | `curl -s "$ZW_BRAIN_IAF_AUTH_SERVER_URL/.well-known/openid-configuration" \| jq .issuer` | 返回 issuer URL |
| 11 | 推理网关密钥引用配置 | `echo $ZW_BRAIN_INFERENCE_API_KEY_REF` | 非空，且不是明文（应以 `arn:` 或 `vault:` 开头） |
| 12 | Blockchain anchor 端点配置（可选） | `echo $ZW_BRAIN_BLOCKCHAIN_ENDPOINT` | 非空 或 显式留 mock-chain |
| 13 | 无明文密钥泄露到代码库 | `grep -rE '(password\|api_key)=.{8,}' --include="*.py" --include="*.json" /opt/zw-brain` | 仅命中 `*_REF` 引用、不出现真实值 |

## 四、preflight 16 段全过（1 项 — 这一项覆盖整个机械规约层）

| # | 检查项 | 怎么验证 | 预期 |
| --- | --- | --- | --- |
| 14 | preflight 全段通过 | `bash scripts/preflight.sh 2>&1 \| tail -3` | `=== preflight: PASS (common + project stages) ===` |

子段包括：branch naming / dev-rules 同步 / agent contract drift / user-story alignment / approved-doc invariants / doc stats sync / audit-must-block (D4) / blockchain-async (D4) / fixture-pii (D11) / no-direct-llm (D6) / dashboard-readonly (D15) / external-refs (D22) / ui-spec-b (Spec B 单主题) / legacy-mappers (D7+D4) — 16 段。

## 五、客户现场一键导出（4 项）

| # | 检查项 | 怎么验证 | 预期 |
| --- | --- | --- | --- |
| 15 | customer_export.sh dry-run 跑通（仿真） | `bash scripts/customer_export.sh --from-dir=old/10示例数据 --output-dir=.data/export-dryrun/B-test --batch-id=B-test --tenant=sd-default --force` | 17 file_count，total_rows > 800K，redaction_summary 含 phone/email/addr/secret |
| 16 | 真实库 dump 成功 | `ZW_BRAIN_DB_PASSWORD=*** bash scripts/customer_export.sh --db-host=... ...` | manifest.json 文件存在 + verify ok |
| 17 | 列级脱敏生效 | `grep -c '<REDACTED:PHONE>' /data/legacy-imports/B-*/dump-dsp_bsp-*.sql` | 数千行（视 dsp_bsp 体量） |
| 18 | crc32 / sha256 校验 ok | `python scripts/customer_export.py verify --batch-dir=/data/legacy-imports/B-*` | `{"ok": true, "failures": []}` |

## 六、M0 端到端（5 项）

| # | 检查项 | 怎么验证 | 预期 |
| --- | --- | --- | --- |
| 19 | 批量导入跑通 | `bash scripts/customer_acceptance_up.sh` | 写 `.data/customer-acceptance/migration-report.json` 且 status=succeeded |
| 20 | `legacy_object_mapping` 一对一回指 | `sqlite3 $ZW_BRAIN_DB_PATH "SELECT COUNT(*), SUM(mapping_status='mapped') FROM legacy_object_mapping"` | total > 0 且 mapped 比例 ≥ 95% |
| 21 | M0 验收 status query 11 卡片 | `curl -s /api/skills/legacy.migration.status.query?role=r7 \| jq '.work_queue_cards \| length'` | `11` |
| 22 | P0 WebUI 页面渲染 | 浏览器访问 `#/p0-migration-acceptance` | 11 张卡片 + totals + canonical/legacy 分布表 |
| 23 | 显式回滚 dry-run 可调 | `python -m zw_brain.entry.legacy_migration.rollback --tenant=sd-default --legacy-system=dsp_catalog --dry-run` | 返回 scanned 数 + audit_id=null |

## 七、9 角色 e2e 契约（10 项 — W5.2 全部）

| # | 检查项 | 怎么验证 | 预期 |
| --- | --- | --- | --- |
| 24 | M0 验收 status query | pytest test_01 | pass |
| 25 | R1 需求登记 | pytest test_02 | pass |
| 26 | R6→R7 反向编目闭环 | pytest test_03 | pass，lifecycle_status=pending_review |
| 27 | R2 分级授权审批 | pytest test_04 | pass |
| 28 | R6 检测规则 + 任务 | pytest test_05 | pass |
| 29 | R3 接派发任务 | pytest test_06 | pass |
| 30 | R4 异常回传 | pytest test_07 | pass |
| 31 | R5 异议四子流程 | pytest test_08 | pass，evaluate 成功 |
| 32 | R8 审计 + 直达督查 | pytest test_09 | pass |
| 33 | audit 链覆盖 12 个核心 skill | pytest test_10 | pass，no missing |

一键跑全部：`pytest tests/test_acceptance_9_roles_e2e.py -v` → 10 passed

## 八、WebUI 9 岗位浏览（6 项）

| # | 检查项 | 怎么验证 | 预期 |
| --- | --- | --- | --- |
| 34 | R1 P1 工作台显示 API 凭据卡 + 需求登记 | 切角色 r1，进 `#/p1-workbench` | 底部出现"我的 API 凭据"和"需求登记前置"两栏 |
| 35 | R2 P3 reviewDetail 有分级授权策略 form | 切 r2，进 `#/p3-request-flow/review/REQ-2026-04-25-0011` | 看到 5 字段策略表（档位/脱敏/频次/有效期/级联） |
| 36 | R6 P5 4 张工作流卡 + 反向编目向导可点 | 切 r6，进 `#/p5-provider` | 看到 4 张 R6 工作流卡；点反向编目能进 `#/p5-provider/wizard/reverse-catalog` |
| 37 | R7 P5 3 张收件箱 + 字段口径裁决可点 | 切 r7，进 `#/p5-provider` | 看到 3 张 R7 卡（标题含 "N 条待我裁决"） |
| 38 | R8 P6 绕行督查 panel | 切 r8，进 `#/p6-compliance-ops` | 底部出现 R8 直达交付清单 + 异议绕行可疑 |
| 39 | R3/R4 P3 任务过滤 + 异常回传 | 切 r3，进 `#/p3-request-flow` | 列表只剩 supplementing/need-fix 状态；右上角有"异常回传"链接 |

## 九、审计 + 合规收口（2 项）

| # | 检查项 | 怎么验证 | 预期 |
| --- | --- | --- | --- |
| 40 | 写 skill 全部产生 audit_event | 9 角色 e2e 跑完后 `sqlite3 $ZW_BRAIN_DB_PATH "SELECT COUNT(DISTINCT skill_id) FROM audit_event"` | ≥ 12（覆盖 W5.2 测试的关键 skill） |
| 41 | blockchain anchor 队列空（或可达） | `sqlite3 $ZW_BRAIN_DB_PATH "SELECT COUNT(*) FROM anchor_outbox WHERE status='pending'"` | 0 或 < 100（pending 队列正在异步处理；mock-chain 配置下应该 = 0） |

---

## 移交完成签名页

```
□ 客户验收人          ____________  日期 _________
□ M0 实施人           ____________  日期 _________
□ zw-brain 产品负责人  ____________  日期 _________

附件：
□ migration-report.json
□ verify-report.json
□ test_acceptance_9_roles_e2e.py 输出（10/10 passed）
□ WebUI 9 岗位浏览验收截图（每岗位 ≥ 1 张）
□ preflight 输出（16 段 PASS）
```

---

## 移交后保修

| 项目 | 保修内容 | 责任方 |
| --- | --- | --- |
| zw-brain 核心 | 主旅程 9 角色 e2e 通过；bug fix 7×24 | zw-brain 团队 |
| 推理网关 | 集团统一推理平台 SLA | 集团推理团队 |
| IAM/OIDC | 客户 IT 部门维护 | 客户 |
| Blockchain anchor | 视客户是否启用 | 客户 / mock-chain 默认本地 |
| 旧库导出兼容性 | 仅承诺 sd-default 17 个 dsp_* schema；新增旧库需 PR | zw-brain 团队 |

## 加固建议（生产环境）

1. **`ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH=0`** 关闭岗位切换，强制走 IAM 角色映射
2. **`ZW_BRAIN_MASK_ROLE=external`** 默认外部脱敏；只在审计回放岗位用 `internal_admin`
3. 数据库换 PostgreSQL，把 `ZW_BRAIN_DATABASE_URL` 指向 PG（schema 兼容）
4. 反向代理统一 TLS 终结 + WAF
5. `customer_export.sh` 的 `ZW_BRAIN_DB_PASSWORD` 走 Vault / KMS，不走文件
