---
title: 重构平台权限梳理-0609 角色↔权限边界重对齐（多点 GATE）
scope: permission-realignment-0609
status: approved  # 角色/权限/状态机多点裁决（D28 GATE，decision_only）：产品研发负责人 2026-06-09 两轮 sign-off（账本 .testing/signoff/permission-realignment-0609.signoff.yaml）
date: 2026-06-09
deciders: 海若产品部产品研发负责人（GATE 决策门）
related_docs:
  - docs/approved/zw-brain-roles.md
  - CLAUDE.md D55 决策索引（承 D54/D52/D34/j1-credential-revoke 决策A）
---

# D55 — 重构平台权限梳理-0609 角色↔权限边界重对齐（多点 GATE）

> **类型**：角色/权限/状态机多点裁决 + 一词一概念（D28 GATE，decision_only）
> **签字**：薛娇（产品研发负责人），2026-06-09（两轮）
> **触发链路**：业务方权限专项梳理 [`old/问题反馈/重构平台权限梳理-0609.docx`](../../old/问题反馈/重构平台权限梳理-0609.docx)（6 角色 × 越界/缺失/细化 21 条）。
> **核查依据**：当前 HEAD 代码事实（file:line 实读 `zw_brain/domain/policy.py` + `zw-brain-web` 导航/动作门）+ 旧平台权威菜单 `old/20260519/平台系统角色菜单梳理v5.xlsx`（全表实读）。
> **性质**：实现前方向裁决（decision_only，不抬 `.feature` 状态）；各任务 P1–P23 实现由 [`old/问题反馈/权限梳理-0609-修复任务目标清单.md`](../../old/问题反馈/权限梳理-0609-修复任务目标清单.md) 承接，落地后各带 D37 效果验收。账本单源 `.testing/signoff/permission-realignment-0609.signoff.yaml`。

---

## 总纲

本轮 90% 是「角色↔权限矩阵错配」而非功能缺陷——业务方拿旧平台 v5 菜单授权当尺子校 zw-brain 的越权/缺权。权威矩阵有四处副本须同改并由守卫 set-equal：`policy.py:PERMISSION_ROLES` ↔ `pageAccess.ts:ACTION_ROLE_GATES` ↔ `productShellNav.ts:roles` ↔ `web_snapshot_redaction.py`。

退役后 **6→5 角色，身份码干净闭环**：做（部门操作员）/审（部门管理员）/管（业务运营员）/维（平台运维员）/查（安全审计员）；保（安全管理员）本期退役。

---

## 裁决一 ｜退本期（消解冲突 + 精简面）

- **P6 专题包整体退出本期**：下线 `zones-pack` shell + `topic.package.*` 能力面（保数据不删库，仅去入口/可见性 + 快照裁剪）。连带消解原 ⊥**D34**（专区=业务运营员策展容器）的「专题包创建下放操作员/管理员」争议与「安全审计员订阅越界」。记债待专题包重新立项恢复。
- **P16 安全管理员退出本期**：v5「安全管理员=数据安全中心（分类分级/识别/脱敏/密钥/风险处置/资产透视）」五大模块本期全缺，角色无专属工作面 → 退役 `ROLE_SECURITY_ADMIN`（`role_codes.py` 白名单 + `ROLE_DISPLAY_NAMES_ZH` + CHECK 约束 + dev-bypass），零散权限（`package.rollback/exposure/trust_level`、`standard.asset.recommend`、`security.scan.result.sync`）改派或退役，守卫/快照同步。记债待数据安全中心立项恢复。

## 裁决二 ｜反转 D53/F1：领数据加部门操作员（P13）

