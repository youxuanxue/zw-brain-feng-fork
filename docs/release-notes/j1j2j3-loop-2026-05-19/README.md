# J1+J2+J3 三旅程闭环验证 — 浏览器端到端 + 截图走读

**日期**：2026-05-19
**驱动文档**：`docs/approved/zw-brain-information-architecture-v2.md`（3 旅程 IA）+ `docs/approved/zw-brain-roles-v2.md`（7 角色）+ `docs/approved/zw-brain-gate1.1-retrofit-2026-05-19.md`（GATE-1.1 评审）

## 验证目标

新基线（GATE-1.1 retrofit 后 7 角色 + 3 旅程 IA）在真浏览器中三旅程主流程都可走通：
- **J1 找数→用数**：发现 → 申请 → 审批 → 凭据领取 → 调用使用
- **J2 挂数→维数**：提供方反向编目 / 收件箱字段裁决 / 平台发布
- **J3 看全局→处异常**：审计回放 / 合规告警 / K12 大屏

## 验证产出（双重证据）

| 类别 | 产出 | 用途 |
|---|---|---|
| 自动化 | `tests/test_j1j2j3_browser_matrix_e2e.py`（6 用例 CDP）+ `tests/test_webui_browser_e2e.py`（既有 1 完整链路用例） | CI 可跑（本地 Chrome 可用即可，默认 `@browser_e2e` skip） |
| 截图 | 本目录下 5 张 PNG + 本走读文档 | 业务/客户验收人眼可读 |

## 复现流程

```bash
# 1. 启动 dev 环境
bash scripts/start-local.sh
# 自动起 REST(8800) + Dashboard(8801) + bypass + auto-seed

# 2. 浏览器打开
open http://127.0.0.1:8800/
# 点击"开发模式登录 dev-bypass"

# 3. 按下方 5 截图剧本逐步操作 + 截图
```

## 5 张关键截图剧本

### 01-j1-credential.png — P4 凭据领取页（J1 闭环最关键缺口已补）

**操作**：
1. 角色切到 `ROLE_ORGAN_OPERATER`（部门操作员）
2. URL hash 输入 `#/p4-delivery-exchange/credential/REQ-2026-04-26-0006`
   - 这是 seed 中已审批通过的婚姻登记申请，凭据已 auto-on-approval 签发

**应看到**：
- 顶部：`访问凭据（婚姻登记"全省通办"）` 标题 + `已签发` 状态
- 中部：3 个面板（App Key 卡 + App Secret 卡 + 调用示例 tab）
  - app_key 显示：`AK-DEMO-REQ-2026-04-26-0006-9E096141`
  - app_secret 默认隐藏（点击"显示"按钮可切换）
  - 调用示例：curl / Python / Java 三种，每个有"复制"按钮
- 右侧：凭据基本信息（有效期、配额）+ 调用监控入口 + （审批人/主管可见）重新签发按钮

**点击体验**：
- 复制 curl 命令 → 终端跑：`curl 'https://api.gov-data.local/v1/services/...?app_key=AK-DEMO-...' -H 'X-App-Key: AK-DEMO-...'`
- 此命令是 demo URL（gov-data.local 不存在），但展示了完整的调用 contract

### 02-j1-sharing-type-ui.png — P3 reviewDetail 共享类型分流面板

**操作**：
1. 角色切到 `ROLE_ORGAN_MANAGER`（部门管理员）
2. URL hash 输入 `#/p3-request-flow/review/REQ-2026-04-25-0011`（停车场，无条件共享）
3. 然后切换 URL hash 输入 `#/p3-request-flow/review/REQ-2026-04-26-0006`（婚姻登记，有条件共享）

**应看到（无条件共享）**：
- 顶部新增"共享类型 / 审批分流"面板
- 显示：`无条件共享（主管部门一步审批）`
- 主审批按钮：`通过并立即下发凭据`（不再是"通过并下发补录"）

**应看到（有条件共享）**：
- 同一面板显示：`有条件共享（主管部门受理 → 提供方审批）`
- 主审批按钮：`受理并转提供方审批`
- 注脚：`两段审批流程在审批流引擎上线前以本期最小承接表达`

**业务意义**：2026-05-19 retrofit 处置兑现 — 旧平台审批角色边界模糊问题，新设计按 sharing_type 字段分流而非按角色拆分。

### 03-j2-provider-wizard.png — P5 反向编目工作流向导

