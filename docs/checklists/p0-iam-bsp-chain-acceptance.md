# P0 链路验收 Checklist：IAM → BSP 权限 → B1.2 身份治理

> **范围**：duwei05 贡献的「认人 → 导权限 → 人工审核 → 策略生效 → 岗位驱动页面权限」黄金链路。  
> **通过标准**：本页 **P0-A～P0-D 全部 PASS**；**P0-E～P0-G** 在「首个客户上线前」必须关闭（当前为 preflight-debt，本 checklist 给出验收口径，不要求今日实现）。  
> **权威引用**：[`docs/iam-login-logout-implementation.md`](../iam-login-logout-implementation.md) · [`docs/roles-permissions-old-platform-vs-zw-brain-handoff.md`](../roles-permissions-old-platform-vs-zw-brain-handoff.md) · [`docs/deployment/m0-site-migration.md`](../deployment/m0-site-migration.md) · PR [#74](https://github.com/feng222666888/zw-brain/pull/74) · PR [#109](https://github.com/feng222666888/zw-brain/pull/109)

---

## 0. 验收前准备

| # | 项 | 命令 / 动作 | 期望 |
|---|-----|-------------|------|
| 0.1 | 代码基线 | `git fetch origin && git rev-parse origin/main` | 记录 commit SHA 写入验收记录 |
| 0.2 | 依赖就绪 | `uv sync` 或 `.venv` 已安装 | `uv run pytest --version` 可执行 |
| 0.3 | Web 产物 | `cd zw-brain-web && npm ci && npm run build` | 存在 `zw-brain-web/dist-vite/index.html` |
| 0.4 | 本地服务 | `bash scripts/start-local.sh`（另开终端） | `curl -sf http://127.0.0.1:8800/healthz` 返回 200 |
| 0.5 | 机械门禁 | `./scripts/preflight.sh` | 全段 PASS |

**环境变量（本地 dev 默认，勿用于 prod）**

```bash
# start-local.sh 在未设置 ZW_BRAIN_IAF_AUTH_SERVER_URL 时自动 export：
# ZW_BRAIN_DEV_IAM_BYPASS=1
# ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only
# ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH=1
```

**真 IAF 联调（可选路径 0.6）**：设置 `ZW_BRAIN_IAF_AUTH_SERVER_URL` 等后 **不要** 开 bypass；见 [`docs/deployment/docker-image-deployment.md`](../deployment/docker-image-deployment.md)。

---

## P0-A · BFF 会话与请求鉴权（IAM 认人）

**角色**：安全审计员 / 实施工程师  
**实现落点**：`zw_brain/shared/auth_session.py` · `zw_brain/entry/rest/server.py` · `zw-brain-web/src/composables/useAuth.ts`

| ID | 验收项 | 步骤 | 期望 | 自动化 |
|----|--------|------|------|--------|
| A-01 | Token 不出浏览器 | DevTools → Application → sessionStorage / Local Storage | **无** `access_token` / `refresh_token` / `id_token`；仅有 `zw-brain.auth.v1` 公开摘要 | 人工 |
| A-02 | HttpOnly Cookie | DevTools → Cookies | 存在 `zw_brain_session`；HttpOnly ✓ | 人工 |
| A-03 | 写请求 CSRF | 在身份治理页点「批准并写入策略」，Network 看 POST | Header 含 `X-CSRF-Token`；无 `Authorization: Bearer` | 人工 |
| A-04 | 会话不可提权 | Cookie 会话下在 skill body 夹带更高 `role` | 必须 403/拒执，不能越权写 | `uv run pytest tests/test_trusted_session_context.py::test_cookie_session_rejects_privilege_escalation_in_skill_body -q` |
| A-05 | bypass 双因子 | 未同时设置 `ZW_BRAIN_DEV_IAM_BYPASS` + `_ACK` | A2A 等无 per-request auth 的 daemon **拒绝启动** | `uv run pytest tests/test_entry_surfaces.py::test_a2a_serve_refuses_without_dev_bypass -q` |
| A-06 | 多标签同步 | 开两个标签页；A 页登出 | B 页会话同步清除或跳转登录 | 人工（BroadcastChannel `zw-brain-auth`） |
| A-07 | 周期刷新 | 保持页面打开 ≥5min 或改短 `REFRESH_CHECK_MS` 测 | 后端 `/auth/iaf/refresh` 被调用，session 续期 | 人工 + Network |

**P0-A 签字**：□ PASS　□ FAIL（备注：________）

---

## P0-B · IAF 登录 + 本地治理投影保留（duwei05 #74 核心修复）

**场景**：真 IAF **无法**在 Token 里配置 `ROLE_*` 时，BSP 预先 seed 的 `actor_org_role_binding` 不能被登录同步冲掉。

**角色**：IAM 管理员 + 治理实施工程师

| ID | 验收项 | 步骤 | 期望 | 自动化 |
|----|--------|------|------|--------|
| B-01 | 联调 seed（dry-run） | `uv run python scripts/dev/seed_iaf_actor.py --iaf-sub 'test-sub-001' --username zhangsan --roles ROLE_ORGAN_OPERATER,ROLE_BUSIAUDIT --dry-run` | 打印将写入的 projection + binding；**不写库** | 脚本 |
| B-02 | 联调 seed（apply） | 同上去掉 `--dry-run`（目标 DB 已 PR #74 schema；否则加 `--allow-schema-reset` 且确认可丢数据） | `actor_projection` + `actor_org_role_binding` 写入成功 | 脚本 + SQL 抽查 |
| B-03 | 登录后 role_codes 保留 | B-02 后走 IAF 登录（或 mock `actor.projection.sync` 带空 product roles 的 claims） | `/auth/iaf/session` 或 snapshot 中 `actor_snapshot.role_codes` **仍含** seed 的角色；**不出现** `no product role available` | 人工（真 IAF）+ B-05 自动化对照 |
| B-04 | sync 合并逻辑 | 对已有 projection 调 `actor.projection.sync`，claims 无 `ROLE_*` | `role_codes` / binding **不被清空** | 代码锚点：`zw_brain/command/handlers/b1/projection.py` L77–93；人工或写集成测试 |
| B-05 | sd-default 真数据上接 IAF | 有 `old/10示例数据/dump-dsp_bsp-202604271139.sql` | import 后 iaf-bound actor 的 snapshot 走 `actor_org_role_binding` | `uv run pytest tests/test_bsp_sd_default_real_dump_e2e.py -q`（无 seed 则 skip，见 0.6） |

**P0-B 签字**：□ PASS　□ FAIL（备注：________）

---

## P0-C · BSP 导入 → 候选 → 审核 → 租户策略

**角色**：业务运营员（`ROLE_BUSIAUDIT`）· 主管部门治理员

| ID | 验收项 | 步骤 | 期望 | 自动化 |
|----|--------|------|------|--------|
| C-01 | PUB 批次 dry-run → apply | — | `GovernanceMapper.import_dump` 统计无 fail-close；产生 `legacy_policy_mapping_candidate` | `uv run pytest tests/test_bsp_permission_pipeline_e2e.py -q` |
| C-02 | 候选列表 skill | `GET /api/skills/governance.policy_candidate.list?role=ROLE_BUSIAUDIT&tenant_id=sd-default`（Cookie 或 Bearer） | 200；`items[]` 含 `legacy_role_ref` / `candidate_status` | 同上 + `tests/test_governance_policy_candidate_review.py` |
| C-03 | 审核写入 skill | `POST /api/skills/governance.policy_candidate.review`，`confirmed: true`，`decision: approve_and_apply` | 返回 `audit_id`；候选状态更新；`tenant_capability_policy` 有新增 | `tests/test_governance_policy_candidate_review.py` |
| C-04 | 策略生效闭环 | 审核前后各调一次 `tenant.policy.evaluate` | 审核前 deny / missing；审核后 **allowed** | `tests/test_bsp_sd_default_real_dump_e2e.py` |
| C-05 | 权限矩阵对齐 | — | `governance.policy_candidate.*.execute` 仅 `ROLE_BUSIAUDIT`（review）/ 审计角色（list） | `uv run pytest tests/test_role_codes_alignment.py -q` |
| C-06 | 审计留痕 | 审核后查 audit feed | skill_id=`governance.policy_candidate.review` 有 write-critical 事件 | `uv run pytest tests/integration/test_audit_replay.py -k policy_candidate -q` |

**P0-C 签字**：□ PASS　□ FAIL（备注：________）

---

## P0-D · Web 消费面：B1.2 身份治理 + 岗位切换

**角色**：业务运营员 · 部门操作员（负向）· 部门管理员

**浏览器基址**：`http://127.0.0.1:8800/`（REST 托管 `dist-vite`）

| ID | 验收项 | 步骤 | 期望 | 自动化 |
|----|--------|------|------|--------|
| D-01 | 接入中心入口 | `#/integration-admin` → 点「身份治理」 | 进入 `#/integration-admin/iam-governance` | `npx playwright test tests/e2e/b12_iam_governance.spec.ts -g "接入中心有身份治理入口"` |
| D-02 | 列表 live | `ROLE_BUSIAUDIT` 进身份治理页 | 标题「身份治理」；列表含数据；badge 为「实时数据」或 seed 内容 | e2e `P0: 业务运营员可进身份治理且列表 live` |
| D-03 | 无权拒绝 | `ROLE_ORGAN_OPERATER` 深链 `#/integration-admin/iam-governance` | **被重定向**，不能停留 | e2e `P0: 部门操作员无权进入身份治理` |
| D-04 | 待审筛选 + 驳回 | 筛「待审核」→ 勾选 →「驳回所选」 | toast「已驳回」；列表刷新 | e2e `P0: 待审核筛选 + 驳回所选` |
| D-05 | 批准并写入 | 勾选 pending →「批准并写入策略」→ 确认 prompt | toast 含 `audit_id`；列表状态更新 | 人工（写操作需真实 backend + confirmed） |
| D-06 | fixture 降级 | 断 backend list API | 显示「后端暂不可达」；审核按钮 disabled | e2e `P0: fixture 模式禁用审核按钮` |
| D-07 | 岗位切换 toast | 顶栏 `#role-switch` 切到无权页岗位 | toast 含**中文岗位名**；自动跳转可用入口 | e2e `P1: 岗位切换 toast` + `tests/e2e/webui_smoke.spec.ts` |
| D-08 | 路由门禁 | 操作员深链 `#/provider` 等无权页 | hash 变更，不能停留 | `tests/test_page_access.py` + e2e smoke |
| D-09 | 契约不漂移 | — | composable 绑定 registry skill；路由非 PagePlaceholder | `uv run pytest tests/test_iam_governance_web_surface.py -q` |

**一键浏览器 P0（需 start-local + build）**

```bash
npx playwright test tests/e2e/b12_iam_governance.spec.ts tests/e2e/webui_smoke.spec.ts -g "岗位切换"
```

**P0-D 签字**：□ PASS　□ FAIL（备注：________）

---

## P0-E～G · 上线前必须关闭的基础设施债（当前 main 已知缺口）

> 下列项 **不阻塞** 本链路在单进程 dev 盒验收；**阻塞** 首个客户生产 / 多副本部署。详见 [`docs/preflight-debt.md`](../preflight-debt.md)。

### P0-E · BFF Session 多进程（Redis） — **已实现 2026-05-26**

| ID | 触发条件 | 验收口径 | 状态 |
|----|----------|----------|------|
| E-01 | REST worker >1 或非 sticky LB | 设置 `ZW_BRAIN_SESSION_REDIS_URL`；任意 replica 签发的 cookie 在其它 replica 可解析 | □ 配置 Redis URL 后验收 |
| E-02 | 实现回归 | `uv run pytest tests/test_auth_session_redis.py -q` 全绿 | □ 自动化 |
| E-03 | prod 守卫 | `ZW_BRAIN_DEPLOY_MODE=prod` 且无 Redis URL → `zw-brain-rest` 启动失败 | □ 自动化 |

**配置示例**：

```bash
export ZW_BRAIN_SESSION_REDIS_URL=redis://127.0.0.1:6379/0
export ZW_BRAIN_DEPLOY_MODE=prod   # 与 Redis URL 联用
uv run pytest tests/test_auth_session_redis.py -q
```

### P0-F · 真数据 BSP 回归进 CI

| ID | 触发条件 | 验收口径 | 状态 |
|----|----------|----------|------|
| F-01 | 首个客户上线前 | CI job 从 git-track 轻量 seed 或对象存储拉 dump 子集，跑 `test_bsp_*` / `test_wave*` **不 skip** | □ CI 当前 skip |
| F-02 | 本地对照 | 有 `.data/zw_brain.db` 时：`uv run pytest tests/test_bsp_sd_default_real_dump_e2e.py tests/test_bsp_permission_pipeline_e2e.py -q` 全绿 | □ 本地 |

**重建 seed 提示**（schema 漂移时）：

```bash
.venv/bin/python -m zw_brain.entry.legacy_migration.main \
  --dumps-dir "old/10示例数据" --db-path .data/zw_brain.db --reset-db \
  --report /tmp/migration-report.json
```

### P0-G · 客户机房 deploy dry-run

| ID | 触发条件 | 验收口径 | 状态 |
|----|----------|----------|------|
| G-01 | 客户机房立项 | 存在 `scripts/deploy_*.sh`；`ZW_BRAIN_DEPLOY_MODE=prod` 清单 **无** bypass 变量 | □ 脚本缺失 |
| G-02 | Docker 单一路径 | 生产只用根目录 `Dockerfile`；`Dockerfile_v1.0.0` 仅内网 dev overlay | 人工核对 |
| G-03 | prod IAM 守卫 | `./scripts/preflight.sh` 段 23 `check_iam_prod_guard.py` PASS | 自动化 |
| G-04 | 监控对接 | 部署后 healthz + audit 指标可达集团运维监控 | □ 未验证 |

---

## 一键自动化验收（开发盒 · 无真 IAF）

在 `origin/main` 上执行，作为 **P0-A～D 的机械预检**（不含 P0-E～G）：

```bash
# 1. 门禁
./scripts/preflight.sh

# 2. 后端链路（不依赖浏览器）
uv run pytest \
  tests/test_bsp_permission_pipeline_e2e.py \
  tests/test_governance_policy_candidate_review.py \
  tests/test_role_codes_alignment.py \
  tests/test_trusted_session_context.py \
  tests/test_iam_governance_web_surface.py \
  tests/test_page_access.py \
  tests/test_wave0_infra.py::test_infra_iam_session_lifecycle \
  tests/test_entry_surfaces.py::test_a2a_serve_refuses_without_dev_bypass \
  tests/test_auth_session_redis.py \
  -q

# 3. 真 dump 闭环（有 old/10示例数据 时；否则预期 skip）
uv run pytest tests/test_bsp_sd_default_real_dump_e2e.py -q

# 4. 浏览器（终端 1: bash scripts/start-local.sh；终端 2:）
cd zw-brain-web && npm run build && cd ..
npx playwright test tests/e2e/b12_iam_governance.spec.ts tests/e2e/webui_smoke.spec.ts

# 5. 客户验收清单（Python 浏览器冒烟，含 B1.2 身份治理中心）
uv run python scripts/customer_acceptance_checklist.py
# 或 Playwright 版：npx playwright test tests/e2e/customer_acceptance_checklist.spec.ts
```

**期望**：2 与 3 全绿（3 可 skip 但须打印 `_seed_guard` 重建提示，而非 ERROR）；4 全绿。

---

## 验收结论表

| 段位 | 内容 | 结果 | 验收人 | 日期 |
|------|------|------|--------|------|
| P0-A | BFF / IAM 鉴权 | □ PASS □ FAIL | | |
| P0-B | IAF + 本地投影保留 | □ PASS □ FAIL | | |
| P0-C | BSP 导入 → 策略闭环 | □ PASS □ FAIL | | |
| P0-D | B1.2 Web + 岗位切换 | □ PASS □ FAIL | | |
| P0-E | Session 多副本 | □ N/A □ DONE | | |
| P0-F | 真数据 CI | □ N/A □ DONE | | |
| P0-G | 客户 deploy | □ N/A □ DONE | | |

**总体判定**

- **链路可交付（dev / 单节点演示）**：P0-A ∧ P0-B ∧ P0-C ∧ P0-D 全部 PASS。  
- **生产可交付（客户机房）**：上式 + P0-E ∧ P0-F ∧ P0-G 全部 DONE。

---

## 已知刻意不做（避免误判为遗漏）

| 项 | 原因 |
|----|------|
| `scripts/validate_bsp_permission_pipeline.py` | PR #74 review 删除；由 pytest e2e 取代 |
| 岗位下拉「全展示 + disabled 无权项」 | Vue 改为只展示有权岗位；功能等价，UX 不同 |
| M0 浏览器实施面 | by design CLI；见 `m0-site-migration.md` |

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-26 | 首版：对齐 duwei05 #74/#109 + preflight-debt P0-E～G |
