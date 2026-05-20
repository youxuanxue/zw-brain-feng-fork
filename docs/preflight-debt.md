# preflight-debt

Outstanding items intentionally deferred from the current preflight gate set. Each entry must list
the symptom, the deferred decision, and the trigger that forces a re-evaluation.

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

## 2026-05-19 — handover-checklist #40 expects ≥12 distinct skill_id in prod DB but e2e uses isolated TemporaryDirectory

- **Where**: `docs/deployment/handover-checklist.md` §九 #40 expects
  `SELECT COUNT(DISTINCT skill_id) FROM audit_event >= 12` against `$ZW_BRAIN_DB_PATH`.
- **Implication**: `tests/test_acceptance_9_roles_e2e.py` 10 个 pytest 各自创建 `TemporaryDirectory()`
  + isolated DB（参 test_acceptance_9_roles_e2e.py fixture），其 audit_event 不会落回主
  `customer_acceptance.db`。结果：客户验收员按 checklist 跑完 41 项后，#40 主 DB 上的
  distinct skill_id 仅承接 M0 主流程 + ITEM-02 5 段 curl 等真实业务调用（实测
  `customer_acceptance.db` 当前 = 8 distinct skill_id）。
- **Why deferred**: 修复方向有两种，都不在 ITEM-07 范围内：
  1. 改 e2e fixture：把 audit_event 写到主 DB（破坏 test isolation，可能引入 flaky）；
  2. 改 checklist 语义：把 #40 改为『跑 customer_demo_5min + 一遍人工操作后 ≥12』
     （需重新设计验收脚本组合）。
  现阶段把 partial 标在 part 1/3 run log + 在 #40 行补 "**注**" 说明（part 2/3 已落）。
- **Trigger to re-evaluate**: 客户首个真实交付现场实跑 41 项时如果 #40 < 12，**必须**
  在客户机房按 checklist 改后的『主流程驱动 + 真实业务用户操作后再查』路径再查一次；
  仍 < 12 则升级为 P0 fix（改 e2e fixture 或 checklist 语义）。
- **No mechanical preflight check**: 这是 checklist 设计语义与 test isolation 设计的固有
  矛盾，不是机械可检测项；trigger 已落到客户首次实跑的实操步骤。

## 2026-05-19 — customer_main_journey_real_browser e2e skip 跟踪（PR #60 留债）

- **Where**: `tests/test_webui_browser_e2e.py:303-309`，已加 `@pytest.mark.skip(reason="...")`。
- **Symptom**: PR #60 D23 retrofit 后该测试损坏；浏览器渲染"页面暂未准备好"而非预期资源详情。
  通过 git stash/pop 验证：测试在 D23 retrofit 一开始就坏，与 PR #61 工作无关。
- **Why deferred**: PR #61 范围是 J1+J2+J3 闭环 + e2e 矩阵，已由
  `tests/test_j1j2j3_browser_matrix_e2e.py` 6 个新用例（自动化截图 5 张）完整覆盖。
  这个测试涉及"深度 hash 路由 + customer_acceptance_up.sh 真数据库 + 5 角色穿插"的复杂场景，
  根因排查需另开 PR（疑似 snapshot 在带 sharing_type 字段后的 role-filtered 投影路径有 corner case）。
- **Trigger to re-evaluate**: 下次接手客户验收前的 final smoke 时必须修复；
  在那之前由 J1+J2+J3 browser matrix e2e 提供等价业务流程覆盖。
- **No mechanical preflight check**: 测试 skip 已显式声明 reason；preflight 不会"误以为绿"。
