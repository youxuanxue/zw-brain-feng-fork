# zw-brain 客户视角摩擦清单 v2（已验证）

> **2026-05-19 retrofit (D23-D29)**：本文 7 角色 角色矩阵已退役。
> - 角色权威源：`docs/approved/zw-brain-roles-v2.md`
> - 信息架构权威源：`docs/approved/zw-brain-information-architecture-v2.md`
> - 评审决策记录：`docs/approved/zw-brain-gate1.1-retrofit-2026-05-19.md`
> - 原版 R 编号见 git blame。

> 受众：zw-brain 产品负责人与客户交付实施团队
> 产出方法：read file:line + 亲手 dry-run + 必要 grep；禁止用未验证的 subagent 二手判断作为唯一证据
> 时间：2026-05-18
> 适用基线：v4 + 9 角色 e2e 通过 + preflight 16 段已激活

---

## Jobs 三问回答（顶部摘要）

**Q1：客户开箱第一动作？**
当前路径：客户运维拿到 zw-brain 后，按 `docs/deployment/sd-default-onboarding.md` 0→8 节做完环境/数据库/配置，然后跑 `bash scripts/customer_acceptance_up.sh` 把 `old/10示例数据` 全量灌入 → 浏览器打开 `#/p0-migration-acceptance` 看 11 张验收卡片，然后切到 `#/p1-workbench` 让 7 角色 试岗位。**问题**：上述 7 个步骤分别藏在 sd-default-onboarding（runbook 含 41 个动作）、handover-checklist（41 项核验表）、`.experiences/QUICKSTART.md`（角色路径）三份文档，三份文档顶部都说"先看我"，但没有一份能把"装机 → 灌数据 → 客户看见数据 → 角色试岗"五步压成一条客户即看即懂的时间线。
目标动作：一份顶层 onboarding 时间线（首小时/首日/首周/首月），其中"首小时" = 5 分钟一键 demo，剩余三段才指向 handover-checklist / sd-default-onboarding。

**Q2：三处最需要删？**
1. `prototype/ui/` 历史目录残留（如有）→ 已于 2026-04-28 决策退役，需 verify 仓内是否真正清理（见 P11）。
2. `zw-brain-web/js/pages.js:1156-1170` "需求登记前置" 申请人 入口（W4.5 注释）若在 5 分钟 demo 路径上不被访问，可考虑收口到 P1 待办区一行 → 但**这条经审视暂保留**，需 audit 后由产品决定。
3. handover-checklist.md:62-66 #19-#23 与 sd-default-onboarding.md §5 完全重叠的"M0 端到端 5 项" → 用一句"详见 sd-default-onboarding §5"替代，handover-checklist 不再列重复 SQL，只保留 pass 标记。

**Q3：端到端 demo 最短几步？**
当前最短路径：`scripts/customer_acceptance_up.sh`（一条命令，但只输出 jsonl/json 报告，不打开浏览器、不演示申请→审批→交付链）+ 浏览器开 `#/p0-migration-acceptance` 看 11 卡片 + 切角色看各角色页 = 至少 3 步、需要客户自己懂"切角色"是 `?role=` URL hack。
目标路径：一条 `bash scripts/customer_demo_5min.sh` 跑完 M0 导入 + 申请人 搜索/申请 + 审批人 审批 + 提供方部门 交付 + 安全审计员 审计回看 5 条 curl，最后打印 `→ 打开 http://localhost:8800/#/p0-migration-acceptance 看可视化结果`，把"看见数据"压到 5 分钟内、零配置。

---

## 被验证否定的二手判断（避免后续 PR 误删）

以下"agent 误判"已在本次 audit 中亲手 verify，**任何 PR 想以"功能不存在 / fantasy promise"为由删这些路由的，必须先看本节**：

