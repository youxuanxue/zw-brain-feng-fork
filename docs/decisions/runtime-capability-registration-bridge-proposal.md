---
title: 通用外部执行桥 + 运行时能力注册（自助接入 + 热更新可用）— 架构方案（待立项）
scope: runtime-capability-registration-bridge
status: proposed  # 架构 + 安全门：需产品研发负责人 sign-off（D28）+ 安全评审 才立项；本文是方案，不是已实现
date: 2026-06-04
deciders: 海若产品部产品研发负责人（GATE 决策门）+ 安全评审
authors:
  - Claude Opus 4.8 (1M context) — 乔布斯式产品专家 + 高级软件研发工程师
related_docs:
  - docs/decisions/integration-admin-governance-axis-refactor.md   # A：接入扩展中心 UI 诚实化（本方案的 UI 前身）
  - docs/approved/zw-brain-architecture.md                          # §3 数据直达/外部依赖；§8.4 7 步流水线；§9.5 adapter 写禁区
  - docs/decisions/national-platform-access-D50.md                 # D50：一处「手工接线」的外部出站实例（本方案要泛化的对象）
  - docs/agent-runtime-t1-readiness.md                             # AgentRuntime T1：本方案的部分脚手架
related_code:
  - zw_brain/command/dispatch.py                                   # 静态 DISPATCH_TABLE（本方案要加运行时兜底的地方）
  - zw_brain/capability_registry/runtime.py                        # load_manifests（每调用重读，已具备运行时可读性）
  - zw_brain/command/handlers/infra/adapter_passthrough.py         # 17 个写死 slug 的「记录型」通用 handler（不是执行器）
  - scripts/check_capability_registration.py                       # 段28 三处一致守卫（本方案要分轨改造）
---

# 通用外部执行桥 + 运行时能力注册

> 阶段：**纯方案（设计 + 立项请求）**，零代码改动。回答负责人的诘问——「自助注册向导 + 热更新使用」**真能实现吗**。
> 结论：**今天不能**（底座问题，非排期）；**能做成,但需要先建本方案描述的执行底座 + 过安全评审 + 负责人 sign-off**。

## 一 · 代码事实（为什么今天不能，逐条带证据）

1. **dispatch 是静态代码绑定。** `dispatch.py` 的 `DISPATCH_TABLE` 是模块加载期写死的字典字面量，
   handler 全部 import 进来；`lookup(skill_id)` 就是 `DISPATCH_TABLE.get(...)`，命不中 → `UnknownSkillError`。
   **没有任何运行时注册钩子。** 表单能写 manifest，写不了 handler。
2. **`execution_binding=external_capability` 没有通用执行器。** 那 14 条外部能力 manifest（如「外部级联同步执行契约」）
   **全是契约空壳**——不在 DISPATCH_TABLE，调用即报错。
3. **唯一像"通用"的 `adapter_passthrough` 不是执行器**，是 17 个**写死 slug**的**记录型** handler（写 run record + 外部对象映射 + 审计），
   不去执行外部业务逻辑；新增 slug 仍要改 `_PASSTHROUGH_CAPS`（代码）。
4. **package 生命周期只写元数据。** register→review→enable 改的是 `review_status / trust_level / 开放范围 / 租户策略`；
   **不会让能力变得可调用**——调用仍要 DISPATCH_TABLE 里有 handler。
5. **段28 守卫会当场拦。** preflight 强制 `DISPATCH_TABLE == _CATEGORIZATION.md == handler 模块导出` 三处一致；
   一个只有 manifest/DB 行、没代码的能力**直接 FAIL**。
6. **AgentRuntime（D30）是脚手架不是热注册路径。** 它是 agent 通信的数据结构 + 回调契约，没接到 dispatch。

→ 所以「填表→进注册表→热更新可用」今天产出的是**既过不了门禁、调用即报错的空壳**。

## 二 · 关键边界：内置 vs 外部，可行性根本不同

- **内置能力 = 平台代码逻辑本身。** 「自助新增内置能力」= 让用户用表单写平台代码——**不现实、也不该承诺**。
  内置的「可扩展」诚实形态 = 研发走能力注册代码路径（manifest + handler + 评审 + 部署）。**本方案不碰内置热更新。**
- **外部能力 = 调外部系统。** 这个**可以**做成真正的运行时自助接入,因为执行逻辑在外部——平台只需一个
  **声明驱动的通用执行器** + **运行时分发** + **治理门**。**本方案只解决外部能力的运行时自助接入。**

