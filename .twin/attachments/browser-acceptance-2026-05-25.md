# 浏览器端到端验收报告 — 2026-05-25

**分支：** `feature/e5-f13-f17-browser-closure`（PR #108）  
**环境：** `bash scripts/start-local.sh` → `http://127.0.0.1:8800`，`NO_PROXY=127.0.0.1,localhost`  
**DB：** `.data/zw_brain.db`（sd-default）

## 自动化

| 命令 | 结果 |
|------|------|
| `npm run e2e` | **56 passed / 4 skipped**（含 customer_acceptance_checklist 12 条） |
| `bash scripts/headless_j1_demo.sh` | 5/5 |
| `python scripts/customer_demo_j1.py` | exit 0（含异议 STEP-7~12） |
| `python scripts/customer_demo_j2.py` | exit 0 |
| `./scripts/preflight.sh` | PASS |

## 逐页结论（Jobs：视觉 / 数据 / 业务 / 逻辑）

| 页面 | 视觉 | 数据 live | 主按钮 → skill | 结论 |
|------|------|-----------|----------------|------|
| P1 工作台 | 待办列表非空 | ✓ | NL 减摩 → live parse | PASS |
| P2 发现 | 资源卡可点 | ✓ | 发起申请 → `request.create` | PASS |
| P2 目录浏览 | 目录树表 | ✓ | 跳转发现页检索 | PASS（F16） |
| P3 在途/审批 | 状态中文 pill | ✓ | 审批 → `approval.case.decide` 枚举对齐 | PASS |
| P3 异议 | 列表+新建+详情 | ✓ | 创建 → `objection.case.create`；提交 → submit | PASS（F13） |
| P3 供需 | 登记+阶段推进 | ✓ | `demand.register` / `demand.phase.advance` | PASS（F14） |
| P4 交付列表 | 任务链 snapshot 全量 | ✓ | 点编号 → 详情非占位 | PASS（F15） |
| P4 任务详情 | DetailPanel | ✓ | 对账 → `delivery.reconcile_receipt` | PASS |
| P4 凭据 | Key + 三语 + 已签发 | ✓ | `credential.query` + `credential.sample.render` | PASS |
| P5 提供方 | 四卡待办非零 | ✓ | 发布 → `catalog.entry.publish` + duplicate_warnings 面板 | PASS（E2 F3 UI） |
| P5 子路由 | wizard/inbox 无占位 | ✓ | 各 wizard 写路径 200 | PASS |
| P7 专题包 | 列表+详情 | ✓ | 订阅 → `topic.package.subscribe` | PASS |
| B1.1 合规 | 4 panel + 助手 | ✓ | 调查助手 live | PASS |
| B1.2 接入 | 3 tab + 包详情链 | ✓ | 写操作 confirm + package.view | PASS（F17） |
| B1.3 三引擎 | Wave2 预览 banner | ✓ | 草稿/预览/入库按钮（E3 F7） | PASS（F16） |

## 仍属人类关卡（非代码缺口）

- **E1 F11 / E2 F6 / E3 F8**：business-signoff（业务方签字）
- **E4 F5/F6**：AgentRuntime 触发式（T1 外部 Agent 接入前不建 runtime）
- **E6 F2/F7**：集团推理 SDK 凭据 / 客户机房 CI/CD dry-run

## 已知 deferred（非主路径）

- `/login` `/profile` `/migration-acceptance` `/integration-admin/iam-governance` 仍 PagePlaceholder（辅助页）
