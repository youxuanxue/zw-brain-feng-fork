# preflight-debt

Outstanding items intentionally deferred from the current preflight gate set. Each entry must list
the symptom, the deferred decision, and the trigger that forces a re-evaluation.

任何一条 entry 在 trigger 触发时必须升级为 P0 fix 或转化为机械化 preflight check；不允许长期沉淀。

## 2026-05-24 — AgentRuntime runtime 触发式延后（D30 retrofit）

- **Where**: 协议规范 `docs/agent-runtime/product-integration-guide.md` + `agent-runtime-api-cn.md` 完整；
  Registry schema 4 新字段（`runtime_spec_version` / `agent_yaml_ref` / `trust_level` / `workspace_required`）
  + `scripts/agentruntime_validate.py` + `scripts/agentruntime_doctor.py` + 内置 Agent `AGENT.yaml` 样本
  **均未创建**。
- **Implication**: 架构基线 §8 / R15 描述了外部 Agent 通过 AgentRuntime 接入的产品决策；但运行时未实现。
  原 §10.2 "Wave 1 必达 ≥1 内置 Agent 用 AGENT.yaml 通过 validate+doctor"（产品负责人 sign-off 2026-05-22）
  已 D30 撤回为触发式（架构 §8.6）。
- **Why deferred**: 当前 zw-brain 无外部 Agent 接入排队，按 OPC「只为真实需求建复杂度」拒绝提前盖楼；
  Registry 单源派生 5 消费面 + `product_scope.{journey,status}` 过滤已机械保证 status≠live 不进任何投影，
  外部 Agent 通过现有 capability 调用走 5 surface 任一面即可，不需要额外 runtime 层。
- **Trigger to re-evaluate** (任一触发即升级为 P0)：
  - **T1**：出现首个真实外部 Agent 接入需求（ANP / Cursor / 第三方 IDE）→ 立即新增 Registry schema 4 字段
    + validate/doctor 工具链 + preflight 段强制约束。
  - **T2**：客户要求 zw-brain 内置 Agent 以 `AGENT.yaml` 形态对外暴露 → 选 1 个低风险 builtin Agent 转写。
  - **T3**：B1.2 接入扩展中心 UI 立项（Wave 2 范围）→ §8.4 7 步流水线 UI 化。
- **No mechanical preflight check (now)**: 段 22 capability 禁区前缀 + `validate_manifest` 现有约束已兜底
  「未授权能力不得变 live+builtin」；额外的 AgentRuntime 字段守卫在 T1/T2 触发前是 noise。
- **不预先盖楼**：在 T1/T2/T3 任一触发前，主仓库不引入未被消费的 schema 字段、不写空跑的 validate/doctor 脚本、
  不在测试夹具里维护 AGENT.yaml 样本。

## 2026-05-24 — 附录 C 4 项 trigger 化 pending（D30 retrofit）

设计基线 §附录 C「软→硬映射」表中以下 4 条由"待接入"改为"trigger 化 pending"。每条配明确 trigger，
任一触发即升级为 P0 fix 或机械化 check：

- **外部能力包必须带治理元数据** — Trigger：出现首个外部能力包注册请求（与 §8.6 T1 联动）。
  届时新增 `scripts/check_external_package_metadata.py`（治理元数据 schema：rollback_target /
  audit_class / tenant_scope / auth_policy 必填）。
- **Capability 确认边界不得被 UI / Agent 绕过** — Trigger：出现 UI / Agent 绕过 `human_confirmation_required`
  的案例 OR §8.6 T1 触发。届时新增 `scripts/check_confirmation_boundary.py`（contract `human_confirmation_required=true`
  必须在 brain.invoke_skill 链路有运行时校验点）。
- **反 per-tenant fork** — Trigger：出现第二个真实租户 OR 客户提出 fork 后端意图。当前单租户 `sd-default`，
  无 fork 风险；多租户实装时新增 `scripts/check_no_tenant_fork.py`（仓库 grep 拒绝 `tenant_id == "specific-customer"`
  类硬编码分支）。
- **控制面不得出现多处手维护投影** — Trigger：`export_agent_contract.py --check` drift 后发现手维护痕迹。
  当前 5 消费面均派生自单 registry；新增 `scripts/check_no_hand_maintained_projection.py`
  扫 5 投影目录是否含"AUTO-GENERATED; DO NOT EDIT BY HAND"banner 之外的人工 patch 痕迹。

## 2026-05-18 — BFF session store is single-process in-memory

- **Where**: `zw_brain/shared/auth_session.AuthSessionStore` (thread-safe dict in the REST entry process).
- **Implication**: A multi-process / multi-replica REST deployment will hand out cookies that only
  resolve on the issuing replica. Subsequent requests routed to a different replica look like
  un-authenticated traffic.
- **Why deferred**: Current zw-brain REST deployment is single-process (one `zw-brain-rest` worker
  per node, sticky LB upstream). Adding Redis / DB-backed sessions before any deployment actually
  needs it would be premature infra.
- **Trigger to re-evaluate**: First time we want to run `zw-brain-rest` behind a non-sticky load
  balancer, or run more than one REST worker, switch to an out-of-process backend (Redis preferred:
  TTL + `secrets.compare_digest` semantics already match the in-memory store).
- **No mechanical preflight check**: Adding a "deployment topology" gate today would be noise. The
  trigger above is concrete enough that we'll know when to act.

## dev-iam-bypass — `ZW_BRAIN_DEV_IAM_BYPASS=1` 仅限本机/演示

