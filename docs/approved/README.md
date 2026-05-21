---
doc_id: docs-approved-readme
status: approved
gate: navigation-only
approved_by: xuejiao02
authors:
  - 薛娇（产品研发负责人）
  - Claude Code (claude-opus-4-7)
related_docs:
  - docs/approved/zw-brain-architecture.md
  - docs/approved/zw-brain-data-model.md
  - docs/approved/zw-brain-roles.md
  - docs/approved/research-yibiaotong.md
related_prs: []
related_commits: []
self_review_rounds: 1
phase_after_approval: 持续维护（每次新增/删除 approved 文档时同步更新）
---

# docs/approved 单一权威导航

> **唯一权威基线**：[`zw-brain-architecture.md`](zw-brain-architecture.md)。
> 其他三份是基线的细节展开（spoke），不是并列权威。
> 跨仓库映射执行级文档见 [`docs/reconstructs/README.md`](../reconstructs/README.md)。

## 文档清单（4 份）

| 文件 | 角色 | 关系 |
|---|---|---|
| **[zw-brain-architecture.md](zw-brain-architecture.md)** | **架构基线（唯一权威）** | spine——所有架构主张、产品形态、路线图、R-编号（R1-R15，持续追加）设计主张在此 |
| [zw-brain-data-model.md](zw-brain-data-model.md) | 数据模型详细展开 | spoke——基线 §9 的事实展开 |
| [zw-brain-roles.md](zw-brain-roles.md) | 7 角色 + tag_lead_dept 详细规范 | spoke——基线 §5.1 / §11 R10/R11 的事实展开 |
| [research-yibiaotong.md](research-yibiaotong.md) | 一表通调研事实 | spoke——基线 §3.4 C 引用的事实证据 |

## 外部规范源（非 approved spoke，但被基线 §八 / R15 引用）

| 文件 | 角色 |
|---|---|
| [../agent-runtime/product-integration-guide.md](../agent-runtime/product-integration-guide.md) | AgentRuntime 产品集成与声明式 Agent 开发指南（`anp-agent/v1.2` 速查 + Embedded SDK / Standalone HTTP 集成 + 生产 readiness checklist） |
| [../agent-runtime/agent-runtime-api-cn.md](../agent-runtime/agent-runtime-api-cn.md) | AgentRuntime API 接入文档（session / task / event-stream / workspace / A2A / 鉴权契约） |

> 这两份是**外部协议规范源**，不属基线 spoke（不在 approved 治理范围内），但 R15 决策的实施必须以这两份为准。新接入外部 Agent 必须直接产出 `AGENT.yaml`。

## 单一事实来源原则

- **架构主张 / 路线图 / R-编号 / 产品形态** = `zw-brain-architecture.md`
- **领域聚合 / 表设计 / 状态机** = `zw-brain-data-model.md`
- **角色码 / 菜单覆盖** = `zw-brain-roles.md` + `zw_brain/domain/role_codes.py`（机械对齐）
- **D-编号 GATE 后决策** = `CLAUDE.md` §决策记录

## 文档纪律

**新增决策**：追加到 `CLAUDE.md` §决策记录（D-编号） + 必要时升 `zw-brain-architecture.md` §11 R-编号；不新建独立文档。

**业务流程决策**：触发 R13 元规则，必须业务方 sign-off 后才进入基线 D/R 编号空间。

**事实补充**：直接吸收进 `zw-brain-architecture.md` 主体（§3 / §9.2 等）；不留外挂事实档案。

**废弃决策**：从仓库删除（git 历史保留即可）；不留 `superseded` / `archived` / `pending` 半死不活状态——这种状态导致实现漂移。
