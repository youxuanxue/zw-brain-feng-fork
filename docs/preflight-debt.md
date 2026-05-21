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
- **Why deferred**: Hard guard 已落 — `start-local.sh` 拦截 `ZW_BRAIN_DEPLOY_MODE=prod`；调用方
  若显式设置 `ZW_BRAIN_IAF_AUTH_SERVER_URL` 则自动放弃 bypass 走真 IAF 流程。docker-image-
  deployment.md 路径不通过 start-local.sh / customer_demo_5min.sh 启动，从入口隔离风险。
- **Trigger to re-evaluate**: 首个真实客户部署上线前，加机械化 preflight 段检测 prod 部署清单
  里 `ZW_BRAIN_DEV_IAM_BYPASS` / `ZW_BRAIN_DEV_IAM_BYPASS_ACK` 不出现；同时审查所有 bypass 分支
  代码是否仍必要（理想是首位客户上线后直接删 bypass 路径，硬性走真 IAM）。
- **Mechanical guardrail (now)**: `start-local.sh` 的 prod-mode 拦截 + `customer_demo_5min.sh`
  的本机端口绑定（127.0.0.1）；这两条已是事实层兜底，不再加 prose 软提醒。