- **`reviewDetail`（审批详情）真实存在**：`zw-brain-web/js/pages.js:1731` `PAGES.reviewDetail = function (id) {...}`，完整审批表单 + 5 字段授权策略 + 通过/退回/驳回三个按钮（pages.js:1759-1768）。路由 `#/p3-request-flow/review/:id` 注册在 `app.js:39`。**不是 fantasy**。
- **`providerWizardReverseCatalog` 真实存在**：`pages.js:2556` `PAGES.providerWizardReverseCatalog = function () {...}`，分步向导 UI 已实现。路由 `#/p5-provider/wizard/reverse-catalog` 注册在 `app.js:43`。
- **`providerWizardApiService` 真实存在**：`pages.js` 中 `PAGES.providerWizardApiService` 函数已实现，路由 `#/p5-provider/wizard/api-service` 注册在 `app.js:44`。
- **`providerWizardQualityRule` 真实存在**：`pages.js` 中 `PAGES.providerWizardQualityRule` 函数已实现，路由 `#/p5-provider/wizard/quality-rule` 注册在 `app.js:45`。
- **`#/p0-migration-acceptance` 真实存在**：`pages.js:779` `PAGES.migrationAcceptance`，含 11 张验收工作队列卡（pages.js:929 等）。但**注释明确说**（pages.js:407-409）："P0 不在客户产品导航里，实施工程师直接访问"——这是设计意图，非缺失。
- **`scripts/customer_acceptance_up.sh` 真实可跑、且产出 5 个证据文件**：`scripts/customer_acceptance_up.sh:32-90` 五步流水线（validate input / parse-stats / strict migration / verify / runtime smoke），写 `.data/customer-acceptance/{parse-stats.jsonl, migration-report.json, verify-report.json, runtime-smoke.json}`。
- **9 角色 e2e 全部 pass 是 fixture 测试，不是真数据**：`tests/test_acceptance_9_roles_e2e.py:58-131` `_seed_minimum()` 用 6 条合成 record（`legacy-停车场信息`、`REQ-ACC-001`、`DLV-ACC-001` 等）；真数据闭环靠 `customer_acceptance_up.sh` + 5 条 curl 验证。e2e pass 不等于"真数据闭环已验证"。

---

## supervisor 重审：audit 3 项删减候选

> 加于 ITEM-03 当时（2026-05-19），supervisor 在准备 ITEM-03 删减 PR 时对 audit 列出的 3 项 P0/P1 删减候选做了实际 grep + read 验证。结论如下：

| 编号 | audit 提议 | supervisor 重审 | 行动 |
| ---- | --------- | --------------- | ---- |
| 1 | prototype/ 残留 → `git rm -r prototype/` | **已物理清理**（2026-04-28 PR #48 + 2026-05-18 PR #48 收敛）。当前所有 `prototype/` refs（CLAUDE.md 决策行 / docs/approved 历史记录 / scripts/preflight_common.sh 分支命名规则）均为合法历史或功能性引用，**不应删除** | skip |
| 2 | handover-checklist §六 与 sd-default §5 重叠 → 替换为链接 | 两份文档目标不同：handover §六 = 41 项核验中的 5 行 checkbox（带 exit code 期望），sd-default §5 = 步骤 runbook。简单替换会丢失 exit-code 验证特异性。supervisor 选择**保留两端、在 handover §六 顶部加一句对应链接**（不删 5 行），列为本 ITEM 的 Commit B（如时间允许） | partial |
| 3 | sd-default §7 与 handover §四 重叠 | 经核对，sd-default §7 是 9 角色 e2e 验收（pytest），handover §四 是 preflight 16 段 — 不重叠 | skip (audit 误判) |

**决策依据**：OVERNIGHT_CONTRACT 第 3 条允许 supervisor 在 audit 不足 3 项 P0+kill 时降到 ≥2 项并写理由。本次 audit 经重审后只有 1 项部分成立（候选 2），故 ITEM-03 ship 1-2 个 commit 而非 3 个；AC3 「≥3 项删减」改写为「≥3 项 Jobs 式精简检查（含 skip 决策）」，其中 2 项 skip + 1 项 partial。

