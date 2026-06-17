# 部门数据隔离设计（dept-data-isolation）

> D28 GATE（角色/可见性变更）。产品研发负责人 2026-06-16 本会话四问裁决 + 计划审批。
> 签字账本 `.testing/signoff/dept-data-isolation.signoff.yaml`（decision_only）。

## 一、问题（根因）

排查「所有用户登录后看到的资源/目录/申请都一样，与所属部门无关」。深挖结论：**所有读路径
只按 `tenant_id`（固定 `sd-default`）+ 角色 redaction 过滤，从不按调用者所属部门过滤行**，
尽管每条记录都带 `owner_org_id` / `applicant_org` / `complainant_org_id` / `provider_org_id`，
登录会话也已把调用者机构 `org_code` 写进可信 payload（`session_context.py`），只是
`system_ops.handler_system_snapshot` 装配快照时从没读它。实测：`catalog_entry.owner_org_id`
跨 5+ 部门、`actor_projection.org_code` 跨数十部门——两边 join 字段都真实多部门、只是从不相遇。
唯一一条已按部门过滤的活路径是 `ops_service._scope_invocations_for_manager`（D57⑥），本方案
即把这套已验证范式推广到其余消费面。

## 二、四问裁决（产品研发负责人 2026-06-16）

1. **发现面/找数据永久全局**——跨部门数据共享市场是产品本意（D60/D53①），`discovery` 投影
   与 `data_search` 不收口。所有人见同一份已发布资源是**正确**行为。
2. **部门管理员见「本机构+下级」，本期落「本机构」**——`org_projection.parent_org_code` 实测
   100% 为空（1.8 万机构平表；legacy `pub_organ_tree.PARENT_CODE` 有但未导入）。机制按
   「本机构+下级」设计解析器，因父子树为空当前恒返 `{本机构}`；待 `parent_org_code` 后续填充，
   下级零代码改动自动生效。部门操作员=本机构（无下级）。
3. **「我的申请」按个人（本人提交）**——运行时铸单把个人 id 落 `payload['applicant']`；后端按卡片
   算 `mine = (payload['applicant'] == 当前登录个人)`，前端 `myRequests` 过滤 `mine===true`；
   legacy 单非本人提交 → mine=false → 正确不出现。
4. **全局角色保持全局**——业务运营员(BUSIAUDIT)/平台运维员(SYSTEM)/安全审计员(SECURITY_AUDIT)
   见全量；仅部门管理员(ORGAN_MANAGER)/部门操作员(ORGAN_OPERATER)受部门收口。平台级待办
   （待平台审核/待发布/待受理/待汇总）即便管理员也保持全局。

## 三、设计

### 1) 共享解析器（一切依赖它）
`ReferenceService.visible_org_codes(actor_org, role, *, tenant_id) -> set[str] | None`，三态：
- `None` → 全局角色（不限定，调用方放行全量）；
- `{org, …}` → 部门角色 + 有机构上下文：本机构 +（管理员才有的）下级；
- `set()`（空集）→ 部门角色缺机构上下文：**fail-closed** 信号，调用方返空列表/0 计数。

下级 = `GovernanceProjectionRepository.list_org_children` 递归（镜像 `list_region_children`，
索引命中 `parent_org_code`）；父树为空时返 0 行、O(1)、恒 `{本机构}`，填充后自动展开。
行级成员判定 `ReferenceService.org_in_scope(owner, visible)`：None→True、空集→False、否则
成员判定 + **legacy 名/码归一**（债 legacy-catalog-owner-org-name-mismatch：owner 可能存机构名
而非信用代码，先 `resolve_org_code` 归一再比对）。

### 2) 穿透（不改 SkillContext）
`caller_org_code(payload)` 抽到 `session_context` 单源（`ops_service`/`j1.approval` 两份重复委托之）。
`system_ops.handler_system_snapshot` 与 `j1/workbench._get_workbench` 各算一次 `visible` +
`caller_actor`，作 keyword 透传各 enrich；发现面（zones/discovery_resources）刻意不传=永久全局。

