# sd-default 客户现场部署 runbook

> 📍 **你在哪一份 zw-brain 文档？**
> | 你是谁 | 看哪份 |
> | --- | --- |
> | 客户运维 / 实施工程师（部署 + 操作） | [`docs/deployment/sd-default-onboarding.md`](./sd-default-onboarding.md)（0.5-1 工作日 runbook） |
> | 客户验收人 / 签收 | [`docs/deployment/handover-checklist.md`](./handover-checklist.md)（41 项核验签收） |
> | 业务用户 / 8 角色试岗 | [`.experiences/QUICKSTART.md`](../../.experiences/QUICKSTART.md)（5 分钟人话指南） |
> | 产品评审 / 架构师 / 角色体验回顾 | [`.experiences/README.md`](../../.experiences/README.md)（角色体验手册） |
> | 客户老板 / CIO 5 分钟看效果 | `bash scripts/customer_demo_5min.sh`（[demo 剧本](../release-notes/customer-demo-5min.md)） |
>
> **本文件**：`docs/deployment/sd-default-onboarding.md` = 客户运维 0.5-1 工作日 runbook；每步带『做什么 / 怎么验证 / 失败排查』。签收看 handover-checklist。

> **适用**：山东省（sd-default）单租户单省政务现场。
> **目标**：从一台空机器开始，到 9 角色（M0 + R1-R8）能在 zw-brain 上完成
> 自己的主旅程，**控制在 0.5-1 个工作日内完成**。

本文档是 W5 客户移交清单（`handover-checklist.md`）的执行手册。
每个步骤都给出"做什么 / 怎么验证 / 失败排查"三段。

---

## 0. 环境前置

### 0.1 必备组件

| 组件 | 版本 | 用途 |
| --- | --- | --- |
| 操作系统 | RHEL 8+ / Ubuntu 22.04+ / Anolis OS 8+ | 主机 OS |
| Python | 3.13+ | 运行时（`pyproject.toml` 锁定） |
| SQLite | 3.40+ | 默认 canonical DB；后续可换 PostgreSQL |
| MySQL 客户端 | 5.7+ / 8.0+ | 仅在客户机房现场跑 `customer_export.sh` 时需要 |
| bash | 4+ | 运行 `scripts/*.sh` |

或者用 Docker 镜像（详见 `docker-image-deployment.md`），跳过 Python / SQLite 单独安装。

### 0.2 必备访问

| 访问 | 用途 | 提供方 |
| --- | --- | --- |
| 客户旧库 (`dsp_*` schemas) | 一键导出 17 张旧表 | 客户 DBA 提供只读账号 |
| IAM/OIDC 端点 | 统一身份登录（IAF 集成） | 客户 IT 部门 |
| 推理网关密钥引用 | LLM 调用走 `zw_brain.shared.inference.client` | 集团推理平台 |
| Blockchain anchor 端点（可选） | 审计回执上链 | mock-chain 默认本地；客户现场需提供 |

---

## 1. 拉代码并安装依赖

```bash
git clone <repo-url> /opt/zw-brain
cd /opt/zw-brain
uv venv && uv pip install -e .
```

**验证**：
```bash
.venv/bin/python -c "import zw_brain; print(zw_brain.__name__)"
# zw_brain
```

**失败排查**：
- `ModuleNotFoundError: zw_brain` → 检查 `pyproject.toml` 是否完整、`uv sync` 是否成功
- 编译依赖缺失（如 cryptography）→ 装 `gcc python3-devel openssl-devel`

---

## 2. 数据库初始化

### 2.1 创建数据目录 + alembic upgrade

```bash
export ZW_BRAIN_DB_PATH=/data/zw-brain/runtime.db
mkdir -p $(dirname $ZW_BRAIN_DB_PATH)
.venv/bin/alembic upgrade head
```

**验证**：
```bash
.venv/bin/python -c "
from zw_brain.shared.migrate import ensure_runtime_schema
ensure_runtime_schema()
from zw_brain.shared.db import create_session_factory
from zw_brain.domain.models import LegacyObjectMappingRecord
with create_session_factory()() as s:
    print('schema OK; legacy_object_mapping count:', s.query(LegacyObjectMappingRecord).count())
"
# schema OK; legacy_object_mapping count: 0
```