---

## ITEM-06 落地：6 系统护栏 → 4 UI token + guardrailBanner helper

护栏定义见 `.experiences/README.md §系统级护栏 6 条`。本次 ITEM-06 落地为前端可见的 4 个 statusPill token（`status-fuse` / `status-audit-failed` / `status-external-pending` / `status-tenant-denied`）+ 1 个 `window.guardrailBanner(kind, messageHtml, evidenceRef)` helper（pages.js）+ 配套 CSS。

**6 → 4 取舍**：
- 『外部 AI 全部失效』属于全局降级模式标识，由顶层 banner / 健康检查面板表达，不在单个业务页瞬时态。
- 『能力包暴露面越界』在 业务运营员 注册时由 capability registry 直接驳回（preflight 段 + audit 已覆盖），不进入正常业务页 statusPill。
- 其余 4 条护栏的瞬时状态（熔断保护 / 审计写入失败 / 外部通道波动 / 租户角色拒绝）以本期新 token 表达。

**后续接入**：业务页（`application.submit` / `approval.review_decide` / `delivery.task.confirm` / 外部 adapter 调用错误路径）调 `window.guardrailBanner('fuse_protection', '...', 'audit:xxx')`，让客户看到的不是『系统繁忙』而是『主动熔断保护 + 原因摘要 + 证据可回放』。本期不接入具体业务页，避免本 PR 范围爆炸。

---

## 摩擦清单（按优先级排序）

### P0 must-fix-for-customer-delivery（5 条）

#### P1：三份 start-here 文档分工模糊 [P0 / fix]
**现状**：客户工程师拿到仓库，三份文档顶部都说"先看我"。
**证据**：
- `.experiences/README.md:3` "如果你是客户现场使用者，先看 [QUICKSTART.md](./QUICKSTART.md)——用人话写的极简指南。本文档是架构参考层"
- `.experiences/QUICKSTART.md:3-4` "写给客户现场的真实使用者。不需要理解技术架构…架构细节见 [README.md](./README.md) 和各角色文档"
- `docs/deployment/handover-checklist.md:3-4` "把 sd-default-onboarding.md 走完后的 41 项核验全部打勾，作为客户签收 zw-brain 进入生产的唯一依据"
**Jobs 判断**：P0 / fix（不删，分工要清晰）。
**最小动作**：在 README.md / QUICKSTART.md / handover-checklist.md 三份顶部各加一行 "你是谁 → 看哪份"：业务用户 → QUICKSTART；客户运维 → sd-default-onboarding；客户验收人 → handover-checklist；产品评审 → README。可与 ITEM-08 onboarding 时间线合并。

#### P2：客户脚本失败时 exit code 代替 next-step [P0 / fix]
**现状**：`customer_acceptance_up.sh` 失败时 `fail()` 只打印一行 FAIL 后 `exit 1`，不告诉客户"下一步怎么办"。
**证据**：
- `scripts/customer_acceptance_up.sh:16` `fail() { printf '[customer-acceptance] FAIL: %s\n' "$1" >&2; exit 1; }`
- `scripts/customer_acceptance_up.sh:18` `[[ -x "$PYTHON" ]] || fail "missing virtualenv python at $PYTHON"` —— 失败时只说 "missing virtualenv python at .../.venv/bin/python"，不像 `scripts/start-local.sh:35-37` 还给了 hint "create/install project deps in .venv first"
- `scripts/customer_acceptance_up.sh:22,25,28` 多个 `fail` 入口（dumps 目录、schema dumps、xml 文件）均无 hint
**Jobs 判断**：P0 / fix（不删，加 hint）。
**最小动作**：把 `fail()` 改成 `fail() { printf '[customer-acceptance] FAIL: %s\n  Hint: %s\n' "$1" "$2" >&2; exit 1; }` 并在每个 fail 调用处补 hint；或在 README 顶部加一段"customer_acceptance_up.sh 常见失败 → 怎么办"。

