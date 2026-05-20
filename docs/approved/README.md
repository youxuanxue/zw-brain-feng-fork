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
| **[zw-brain-architecture.md](zw-brain-architecture.md)** | **架构基线（唯一权威）** | spine——所有架构主张、产品形态、路线图、R-编号设计主张在此 |
| [zw-brain-data-model.md](zw-brain-data-model.md) | 数据模型详细展开 | spoke——基线 §9 的事实展开 |
| [zw-brain-roles.md](zw-brain-roles.md) | 7 角色 + tag_lead_dept 详细规范 | spoke——基线 §5.1 / §11 R10/R11 的事实展开 |
| [research-yibiaotong.md](research-yibiaotong.md) | 一表通调研事实 | spoke——基线 §3.4 C 引用的事实证据 |

## 单一事实来源原则

- **架构主张 / 路线图 / R-编号 / 产品形态** = `zw-brain-architecture.md`
- **领域聚合 / 表设计 / 状态机** = `zw-brain-data-model.md`
- **角色码 / 菜单覆盖** = `zw-brain-roles.md` + `zw_brain/domain/role_codes.py`（机械对齐）
- **D-编号 GATE 后决策** = CLAUDE.md §决策记录
- **R[1-8] 用户角色编号** = **已退役**（D23，基线 §11 R10）

## 文档纪律

**新增决策**：追加到 `zw-brain-architecture.md` 修订记录 + 必要时升 §11 R-编号；不新建独立文档。

**业务流程决策**：触发 R13 元规则，必须业务方 sign-off 后才进入基线 D/R 编号空间。

**事实补充**：直接吸收进 `zw-brain-architecture.md` 主体（§3 / §9.2 等已 reality-driven）；不留外挂事实档案。

**废弃决策**：从仓库删除（git 历史保留即可）；不留 `superseded` / `archived` / `pending` 半死不活状态——这种状态导致实现漂移。

## 历史决策档案位置

GATE-1（2026-04-18）+ GATE-1.1 retrofit（2026-05-19 业务方 sign-off）+ v4.1 二轮反转（2026-05-20）+ reality check（2026-05-20）的全部决策已吸收进 `zw-brain-architecture.md` 的：

- 修订记录段（按时间线列出每次变更的性质 + 触发源）
- §11 关键设计主张（R1-R17）
- §3 reality-driven 章节（旧平台真实事实）

完整历史细节（21 条业务反馈处置、reality check 调研过程等）从 git 历史 `feature/v4.1-jobs-refocus` 分支的早期 commit 找回。
