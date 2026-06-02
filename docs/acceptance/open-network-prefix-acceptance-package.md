---
doc_id: open-network-prefix-acceptance-package
status: awaiting-signoff
gate: pending
scope: open-network-prefix
evidence: .testing/acceptance/open-network-prefix/evidence.json
sign_off_required:
  - 海若产品部业务方
vehicle_pr: "#184"
driven_by:
  - PR #184「统一为所有接口增加 zw-brain/ 前缀」（反代部署前缀：vite base /zw-brain/ + 后端剥前缀路由 + 前端 apiUrl 单一前缀源）
  - tests/test_rest_zw_brain_prefix.py（前缀路由 + OIDC 同源边界负向）
  - tests/test_rest_web_static.py（dist-vite 前缀资产服务）
  - tests/test_contract_projection.py / tests/test_platform_guide_web_surface.py（apiUrl 网关守卫）
  - .testing/waves/wave-0-golden-path/features/infra-contract-projection.feature（单一契约→五消费面投影一致，前缀部署下仍成立）
---

# open-network-prefix 效果验收材料包 — 反代部署前缀（/zw-brain/）

> **D37 效果验收**（"做完的东西真能跑"）。PR #184 把 WebUI + 后端统一挂到 `/zw-brain/`
> 反代前缀下，使本服务可在网关子路径部署。验收点挂
> `.testing/acceptance/open-network-prefix/evidence.json`，由 `capture_acceptance_evidence.py`
> 在 **customer_acceptance_up 重建的干净全量真实库** 上现场跑出（contract + 全套 pytest 退出码），段 55 守卫。
> 浏览器层活跑作为「业务方眼见为实」人验补充。

## 验收范围

**覆盖**：
- 后端 REST 在 `/zw-brain/` 前缀下路由（健康检查 / auth / api/skills / agent-runtime），裸路径保留 back-compat；前缀剥离有边界（`/zw-brainfoo` 不误剥）。
- OIDC 登录回跳同源校验精确化：跨 host **与**同 host 跨端口都拒绝（撤销 PR 初版的"忽略端口"放宽 — 防开放重定向）；nginx 外部端口经 X-Forwarded-Host/Port 还原。
- 前端 `vite base=/zw-brain/` + 单一前缀源 `useApiBase.ts`（`apiUrl`/`appOrigin`），消除散落硬编码；built index 在前缀下引用 `/zw-brain/assets/*` 并可加载。
- 前端 router `createWebHashHistory(import.meta.env.BASE_URL)`：SPA 跳转（登录/登出/页间）后地址栏保留 `/zw-brain/` 前缀（走查发现并修复，guard 测试防回潮）。
- 反代前缀部署文档：`docs/deployment/docker-image-deployment.md` §4.1 nginx `location /zw-brain/` + X-Forwarded-* 转发头要求。
- 单一能力契约 → 五消费面投影一致性在前缀部署下不破（infra-contract-projection）。

**不在本次范围**：
- 真实 IAF/OIDC 生产接入与 docker 镜像部署（本次本地以 dev bypass + mock 推理走查；prod 走 docs/deployment/docker-image-deployment.md）。
- WebUI Playwright e2e 层活跑（本机 `--with-e2e` 不能干净复现，已在册 debt）；本次浏览器活跑以人验记录，不挂机器 e2e 证据。
- 仓内 ~30 个测试 fixture 裸改 `ZW_BRAIN_DB_PATH` 无 teardown 的测试隔离债（已登记 `.testing/debt/test-db-path-isolation.debt.yaml`，本次仅修复受害测试 provider_snapshot）。

## 验收点 + 证据（每条挂 evidence 标签）

| 验收点 | evidence（机读证据） | 结果 | 业务方判定 |
|---|---|---|---|
| 单一能力契约 → 五消费面投影一致，前缀改造零漂移 | `5 消费面投影一致`（contract） | pass | ☑ 通过 |
| 后端全套绿（干净全量真实库）：含前缀路由 + 同源边界负向 + dist-vite 前缀资产 + 全仓不回归 | `后端 / 契约测试套`（pytest exit 0） | pass | ☑ 通过 |

## 业务方眼见为实（本地全栈 `:8800` 走查，2026-06-02 通过）

> 入口 `http://127.0.0.1:8800/zw-brain/`（dev bypass + mock 推理）。

- WebUI 在 `/zw-brain/` 前缀下加载，资产 `/zw-brain/assets/*` 正常拉取；dev bypass 直登，角色切换可切各角色逐页走查。
- 健康检查 `/zw-brain/health` 与裸 `/health` 均通；带前缀的 skill 调用经鉴权门可达。
- 登录回跳：同源 `/zw-brain/` 放行并生成 authorization_url；跨 host、同 host 跨端口均被拒（`redirect origin mismatch`）。
- 页间 / 登录 / 登出跳转后地址栏始终保留 `/zw-brain/`（走查首轮发现 `localhost:8800/#/login` 丢前缀 → 修 router base 后复验通过）。
- 全前缀敏感面复扫（location/history/asset/cookie path/重定向）无其它遗漏。

## 数字纪律

测试 / 投影计数为事实计数，住 evidence.json（脚本采集），prose 不裸写易漂移数字。

## 落盘（验收通过后 — D46.b/d，账本是唯一权威源）

- [ ] **A**：vehicle PR #184 加 label `signoff:open-network-prefix` + PR body 写 `<!-- signoff ... -->` 机读块（`scope: open-network-prefix` / `kind: 效果验收` / `decision_only: true` / `covers: []`）。合并时 `signoff-ledger.yml` 自动落 `.testing/signoff/open-network-prefix.signoff.yaml` 账本。
  > 反代前缀属部署形态工作，无独立 `.feature` 入飞轮（infra-contract-projection.feature 是五消费面契约一致性、非本前缀的交付物），故 `covers` 留空、不抬任何 feature 状态（沿用 j1-catalog-drilldown 先例）。
- [ ] **B**：CLAUDE.md 追加 `D<编号>` 决策条（反代前缀部署 + OIDC 同源边界精确化）。
- [ ] **C**：本文 frontmatter `status: approved`（账本落盘后）。

> A 由段 54（approved scope ↔ 账本）+ 段 63（账本 schema/covers/evidence）校验；本文证据真实性 + 结构由段 55 校验。
> 业务方 2026-06-02 本地全栈走查通过；合并到 main 待产品负责人指令。
