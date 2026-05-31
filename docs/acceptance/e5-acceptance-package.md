---
doc_id: e5-acceptance-package
status: approved
gate: signed
scope: e5
evidence: .testing/acceptance/e5/evidence.json
sign_off_required:
  - 海若产品部业务方
signed_off_by: 海若产品部业务方
signed_off_at: 2026-05-29
vehicle_pr: "#164"
driven_by:
  - "e5 WebUI / 5 消费面投影（17 feature，本次补效果验收签字）"
---

# e5 WebUI / 5 消费面投影 — 效果验收材料包

> **本文是 D37 验收守卫的首个 dogfood**：e5（WebUI 8 页面 + 5 消费面投影 + NL 加速器，
> plan 17 feature 全 completed）交付已久但从未走效果验收。本材料按 D37 模板产出，
> 证据由 `capture_acceptance_evidence.py` **现场跑出**，preflight 段 55 守卫。
>
> **状态**：`approved` —— 机器证据就位 + 业务方 2026-05-29 A/B/C 清单走查全过，效果验收通过。

## 验收范围

- **覆盖**：J1/J2/B1.1/B1.2 用户可见路径（P2 发现 / P3 申请·异议·供需 / P4 交付·凭据·调用监控 /
  P5 编目·发布 / B1.1 合规四 panel / B1.2 接入·身份治理 / P7 专题订阅）+ 5 消费面契约投影一致性。
- **不覆盖（避免"验收即全行"误读）**：e6 平台基建（推理网关 F2 / 部署 F8 仍 blocked）、
  Wave 2 三引擎正式发布（preview banner 态）、F9 TopicPackage delivery（未建）。

## 验收点 + 证据

> 每条挂 `.testing/acceptance/e5/evidence.json` 里的 check 名；段 55 回链校验 result=pass。

| 验收点 | evidence（机读证据） | 结果 | 业务方判定 |
|---|---|---|---|
| 5 消费面（WebUI/REST/CLI/MCP/A2A）契约单源投影一致 | `5 消费面投影一致`（contract，REST=196/CLI=1/MCP=62/A2A=1/Skills=187 零漂移） | pass | ☐ 通过 / ☐ 打回 |
| 后端 / 契约测试套全绿 | `后端 / 契约测试套`（pytest exit 0，0 failed） | pass | ☐ 通过 / ☐ 打回 |
| WebUI 关键路径浏览器活跑 | `WebUI 活跑验收（customer_acceptance_checklist）`（e2e 15 passed / 1 skipped，覆盖 P2/P3/P4/P5/B1.1/B1.2/P7） | pass | ☐ 通过 / ☐ 打回 |

## 业务方眼见为实（人验，机器测不了的）—— 2026-05-29 全过 ✅

机器证据是底线；"效果"由业务方在浏览器（`scripts/start-local.sh` 起本地、顶栏切角色）
按客户 / 用户视角走查。本次全部通过。

**A 客户（买方）关心 — 整体效果**

| # | 检查项 | 判据 | 结果 |
|---|---|---|---|
| A1 | 不是旧平台换皮 | ≤10 场景页、无旧菜单树、走旅程非翻菜单 | ✅ |
| A2 | 解决旧痛点（入口埋深 + 无订阅闭环） | P2 一步到申请；P7 专题订阅闭环可用 | ✅ |
| A3 | 真实数据非 Mock | 全程 sd-default 山东真目录，无假数据 | ✅ |
| A4 | 审计可查 | 发起/审批/发布后审计·调用记录可查（D4） | ✅ |
| A5 | 不复刻已签字不做项 | 无旧专区后台站 / 示范应用门户 / basesubject 建库页 | ✅ |
| A6 | 一处契约五处一致 | WebUI/REST/CLI/MCP/A2A 抽查一致（投影零漂移） | ✅ |

**B 用户（按角色日常活）关心**

| 角色 | 检查项 | 结果 |
|---|---|---|
| 部门操作员 `ROLE_ORGAN_OPERATER` | P2 检索出结果 / NL 加速器搜出资源 / P3 发起申请 / P4 领凭据·三语可读 | ✅ |
| 部门管理员 `ROLE_ORGAN_MANAGER` | P5 待办非零可点 / 反向编目向导生成建议 / P3 部门审批 | ✅ |
| 业务运营员 `ROLE_BUSIAUDIT` | P5 发布（含 duplicate_warnings）/ B1.1 运营·合规面 / 跨组织全域可见 | ✅ |
| 安全审计员 `ROLE_SECURITY_AUDIT` | 可查全域审计 / 进不去 P7 主导航（入口不渲染） | ✅ |
| 越权（操作员进身份治理） | B1.2 入口不渲染（无权=不可见，非"可见+403"） | ✅ |

**C 跨切非谈判项**

| # | 检查项 | 结果 |
|---|---|---|
| C1 | 无权不可见（不渲染，非可见+禁用/403） | ✅ |
| C2 | 中文、无工程术语泄漏（无 skill_id/manifest/slug） | ✅ |
| C3 | 真数据量下不白屏/超时/截断关键列 | ✅ |
| C4 | 异常路径中文友好提示（驳回/无权重定向） | ✅ |

## 落盘（业务方 2026-05-29 验收通过）

- [x] **A**：签字落 `.testing/signoff/e5.signoff.yaml` 账本，`covers` 列被签 feature（D46.b 单一权威源；status 由账本现算，无 promote 翻转）
- [x] **B**：vehicle PR 加 label `signoff:e5` + body 机读块（合并自动落账本）
- [x] **C**：CLAUDE.md 追加 D38
- [x] **D**：本文 `status: approved`

> 落盘后由段 54 校验 A/C 一致；本文证据真实性 + 结构由段 55 校验。

## dogfood 暴露的真实约束（D37 记录）

- **证据 provenance**：capture 须在 PR 分支的工作环境跑。本次因 worktree 无 venv，
  在共享主仓（sibling commit）采集，故 evidence `git_sha` 非本分支祖先 → 段 55 如实
  WARN「陈旧/异线」。**正常流程在 PR commit 上采集即无此 WARN**。待办：让 worktree 可
  跑验证 或 CI 在 PR commit 上重采。
- **采集隔离**：e2e 活跑把共享 dev DB 撑到 200MB+，导致随后 pytest 变慢/与他人 pytest
  抢 sqlite 锁。验收采集应用**独立/临时 DB**，勿污染共享 dev 库。