## 三 · 目标架构（让外部能力真能热注册 + 热调用）

### 3.1 manifest 声明驱动（数据,不是代码）
外部能力 manifest 增声明字段:`endpoint`（URL/通道）、`protocol`（http / mcp / a2a）、
`input_contract` / `output_contract`（已有 input/output_schema）、`trust_level`（默认最低）、
`audit_class`、`auth_ref`（凭据指针,承 D36 `_API_KEY_REF`）、`writeback_policy`（仅投影/审计,承 §9.5）。

### 3.2 通用外部执行器（一个 handler 跑所有外部能力）
新增 `external_bridge.handler`:输入 = 注册的外部 manifest + payload → 按 `protocol` 调 `endpoint`,
做 **超时 / 重试 / 幂等键 / 沙箱（出站白名单防 SSRF）/ 审计 / 投影回写**。复用既有 SkillPipeline 六层中间件
（policy→identity→audit→capability_call→persist→anchor),写侧严守 §9.5（只回写投影/审计,不写主状态）。

### 3.3 运行时分发兜底（保留 builtin 静态）
`lookup(skill_id)` 加一层兜底:静态表命不中 → 查 **DB 注册表**,若是「已审批 + 已启用」的 external_capability,
路由到 `external_bridge.handler`。**builtin 永远走静态表**（可信、性能、可审计）。

### 3.4 DB 驱动的注册表
外部能力注册 = 写 DB 行（manifest + endpoint + trust + status=pending）;审批通过 + enable → status=live → 执行器可读。
`load_manifests` 已是每调用重读文件,DB 行同理运行时可见——**热生效,无需重启**。

### 3.5 守卫分轨改造（段28）
- **builtin 道**:维持 `DISPATCH_TABLE == _CATEGORIZATION.md == handler 导出` 三处一致（代码绑定不放松）。
- **runtime-external 道**:新校验 = manifest schema 合法 + endpoint/protocol 声明完整 + trust 默认最低 + 审批门已挂 + writeback 仅投影。
  即「无代码、运行时注册」的能力由**另一套不变量**守,不再要求代码存在。

### 3.6 治理门（安全是头等约束）
- 新外部能力**默认最低信任级**,**必经审批**（human_confirmation）才能 enable;
- **出站白名单 + 沙箱**（防 SSRF/任意端点）;**超时 + 熔断**;**每次调用全审计**;
- **写禁区**:外部能力不得写主状态,只能回投影/审计（承 §9.5 / 段25 / 段22 边界）;
- **多租户隔离**:注册 + 调用按 tenant 收口。

### 3.7 自助接入向导 UI
表单:声明 endpoint/protocol/契约/凭据指针 → **校验**（schema + 端点可达性 + 契约对齐）→ 提交**审批** →
批准后 **enable → 热可调用**。这才是「自助注册 + 热更新」的真实形态。

## 四 · 与现状的关系（不是从零造）
- `adapter.national.*`（D50）= 一处**手工接线**的外部出站实例 → 本方案**泛化**它。
- `adapter_passthrough` 的「记录型通用 handler」模式 + SkillPipeline 中间件 = 可复用的审计/幂等/投影底座。
- AgentRuntime（D30/D33.b）= 外部 agent 契约脚手架 → 执行桥可作为它的运行时落点。

## 五 · 风险（必须安全评审）
SSRF/任意出站、信任级提升、沙箱逃逸、审计完整性、跨租户越权、§9.5 写禁区被绕、性能（运行时分发热路径）、
版本与回滚、凭据泄露（auth_ref 解引用）。**默认 off + 默认最低信任 + 审批门 + 出站白名单**为底线。

## 六 · 分期建议
- **P1**:通用 HTTP 执行器 + 运行时分发兜底,**仅限只读/投影回写**的外部能力,flag 默认 off,出站白名单。
- **P2**:自助接入向导 + 审批门 + 信任默认级 + 段28 分轨守卫。
- **P3**:MCP / A2A 协议支持;与 AgentRuntime 收口。
- **P4**:放量 + 多租户 + 回滚/版本治理。

## 七 · 立项门
本方案属 **架构 + 安全门（D28 + 安全评审）**。**今天不实施**;待产品研发负责人 sign-off + 安全评审通过才立项,
届时登记 D-编号。在此之前,接入扩展中心 UI（A）对外**诚实展示**「已审批接入 ≠ 已能跑」,不做假自助按钮。
