---
doc_id: role-projection-views-business-review-package
status: awaiting-signoff   # awaiting-signoff → approved（业务方 sign-off 后；PR 合并 label signoff:<scope> 自动落账 D46.d）
gate: pending              # pending → signed
sign_off_required:
  - 业务方试用代表（海若产品部）
vehicle_pr: TBD（feature/p1-data-presentation-role-projection）
scope: p1-data-presentation-role-projection
driven_by:
  - 客户试用反馈 0604（业务方试用代表原话 + 截图实证）
  - docs/roles-permissions-old-platform-vs-zw-brain-handoff.md（7 角色码权威）
  - zw_brain/domain/policy.py PERMISSION_ROLES（角色↔能力映射）
  - .testing/waves/wave-1-j1-j2-closed-loop/features/j1-role-projection-views.feature
---

# 办共享申请角色投影三视图 + 真实导入数据呈现规范化 — 业务方 review 材料包

> 本材料属 **D28 角色/流程/状态机变更**，须业务方 sign-off 才进 D-编号 / 翻 Done（D46）。
> 提问的业务方试用代表是天然签字人；本包把其原话作为需求锚。
> **本组绝不自签**：`.testing/signoff/` 账本不写本 scope，PR body 标注 pending business sign-off。

## 0. 背景速览（开会前先读）

- **触发链路**：客户试用首轮反馈（0604），业务方试用代表在「办共享申请」与工作台两处发现：
  数据没分角色一锅炖、业务运营员待办不对路、真实导入单脏值裸奔。
- **本次签字范围**：3 个业务可感知决策点（三视图拆分定义 / 各角色码待办语义 / 脏数据降级规则）。
  技术实现（投影 lib、注册表、机械化分类器）由开发侧承担，不需业务方逐行确认。

### 业务方原话（需求锚，逐字）

- 缺陷 1：「是看我的已办？还是我的申请？我的授权，里面的数据没分角色，建议分开。」
- 缺陷 2：业务运营员的待办主要是「待发布目录、待发布资源、待受理申请」等，
  现在显示的内容（「城市运行专区待纳入停车场信息回流候选」「ledger.entity.base.read 能力包待审核」）不对路。
- 缺陷 3（截图）：用途列「测试」「167」脏值；提交时间跨 2023-2025 历史单与在产单无区分。

## 启动硬前置（sequencing — 强制节）

- **无上游依赖**。本组所需真实库数据（application_record 262 行 / catalog_entry / resource_asset）
  已在 sd-default 真实库就位（干净重建实证：见 §4 数据真实性）。
- 平行三组边界已读懂：渲染规则层（第一组）/ 待办机制层（第二组）/ 详情筛选层（第三组）
  各自负责；本组只做**数据语义与角色投影**，重叠文件只加投影/过滤逻辑（见 PR body 冲突清单）。

## 概念边界澄清（触及 legacy 概念）

| | 本次范围内的概念 | 易混淆的相邻概念（不在本节） |
|---|---|---|
| 本质 | 申请单按**当前岗位**投影到三视图 + 用途脏值机械降级 | 旧平台「我的待办」菜单形态（不复刻菜单，D1） |
| 旧表 / SoT | `old/12-datastructure/dsp-catalog3` data_apply（application_record 源）| 旧 R1-R8 角色矩阵（已退役，D29，本组用 7 角色码） |
| zw-brain 落点 | requests/approvals 投影 + provider 队列 + roleTodoRegistry | 待办「可点可办」机制（第二组） / hex 派生名渲染（第一组） |

## 1. 决策点一 — 三视图拆分定义（缺陷 1）

> 「一个视图只回答一个问题」是底线；具体叫法可由业务方微调（政务白话、简短动宾）。

| 视图 | 回答的问题 | 数据口径（真实库现算） | 可见岗位 | 建议（Jobs 视角） | 业务方判定 |
|---|---|---|---|---|---|
| 我的申请 | 我作为需方发起的（草稿/在途/已办结） | requests ∖ 授权态（status∉granted/effective/suspended/expired） | 全部 | **必含** — 需方主线，恒在 | ☐ 采纳 / ☐ 调整 |
| 待我办理 | 按我的角色码该我处理的（审核/审批/受理） | 部门管理员=审批队列 / 业务运营员=平台复核队列 | 仅有队列的岗位 | **必含** — 无权岗位入口不渲染（无权=不可见） | ☐ 采纳 / ☐ 调整 |
| 我的授权 | 我已获得的授权与凭据状态 | requests ∩ 授权态（granted/effective/suspended/expired），凭据诚实化承 D47 | 全部 | **必含** — 凭据 not_issued 不捏造 | ☐ 采纳 / ☐ 调整 |

## 2. 决策点二 — 各角色码待办语义注册表（缺陷 2）