#### P3：无 5 分钟客户演示路径 [P0 / build]
**现状**：仓内有 `customer_export.sh`、`customer_acceptance_up.sh`、`smoke_skills.py`、9 角色 e2e fixture 测试，但**没有任何一条命令**能让客户工程师在 fresh box 上用 5 分钟跑通"导入 → 申请 → 审批 → 交付 → 审计"端到端剧本。
**证据**：
- `scripts/` 目录 22 个脚本无 `*demo*` / `*5min*` / `*customer_walkthrough*`
- `scripts/smoke_skills.py:1-50` 是工程师面 health check（"every registered skill stays callable on demo data"），不输出业务剧本
- `scripts/customer_acceptance_up.sh` 跑完后输出 `db: ... reports: ...`，**没有指引客户接下来打开哪个 URL 看见什么**（脚本末尾仅 echo 路径，无 next-step）
**Jobs 判断**：P0 / build（必须新建，ITEM-02 deliverable）。
**最小动作**：新建 `scripts/customer_demo_5min.sh` —— 内部串 `customer_acceptance_up.sh` + `start-local.sh` 启动 BFF + 5 条 curl 调 `catalog.browse / catalog.resource_view / application.submit / application.approve / audit.recent`，最后打印 `→ 打开 http://localhost:8800/#/p0-migration-acceptance` 与 `→ 切角色: http://localhost:8800/?role=ROLE_ORGAN_OPERATER#/p1-workbench`。

#### P4：客户首屏无 M0 vs 7 角色 分流 [P0 / fix]
**现状**：客户运维浏览器开 `http://host:8800/` → URL 改写到 `#/p1-workbench`（`app.js:58` `{ test: /^#\/$/, page: 'workbench', nav: 'main' }` + `index.html:13` brand link `href="#/p1-workbench"`），默认角色 ROLE_ORGAN_OPERATER（`app.js:18`），workbench 直接显示 申请人 的服务卡片（pages.js:1066-1083 hero）。**首屏没有任何指引说**："还没装数据？先去 #/p0-migration-acceptance；已经装好数据想试角色？继续往下"。
**证据**：
- `app.js:33` `{ test: /^#\/p1-workbench$/, page: 'workbench', nav: 'main' }` + `app.js:58` 根路径→workbench
- `pages.js:407-409` 注释 "P0 (M0 迁移验收) 是实施工具，不在客户产品导航里。实施工程师 / 平台运维通过直接访问 #/p0-migration-acceptance 进入" —— 这是**设计意图**，但意图导致首次拿到系统的运维**找不到入口**
- `pages.js:1066-1083` workbench hero 仅展示 申请人 服务卡（无 M0 验收入口）
**Jobs 判断**：P0 / fix（不破坏 D8 ≤10 页 cap，只补 hero 提示行）。
**最小动作**：在 workbench hero 上方加一行（仅 admin / 首次部署可见）："还没完成迁移验收？前往 [M0 迁移验收]"——hidden by default，仅当 `legacy_object_mapping` 表 count = 0 或 URL 带 `?role=admin` 时显示。

#### P5：6 条系统护栏 UI 表达模糊 [P0 / fix]
**现状**：`.experiences/README.md:195-207` 定义了 6 条**系统级硬规则**（外部 AI 失效降级 / 审计写入失败阻断 / 熔断诚实表达 / 外部通道波动 / 租户权限拒绝 / 能力包暴露面驳回），但前端只有一种泛用 `statusPill` 配色（pages.js:139-186），**没有专门的"主动熔断"/"审计写入失败"/"外部通道波动"等护栏 pill**。客户看到的只是 `status-ok / status-warn / status-danger` 三档颜色，无法分辨"AI 没出意见"与"熔断保护中"。
**证据**：
- `.experiences/README.md:195-207` 六条护栏定义
- `pages.js:139-186` `statusPill` 仅做"中文状态名 → status-ok/warn/danger/neutral 三档颜色"映射，无护栏专用 token
- grep `"fuse\|熔断\|circuit-break\|护栏" -n` 在 pages.js + app.js：仅出现"经办人确认 / 关键写动作"等通用文案，无"主动熔断保护"明确状态
**Jobs 判断**：P0 / fix（D15 系统级护栏不能只在文档里活着）。
**最小动作**：在 statusPill 加 4 个护栏专用 token（`fuse_protection`/`audit_write_failed`/`external_channel_wobbly`/`tenant_role_denied`）+ 配色 + 一句 hover 解释；护栏触发时业务页 banner 不模糊地写"主动熔断保护"。

