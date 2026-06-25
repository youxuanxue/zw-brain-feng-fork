# spec-delta：数据源管理 + 反向编目/挂接全链路

## Background

供数方需要一条可演示、可验收的端到端路径：**登记数据源 →（有表）反向编目 /（有目录）资源挂接**，且 UI 文案面向业务人员而非工程人员。PR #340 在 backend 投影与 6 个 capability 基础上，补齐 WebUI 三页联动与乔布斯式 UX 走查修复。

## Delta

### ADDED

- `datasource_endpoint_projection` 表 + legacy `dsp_pipelines.meta_database` 脱敏导入
- 6 个 capability：`datasource.endpoint.*` / `datasource.table.*` / `datasource.connectivity.test`
- WebUI：`/provider/datasources`、反向编目三步向导、挂接向导数据源下拉
- `provider.datasource_endpoints` snapshot 投影
- Playwright 验收：`tests/e2e/catalog_datasource_walkthrough.spec.ts`

### MODIFIED

- 提供方首页页头：先登记数据源，再编目或挂接
- 数据源管理：显示名称/库实例名、删除确认、连通性中性态、分区计数
- 反向编目：操作员创建后回首页（非越权进审核页）；加载态；在线编制分流
- 挂接向导：数据源选项带分区、中文 placeholder、空态引导
- 操作员 snapshot redaction 补 `datasource_endpoints`（修复列表空白）

---

## 本地部署（客户验收环境）

> **范围**：sd-default 单租户、dev 免登录 + 角色切换（`start-local.sh`）。生产见 [`docs/deployment/docker-image-deployment.md`](deployment/docker-image-deployment.md)。

### 0. 前置

| 项 | 要求 |
|---|---|
| 分支 | `feature/catalog-datasource-e2e`（PR #340） |
| 工作目录 | 检出该分支的 zw-brain 根目录（可用 worktree） |
| Python | 3.13+，`.venv` 已装 `pip install -e '.[postgres]'` |
| PostgreSQL | `docker compose up -d postgres`（默认 `127.0.0.1:5432/zw_brain`） |
| 示例 dump | `old/10示例数据/dump-dsp_pipelines-*.sql` 等（无 dump 时仅验手工登记 B3–B6） |
| 浏览器 | Chrome / Edge；自动化验收需 Playwright |

**注意**：若本机 `:8800` 已被 Docker 旧镜像占用，请用 **`:8803`** 起 feature 分支代码（见 §1 备选端口）。

### 1. 一键灌库 + 起 Web（推荐）

```bash
cd /path/to/zw-brain   # feature/catalog-datasource-e2e

# worktree 若无 old/，链到主仓示例数据：
# ln -sf /path/to/zw-brain/old ./old

export ZW_BRAIN_TRIAL_SCHEMAS="dsp_bsp dsp_catalog dsp_metaresource dsp_require dsp_handling dsp_example dsp_pipelines"
bash scripts/trial-up.sh --skip-health
# trial-up 灌库后会尝试占 8800；若端口冲突可忽略 REST 启动失败，改用手动 start-local

export NO_PROXY=127.0.0.1,localhost${NO_PROXY:+,$NO_PROXY}
bash scripts/start-local.sh
# 默认 http://127.0.0.1:8800
```

**端口被占用时**（Docker 等已占 8800）：

```bash
export ZW_BRAIN_REST_PORT=8803
bash scripts/start-local.sh
# 浏览器 / e2e 改用 http://127.0.0.1:8803
```

**健康检查**：

```bash
curl -s http://127.0.0.1:8800/health   # 或 :8803
```

浏览器打开对应地址，页头 **岗位切换** 选 **部门操作员 / 部门管理员**。

### 2. Docker 全栈（可选，易与 feature 分支代码不一致）

```bash
cp .env.example .env
docker compose up -d
curl -s http://127.0.0.1:8800/health
```

Compose 镜像未含本 PR 时，**客户演示请优先 §1**（源码 `start-local.sh`），勿混用旧容器验新 UI。

### 3. 自动化验收（实施工程师）

```bash
export NO_PROXY=127.0.0.1,localhost
export ZW_E2E_BASE_URL=http://127.0.0.1:8803   # 与 start-local 端口一致

npx playwright test tests/e2e/catalog_datasource_walkthrough.spec.ts
```

---

## 产品验收清单（走查版）

**角色**：部门操作员（主）、部门管理员（辅）  
**入口**：提供方管理 → `#/provider`  
**走查环境**：worktree + `trial-up --skip-health` + `ZW_BRAIN_REST_PORT=8803 start-local`（2026-06-25）

### A. 环境与首页

| # | 步骤 | 预期 | 结果 |
|---|---|---|---|
| A1 | 打开 `/health` 与首页 | 200，无白屏 | **通过**（8803 `/health` 200） |
| A2 | 页头切换操作员/管理员 | 均可进 P5 | **通过**（Playwright） |
| A3 | 读 P5 页头说明 | 含「先登记数据源，再编目或挂接」 | **通过** |
| A4 | 页头药丸顺序 | 数据源管理在在线编制之前 | **通过** |

