# 任务：P2 — e2e 写路径切无 cookie + 全量 feature 重采

> **给接手的干净 session**：这是一份自包含执行任务书，读完即可执行，不依赖任何历史对话。
> 起手：`读 docs/follow-ups/p2-csrf-e2e-no-cookie-write-and-recapture.md，按它执行`。
> 性质：**测试桩债止血 + 一次有意的 feature 测量重采**。低产品风险、**高流程风险**（重采会牵动全部 feature 指纹），必须**专门一个 session 盯着做**，不可塞进顺手小 PR。
> 基线：从最新 `main` 起一条 `fix/` 分支。

---

## 0. 一句话目标

把 e2e 里"带 cookie 调 `/api/skills` 写接口"（命中 CSRF → 403 → 测试 setup 假失败/假 skip）的 9 个点，全部切到**无 cookie 的 `playwright.request.newContext()`**（role 走 body），加一道守卫防回潮；因其中 5 个点住在**全局盐文件** `tests/e2e/helpers.ts`，改完会让全部 ~51 个 feature 指纹失效 → **必须做一次 `--with-e2e` 全量重采**把绿 feature 重新盖指纹，最后 preflight 段60 + CI 全绿。

---

## 1. 背景：问题是什么（症状）

部分 e2e 测试跑前要"造数据"（建假申请/异议等），办法是**带着浏览器登录 cookie、直接 `page.request.post('/api/skills/<skill>')`**。但后端 CSRF 双提交防伪要求：**带 cookie 的请求必须附 X-CSRF 令牌**。这些直调没带令牌 → **403 `csrf_token_invalid`** → 造不出数据 → 测试 setup 失败/skip。表面"绿"实则**假覆盖**（典型受害：`b12_iam_governance` 4 个 P0、`webui_smoke` 的 mint、`wave15` 两级链路、`form_autofill`）。

## 2. 根因（已三轮证伪，勿重复怀疑）

- **CSRF 双提交是签字安全设计（PR#53），生产侧正确，一字不动。** 机制在 `zw_brain/entry/rest/server.py`（grep `csrf`/`X-CSRF`/`_dev_iam_bypass`）：**Path 1 = 有 cookie 会话**强制校验 X-CSRF；**Path 2 = 无 cookie**走 dev-bypass、role 从 body 取、**不校验 CSRF**。
- **缺陷纯在测试客户端**：`page.request` 复用浏览器 cookie → 命中 Path 1 却不附令牌 → 必 403。
- **正确范式 = 无 cookie 上下文**：`const api = await playwright.request.newContext(); api.post('/api/skills/<skill>', { data: { role:'ROLE_X', ...} })`。**参照现成实现**：`tests/e2e/permission_matrix_walkthrough.spec.ts` 的 `invoke(api, skill, data)`。

## 3. 修复范围（当前 main 实测 9 个写点；先 grep 复核行号，勿信本文件固定行号）

复核命令：`grep -rnE "page\.request\.(post|put|patch|delete)\(" tests/e2e/ | grep api/skills`

| 文件 | 写点 | 说明 |
|---|---|---|
| `tests/e2e/webui_smoke.spec.ts` | 3：`request.create` / `request.submit` / `application.platform_approve`（`mintRejectedRequest`） | 非盐、0 feature 引用 |
| `tests/e2e/wave15_two_stage_walkthrough.spec.ts` | 1：`invoke` 泛型 POST | 非盐、0 feature 引用 |
| **`tests/e2e/helpers.ts`** | **5**：`catalog.entry.query` ×4 + `catalog.entry.review` ×1 | **GLOBAL_SALT_FILE！改它即触发全量重采** |