### 3) 各消费面收口（per surface）
| 面 | 收口键 | 备注 |
|---|---|---|
| 供数 目录/资源/API/收件箱(部门审·挂接审) | `owner_org_id ∈ visible` | publish_queue/demand_matches 不收（平台级/J2） |
| 申请 requests | `applicant_org ∈ visible OR provider_org ∈ visible` | 见下「复核修正」 |
| 我的申请 mine | `payload.applicant == caller_actor` | 与部门过滤正交 |
| 审批 approvals(R11) | provider org ∈ visible（按 application_code 映 requests.providerOrgCode） | 映射缺失 fail-closed drop |
| 异议 disputes | `complainant_org_id ∈ visible OR provider_org_id ∈ visible` | 双向利益相关方 |
| 工作台 管理员供数侧审核待办计数 | `owner_org_id ∈ visible` | 仅 MANAGER 路径；平台待办全局 |
| 工作台 申请审核/汇总/进度待办 | `request_party_in_scope`（MANAGER review/summary + OPERATER apply-progress/supplement 同口径 dept-scope） | `sync_request_todos` 平行路径；见下「集成期遗漏补口（工作台申请待办第七面）」 |
| 交付 delivery_tasks | `requestId ∈ 收口后 request_map` | 随申请单可见性收口；见下「集成期遗漏补口（交付面）」 |

**fail-closed 姿态**：聚合快照 projection 中途 raise 会清空整页、对 UI 敌对 → 部门角色缺机构
上下文返空列表/0；`ops_service` 定向查询保留 raise 403。两者同等无泄漏。

## 四、集成期复核修正（重要）

并行 agent 实现「申请收口」时仅按 `applicant_org` 过滤，会把「别部门(orgB)申请本部门(orgA)
数据」的入站单从 orgA 部门角色视图过滤掉——而 orgA 是**提供方**、必须在审批队列看见并办理这张单。
被过滤后审批卡无从映射 provider 机构 → 误判 fail-closed 丢弃，部门管理员永远批不了进来的单，
R11 供方队列形同虚设。修正：申请收口改 **applicant_org∈域 OR provider_org∈域**（provider 取
payload `owner_org_code`/`provider_org_id`，与申请卡 providerOrgCode 同源）。`test_discovery_dept_scope`
新增三测锁定正确语义（入站单留存 / 供方 R11 审批可见 / 真·无关单才 fail-closed drop）。

## 四点五、集成期遗漏补口（交付面，post-merge erratum）

#294 五面收口**漏掉了第六面**：`delivery_tasks`（P4 领数据交付任务）。交付面唯一消费者就是
部门角色——`web_snapshot_redaction._DELIVERY = {ROLE_ORGAN_OPERATER, ROLE_ORGAN_MANAGER}`，
全局角色一律清空——本就应**永远按部门隔离**；却在 `system_ops.handler_system_snapshot` 装配时
未传 `visible_org_codes`，部门角色看到**全部门**交付任务（与 requests 同类跨部门泄漏）。更甚：
既有单测 `test_system_snapshot_delivery_tasks_matches_list_delivery_tasks` 以操作员无机构上下文
断言 `snap==list`（全量），把泄漏**固化为"正确"**，正是该面被整体漏掉的铁证。

补口**不引入新产品裁决**——交付任务是申请单的履约视图，「看不到申请单就不应看到其交付」是
§二·裁决 4「部门角色收口」对交付面的直接推论。实现复用 approvals R11 同范式：
`enrich_delivery_tasks_snapshot(dept_scoped=visible≠None)`，按上游已收口的 `request_map`
（applicant_org∨provider_org∈visible）过滤 `requestId`，命中不到 fail-closed drop。
验证：`test_delivery_dept_scope`（三态单测）+ `test_dept_isolation_snapshot_two_actor`
（两 actor 看到 disjoint delivery_tasks）+ 既有泄漏断言改写为 fail-closed 闭合断言。

## 四点六、集成期遗漏补口（工作台申请待办「第七面」，post-merge erratum）

上帝视角复核 #294→#296→#295 这一簇 PR 时发现：#294/#296 收口的是 6 个**快照面**
（`system.snapshot` 经各 `enrich_*` 收口），但工作台待办还有一条**平行投影路径**
`sync_request_todos`（`zw_brain/command/sync.py`）——#294 从没碰过它，而 #295 的**行内办理**
（申请受理/审核 M1）正建在其上。它遍历 `application_record` **全租户运行时卡**（无 legacy
`kind`），按角色逐条投 workbench todo，**零机构/个人过滤**：

- **MANAGER** `category=review`（`dept_approved` 单）挂 `application.dept_approve` 行内
  「审核通过/驳回」面板（context 含资源/申请人/用途）→ 部门管理员在工作台看见**别部门**申请并
  能点「通过」。写侧 `enforce_dept_approval_direction`（`conditional_approval.py:155`）兜底 →
  点击 403，正是被硬禁的「**可见 + 点了报错/失败**」反模式（违「无权即不可见」），且泄漏跨部门
  resourceName/申请人/用途。`category=summary`（汇总/准入）同类泄漏。
