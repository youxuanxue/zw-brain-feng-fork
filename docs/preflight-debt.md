# preflight-debt

Outstanding items intentionally deferred from the current preflight gate set. Each entry must list
the symptom, the deferred decision, and the trigger that forces a re-evaluation.

任何一条 entry 在 trigger 触发时必须升级为 P0 fix 或转化为机械化 preflight check；不允许长期沉淀。

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

## 2026-05-22 — standard.asset.sync manifest preserved with deferred:wave-4 status

- **Where**: `zw_brain/skill_registration/registered/standard.asset.sync.json` (status=deferred:wave-4,
  journey=b1)；引用面包含 `zw_brain/command/brain.py` dispatch case (line 267, 与 4 个其他 skill 共享 case)、
  `zw_brain/domain/policy.py` 权限映射 (line 180)、`zw_brain/domain/repositories/compliance_ops.py`
  docstring (line 29)、`scripts/regenerate_bsp_capability_manifest.py` 旧平台 FUNC_GOVERN_STANDARD
  映射 (line 30)、3 个生成产物 (`zw_brain/entry/rest/openapi.json`、`zw_brain/entry/a2a/agent_card.json`、
  `zw_brain/entry/a2a/tools/runtime_bindings.json`)、2 份文档 (`docs/agent_integration.md`、
  `docs/reconstructs/compliance-ops-adapters-reconstruction-plan-v1.md`)。
- **Implication**: §1.3 "标准服务 = 旧平台几乎不用" — UI 不可达即可，无业务运行必要。本期未物理删除。
- **Why deferred**: P0-03 范围严守 registry 元数据，不允许动 `export_agent_contract.py` 与 5 surface 投影（P0-04 范围）；
  物理删除需触 8 个引用面 + 重新生成 3 个 openapi/a2a artifacts，与 P0-04 投影过滤路径冲突。
  P0-04 实现 status≠live 过滤后，deferred:wave-4 已机械不进任一消费面投影（webui/api/cli/mcp/a2a），
  与物理删除业务效果等价。
- **Trigger to re-evaluate**: (a) P0-04 投影过滤完成且确认 status=deferred:wave-4 已不进 openapi/agent_card/runtime_bindings；
  (b) Wave 4 legacy 退役期统一清理：届时一并删除 manifest + brain.py dispatch case 中的 `standard.asset.sync` 分支 +
  policy.py 权限条目 + scripts mapper + 2 份 doc 引用 + 重新生成 3 个 artifact；
  (c) 任何客户场景实际触发 `standard.asset.sync.execute` 调用——则立即从 debt 升级为产品需求。
- **No mechanical preflight check (now)**: AC2 新门禁 (P0-05 段 22) 只拦"禁区域 status=live+builtin"；deferred:wave-4
  本就不是 live，机械上不会触发回归。

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