**改法**：
1. 新增/复用一个无 cookie 写助手（可放 `tests/e2e/helpers.ts` 内，或新建 `tests/e2e/apiContext.ts`——见 §6「能否避开重采」）。形如 `mintViaApi(playwright, skill, data)` / `newApiContext(playwright)`，内部 `playwright.request.newContext()`，role 走 body。
2. 把上述 9 个写 POST 切过去；**需要把 `playwright` fixture 传进相关 helper / 用例**（解构 `{ page, playwright }`）。
3. **GET 读不动**：`page.request.get(...)` 是合法读路径（如 `workbench_todo_closure` 的 GET 范式、snapshot GET），不切、不误伤。`catalog.entry.query` 虽是读 skill 但当前走 POST——切无 cookie POST 即可（或确认后端支持 GET 再改 GET，二选一，别两头改）。
4. **加守卫 `scripts/check_e2e_no_cookie_write.py`**：正则禁 `page.request.(post|put|patch|delete)(` 指向 `/api/skills/`；**白名单 `page.request.get`**；`// csrf-ok:` 行豁免兜底。命中 FAIL 打印 file:line。**必须用真实样本验非 co-vacuous**：注入一行写 POST→守卫红、注入 GET→不报、移除→绿（把三次输出写进 PR）。在 `scripts/preflight.sh` 的 CHECKS 表注册新段（仿现有段如 `check_no_placeholder_word` 的挂法，tab 分隔三字段）。

> 注：二轮曾有 worker 完整做过这套切换（patch 已弃，但范式可复刻）。本任务从头做即可。

## 4. 为什么必须重采（核心，别想绕）

`tests/e2e/helpers.ts` 在 `scripts/feature_status_lib.py` 的 `GLOBAL_SALT_FILES`（grep 确认，约第 62 行）。feature-status 的"已验收"印章按一个**内容指纹** = `.feature` + 其引用测试文件 + **全局盐文件**。**一动盐文件，全部 ~51 个 feature 指纹一起失效** → `scripts/preflight.sh` 段60 `feature-measurement` 会 FAIL（"N 个 feature 测量陈旧"）+ `feature-status-gen` 漂移，直到重采。这是 D46.g 防偷懒设计，不是 bug。

## 5. 重采流程（命令 + 环境 + 风险）

- **重采脚本**：`scripts/capture_feature_status.py --with-e2e`（**现场跑测试、退出码即事实，禁手写 result**）。CI 配方见 `.github/workflows/ci.yml`（grep `capture_feature_status`，约 :262）：`--with-e2e --e2e-only`，跑在 **seed_snapshot（干净 light 种子）** 上，**e2e allowlist 当前仅 `twin_browser_pages.spec.ts`**。
- **环境**：
  - PG 在线：`docker compose up -d postgres`（D66 全盘 PG）。
  - 干净 seed（重采须在"feature 本绿"的环境跑，否则数据缺位会把 feature 误判非绿）。本地起栈：`bash scripts/start-local.sh`（dev IAM bypass + mock 推理，:8800）。
  - venv：用仓库 `.venv`（含 psycopg）；`set -a; . ./.env; set +a`。
- **三个风险（必须盯）**：
  1. **vacuous-skip 守卫**：`passed==0` 一律记非绿。起栈跑 e2e 时把会 skip 的前置 flag 打开（如 `ZW_BRAIN_NATIONAL_CHANNEL_ENABLED=1`，见 `capture_feature_status.py` 头注 + `national-platform-access-D50.md`）。
  2. **flaky 翻绿→非绿**：重采那一刻某 feature 测试抽风没过 → 它从 Done 掉成非 Done = **测量回归**，看着像一口气搞坏几十个 feature。**逐个失败要查清是真失败还是 flaky/环境**，不能放任 capture 把它记非绿。
  3. **产物落盘**：`.testing/status/measurement/<git_sha>.json`（tracked + banner），preflight 段60 读；`feature-status.md` 由 `gen_feature_status.py` 现算，跑 `python3 scripts/gen_feature_status.py` 重生成、勿手改。

## 6. 能否避开重采？（一个判断点，接手时定）

- **完整修**（修全部 9 点，含 helpers.ts 5 点）→ 碰盐文件 → **必重采**。这是本任务默认路径。
- **盐文件无关偏方**：把无 cookie 助手放**新文件**（如 `tests/e2e/apiContext.ts`，不在 GLOBAL_SALT_FILES），**只改 `webui_smoke`/`wave15`（0 feature 引用、非盐）**、**不碰 helpers.ts 的 5 点** → 不触发重采。但这样 **helpers.ts 里 5 个写点仍假失败**、修不彻底。
- **建议**：既然要做就**做完整**（含 helpers.ts）+ 走重采；偏方只是"实在不想重采时的半程止血"。重采本就是这个任务的正题。