- **v5 依据**：数据订阅·资源订阅（已授权资源/库表订阅/文件下载/文件夹订阅/任务监控/订阅任务对账/数据探查）= 部门操作员 + 部门管理员。
- **现状**：0605 的 F1（D53）把领数据收窄到**仅部门管理员**（`productShellNav.ts:59` + `policy.py:55-56`）。
- **裁决**：**反转 F1**，领数据回归 部门操作员 + 部门管理员。`delivery.list/view`、`delivery.subscription.manage`、`subscription.terminate` 补 `ROLE_ORGAN_OPERATER`；`delivery-exchange` 导航加 OPERATER。叠加 P18 后 delivery 角色集 = {OPERATER, MANAGER}（安全审计员退出）。**须改 D53 全文**（F1 收窄口径作废）。

## 裁决三 ｜业务运营员保留受理、退出申请人（P7）

- **docx 依据**：业务运营员「在申请流程中扮演的是**处理别人申请**的角色，而不是自己去提申请的角色」——即受理（初级审核），非申请人。
- **裁决**：`request-flow` shell 对 `ROLE_BUSIAUDIT` **保留开放**（承受理 + j1-credential-revoke 决策 A 的收回/暂停，二者兼容）；前端隐「我的申请 / 我的授权 / 资源发现 / 我的异议 / 登记需求」申请人入口（无权不可见）；业务运营员 request-flow 视图收敛为「受理工作台」；`demand.register/list`、`objection.case.create` 去 BUSIAUDIT。「待我办理空」根因=受理待办未投影，并入 P21。

## 裁决四 ｜受理/审核两级口径（P21，改 D49 关联）

- **裁决**：**无条件共享** = 业务运营员受理即终结；**有条件共享** = 业务运营员受理（第一级）→ 部门管理员审核（第二级）。受理 = 初级审核。
- **现状相反**：无条件 `application.resource.review = {ROLE_ORGAN_MANAGER}` 管理员单步（`policy.py:178`）；有条件 `application.dept_approve`（管理员部门审 `:183`）→ `application.platform_approve = {ROLE_BUSIAUDIT}`（业务运营员平台复核 `:185`）——即两级**角色与顺序对调**。
- **实现约束**：调整审批两级角色/stage 顺序为「受理(BUSIAUDIT)→审核(MANAGER)」（或新增 `application.resource.accept` 受理能力）；`sync.py:sync_request_todos` 增 BUSIAUDIT 受理待办投影（深链受理收件箱，修「待我办理空」）；优先在 D49 审批流引擎层用 schema 节点表达两级。**精确状态名 / 驳回回退路径在实现时定**。属状态机变更，**改 D49 关联全文**。

## 裁决五 ｜流程表单配置归平台运维员（P3，反转 D49 配置角色）

- **docx 依据**：审批流程/申请表单/智能推荐配置属系统级配置，应是平台运维员权限。
- **现状错位**：导航 `engines.roles = [BUSIAUDIT, SYSTEM]`（`productShellNav.ts:104`），但三引擎 commit 类能力全 = `ROLE_ORGAN_MANAGER`（`policy.py:231-243`，D49/Wave-2 项目级）——「谁能看配置页」与「谁能存配置」两拨人。
- **裁决**：定性**平台级系统配置 = 平台运维员（ROLE_SYSTEM）独有**。三引擎全部 commit/nl_draft/promote/revert 能力 `ROLE_ORGAN_MANAGER` → `ROLE_SYSTEM`；`engines` 导航去 BUSIAUDIT、仅 SYSTEM。引擎走查 / `find_live_for_scope` / approval_flow_walker 机制不变，仅角色门收归。**反转 D49 配置角色**（部门管理员项目级提交 → 平台运维员平台级），**改 D49 全文**。注：用户面 `recommendation.similar_catalog.suggest`（申请前置目录推荐，`policy.py:244`）是消费侧，**不随配置侧迁移**，保 OPERATER/MANAGER/BUSIAUDIT。

## 裁决六 ｜A 档照 v5 校正（口径已被旧平台事实锁定）

