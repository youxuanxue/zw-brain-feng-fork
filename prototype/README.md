# 产品叙事与能力边界（持续演进）

本目录保留**可编辑的产品材料**，与可点击 SPA 解耦：交互验证以正式 WebUI（`zw-brain-web/`）为准。

| 路径 | 用途 |
|------|------|
| `capability-sheets/` | 能力边界、内建 / 外部化判定与评审输入 |
| `storyboards/` | 端到端旅程与场景叙事（含负向与护栏） |

历史：仓库曾含 `prototype/ui/` 等可点击原型，已移除以降低与生产界面的重复维护成本。

## 客户交付运行主路径

`pyproject.toml` 的 wheel 交付物包含 `zw_brain/`、Alembic 迁移、WebUI 静态资产、Dashboard 静态资产、REST OpenAPI、MCP tools、A2A card/runtime bindings 与 Skill registry。客户环境只需要安装 wheel、准备 SQLite DB 路径和旧平台脱敏 dump 目录；运行时不需要旧平台在线。

### 环境变量 / Secret

| 变量 | 用途 |
| --- | --- |
| `ZW_BRAIN_DB_PATH` | canonical SQLite DB 路径，所有运行时读写的主状态库 |
| `ZW_BRAIN_TENANT_ID` | 租户 ID；当前单省单租户默认 `sd-default` |
| `ZW_BRAIN_REST_HOST` / `ZW_BRAIN_REST_PORT` | REST + WebUI 监听地址与端口 |
| `ZW_BRAIN_DASHBOARD_BFF_HOST` / `ZW_BRAIN_DASHBOARD_BFF_PORT` | Dashboard BFF 监听地址与端口 |
| `ZW_BRAIN_REST_BASE_URL` | A2A / 外部客户端看到的 REST base URL |
| `ZW_BRAIN_WEBUI_DASHBOARD_URL` | WebUI 指向独立 Dashboard 的入口 URL |
| `ZW_BRAIN_IAF_*` | IAF/OIDC 在线 IAM 对接配置；客户上线时通过部署 Secret 注入 |

不要把密码、token、client secret、证书或未脱敏敏感字段写入仓库、命令样例、迁移报告、日志或审计输出。

### 安装 / 导入 / 启动

```bash
python3 -m build --wheel
python3 -m venv .venv-delivery
. .venv-delivery/bin/activate
python -m pip install dist/zw_brain-*.whl

export ZW_BRAIN_TENANT_ID=sd-default
export ZW_BRAIN_DB_PATH=/opt/zw-brain/customer.db

zw-brain-migrate-legacy \
  --dumps-dir /path/to/desensitized-legacy-dumps \
  --db-path "$ZW_BRAIN_DB_PATH" \
  --profile customer-core-v1 \
  --reset-db \
  --strict \
  --acceptance \
  --report /opt/zw-brain/migration-acceptance-report.json

zw-brain-cli catalog.browse --payload '{"lifecycle":"all","role":"r1"}'
ZW_BRAIN_REST_HOST=0.0.0.0 ZW_BRAIN_REST_PORT=8800 zw-brain-rest
ZW_BRAIN_DASHBOARD_BFF_HOST=0.0.0.0 ZW_BRAIN_DASHBOARD_BFF_PORT=8801 zw-brain-dashboard-bff
```

REST 启动后，客户 WebUI 入口为 `http://<host>:8800/index.html`，Dashboard 入口为 `http://<host>:8801/index.html`。旧平台停止或不可访问后，只要 `ZW_BRAIN_DB_PATH` 指向已导入 canonical DB，核心查询、申请、审批、交付、异议与审计旅程仍应可运行。

### 最终离线验收矩阵

```bash
python3 scripts/export_agent_contract.py --check
python3 -m pytest tests/test_installed_legacy_migration.py tests/test_legacy_runtime_offline.py tests/test_webui_journey_contract.py tests/test_contract_projection.py tests/test_entry_runtimes.py tests/test_brain_service.py tests/test_domain_policy.py tests/test_repositories.py tests/test_database_store.py tests/test_rest_runtime.py tests/test_dashboard_bff.py
PYTHONPATH=/Users/xuejiao/Codes/dev-rules /usr/bin/python3 -m scripts.xuejiao_twin validate .xuejiao-twin-final
bash scripts/preflight.sh
```

当前离线验收用 HTTP+asset smoke 代替浏览器自动化：仓库未声明 Playwright/Selenium。在线外部依赖（IAF/OIDC、集团推理平台、国家平台、外部链）在本矩阵中使用正式 adapter/配置边界或离线 mock 验证，不把第三方 secret 写入交付包；客户上线前需要补齐对应 `ZW_BRAIN_IAF_*`、推理平台、国家平台和链适配器 Secret。