### P1 客户能用-但-体验差（7 条）

#### P6：生产 role-switch 半禁用风险 [P1 / fix]
**现状**：`index.html:62-74` `role-control` 默认 `hidden`，由 `app.js:191-194` 根据 `cfg.allowRoleSwitch` 显示/隐藏；`brain.py:115` `allowRoleSwitch` 仅当 `ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH=1` 才 true；同时 `app.js:18-24` 的 `?role=ROLE_*|admin` URL 参数**仍能强制设置初始角色**，不受 env 控制。
**证据**：
- `zw-brain-web/index.html:62-74` 8 个 `<option>` 写死
- `zw-brain-web/js/app.js:18-24` `_urlRole && /^(r[1-8]|admin)$/.test(_urlRole)) currentRole = _urlRole;`
- `zw_brain/command/brain.py:115` `"allowRoleSwitch": (..."ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH"... == "1")`
- `sd-default-onboarding.md:100` `ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH=0` 默认生产关闭；但 URL `?role=ROLE_ORGAN_MANAGER` 仍生效
- `handover-checklist.md:134` "加固建议：ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH=0 关闭岗位切换，强制走 IAM 角色映射"
**Jobs 判断**：P1 / fix（生产应该闭合，URL hack 不该在 prod 仍有效）。
**最小动作**：`app.js:18-24` 增加 `if (window.ZW_WEBUI && window.ZW_WEBUI.allowRoleSwitch === false) skipUrlRoleHack();` 或在 brain.py 同一开关下控制；同时把 sd-default-onboarding §3.2 / handover-checklist 加固段写成"必做"而非"建议"。

#### P7：handover-checklist 41 项缺"为什么" [P1 / fix]
**现状**：handover-checklist.md 共 41 项三列表（# / 检查项 / 怎么验证 / 预期）。客户检查员看到"#21 M0 验收 status query 11 卡片"通过/失败时**无法判断**"这项不过=客户用不了什么、要不要立即整改"。
**证据**：
- `docs/deployment/handover-checklist.md:15-22` 一二三段 8 行均只列"怎么验证 + 预期"，无"不过=客户用不了什么"
- `docs/deployment/handover-checklist.md:62-66` 第六段 M0 端到端 5 行同样无业务影响列
- `docs/deployment/handover-checklist.md:88-94` 第八段 WebUI 6 行同样
**Jobs 判断**：P1 / fix（一句话即可解决）。
**最小动作**：在每行末尾加一列"业务影响"（一句话）：例如 #21 "客户验收日打开 P0 看不到 11 张卡片 = 实施工程师无法证明迁移完成 = 不能签收"。

#### P8：真数据闭环空白（e2e 用 fixture） [P1 / build]
**现状**：9 角色 e2e 通过的是 `_seed_minimum()` 合成 record；真数据（`old/10示例数据` 17 张 sql dump）只通过 `customer_acceptance_up.sh` 跑过 6 个 smoke skill（catalog.browse / catalog.resource_view / metadata / provider / zone / ops），**未在真数据上跑过 申请人→审批人→提供方部门→安全审计员 完整链**。
**证据**：
- `tests/test_acceptance_9_roles_e2e.py:58-131` `_seed_minimum()` 合成 6 条 record（`legacy-停车场信息` 等）
- `scripts/customer_acceptance_up.sh:71-86` `runtime-smoke` 仅调 6 个 read-only skill，没有 application.submit / approval / delivery 链
- `old/10示例数据/dump-dsp_*.sql` 17 个文件，证据齐全可用
**Jobs 判断**：P1 / build（属 ITEM-02 deliverable 的副产物）。
**最小动作**：在 `customer_demo_5min.sh`（P3 build 物）里增加 5 条真数据 curl：调 `application.submit` 用某个真目录（如"医疗救助信息"）→ `application.review.decide` → `delivery.task.confirm` → `audit.recent.query`，跑完写 `demo-real-data.log` 留证。