### 2.2 默认租户写入

zw-brain 单租户单省，默认 `tenant_id=sd-default`、`region_code=370000000000`。
无需手工写入——所有 mapper / skill / API 默认走 `_DEFAULT_TENANT_ID`。

---

## 3. 配置环境变量

把以下写到 `/etc/zw-brain/zw-brain.env`（或 systemd unit 的 `EnvironmentFile`）：

```bash
# 基础
ZW_BRAIN_DB_PATH=/data/zw-brain/runtime.db
ZW_BRAIN_LEGACY_DUMPS_DIR=/data/zw-brain/legacy-imports
ZW_BRAIN_LEGACY_DATASTRUCTURE_DIR=/opt/zw-brain/old/12-datastructure

# WebUI / REST
ZW_BRAIN_DEPLOYMENT_LABEL="山东政务数据大脑 · 生产"
ZW_BRAIN_WEBUI_IDENTITY_LABEL="您的账号"
ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH=0     # 生产关闭岗位切换（仅训练环境打开）

# IAF/OIDC 统一身份
ZW_BRAIN_IAF_AUTH_SERVER_URL=https://iam.sd.gov.cn/realms/zw
ZW_BRAIN_IAF_CLIENT_ID=zw-brain-prod
ZW_BRAIN_IAF_ISSUER=https://iam.sd.gov.cn/realms/zw
ZW_BRAIN_IAF_AUDIENCE=zw-brain-prod
ZW_BRAIN_IAF_CLIENT_SECRET_REF=arn:secrets:iaf-zw-prod  # 走密钥引用，不明文

# 推理网关（集团统一）
ZW_BRAIN_INFERENCE_GATEWAY_URL=https://inference.inspur.com/v1
ZW_BRAIN_INFERENCE_API_KEY_REF=arn:secrets:inspur-inference-zw

# Blockchain anchor (可选；mock-chain 是默认)
ZW_BRAIN_BLOCKCHAIN_ENDPOINT=https://chain.sd.gov.cn/anchor
ZW_BRAIN_BLOCKCHAIN_KEY_REF=arn:secrets:chain-zw

# 读侧脱敏档位 (按需调；external = 默认对外，internal_admin = 仅审计回放)
ZW_BRAIN_MASK_ROLE=external
```

**验证**：
```bash
source /etc/zw-brain/zw-brain.env
.venv/bin/python -c "
from zw_brain.shared.inference.client import get_client
client = get_client()
print('inference client:', client.__class__.__name__)
"
```

**失败排查**：
- `inference client gateway not reachable` → 推理网关网络问题；客户先用 mock client 跑通后切换
- IAF 配置错误 → WebUI 登录页会显示"统一身份未配置"，可临时用 `ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH=1` 走训练态

---

## 4. 客户现场一键导出（M0.1）

在客户旧库所在机房执行（**仅这一步需要 mysql 客户端**）：

```bash
export ZW_BRAIN_DB_PASSWORD="$(cat /run/secrets/legacy_db_pw)"  # 走密钥管理，不写文件
bash /opt/zw-brain/scripts/customer_export.sh \
  --db-host=10.x.x.x --db-port=3306 --db-user=zw_export \
  --output-dir=/data/zw-brain/legacy-imports/B-$(date +%Y%m%d-%H%M) \
  --batch-id=B-$(date +%Y%m%d-%H%M) --tenant=sd-default
```

脚本会：
1. `mysqldump` 17 个 dsp_* 库 + data_resource
2. 按 `old/12-datastructure/*.xml` 的 `sensitive_level` 字段做**列级脱敏**（phone/email/idcard/addr/secret/ip/connstr 等）
3. 生成 `.crc` 和 `.rowcount` 文件 + `manifest.json`
4. `verify` 阶段重读 hash 防篡改

**验证**：
```bash
cat /data/zw-brain/legacy-imports/B-*/manifest.json | jq .redaction_summary
# 应看到 phone / email / addr / secret 几大类的脱敏计数
```

**失败排查**：
- `mysqldump failed` → 检查只读账号权限、网络、mysql 客户端兼容性
- crc32 mismatch → 磁盘 I/O 问题；重跑 export（脚本支持 `--force` 覆盖）

