---
status: approved
gate: signed
scope: j1-credential-revoke-semantics
kind: 决策签字
---

# j1-credential-revoke 角色矩阵 + 暂停语义 业务方 review 材料包 — 撤回/暂停的「谁能做、做到什么程度」定稿

> 本期 #181 把撤回/暂停 UI 接真能力并去假成功（含真实库申请真落库 R-004）。本地走查发现
> 交付与 `j1-credential-revoke.feature` SPEC 存在两处需业务方拍板的偏差：撤回/暂停的**角色**、
> 以及**暂停语义/撤回是否连带凭据**的深度。本材料包供业务方一次签掉,落 `.testing/signoff/`。

## 0. 背景速览（开会前先读）

- SPEC：`.testing/waves/wave-1-j1-j2-closed-loop/features/j1-credential-revoke.feature`。
- #181 实际交付（走查实测）：仅 `ROLE_ORGAN_MANAGER` 能撤回/暂停;`status-only` 暂停(无恢复、不禁凭据);撤回只改 application 状态、不连带 credential.revoke。
- SPEC 期望：撤回/暂停由 `ROLE_BUSIAUDIT`(业务运营员) + 申请人主动放弃;暂停可设恢复时间并自动恢复、凭据临时 disabled、调用方收 `credential_suspended`;撤回连带凭据 revoked。

## 启动硬前置（sequencing — 强制节）

无上游依赖。本决策只裁定 j1-credential-revoke 自身的角色与语义范围,不阻塞他项;其落地实现按裁定结果另立工单(见末节)。

## 概念边界澄清（触及「授权/凭据/暂停/撤回」核心概念）

- **撤回(revoke)** = 不可逆终态:授权作废、凭据失效,申请人需重新申请。
- **暂停(suspend)** = 可恢复的应用层计算态:授权不失效、临时不可用。本期裁定其深度(见决策 B)。
- 二者均**非** legacy「数据交换」语义,是 Agent-Native 授权生命周期动作,不复刻旧平台审批字段。

## 1. 决策点 A — 撤回/暂停的角色矩阵

| 决策点 | 候选 | 建议 | 业务方判定 |
| --- | --- | --- | --- |
| 谁能撤回/暂停已生效授权 | (1) 改 SPEC 认可现状 = `ROLE_ORGAN_MANAGER`(审批人);(2) 按 SPEC = `ROLE_BUSIAUDIT`(业务运营员) + 申请人本人主动放弃,收回 MANAGER | (2) 按 SPEC 改 policy:合规驱动的撤回归业务运营员,申请人有权主动放弃自己的授权,职责更清晰 | **(2) 按 SPEC 改 policy（BUSIAUDIT + 申请人主动放弃）** |

判定后果：#181 现状的 `ROLE_ORGAN_MANAGER` 门控为**临时**,与裁定不符;须改 policy 为 BUSIAUDIT、补「申请人主动放弃」流程(`initiated_by=applicant`、自己发起不通知自己)、补 owner 校验(非申请人不能撤他人),并收回 MANAGER。此为独立实现工单。

## 2. 决策点 B — 暂停语义深度 + 撤回是否连带凭据

| 决策点 | 候选 | 建议 | 业务方判定 |
| --- | --- | --- | --- |
| 暂停语义 + 撤回连带凭据的本期范围 | (1) Wave1 收窄:`status-only` 暂停(无恢复时间/自动恢复/凭据 disabled)、撤回不连带 credential.revoke;(2) 本期做满 SPEC | (1) Wave1 收窄:先把「真能用、无假成功、状态真落库」立住,完整暂停恢复链与凭据连带按真实业务节奏后置 | **(1) 接受 Wave1 收窄** |

判定后果：SPEC 中「暂停设恢复时间/7 天自动恢复/凭据临时 disabled/调用方 credential_suspended」与「撤回连带 credential.revoke」标 Wave2 Deferred,本期不实现;UI 对暂停/撤回保持诚实(真落库或诚实报错,不假成功)。

## 数字纪律

本材料包不含进度/任务计数等过程数字;技术状态码(如调用方 403)与申请单标识为行为描述,非过程指标。

## 落盘（sign-off 后 — D46.b/d,账本是唯一权威源）

- 本文 frontmatter `status: approved`(业务方已拍 A=(2)、B=(1))。
- 账本：`.testing/signoff/j1-credential-revoke-semantics.signoff.yaml`(`kind: 决策签字`、`decision_only: true`、`covers: []` — 决策签字不直接抬 feature 状态;feature 翻 Done 待 A 实现 + 测量绿后另签 covers)。
- 一致性由段 54 + 段 63 校验。
