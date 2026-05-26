---
doc_id: testing-cross-cutting-consumer-faces
status: navigation
driven_by:
  - docs/approved/zw-brain-architecture.md §6.1 / §6.5 / R3
---

# 五消费面 × Capability 投影矩阵

> **目的**：保证同一 Capability 在 WebUI / API / CLI / MCP / A2A 五个消费面的投影一致性都有 .feature 覆盖（R3 / §6.5）。
> 任意一处投影需要"手维护"都是反模式（确定性自动化运营和运维禁止）。

## 五消费面定位（基线 §6.1）

| 消费面 | 目标用户 | 首波优先级 |
|--------|---------|-----------|
| WebUI | 人类用户 | 高（Wave 0） |
| API | 第三方系统 | 高（Wave 0） |
| CLI | 运维 / Headless / 后台 Agent | 高（Wave 0） |
| MCP | IDE / Claude / Cursor 类 Agent | 中（Wave 3 硬化） |
| A2A | 外部 Agent 平台 | 中（Wave 3 硬化） |

## 覆盖矩阵：每个面被哪些 .feature 覆盖

| Capability 类别 | WebUI | API | CLI | MCP | A2A |
|---|---|---|---|---|---|
| `resource.search` | wave-0 j1-resource-discovery + wave-0 infra-contract-projection (Scenario Outline) | 同左 | 同左 | wave-0 infra-contract-projection + wave-3 mcp-hardening | wave-0 infra-contract-projection + wave-3 a2a-hardening |
| `application.draft` / `application.submit` | wave-0 j1-application-draft | 同左 | wave-0 j1-credential-issue (CLI) | wave-3 mcp-hardening (human_confirmation) | wave-3 a2a-hardening |
| `application.approve` | wave-0 j1-approval-* | 同左 | — | wave-3 mcp-hardening (trust_level 裁剪) | wave-3 a2a-hardening |
| `credential.view/issue/revoke` | wave-0 j1-credential-issue + wave-1 j1-credential-revoke | 同左 | wave-0 j1-credential-issue (CLI Scenario) | — | — |
| `catalog.publish/draft/dept_approve` | wave-1 j2-* | 同左 | — | — | — |
| `objection.submit/process` | wave-1 j1-objection-* | 同左 | — | — | — |
| `registry.*` (Capability 注册) | wave-2 b1-2-* | 同左 | wave-2 b1-2-package-registration (CLI 等价) | — | — |
| `inference.chat` (内部) | — | — | — | — | — |
| `audit.search` (B1.1) | wave-2 b1-1-* | 同左 | — | — | — |

## 投影一致性硬约束（基线 §6.5）

| 约束 | 机械检查入口 | .feature 覆盖 |
|---|---|---|
| 同一 Capability 在 5 面用同一 slug | `export_agent_contract.py --check` | wave-0 infra-contract-projection.feature |
| input_schema / output_schema 跨面一致 | 同上 | 同上 |
| `human_confirmation_required` 跨面统一 | 同上 | wave-3 mcp-hardening |
| `exposure` 字段裁剪生效 | 同上 | wave-3 mcp-hardening + wave-3 a2a-hardening |
| 任何手编辑 entry/*/ schema 文件被拦下 | preflight 段 | wave-0 infra-contract-projection (回归 Scenario) |
| 5 面投影从同一 registry 派生 | 同上 | wave-0 infra-contract-projection |

## 维护原则

- 新增 Capability → registry 写一处，5 面投影自动生成
- 任何手编辑投影文件 PR review 必拒
- Wave 3 MCP/A2A 生产硬化后，矩阵中"中"优先级面也必须满足同样的 R3 一致性要求
- 同 .feature 文件可被多个面引用（如 wave-0 j1-resource-discovery 末尾的 Scenario Outline 覆盖 API + CLI）
