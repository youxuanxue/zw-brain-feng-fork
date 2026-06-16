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
| 工作台 管理员审核待办计数 | `owner_org_id ∈ visible` | 仅 MANAGER 路径；平台待办全局 |

**fail-closed 姿态**：聚合快照 projection 中途 raise 会清空整页、对 UI 敌对 → 部门角色缺机构
上下文返空列表/0；`ops_service` 定向查询保留 raise 403。两者同等无泄漏。

## 四、集成期复核修正（重要）

并行 agent 实现「申请收口」时仅按 `applicant_org` 过滤，会把「别部门(orgB)申请本部门(orgA)
数据」的入站单从 orgA 部门角色视图过滤掉——而 orgA 是**提供方**、必须在审批队列看见并办理这张单。
被过滤后审批卡无从映射 provider 机构 → 误判 fail-closed 丢弃，部门管理员永远批不了进来的单，
R11 供方队列形同虚设。修正：申请收口改 **applicant_org∈域 OR provider_org∈域**（provider 取
payload `owner_org_code`/`provider_org_id`，与申请卡 providerOrgCode 同源）。`test_discovery_dept_scope`
新增三测锁定正确语义（入站单留存 / 供方 R11 审批可见 / 真·无关单才 fail-closed drop）。

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