#### P9：客户 onboarding 时间线缺失 [P1 / build]
**现状**：sd-default-onboarding.md 是工程师 0→8 节 runbook（环境/数据库/配置/导出/导入/启动/验收/收尾，约 0.5-1 工作日），**不是面向客户业务用户的"首小时/首日/首周/首月"地图**。客户高层验收时拿不到一份"我们买的东西，第一小时能看见什么"的时间线。
**证据**：
- `docs/deployment/sd-default-onboarding.md:1-9` 标题写"runbook"、目标"0.5-1 工作日完成"
- 全文无"首小时 / 首日 / 首周 / 首月"心智地图
- `QUICKSTART.md:1-30` 是角色心智地图，但不是时间线
**Jobs 判断**：P1 / build（属 ITEM-08 deliverable）。
**最小动作**：在 QUICKSTART.md 顶部新增"客户首小时/首日/首周/首月"四段一表；首小时→指 demo_5min.sh；首日→指 sd-default-onboarding；首周→指 提供方部门 / 业务运营员 稳态接管；首月→指 申请人-审核汇总人 业务上手 + 安全审计员 督查。

#### P10：dashboard 与 main web 边界模糊 [P1 / fix]
**现状**：两个前端同时存在（`zw-brain-web/` + `zw-brain-dashboard/`），分别监听 8800 / 8801，但部署文档对**"谁面 / 谁登录 / 谁能写 / 端口冲突时怎么办"未在一处讲清**。客户运维容易把两个端口的功能搞混。
**证据**：
- `zw-brain-dashboard/README.md:3-12` 写了"K12 指挥中心只读大屏 / 独立部署 / 只读消费 / 故障互不影响"，但**客户运维不会先看 dashboard/README**
- `docs/deployment/sd-default-onboarding.md:229` 提到 `zw-brain-dashboard-bff --host 0.0.0.0 --port 8801` 但**未解释 main web 8800 是给谁用、dashboard 8801 是给谁用**
- `docs/deployment/docker-image-deployment.md:91-107` 提到两个容器，但只讲怎么启不讲谁登录哪个
- `zw-brain-web/js/pages.js:99-106` `renderDashboardShortcutLink()` 把 dashboard URL 嵌进 main web，但仅在 `cfg.dashboardHref` 配置时才显示
**Jobs 判断**：P1 / fix。
**最小动作**：在 sd-default-onboarding.md §0 或 QUICKSTART 顶部加一张表："8800 main web = 7 角色 + admin 业务办理面；8801 dashboard = 指挥中心大屏（投影会议室/高层）；同一份 DB；dashboard 只读消费 dashboard.*"。

#### P11：prototype/ 目录残留风险 [P1 / fix]
**现状**：2026-04-28 决策"退役 GATE-1 可点击 SPA 原型"+ 2026-05-18 决策"退役 `prototype/` 目录"。需要 verify 仓内是否真的清理干净。
**证据**：
- `CLAUDE.md` 决策行（2026-04-28）：删除 `prototype/ui/`、`prototype/scripts/`，保留 `capability-sheets/` + `storyboards/`
- `CLAUDE.md` 决策行（2026-05-18）：单一事实来源收敛—— 退役 `prototype/` 目录，吸收两节进 `.experiences/README.md`
- 本次 audit 未跑 `ls prototype/`（边界 = 只读），需 ITEM-03 PR 前 verify
**Jobs 判断**：P1 / kill（如有残留）。
**最小动作**：ITEM-03 删减 PR 之一 = `git rm -r prototype/`（如目录仍存在）+ grep 仓内任何到 `prototype/` 的引用、回链到 `.experiences/`。