### B. 数据源管理 `#/provider/datasources`

| # | 步骤 | 预期 | 结果 |
|---|---|---|---|
| B1 | 点左侧 前置库/标准库/服务库 | Tab 显示数量；列表随分区切换 | **通过**（前置库（8）等） |
| B2 | 搜索名称/部门 | 列表过滤正确 | **通过**（登记后按名称搜索） |
| B3 | 「登记数据源」→ 填显示名称+库实例名 → 保存 | 成功「数据源已登记」；列表出现；连通「未探测」 | **通过** |
| B4 | 「检查连通」 | toast 说明同步记录；状态刷新 | **通过** |
| B5 | 编辑联系人 → 保存 | 字段更新 | **通过**（「数据源已更新」） |
| B6 | 删除 → 确认框 → 确定 | 行消失 | **通过**（需 confirm + 表格断言） |
| B7 | **负向**：业务运营员访问该 URL | 被拦截或不可见 | **通过**（重定向离开 datasources） |

**文案门禁**：页面不出现「endpoint / 元数据 / 导入示例数据」等业务可见工程词 → **通过**

### C. 反向编目 `#/provider/wizard/reverse-catalog`

| # | 步骤 | 预期 | 结果 |
|---|---|---|---|
| C1 | 选「前置资源」/「已落地资源」 | 数据源下拉随来源变化 | **通过**（下拉有选项） |
| C2 | 选数据源 → 下一步 | 出现库表列表或「正在加载库表…」 | **通过** |
| C3 | 无表空态 | 提示确认库表采集；分流在线编制 | **通过**（代码 + 空态文案走查） |
| C4 | 选表 → 第 3 步 | 字段列表；目录名可编辑 | **部分**（dump 下部分数据源无表，未逐表点选 C4） |
| C5 | **操作员** 创建草稿 | 回 **提供方管理**，不进审核页 | **通过**（代码路径 + 角色门控） |
| C6 | **管理员** 创建草稿 | 进入 **反向编目审核** | **部分**（有表时走 field-decision；无表跳过） |
| C7 | 无字段时创建按钮 | 禁用 | **通过**（`:disabled` 绑定） |

### D. 资源挂接 `#/provider/wizard/hookup-submit`

| # | 步骤 | 预期 | 结果 |
|---|---|---|---|
| D1 | 库表形态 →「选择数据源」 | 选项含分区；选中回填 | **通过**（下拉可见 + 选项>1） |
| D2 | 选「不选，手动填写」 | 可手填 | **通过**（index 0 清空） |
| D3 | 无数据源空态 | 引导至数据源管理 | **通过**（代码走查） |
| D4 | 选目录 + 表名 + 字段 → 保存草稿 | 成功或业务级错误（非 500） | **未验**（需已发布目录 + 完整挂接数据，留人工） |

### E. API 抽检

```bash
BASE=http://127.0.0.1:8803
curl -s -X POST "$BASE/api/skills/datasource.endpoint.list" \
  -H 'Content-Type: application/json' \
  -d '{"role":"ROLE_ORGAN_OPERATER"}' | python3 -c "import sys,json;d=json.load(sys.stdin);print('total',d.get('total'));assert 'password' not in str(d).lower()"

curl -s "$BASE/api/snapshot?role=ROLE_ORGAN_OPERATER" | python3 -c \
  "import sys,json;p=json.load(sys.stdin).get('provider',{});print('endpoints',len(p.get('datasource_endpoints',[])))"
```

| # | 预期 | 结果 |
|---|---|---|
| E1 | list 无密码字段；total≥0 | **通过**（total=3） |
| E2 | snapshot 含 `datasource_endpoints` | **通过**（endpoints=3，部门可见域子集） |

### 签收

- **结论**：**通过**（A/B/E 全过；C/D 核心链路 + 权限 + 文案全过；C4/C6/D4 依赖有表/已发布目录项为部分或未验，不阻断演示主线）
- **阻断项**：无

---

## Validation

**2026-06-25 第二轮走查（push c2b07c59 后）**

| 检查 | 命令 / 动作 | 结果 |
|---|---|---|
| Legacy 导入 | `trial-up.sh --skip-health`（含 dsp_pipelines） | OK；投影 **18** 条（前置 15 / 标准 1 / 服务 2） |
| 本地起服 | `ZW_BRAIN_REST_PORT=8803 start-local.sh` | REST + WebUI 8803 健康 |
| API E1/E2 | curl list + snapshot | total=3，endpoints=3，无 password |
| Playwright | `catalog_datasource_walkthrough.spec.ts` | **5/5 通过** |
| 单测 | `pytest tests/test_datasource_endpoint.py tests/test_provider_snapshot_projection.py::test_operater_snapshot_includes_datasource_endpoints` | 全绿（同 PR） |
| preflight | `./scripts/preflight.sh` | 提交前必跑 |

**已修复阻断缺陷（首轮回合）**

1. 操作员 snapshot 缺 `datasource_endpoints` → redaction 补 key
2. 操作员创建反向草稿越权跳审核页 → 按角色分流回 `#/provider`