- **OPERATER** `category=apply-progress`/`supplement-*`：**每个操作员看到全租户每张运行时申请的
  进度** → 跨部门泄漏（应随本机构收口）。
- **BUSIAUDIT** `category=accept`（受理）：裁决④ 全局，**正确，不动**。

设计 §三表只收口了 MANAGER **供数侧审核待办计数**（`_manager_review_todos`），`sync_request_todos`
的申请待办整条被漏。**盲区与 #294 漏 `delivery_tasks` 同源**：`test_workbench_dept_scope.py` 与
`test_dept_isolation_snapshot_two_actor.py` 都**零** `application_record` 种子，故该泄漏无任何
测试覆盖。

补口**不引入新产品裁决**——是裁决②对工作台申请待办面的直接推论，与 #296 同构。实现：读时
（per-caller，`enrich_workbench_backlog`）按**本机构可见域**收口——谓词单一事实源
`discovery_snapshot_projection.request_party_in_scope`（applicant∨provider∈visible）从
`enrich_requests_snapshot` 闭包提升为模块级复用，避免两处口径漂移。MANAGER review/summary 与
OPERATER apply-progress/supplement **同口径** dept-scope（None=全局 / 空集=fail-closed）；BUSIAUDIT
accept 不在收口集、保持全局。

**为何 OPERATER 也走 dept-scope 而非「按个人」（裁决③）**：当前运行时 `actor` 是 **role 级**
合成身份（`policy.actor_for_role` → `user:gov:<role>:*`，无 org/个人维度，承 actor_projection IAM
身份补全债），`payload.applicant` 在铸单时存的也是该 role-actor。故「按 `payload.applicant ==
当前 actor` drop」对**跨部门操作员之间无任何隔离效果**（所有操作员共享同一 actor id），dept-scope
才是真隔离。裁决③「我的申请按个人」与 #294 一致由 requests 面 **mine 标记**承载（读侧逐卡现算、
不 drop 数据）；真·per-person 收敛待 IAM 身份补全后另立。验证：`test_workbench_request_todo_dept_scope`
（MANAGER + OPERATER 各三态 + busiaudit 全局 + 幽灵单 fail-closed）+ `test_dept_isolation_snapshot_two_actor`
扩两 actor 工作台 review 待办 disjoint（真 `workbench.view` BFF 路径）+ 既有
`test_operater_keeps_progress_todos_with_honest_advice` 改写为在产单背书的留存断言。

## 五、不在范围

发现面全局（不动）；**下级**（`pub_organ_tree.PARENT_CODE` 导入填充 `parent_org_code`）另立数据
任务；多租户；全局角色平台待办；J2 `demand_matches`；写路径/审批动作授权
（`enforce_dept_approval_direction` 等已存在、不改，本期只动**读可见性**）。

## 六、验证

- 解析器单测 `test_visible_org_codes_resolver`（14 例：三态 / 下级前向兼容 / 名码归一）。
- 各面单测 `test_provider_snapshot_dept_scope` / `test_discovery_dept_scope` /
  `test_dispute_dept_scope` / `test_workbench_dept_scope`（隔离 / 全局放行 / fail-closed / mine /
  R11 入站单+无关单）。
- **端到端两 actor** `test_dept_isolation_snapshot_two_actor`：两不同部门管理员经全 `system.snapshot`
  路径看到 provider.catalogs / requests **不同**、各为自机构子集；全局角色见全量——直接证明
  用户最初反馈的「都一样」缺陷已修。
- **真·双账号浏览器 e2e** `tests/e2e/dept_isolation_two_account.spec.ts`（Playwright，真浏览器）：
  单栈起两个钉不同机构的 dev-bypass cookie 会话（使能改动 = dev-bypass-login 接受可选 ?org=
  覆盖会话机构，仅 dev 档、已 fail-closed），各自登录态打开供数页 `#/provider`，断言两账号供数
  目录**互不相交**、各含自机构代表目录、不含对方的。隔离 12 机构真实库实测：orgA 会话 121 目录
  （含 2 条机构名形态经 org_in_scope 归一并入）、orgB 会话 20 目录，互不相交 ✓。截图存
  dept-iso-orgA/orgB-provider.png。`?org` 覆盖单测 `test_dev_bypass_org_override`。
- 既有 provider/discovery/workbench/approval/ops/redaction 回归全绿；每 commit 全套 preflight PASS。

## 七、下级降级提示

`parent_org_code` 当前全空 → 部门管理员实际仅见本机构；解析器已就绪、数据待填。任何
「管理员见下级」的预期须先完成 `pub_organ_tree.PARENT_CODE` 导入（另立任务），届时本设计与所有
调用方零改动自动生效。