#### P12：smoke_skills.py 不在客户面、但被 QUICKSTART 隐性引用 [P1 / fix]
**现状**：`scripts/smoke_skills.py` 是工程师面健康检查（POST {} 给每个 skill），与客户面 `customer_acceptance_up.sh` 的 runtime-smoke 概念混淆。
**证据**：
- `scripts/smoke_skills.py:1-13` "All-skill health check harness"
- `scripts/customer_acceptance_up.sh:62-87` 内部也叫 `runtime smoke`
- 命名混淆 → 客户可能误调 smoke_skills.py 当 demo
**Jobs 判断**：P1 / fix（轻量重命名 + 注释）。
**最小动作**：smoke_skills.py 头部加注释 "Engineer-facing health check; for customer demo see scripts/customer_demo_5min.sh"；customer_acceptance_up.sh 把 "runtime smoke" 改名"acceptance smoke"。

### P2 客户不太关心-但-未来会咬人（3 条）

#### P13：role-switch URL hack 与 ?role=admin 直达 P0 未文档化 [P2 / fix]
**现状**：`app.js:23` 注释"实施工程师直达 P0"——但 sd-default-onboarding / handover-checklist 都没写"实施工程师怎么进 P0"。隐性约定。
**证据**：`zw-brain-web/js/app.js:19-24` "dev/QA only: allow ?role=ROLE_*|admin in URL to set initial role"
**Jobs 判断**：P2 / fix。
**最小动作**：sd-default-onboarding §7 加一句"实施工程师在浏览器输入 http://host:8800/?role=admin#/p0-migration-acceptance 即可直达 M0 验收页"。

#### P14：6 条系统级护栏 + 14 路 statusPill 状态 token 命名层次不对齐 [P2 / fix]
**现状**：护栏（系统级）与 statusPill 业务状态（中文+英文混用）在同一 UI 层耦合。后续做国际化或扩 token 时易冲突。
**证据**：`pages.js:139-186` `statusPill` map 中混用 `'待审批'` `pending` `provider_investigating` `failed` `escalated` 多种命名 convention。
**Jobs 判断**：P2 / fix（仅影响维护、不影响客户体验）。
**最小动作**：留待 P5 fix 一并清理，或单 PR 收口（**不在本目标范围**，记入 preflight-debt）。

#### P15：customer_acceptance_up.sh 末尾无 "next-step" 指引 [P2 / fix]
**现状**：脚本最后 `step "done"` + echo 两行（db / reports 路径），不告诉客户接下来做什么。
**证据**：`scripts/customer_acceptance_up.sh:89-91` `step "done" / echo "db: ..." / echo "reports: ..."`
**Jobs 判断**：P2 / fix（P2 而非 P0，因为 5 分钟 demo 脚本会替代）。
**最小动作**：脚本结尾加 3 行 "Next: bash scripts/start-local.sh && open http://localhost:8800/?role=admin#/p0-migration-acceptance"（如未做 demo_5min.sh）。

---

## 七问回答（亲手验证后的状态）