---

## 5. 批量导入 + 验证（M0.2-M0.4）

```bash
bash /opt/zw-brain/scripts/customer_acceptance_up.sh
```

这个脚本会按顺序：
1. `import_legacy_dumps.py` 把 dump 流式 parse 进 7 个 mapper（catalog_metadata / connect / exchange / governance / objection / pipelines / projections / service / topic_package）
2. 生成 `legacy_object_mapping` 一对一回指证据
3. `verify_legacy_migration()` 端到端 dry_run → apply → repeat_apply 三阶段验收
4. 跑 6 个 smoke skill（catalog.browse / catalog.resource_view / metadata.* / provider.view / zone / ops.catalog.statistics）

**验证**：
```bash
ls /data/zw-brain/customer-acceptance/
# parse-stats.jsonl  migration-report.json  verify-report.json  runtime-smoke.txt
cat /data/zw-brain/customer-acceptance/verify-report.json | jq .total_unresolved
# 0
```

**失败排查**：
- `total_unresolved > 0` → 看 `migration-report.json` 的 `by_canonical_type` 找哪类对象无法解析
- `total_conflicted > 0` → 一对多映射；通常是同一 legacy_object_ref 被两个 canonical 引用，开 PR #43 doc/reconstructs/legacy-import-mapping-v1.md 核对预期

---

## 6. 启动服务

### 6.1 REST + WebUI（主服务）

```bash
.venv/bin/zw-brain-rest --host 0.0.0.0 --port 8800
```

systemd unit 模板：
```ini
[Unit]
Description=zw-brain REST + WebUI
After=network.target

[Service]
User=zw-brain
WorkingDirectory=/opt/zw-brain
EnvironmentFile=/etc/zw-brain/zw-brain.env
ExecStart=/opt/zw-brain/.venv/bin/zw-brain-rest --host 0.0.0.0 --port 8800
Restart=always

[Install]
WantedBy=multi-user.target
```

**验证**：
```bash
curl -s http://localhost:8800/health | jq .
# {"status":"ok","tenant":"sd-default", ...}
curl -s http://localhost:8800/openapi.json | jq '.paths | length'
# 180+
```

### 6.2 Dashboard BFF（只读运营面）

```bash
.venv/bin/zw-brain-dashboard-bff --host 0.0.0.0 --port 8801
```

### 6.3 反向代理（可选）

把 WebUI 8800 / Dashboard 8801 / 统一身份回调地址挂在 nginx 后面，统一 TLS 终结。

---

## 7. 9 角色 e2e 验收

跑端到端 acceptance 测试，**这就是客户现场移交的最终签收依据**：

```bash
.venv/bin/python -m pytest tests/test_acceptance_9_roles_e2e.py -v
```

应该看到 10/10 通过：
- `test_01_m0_acceptance_status_query` — M0 验收 status query
- `test_02_r1_demand_registration_intent_submit` — R1 需求登记
- `test_03_r7_reverse_draft_create_then_confirm` — R6→R7 反向编目闭环
- `test_04_r2_application_review_with_grade_policy` — R2 分级授权策略审批
- `test_05_r6_quality_rule_and_api_service` — R6 检测规则 + 任务触发
- `test_06_r3_supplement_skill_callable` — R3 接补差任务派发
- `test_07_r4_exception_callback_handoff` — R4 异常回传
- `test_08_r5_objection_four_substages` — R5 异议四子流程
- `test_09_r8_audit_list_and_direct_access` — R8 审计抽查 + 直达绕行
- `test_10_audit_chain_covers_all_roles` — audit 链覆盖所有角色

**失败排查**：
- 某个角色测试失败 → 看具体 skill_id 与对应角色的 `PERMISSION_ROLES` 配置；客户现场如自定义岗位映射需同步改 `zw_brain/domain/policy.py`
- audit_event 缺事件 → 检查 `audit_bus.configure_sink` 是否在 BrainService 初始化时被调用

---

## 8. WebUI 浏览验收

打开 `https://<host>:8800/`，按顺序切换岗位走通：