| 任务 | 角色 | 越权/缺权 → 目标态（v5） | 关键 file:line |
|---|---|---|---|
| P1 | 业务运营员 | 退供数维护，仅保发布权 | `policy.py:206,214`（去 BUSIAUDIT）；`productShellNav.ts:76` |
| P2 | 业务运营员 | 退外部系统接入（归平台运维员） | `productShellNav.ts:94`（去 BUSIAUDIT）；`adapter.external/cascade.*` |
| P4 | 业务运营员 | 退身份治理（归平台运维员） | `policy.py:62-64,307`；`productShellNav.ts:114` |
| P8 | 平台运维员 | 退审计日志，保服务调用监控 | `policy.py:70-76`（去 SYSTEM）；查审计 shell 拆分 |
| P9 | 部门管理员 | 退审计查看，保异议/合规 | `policy.py:65-66,70-76`（去 MANAGER） |
| P11 | 操作员+管理员 | 在线目录编制可达 | `pageAccess.ts:39`（route 加 MANAGER） |
| P14 | 部门操作员 | 反向编目开放 | `policy.py:321-322`（加 OPERATER）；`pageAccess.ts:49` |
| P17 | 安全审计员 | 完全退出找数据 | `policy.py:38,50-51`（去 SECURITY_AUDIT）；`productShellNav.ts:39` |
| P18 | 安全审计员 | 退领数据（凭据/回执/下载） | `policy.py:106,108,190,55-56`（去 SECURITY_AUDIT） |

> P5/P12/P20 为可见性落账 + 工作台一致性投影（无角色集冲突）；P10 为部门管理员供数审核待办投影（**「发布」类属业务运营员待办、不挂管理员**，管理员投真实审核 stage）。

## 裁决七 ｜安全审计员收敛为只读监督者（P22，上帝视角补漏）

- **docx 角色澄清明示**：安全审计员「权限范围高度收敛，仅能查看基础支撑日志、运行监控审计日志、数据安全事件日志，**无任何写操作权限**，是'查'的角色」。
- **现状矛盾（per-item 问题清单未列、上帝视角对照角色定义发现）**：`policy.py` 给 SECURITY_AUDIT 大量**写**能力——异议 `objection.case.accept/reject/assign/reply/review/escalate/close`(`:269-276`)；合规调查 `compliance.case.open/assign/resolve/close`+`signal.ingest`+`risk.event.ingest`+`rule.configure`(`:248-254`)；运维工单/巡检 `ops.ticket.create/close`+`ops.shift_handover.submit`(`:380-382`)；谱系/质量 `metadata.lineage.upsert`(`:211`)/`ops.catalog.quality.upsert`(`:212`)；应急熔断 `system.toggle_outage`(`:392`)；`legacy.*.import`(`:314-315`)/`org|actor.projection.sync`(`:310-311`)/`security.scan.result.sync`(`:261`)。
- **裁决**：安全审计员收敛为**纯只读监督者**——①异议写权移除 SECURITY_AUDIT（保 `objection.*.query` 只读；异议=业务运营员+部门管理员 per v5）；②运维工单/巡检/交接归还 `ROLE_SYSTEM`（平台运维员，v5「运维管理」+ docx「维」）；③谱系/质量 upsert、legacy import、projection sync、toggle_outage、scan.result.sync 去 SECURITY_AUDIT；④合规调查 `compliance.case.*`/`risk`/`signal` 随 P16 数据安全中心退本期一并处置（暂留只读 query 或整体退役）。

---

## 实现约束（共同）

1. 四副本同改 + 守卫 set-equal（`policy.py` / `pageAccess.ts` / `productShellNav.ts` / `web_snapshot_redaction.py`），`tests/test_role_codes_alignment.py` / `test_action_role_gates_aligned_with_backend_policy` 兜底。
2. 无权=不可见（不渲染入口/按钮/深链，禁「可见+禁用/403」）。
3. 改已签 D-决策全文 3 处：**D53**（P13 反转领数据收窄）、**D49**（P21 受理两级 + P3 配置角色，两处）。
4. D37 效果验收按角色逐个真 UI 走查；尤须验「无写权的安全审计员」「承接后台四模块的平台运维员」「业务运营员受理工作台」三处变化最大的角色。