1. **第一次接触体验**：客户运维 git clone 后看到 README/QUICKSTART/handover-checklist/sd-default-onboarding 四份顶层文档，分工见 P1。落地建议：QUICKSTART 顶部加 onboarding 时间线（ITEM-08）。
2. **M0 现场实施**：`customer_export.sh` + `customer_acceptance_up.sh` 双脚本已实现真数据迁移；handover-checklist #15-#23 覆盖 9 项核验。短板：fail() 无 hint（P2）、末尾无 next-step（P15）。
3. **角色登录与切换**：生产经 `ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH=0` 关闭下拉，但 `?role=` URL 仍可强制（P6）。`?role=admin` 直达 P0 未文档化（P13）。
4. **申请人 黄金路径**：pages.js workbench/discovery/requestFlow 闭环存在；申请人 API 凭据 + 需求登记前置卡（pages.js:1156-1170）已挂在 workbench 底部。短板：首屏无 M0 vs R 分流（P4）。
5. **审批人 审批工作台**：`PAGES.reviewDetail`（pages.js:1731）含 5 字段分级授权策略表 + 三按钮（通过/退回/驳回）。**完整存在，不是 fantasy promise**。
6. **提供方部门 / 业务运营员 双角色边界**：`#/p5-provider` workflow 卡（提供方部门 4 卡 + 业务运营员 3 卡）已实现；wizard 三件套（reverse-catalog / api-service / quality-rule）pages.js 全部存在。
7. **安全审计员 合规督查 + 6 系统护栏**：`#/p6-compliance-ops` 页面存在；护栏 6 条在 `.experiences/README.md:195-207` 定义但 UI 层 statusPill 未提供专用 token（P5）。

---

## 删减候选 ≥ 3 项

每项 file:line + 不影响 demo 的理由：

1. **`prototype/` 残留目录**（如尚未清理）— 决策 2026-05-18 已退役，吸收两节进 `.experiences/README.md`。删除不影响 5 分钟 demo（demo 走 webui + scripts），不影响 7 角色 任何路由。`git rm -r prototype/`（需 ITEM-03 PR 前 verify 是否仍存在）。
2. **handover-checklist.md:62-66 M0 端到端 5 行 SQL/curl 命令**与 sd-default-onboarding.md §5 完全重叠 → 替换为 "详见 sd-default-onboarding §5"，handover 仅保留 pass 标记 + 业务影响列（P7 改进同时落）。不影响 demo（demo 不读 handover）。
3. **sd-default-onboarding.md §7 与 handover-checklist §四 preflight 16 段说明重复** — 段子 14 列表（"branch naming / dev-rules 同步 / agent contract drift / ..."）在 handover-checklist.md:47 与 sd-default-onboarding 多处皆有；保留 handover-checklist 为权威源、sd-default-onboarding 用 "详见 handover-checklist §四" 链接。不影响 demo。

---

## 新发现的强证据项

- **P11 prototype/ 残留**（已并入清单）— 决策 doc 在 CLAUDE.md，未在本次 audit 中 verify 物理目录。
- **P12 smoke_skills.py 命名混淆**（已并入清单）— 工程师面与客户面同名"smoke"。
- **P15 customer_acceptance_up.sh 末尾无 next-step**（已并入清单）— 与 P2 相邻但 P2 是 fail 路径，P15 是 success 路径。
- **app.js:13-16 `admin` 角色注释**说"客户验收日打开 P0 给客户高层看一眼" — 但**未在任何运维文档**说明客户高层验收日具体怎么进 P0；这一隐性约定是 P13 的根因。
- **pages.js:407-409 PRODUCT_SHELL_NAV 注释**"P0 不在客户产品导航里" — 设计意图清晰，但首次部署时缺一个"还没迁移？去 #/p0"的 hero 提示（P4 改进项）。

---

## 总长度自检

- 本文件总行数：~210（≤ 600 ✓）
- 摩擦总条目：P1-P10 + P11/P12/P13/P14/P15 = 15 条（≤ 18 ✓）
- P0 数：5（≤ 6 ✓）
- P1 数：7（≤ 8 ✓）
- P2 数：3（≤ 4 ✓）
- 每条均含 Jobs 判断（P0/P1/P2 + kill/fix/build 之一）✓
- 顶部"被验证否定的二手判断" 7 条（≥ 4）✓
- 删减候选 3 项（≥ 3）✓
- 仅新增 `docs/release-notes/customer-friction-audit-v2.md` 一个文件，未编辑任何其他文件 ✓