| 岗位 | 主入口 | 关键动作 |
| --- | --- | --- |
| M0（隐式：R7 + R8） | `#/p0-migration-acceptance` | 11 张工作队列卡片状态 |
| R1 | `#/p1-workbench` | "我的 API 凭据"卡 + "需求登记前置"表单 |
| R2 | `#/p3-request-flow/review/<req>` | 分级授权策略 inline 表单 |
| R3/R4 | `#/p3-request-flow` | "只看我的"列表过滤 + "异常回传" |
| R5 | `#/p6-compliance-ops/dispute/<obj>` | 异议四子流程 4 张表单卡 |
| R6 | `#/p5-provider` | 4 张 R6 工作流卡（反向编目 / API 服务化 / 检测规则 / 资源挂接） |
| R7 | `#/p5-provider` | 3 张 R7 收件箱（字段裁决 / 挂接审核 / 供需对接） |
| R8 | `#/p6-compliance-ops` | "R8 绕行督查"panel |

**客户现场签收脚本**：让客户每个岗位 1-2 个真实业务对象走完一次主旅程，把审计日志截图作为签收附件。

---

## 9. 回滚 / 缺口补迁

### 9.1 单 schema 回滚

```bash
.venv/bin/python -m zw_brain.entry.legacy_migration.rollback \
  --tenant=sd-default --legacy-system=dsp_catalog --commit
```

把 `legacy_object_mapping.mapping_status` 翻 `rolled_back`，写一次 `audit_event(skill_id=legacy.migration.rollback)`。**不删除** canonical 记录；重跑 import 时 mapper 会用 `idempotency_key` 命中既有 `AdapterRunRecord` 跳过已成功的部分。

加 `--also-suspend-canonical` 同时把 `catalog_entry.lifecycle_status` / `resource_asset.lifecycle_status` / `application_record.status` / `approval_case.current_status` 翻 `suspended`。

### 9.2 批次回滚

```bash
.venv/bin/python -m zw_brain.entry.legacy_migration.rollback \
  --tenant=sd-default --batch-id=B-2026-05-16-01 --commit
```

按 `legacy_object_mapping.evidence_json.import_batch_id` 过滤；同样不删除 canonical。

### 9.3 缺口补迁

第二批新增数据时，重跑 `customer_export.sh` + `customer_acceptance_up.sh`。`AdapterRunRecord.idempotency_key` 保证已成功的对象不会重复写入；新对象会追加到 canonical + mapping。

---

## 10. 移交前最终核验

按 `docs/deployment/handover-checklist.md` 走完 41 项检查。客户现场最终签收 = checklist 全打勾 + W5.2 全 10 项 e2e 通过 + WebUI 9 岗位浏览通过。

---

## 附录 A：常见运行时问题

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| WebUI 加载白屏 | `_assets/zw-brain-web` 静态资源路径错 | 检查 `ZW_BRAIN_WEBUI_PUBLIC` 或 nginx root |
| 登录卡 IAF 重定向 | `ZW_BRAIN_IAF_ISSUER` / `_AUDIENCE` 不匹配 | 找 IT 部门核 OIDC 配置 |
| 一些 skill 返回 403 / AccessDeniedError | 角色未在 `policy.PERMISSION_ROLES` 中授权 | 确认账号在 IAM 角色映射；或临时用 webui_role_switch |
| 审计写入失败 → 整个写 skill 抛 AuditWriteError | DB 锁 / 网络问题 | 不要 swallow（D4 元规则）；检查 DB |
| 推理网关调用超时 | 网关 down / 密钥过期 | 走 `zw_brain.shared.inference.client` 的 fallback；不调第三方 LLM SDK（D6） |

## 附录 B：组件清单（按 `pyproject.toml`）

- 入口：`zw-brain-rest`, `zw-brain-dashboard-bff`, `zw-brain-cli`, `zw-brain-mcp`, `zw-brain-a2a`, `zw-brain-migrate-legacy`
- 测试：`pytest tests/` 全套 441+ 用例
- 契约：`scripts/export_agent_contract.py` 生成 5 端口契约（180 REST / 1 CLI / 61 MCP / 1 A2A / 192 Skills）
- preflight：`bash scripts/preflight.sh` — 16 段机械检查
