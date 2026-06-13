---
doc_id: mcp-hardening-business-review-package
status: awaiting-signoff   # awaiting-signoff → approved（业务方 sign-off 后；PR 合并时 label signoff:<scope> 自动落账本 D46.d）
gate: pending              # pending → signed
sign_off_required:
  - 海若产品部业务方
vehicle_pr: <PR 号，待建>
scope: mcp-hardening
driven_by:
  - .testing/waves/wave-3-protocol-tenant-national/features/mcp-hardening.feature（SPEC）
  - docs/approved/zw-brain-architecture.md §6.1 五消费面 / §10.4 MCP/A2A 生产级硬化 / §5.4.5 AI 不直接触发责任性写
---

# MCP 投影生产级硬化 业务方 review 材料包 — 协议硬化项确认

> **本文是 D35 决策签字材料包**（协议硬化，触及 §5.4.5 反约束 + trust ladder）。
> 通过 preflight 段 53/54 守卫。**本文不写 signed_by**——签字事实由 PR 合并时
> GitHub approvers 自动落 `.testing/signoff/mcp-hardening.signoff.yaml` 账本（D46.d）。
>
> **[实际落账更正]** 本材料包对应的签字账本实际落在 **`.testing/signoff/intest-conditional-mcp.signoff.yaml`**（产品研发负责人 2026-06-03 sign-off，与 j1-approval-conditional 合签，`covers` 含 mcp-hardening.feature）；非上行所述 `mcp-hardening.signoff.yaml`（该文件不存在）。

## 0. 背景速览（开会前先读）

- 触发链路：MCP 是五消费面之一（IDE/Claude/Cursor 类 Agent 入口）。本期把 MCP 投影从
  「能列工具」硬化到「生产级可观测 + 鉴权 + 信任分级 + 结构化错误」，确保 AI 工作流调用
  与 WebUI/API 一致且不能越权。状态轴现为 **InTest（测量绿 / 待签）**。
- 本次签字范围：业务可感知 4 项 —— ① 责任性写操作的人工确认门；② 外部 Agent 信任分级裁剪；
  ③ 结构化错误（非 500 黑盒）；④ MCP 工具列表与契约单一事实源（禁手编辑）。

## 启动硬前置（sequencing — 强制节）

- 无上游依赖。所有 P0+P1 capability 已注册、MCP manifest 由 capability registry 自动生成
  （`zw_brain/entry/mcp/tools/*.json` 为生成产物，`export_agent_contract.py --check` 守 drift）。

## 1. 决策点：协议硬化项（生产级 MCP 投影）

> 真实性标签：行为由 `zw_brain/entry/mcp/server.py` + `zw_brain/shared/runtime_config.py`
> （MCP trust ladder + quota）实装，pytest 驱动真实 MCP entry-path（非 mock）断言。

| 硬化项 | 实现 / 行为 | 建议（Jobs 视角） | 业务方判定 |
|---|---|---|---|
| 责任性写操作人工确认门（§5.4.5 AI 不直接触发责任性写） | hcr capability 未带 confirmed → 返回 `pending_confirmation` 结构化信封 + `retry_with={confirmed:true}`，不提交、不静默 None；工具描述含 "Requires user confirmation" + annotations.humanConfirmationRequired | **含** — AI 必须在 IDE 内显式确认才能 commit | ☐ 含 / ☐ 改 |
| 外部 Agent 信任分级裁剪（trust ladder untrusted/verified/platform） | 默认 caller=untrusted；责任性写要求 ≥verified（`MCP_MIN_WRITE_TRUST_LEVEL`），untrusted 调用拒 + audit reject reason=trust_level_insufficient；读能力对 untrusted 仍开放 | **含** — 默认从严，平台可经 `ZW_BRAIN_MCP_CALLER_TRUST_LEVEL` 升信任 | ☐ 含 / ☐ 改 |
| 结构化错误（非 500 黑盒） | quota_exceeded → JSON-RPC -32005 + `data.retry_after`；tool_not_found → -32601；trust_level_insufficient → -32003 + `data.trust_level`；IDE/Agent 可识别 | **含** — 错误可被 Agent 识别处置，非黑盒 | ☐ 含 / ☐ 改 |
| MCP 工具列表与契约单一事实源 | 工具列表与 OpenAPI 一致；exposure 不含 mcp 的 capability 在 MCP 不可见（直接调 tool_not_found）；手编辑 tools/*.json 由 `export_agent_contract.py --check` 反向探测拦下 | **含** — 投影从同一 registry 派生，禁手编辑 | ☐ 含 / ☐ 改 |

## 测试证据（pytest 真写库，本期实跑通过）

> 标签：驱动真实 `zw_brain.entry.mcp.server` entry points（invoke_tool / _handle_tools_call /
> list_tools），临时 DB + dev-IAM-bypass 身份，读真实 audit / capability_call 行或 JSON-RPC 信封，无 stub。

- `tests/test_wave3_mcp_hardening.py` — **17 个 pytest 全通过**（2026-06-02 capture 实跑 `.................`）。
  覆盖 S2–S7：source=mcp 审计/capability_call provenance（含直接 in_process 调用不误标 mcp）/
  human_confirmation pending 信封 + 描述标记 / quota_exceeded+retry_after / tool_not_found /
  exposure 过滤 + SurfaceNotEnabledError / trust_level 裁剪（拒+audit / verified 通过 / 读放行）/
  export_agent_contract --check 无 drift。
- `tests/test_wave3_protocol_tenant.py` — 协议/多租户底座回归，4 pass。
- 实装：`zw_brain/entry/mcp/server.py` + `zw_brain/shared/runtime_config.py`（trust ladder + quota）+
  `scripts/export_agent_contract.py`（MCP descriptor + --check）。

## 诚实留债

- **quota 口径**：当前为进程内 per-minute 窗口（`ZW_BRAIN_MCP_TOOL_QUOTA_PER_MINUTE`），
  非分布式/持久化配额；多实例部署下口径需业务确认（按实例还是按租户/调用方）。
- **trust_level 部署级**：caller 信任级由部署环境变量 `ZW_BRAIN_MCP_CALLER_TRUST_LEVEL`
  静态决定（stdio daemon 无 per-message client 身份）；per-caller 动态鉴权待 B1.2 立项。

## 落盘（sign-off 后 — D46.b/d，账本是唯一权威源）

- [ ] **A**：vehicle PR 加 label `signoff:mcp-hardening` + PR body `<!-- signoff -->` 机读块
      （`scope: mcp-hardening` / `kind: 决策签字` / `covers: .testing/waves/wave-3-protocol-tenant-national/features/mcp-hardening.feature`）。
- [ ] **B**：本文 frontmatter `status: approved`。
- [ ] **C**：CLAUDE.md 追加 D 决策条（记实质裁决）。

## sign-off PR body 机读块

```
<!-- signoff
scope: mcp-hardening
kind: 决策签字
decision_only: false
covers:
  - .testing/waves/wave-3-protocol-tenant-national/features/mcp-hardening.feature
-->
```