> 数据驱动注册表（roleTodoRegistry.ts），非散落 if-else。每类待办 = 标题（白话）+ 计数口径 + 深链。
> 计数=0 的类目不渲染（工作台保持聚焦）。无权角色待办类型**不入表** ⇒ UI 不渲染（无权=不可见）。

| 角色码 | 待办类型（有序） | 计数口径（真实库现算） | 深链 | 建议 | 业务方判定 |
|---|---|---|---|---|---|
| 部门操作员 | 待补正的共享申请 | requests.status=need-fix | #/request-flow | **采纳** | ☐ |
| 部门管理员 | 待我审批的共享申请；待审核的部门目录 | approvals∩部门待审；catalog pending_review | #/request-flow；#/provider/inbox/catalog-review | **采纳** | ☐ |
| 业务运营员 | 待受理的共享申请；待发布的目录；待发布的资源；待补全的申请用途 | submitted/under_review；catalog approved_pending_publish；resource pending_review；用途脏单数 | #/request-flow；#/provider/inbox/catalog-review；#/provider/inbox/hookup-review；#/provider | **采纳** — 对齐业务方原话三类 + 数据质量 | ☐ |
| 安全审计员 | （无业务待办，只读督查） | — | — | **采纳** — 注册表留空 ⇒ 工作台不渲染待办 | ☐ |

## 3. 决策点三 — 脏数据降级规则（缺陷 3）

> 脏值判定**机械化**（data_quality.py 单源 + dataQuality.ts 镜像 + test_data_quality_classifier.py 守一致）。

| 规则项 | 判定 | 数据真实性 | 处置 | 建议 | 业务方判定 |
|---|---|---|---|---|---|
| 空/纯空白 | empty | 干净重建库现算（4 单，§4 口径） | 列表降级「未填写用途」+ 进供方质量队列 | **采纳** | ☐ |
| 纯数字/数字+分隔符 | numeric_only | 干净重建库现算（「167」「169,167」，§4 口径） | 同上 | **采纳** | ☐ |
| 占位测试词（枚举） | placeholder | 干净重建库现算（「测试」，§4 口径） | 同上 | **采纳** | ☐ |
| 来源区分 | source_ref/legacy_object_ref 存在=历史导入 | 干净重建库现算（92/96 历史导入，§4 口径） | 列表克制标识「历史导入」/「在产」（仅呈现，不门控动作 D47.b） | **采纳** | ☐ |

## 数字纪律（段 53 Layer 2）

- 本包不含会议时长 / worker·day / 未 stat-wrap 的「N 态」过程数字。
- 数据真实性计数（脏单 / 历史导入）由 §4 干净库实证给出口径，非估算。

## 4. 数据真实性（干净真实库实证）

> 干净重建 sd-default 真实库（application_record 262 行）跑投影口径，非本地脏库：

- apply 类用途脏值机械分类：placeholder 1（测试）/ numeric_only 2（167、169,167）/ empty 4 = 7 脏单
  （含 demand-kind 后 snapshot 投影计 9 脏单）。
- 历史导入 vs 在产：source_ref/legacy_object_ref 命中 92/96（在产 4）。
- 供方队列：catalog approved_pending_publish 3 / pending_review 11；resource pending_review 6。
- e2e 全绿（tests/e2e/role_projection_views.spec.ts 5/5）+ classifier 单测 18/18 + 后端投影 48 绿。

## 验收路径

1. 顶栏切岗位 → P3「办共享申请」：三视图 tab 按岗位投影；纯需方无「待我办理」（DOM 不存在）。
2. 切业务运营员 → 工作台 P1：待办落「待受理/待发布/数据质量」类目，无错配能力包内容。
3. P3 我的申请列表：用途脏值降级「未填写用途」，原始脏串不在用途列；历史导入/在产标识可见。
4. P5 提供方：业务运营员见「待补全的申请用途」数据质量队列；其余岗位不渲染。

## 落盘（sign-off 后 — D46.b/d，账本是唯一权威源）

- 业务方 sign-off 后：本文 status awaiting-signoff → approved；
  PR 加 label `signoff:p1-data-presentation-role-projection` + body 机读块，合并自动落
  `.testing/signoff/p1-data-presentation-role-projection.signoff.yaml`（D46.d）。
- 在此之前 feature 状态如实保持**未 Done**（无签字不翻 Done，D46）。

> **[实际落账更正]** 本材料包对应的签字账本实际落在 **`.testing/signoff/j1-role-projection-views.signoff.yaml`**（薛娇 2026-06-13 效果验收 sign-off，`covers` 含 `j1-role-projection-views.feature`）；非上行所述 `p1-data-presentation-role-projection.signoff.yaml`（该文件不存在）。