**操作**：
1. 角色切到 `ROLE_ORGAN_MANAGER`（部门管理员，提供方）
2. URL hash 输入 `#/p5-provider/wizard/reverse-catalog`
3. 点击"加载候选 schema 清单"按钮

**应看到**：
- 顶部：`反向编目工作流` 主标题 + `选源 → 预填 → 提交，一气呵成` 副标题
- 第 1 步：候选 schema 列表（如有 customer_acceptance_up.sh 导入数据则有多条）
- 选一个 schema 后第 2 步：90% 预填的字段表 + 绿/黄/橙置信度色块

**业务意义**：J2 反向编目链路完整 — 旧平台"基于数据表反向编目"能力的现代化实现。

### 04-j3-compliance-audit.png — P6 合规运营审计回放

**操作**：
1. 角色切到 `ROLE_SECURITY_AUDIT`（安全审计员）
2. URL hash 输入 `#/p6-compliance-ops`

**应看到**：
- 主面板：`合规运营` 标题
- 左侧：争议列表 / 异议处理 6 子流程框架
- 右侧：审计事件时间线，含 `application.resource.submit.after` / `application.resource.review.after` / `summary.confirm.after` / `delivery.reconcile_receipt.after` / `backflow.confirm.after` 等 audit phase
- 审计回放有 J1 全链路证据（按时间倒序）

**业务意义**：J3 审计督查闭环 — 旧平台合规督查角色的承接；只读不改业务事实。

### 05-j3-dashboard-link.png — P8 K12 大屏入口卡

**操作**：
1. 角色切到 `ROLE_BUSIAUDIT`（业务运营员/主管部门）
2. URL hash 输入 `#/p8-integration-admin`

**应看到**：
- 主页面：`受控接入治理`
- 右上 aside：新增 **K12 数据治理大屏（独立部署）** 卡片
  - 卡片描述：独立 zw-brain-dashboard 部署单元，与主大脑解耦
  - 启动提示：如未启动请运行 `bash scripts/start-local.sh`（自动启 8801）
  - 主按钮：`打开 K12 数据治理大屏 →`（链接 http://127.0.0.1:8801/，新标签页打开）

**点击体验**：
- 点击按钮 → 新标签页打开 zw-brain-dashboard（如 start-local.sh 同时启了 8801 则可见全量大屏）

**业务意义**：D24 IA 收敛 — 把基线 §5 旧 S2 "平台接入与扩展" 与 K12 大屏的关系明确：K12 是独立只读 dashboard 单元；J3 看全局→处异常旅程从 P8 提供入口。

## 角色 / 旅程 / 截图对应矩阵

| 角色 | 截图 | 旅程 | 验证维度 |
|---|---|---|---|
| ROLE_ORGAN_OPERATER 部门操作员 | 01 | J1 | 凭据领取 + 调用示例 |
| ROLE_ORGAN_MANAGER 部门管理员 | 02, 03 | J1 + J2 | 共享类型分流审批 + 提供方反向编目 |
| ROLE_BUSIAUDIT 业务运营员 | 05 | J3 | K12 大屏入口 |
| ROLE_SECURITY_AUDIT 安全审计员 | 04 | J3 | 审计回放时间线 |
| 多角色穿插 | (既有 customer_main_journey e2e) | J1 全链路 | 申请 → 审批 → 补录 → 汇总 → 交付 → 审计 |

## 自动化 e2e 跑法

```bash
# 本地 Chrome 可用：
.venv/bin/python -m pytest tests/test_j1j2j3_browser_matrix_e2e.py -v -m browser_e2e

# 期望：6 个测试全过；如 Chrome 不可用会 skip
```

## 验收清单

- [ ] 截图 5 张已保存到本目录
- [ ] 每张截图按上方剧本可复现
- [ ] 自动化 e2e 在本地 Chrome 可跑全过
- [ ] 5 张截图能向客户老板/部门负责人 5 分钟讲完三旅程核心闭环
- [ ] preflight PASS（19 段全通）
- [ ] 仓内历史角色码字面值残留为 0（preflight 段 19）

## 已知限制（demo 边界）

- 凭据使用 `AK-DEMO-` / `SK-DEMO-` 前缀，不接 IAM 加密存储（评审主文档 §八 P0 延后立项）
- 调用 URL 模板 `https://api.gov-data.local/v1/services/...` 是 demo（域名不存在）；接生产网关后替换
- 审批流程目前是单一硬编码状态机，sharing_type 仅做 UI 分流（D25 审批流引擎延后立项）
- 表单字段硬编码（D26 表单 schema 化引擎延后立项）
