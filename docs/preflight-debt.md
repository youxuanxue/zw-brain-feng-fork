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

## 2026-05-21 — 前端路由编号化（P0–P8）是反模式 — 待去编号化

- **Where**: `zw-brain-web/js/app.js`（9 个主路由全部带 `#/p0-…` ~ `#/p8-…` 编号前缀）+
  `zw-brain-web/js/pages.js`（`key: 'p1'` ~ `'p8'` 8 处 page key 编号化 + 14+ 处 href / 映射）
  + 后端测试 `tests/test_j1j2_b1_browser_matrix_e2e.py`、`tests/test_w4_inline_panels.py` 等
  对 `#/p4-…` / `#/p6-…` 等路由名断言。
- **Implication**: 把信息架构编号烙进 URL 是反模式：
  1. **IA 一动就全栈改**。基线 `docs/approved/zw-brain-architecture.md` §5.2 已把 P6 改名 **B1.1
     合规与运营**、P8 改名 **B1.2 平台接入与扩展中心**；实现层未跟，于是 PR #68 不得不用 7 处
     "（路由仍为 p6-compliance-ops）"桥接注释做表面修复 —— 漂移的根因正是编号化路由本身。
  2. **P0/P6/P8 已经"语义和编号脱钩"**。P0 是实施工程师迁移验收（非普通用户旅程），P6/P8 是后台
     支撑面（非主旅程序列）。编号失去信息价值，反而成为认知负担。
  3. **新增/重排页面无处插**。加新页面要插哪个编号？把 P0 移到 P8？编号成为扩展性枷锁。
  4. **URL 对用户不透明**。`#/p6-compliance-ops` 中 `p6` 是冗余信息（路径段已有 `compliance-ops`）。
- **Why deferred**: 去编号化是 9 路由 × 20+ 文件的跨栈改造（app.js 路由表、pages.js page key 常量、
  document.title、UI 跳转 hash、外链书签、所有 e2e 测试 fixture 路由断言、auth.js 路由白名单），
  且需重跑 webui 浏览器 e2e 全矩阵 + 截图回归。属独立工程量，绑进 PR #68 会让 review 复杂度失控。
- **Trigger to re-evaluate**: 任一条命中即起独立 PR：(a) 基线 §5.2 / R16 后续 R 编号推进 B1.1/B1.2
  落地；(b) 客户/新成员对 "P6 是什么" 提出第二次困惑；(c) 下一次针对 B1.1 / B1.2 surface 的功能 PR
  顺手统一；(d) 主动选择"路由清洁周"集中改造。
- **目标终态**: 路由 = 纯语义路径（`#/compliance-ops` / `#/discovery` / `#/provider` / `#/request-flow`
  / `#/delivery-exchange` / `#/zones-pack` / `#/integration-admin` / `#/migration-acceptance` /
  `#/workbench`）；编号留在 IA 文档 (`docs/approved/zw-brain-architecture.md` §5.2) 内部，**不暴露给
  路由/URL/page key**。这样 IA 重排只动文档，不动代码。
- **Mechanical guardrail (now)**: 注释/docstring 在 PR #68 内统一带 "（路由仍为 p6-compliance-ops）"
  桥接说明 —— 让读到注释的人不必跨文件追线。无对应 preflight hook（编号化是合法 URL 段，非退役 token）；
  靠 trigger 主动重评。去编号化落地后，应增加 preflight check：禁止 `app.js` / `pages.js` 路由表新增
  `#/p[0-9]` 形式路由（防回潮）。

## dev-iam-bypass — `ZW_BRAIN_DEV_IAM_BYPASS=1` 仅限本机/演示

- **Where**: `scripts/start-local.sh`、`scripts/customer_demo_5min.sh` 默认 export
  `ZW_BRAIN_DEV_IAM_BYPASS=1` + `ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only`，使本机不依赖
  IAF/OIDC 即可登录走 WebUI；逻辑在 `zw_brain/shared/auth_session.py` + `zw_brain/entry/rest.py`
  的 bypass 分支。
- **Implication**: 该 bypass 在生产环境会绕过真实 IAM；客户机房若误开等于无身份认证。
- **Why deferred**: Hard guard 已落 — `start-local.sh` 拦截 `ZW_BRAIN_DEPLOY_MODE=prod`；调用方
  若显式设置 `ZW_BRAIN_IAF_AUTH_SERVER_URL` 则自动放弃 bypass 走真 IAF 流程。docker-image-
  deployment.md 路径不通过 start-local.sh / customer_demo_5min.sh 启动，从入口隔离风险。
- **Trigger to re-evaluate**: 首个真实客户部署上线前，加机械化 preflight 段检测 prod 部署清单
  里 `ZW_BRAIN_DEV_IAM_BYPASS` / `ZW_BRAIN_DEV_IAM_BYPASS_ACK` 不出现；同时审查所有 bypass 分支
  代码是否仍必要（理想是首位客户上线后直接删 bypass 路径，硬性走真 IAM）。
- **Mechanical guardrail (now)**: `start-local.sh` 的 prod-mode 拦截 + `customer_demo_5min.sh`
  的本机端口绑定（127.0.0.1）；这两条已是事实层兜底，不再加 prose 软提醒。