- **Where**: `scripts/start-local.sh`、`scripts/customer_demo_5min.sh` 默认 export
  `ZW_BRAIN_DEV_IAM_BYPASS=1` + `ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only`，使本机不依赖
  IAF/OIDC 即可登录走 WebUI；逻辑在 `zw_brain/shared/auth_session.py` + `zw_brain/entry/rest.py`
  的 bypass 分支。
- **Implication**: 该 bypass 在生产环境会绕过真实 IAM；客户机房若误开等于无身份认证。
- **Status (2026-05-23 G1.4 升级)**: Mechanical preflight (now) — 段 23
  `scripts/check_iam_prod_guard.py` 扫描部署清单（`Dockerfile*` /
  `docker-compose*.yaml` / `scripts/deploy*.sh`），若同文件同时出现
  `ZW_BRAIN_DEPLOY_MODE=prod` 与 `ZW_BRAIN_DEV_IAM_BYPASS*` 任一关键字
  → exit 1。debt entry trigger（「首个真实客户部署上线前」）由 G3「找一个真客户
  在屏幕前 30 分钟跑通」等价触发，故此 G1 期落地。
- **Why preflight (and not deletion of bypass code yet)**: bypass 在
  `start-local.sh` + `customer_demo_5min.sh` + Playwright e2e 路径仍是
  默认入口；删除代码层 bypass 路径在首位客户上线后处理。当下机械守的是
  「漏到生产清单」这条最危险路径。
- **Mechanical guardrail (now)**:
  1. `start-local.sh` 的 prod-mode 拦截（运行时）
  2. `customer_demo_5min.sh` 的 127.0.0.1 绑定（网络层）
  3. **段 23 preflight scan**（commit-time，G1.4 新增）
  这三条层叠兜底；不再加 prose 软提醒。

## 2026-05-23 — 5 个 borderline B1 业务报表 capability 仍 live，待业务方 sign-off

- **Where**: 5 个 manifest 当前 `product_scope = {journey: b1, status: live}`：
  - `service.rating.submit` (服务评价提交)
  - `ops.catalog.statistics.query` (目录资源统计)
  - `ops.exchange.statistics.query` (交换统计)
  - `ops.service.invocation.query` (服务调用统计)
  - `ops.service.report.query` (服务运行态势)
- **Implication**: 这 5 条按 `docs/reconstructs/p0-contract-classification.md` §2.5 / §2.8 判定语义是
  "**业务运营报表**"（基于 capability_call / rating 业务事实），不是 §1.3 "运行监控" 禁区。当前保留 live B1。
  若业务方下次 review 判定其中任何一条更接近"运维监控"或"应用案例评分"形态，需翻转 status → external，
  并重新生成 5 surface 投影。
- **Why deferred**: PR #75 (P0-04) 落地时业务方未现场 sign-off；提前一刀切到 external 会误伤实际业务报表场景。
  Jobs 风格的可逆决策：保留 live + 走 debt 跟踪，比预先砍掉再回来补成本低。
- **Trigger to re-evaluate**: (a) 业务方（红军 / 旧平台产研负责人）下次 IA review 对 5 条逐一 sign-off；
  (b) 任何客户实际反对场景出现——立即翻 status=external + 重新跑 `python scripts/export_agent_contract.py`
  让 5 surface 同步剔除。
- **No mechanical preflight check (now)**: 段 22 不收录"borderline 业务报表" 前缀（不在 §1.3 已观察禁区前缀清单内）；
  这是设计 intent，避免 false positive 误伤合法报表能力。debt 条目本身就是兜底跟踪。

## 2026-05-23 — 集成测试用 `brain.invoke_skill()` 直调，绕过 trust-stamp 路径

- **Where**: `tests/test_wave1_j2_pipeline.py`、其他通过 `_call(brain, skill, payload)` →
  `brain.invoke_skill(...)` 直调集成测试。生产 mutate skill 入口是
  `REST cookie session → build_trusted_skill_payload → _TRUSTED_SESSION_MARKER stamp → invoke_skill`，
  这些集成测试**完全跳过 stamp 步骤**。
- **Implication**: 任何因 `_TRUSTED_SESSION_MARKER`（object() 哨兵）跨序列化边界泄漏导致的
  TypeError，**pytest 集成层无法覆盖**——必须 e2e（Playwright cookie session）才能复现。
  PR #79 的 B1 + B3 两个 production 500 都属此类（existing 20 项 regression 全过、客户演练打一发就 500）。
- **Why deferred**: 全面在集成层补 trusted-payload fixture 是一次较大的测试 pyramid 改造（每个
  mutate skill 测试都要加 fixture），单 PR 内做会过度扩张范围。PR #79 已在 `tests/test_trusted_session_context.py`
  新增 `test_mutate_skill_with_trusted_payload_persists_anchor_outbox` 作为此 bug 类的护栏——
  下次出现类似 sentinel 跨边界问题，本测试会失败。但**其他 mutate skill 仍存在层级缺口**。
- **Trigger to re-evaluate**: (a) 再出现一次"e2e 抓到、pytest 没抓到"的 production 现场——立即把
  trusted-payload helper 提取到 `tests/_trusted_payload.py` 并所有 mutate skill 集成测试改走该 helper；
  (b) Wave 2 测试 pyramid 整改窗口期，主动 retrofit。
- **No mechanical preflight check (now)**: 检测"集成测试是否经过 trust-stamp"需要 AST 分析或测试
  覆盖率打标，复杂度高于价值。Debt 条目兜底，加 R-001 类点护栏。