## 7. 执行步骤（建议顺序）

1. 起栈 + PG + 干净 seed，确认 preflight 当前绿（基线）。
2. 写无 cookie 助手 + 切 9 个写点 + GET 不动。
3. 写守卫 `check_e2e_no_cookie_write.py` + 挂 preflight；真实样本验非 co-vacuous（注入→红/GET→不报/移除→绿）。
4. `vue-tsc`（如涉及）+ `npx playwright test --list`（语法）+ `ruff check` 守卫。
5. **重采**：`python3 scripts/capture_feature_status.py --with-e2e`（按 CI 配方的 flag/seed）；逐个非绿 feature 查清真伪，直到全部该绿的回绿。`gen_feature_status.py` 重生成。
6. `bash scripts/preflight.sh` → **段60 feature-measurement 绿 + feature-status-gen 绿 + 新守卫绿**，零 FAIL。
7. **真覆盖自证**：起栈（富真库可选）跑之前会 skip 的 spec（`webui_smoke` mint 链、`wave15`、`b12_iam_governance`），确认**真 RUN 且 passed**（非 skip）。
8. 开 PR（base main），CI 全绿（尤其 `e2e + feature measurement` job）。**merge 永远人工**。

## 8. 验收门（全绿才算完）

- [ ] 9 个写点全切无 cookie；GET 读未误伤
- [ ] 守卫 `check_e2e_no_cookie_write.py` 挂 preflight，且**真实样本验过非 co-vacuous**
- [ ] `preflight.sh` 零 FAIL（段60 feature-measurement 新鲜 + feature-status-gen 一致）
- [ ] 重采产物 `.testing/status/measurement/*.json` 更新，无 feature 因本次掉绿（掉绿的逐个查清并修/复核）
- [ ] 之前 skip 的 spec 在真栈上真 RUN 且 passed
- [ ] PR CI 全绿（含 e2e + feature measurement job）

## 9. ROI / 决策背景（为什么之前一直 defer）

- 三轮 god's-eye 一致分类为 **test-quality-debt**，非产品缺陷；CSRF 生产侧正确。
- **CI e2e 测量 allowlist 只有 `twin_browser_pages`，根本不跑这些 spec** → 这个"假覆盖"只在**有人本地全量跑**时才咬一口，平时合并/CI 不受影响。**低优先级**。
- 成本/风险高（碰盐 → 全量重采 + flaky 翻绿风险）。低价值 + 高成本 = 一直 defer 到"专门重采周期"批处理——**就是本任务**。

## 10. 锚点速查（接手先 grep 复核，勿信固定行号）

- 写点：`grep -rnE "page\.request\.(post|put|patch|delete)\(" tests/e2e/ | grep api/skills`
- 盐文件：`grep -nA10 GLOBAL_SALT_FILES scripts/feature_status_lib.py`
- 无 cookie 范式参照：`tests/e2e/permission_matrix_walkthrough.spec.ts`（`invoke` / `newContext`）
- CSRF 机制：`grep -nE "csrf|X-CSRF|_dev_iam_bypass" zw_brain/entry/rest/server.py`
- 重采脚本头注（flag/vacuous-skip）：`sed -n '1,40p' scripts/capture_feature_status.py`
- CI 重采配方：`grep -n capture_feature_status .github/workflows/ci.yml`
- 指纹算法（含盐）：`grep -nA20 "def feature_fingerprint" scripts/feature_status_lib.py`

## 11. 环境 gotcha（本机/worktree）

- worktree 跑需软链主仓 `node_modules`（`ln -sfn <主仓>/zw-brain-web/node_modules zw-brain-web/node_modules`、根 `node_modules` 同理）；EnterWorktree 建的 `worktree-<name>` 分支撞命名门 → `git branch -m fix/<名>`。
- curl 本地 REST 要 `--noproxy '*'`；REST 是 stdlib http.server。
- 提交一律走 preflight（pre-commit hook），禁 `--no-verify`。
- 改任何 feature-backed 测试都会再触发重采——本任务结束后若还要动 helpers.ts，同样要重采。
