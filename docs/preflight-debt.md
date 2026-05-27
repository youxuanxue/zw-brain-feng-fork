# preflight-debt

Outstanding items intentionally deferred from the current preflight gate set. Each entry must list
the symptom, the deferred decision, and the trigger that forces a re-evaluation.

任何一条 entry 在 trigger 触发时必须升级为 P0 fix 或转化为机械化 preflight check；不允许长期沉淀。

## entry 必填字段约定（2026-05-26）

**自本约定起新增的** trigger 化延后 entry，应含 `Where` / `Implication` / `Why deferred`
/ `Trigger to re-evaluate` 四个核心字段；并且**如果 trigger 触发当日落地的代码会撞 main
已占用的标识符**，必须额外补一行 `Reserved names (taken)`，记录当前 main 已占用、将来
trigger 触发时会撞名的标识符（字段名 / enum 值 / slug 前缀 / 类名 …）+ rename 取舍提示。

既有 entry（2026-05-26 之前）字段命名不严格统一，仅在触动重写时一并补齐——避免一次性
回填造成纯文字 PR 噪声。

目的：防止 trigger 触发当日才发现撞名再返工选 rename 路径。"已占名"清单与 entry 同生命周期，
trigger 关闭即可删除字段。

## 2026-05-26 — BrainService 残留读路径方法群下沉（brain.py god-class）

- **Where**: `zw_brain/command/brain.py`（3462 LOC）拆分后 185 cap dispatcher 全迁出至 `dispatch.py`
  + `handlers/{j1,j2,b1,infra}/`，但 `BrainService` 类本身仍持有 **~192 方法**，其中绝大多数是
  `_*_record_to_dict` / `_*_projection` / `_topic_*` / `_governance_*` / `_delivery_*` 读路径
  映射 + 投影 helper（语义上属 projection / repository 层，非编排层）。
- **Implication**: §10.2 已 re-scope —— AC1 真实意图「dispatch 不臃肿」由 `dispatch.py` 360 LOC +
  brain.py 内 0 case dispatcher 达成，brain.py 不再卡 LOC 上限。但 192 方法 god-class 仍是真实债：
  多 worker 若同时改读路径投影方法仍会在此文件 merge 撞车；类体过大降低可读性。
- **Why deferred**: 当前无活跃功能需要这些方法搬家；把 ~3000 LOC 读路径方法盲搬到 projection/domain
  层是高 blast-radius 的投机式重构（违反「不为假设造复杂度」）。re-scope 已入档 §10.2，状态板不再
  谎报 ≤500。
- **Trigger to re-evaluate**: (a) 出现一次 brain.py 读路径方法的多 worker merge 撞车 → 把撞车簇
  方法下沉到对应 projection repo；(b) Wave 2/3 读路径重构窗口期主动分批下沉（按 j1/j2/b1/governance
  域切）。任一触发当日按域切片下沉，不整文件一次性搬。
- **No mechanical preflight check (now)**: brain.py LOC 上限已显式退役（§10.2），不设 LOC 门禁避免
  把"不卡上限"的结论又机械化回来；debt 条目兜底跟踪。
- **Update (2026-05-26)**: 仍**不加** LOC / 方法数上限（与上一条一致）。本次只硬化两个**精准回归面**，
  非笼统增长门禁：① 段 35 `check_brain_no_request_state_singleton.py` —— per-request `role` 必走
  `zw_brain/shared/ui_request_context.py` 的 ContextVar，`_ui_state` 单例 backing dict 不得 seed
  `role`（锁死并发污染修复，`_UIStateProxy`）；② 段 36 `check_no_demo_id_literals.py` —— `REQ-/DLV-/PKG-`
  demo id 限 `zw_brain/command/demo_state_sync.py`，不得回潮进 `brain.py`/handlers。两者针对本轮已修的
  具体回归点，不构成对 §10.2「不卡 LOC 上限」结论的翻推。

## 2026-05-26 — 读路径热表 tenant-only 全扫白名单（PR #113 同模式残留）

- **Where**: 段 32 `scripts/check_read_path_full_scan.py` 在当前 main HEAD 扫到 12 处与
  PR #113 同模式的 `select(HotModel).where(tenant_id==X)` 不带 limit / 不带额外
  业务过滤维度的全量扫表点：
  - `zw_brain/domain/repositories/catalog.py::list_model_fields_all` —
    legacy verification 一次性 count/set-membership
  - `zw_brain/domain/repositories/delivery.py::list_tasks` —
    J1 投递任务全量列表
  - `zw_brain/domain/repositories/application.py::list_records` —
    J1 申请全量列表（governance/dispute/approval handler 复用）
  - `zw_brain/domain/repositories/approval.py::list_cases` —
    审批 case 全量列表（与 application 同步触发）
  - `zw_brain/domain/repositories/supply_demand.py::list_demands` —
    payload_json.kind 维度过滤需 SQL JSON 算子才能下推
  - `zw_brain/command/handlers/j2/metadata.py` `existing_reverse` 推断 —
    summary_json.source 同 JSON 维度场景
  - `zw_brain/domain/repositories/catalog.py::_entry_list_statement` return —
    PR #113 修复路径 query builder；调用方须传 filter/limit
  - `zw_brain/domain/repositories/catalog.py::list_items` —
    catalog_code 可选；None 时 tenant-only 全量 item
  - `zw_brain/domain/repositories/delivery.py::list_attempts` —
    delivery_code/attempt_code 可选；双 None 时 tenant-only
  - `zw_brain/domain/repositories/objection.py::list_cases` —
    status 可选；None 时 tenant-only 全量 objection
  - `zw_brain/domain/repositories/resource_api.py::list_assets` —
    lifecycle_status 可选；None 时 tenant-only 全量 resource
  - `zw_brain/domain/repositories/resource_api.py::list_bindings` —
    resource_code 可选；None 时 tenant-only 全量 binding
- **Implication**: 与 PR #113 catalog.entry.query 同形态的「读路径全量扫表 + 内存
  过滤」反模式残留点；当前单租户 sd-default 下行数 ≤ 数千，未触发 P5「待发布目录」
  级的卡顿，但**多租户接入或 J1/J2 量级进入万级时同类卡顿必定复现**。
- **Why deferred**: PR #113 修的是 P5 阻塞客户演示的最高优先级单点；本次本意是用段 32
  把这条「同模式 list-only-tenant」机械化，把残留 6 处一次性修完会显著超出
  「基线漂移收口」PR 范围。改修需要：(a) 给每个 repo 接口加业务维度参数；
  (b) 同步改 ≥10 个 caller；(c) JSON 列下推需要 SQLite vs PostgreSQL 分支。
  Jobs 风格的可逆决策：先用 `# full-scan-ok: <理由>` 把 6 处标记为显式接受的债务，
  机械守住「新增点不得回潮」，旧点等触发再批改。
- **Trigger to re-evaluate** (任一触发即升级为 P0 fix)：
  - **T1**：J1 申请量 / catalog 量进入万级（≥ 10k 行）→ 出现 P5 同类客户卡顿。
  - **T2**：第二个真实租户接入 → tenant-only filter 不再有界。
  - **T3**：再出现一次「客户演示卡顿被现场 hotfix」事件 → 不再容忍残留点。
  届时按 PR #113 同手法把每个 `list_*` 改造为业务维度下推 + paged 接口；
  JSON 列场景额外评估「把维度提到独立索引列」（D7 adapter 输入归口）。
- **Mechanical guardrail (now)**: 段 32 `scripts/check_read_path_full_scan.py`
  对**新增**的 `select(HotModel).where(tenant_id==X)` 不带 limit / 不带额外维度
  过滤的写法一律拦下，必须显式加 `# full-scan-ok: <≥7 字符理由>` 才放行；
  即未来回潮必先经过明确"接受债务"的动作，杜绝隐式漂移。

## 2026-05-25 — 真数据回归不在 CI 自动门禁（D11 张力）

- **Where**: 14 个真数据测试模块（`tests/test_wave{0,1}_*` J1/J2 黄金链路）靠 `tests/_seed_guard.require_real_seed`
  守卫；seed `.data/zw_brain.db` 是 gitignore 的本地 513MB→123MB 灌库产物。CI runner 无此 seed，
  这批测试全部 `pytest.skip`。
- **Implication**: 基线 D11「所有 Skill 必须以旧平台真实业务数据回归验证，禁止 Mock 业务数据」当前**只在本地手动跑**，
  不在 push/PR 的自动门禁内。CI 绿 ≠ 真数据链路绿——真数据回归靠本地或客户验收承接。
- **Why deferred**: 用户 2026-05-25 明确本期只硬化守卫，CI 覆盖转 debt+trigger。dumps（`old/10示例数据/*.sql`，
  最大 dsp_message 286MB）未 git-track，CI 引入真数据需先解决数据来源（轻量 seed 子集 git-track 化 or
  对象存储拉取）+ 构建时长，范围明显更大。
- **Trigger to re-evaluate**（任一触发即升级）：(a) 首个真实客户上线前——真数据回归必须进 CI 门禁；
  (b) dumps 完成脱敏 + 可 git-track 的轻量 seed 子集就位；(c) 再次出现"本地真数据抓到、CI 没抓到"的
  production 现场。届时新增 CI job：从 dumps/子集构建 seed → 跑 `tests/test_wave*` 真数据套件。
- **Mechanical guardrail (now)**: `tests/_seed_guard.schema_drift_reason()` 在 seed schema 落后于
  当前模型时**干净 skip + 打印重建命令**（替代此前 copy-paste `_seed_ready()` 只查行数、stale seed 抛
  61 个 `no such column` cryptic ERROR 的回潮路径）。

## 2026-05-25 — 推理客户端等真实网关验证（E6 AC2，卡集团 SDK 凭据）

- **Where**: `zw_brain/shared/inference/client.py`（239 LOC）**platform 模式 chat/embed 真实 HTTP 路径已实装**
  （`client.py:146-209`，POST `/v1/chat/completions` + `/v1/embeddings`），默认 strict platform，env 显式切 mock；
  非 mock-only。**代码层生产化已完成**，缺的是真实网关凭据下的连通验证。
- **Implication**: 基线 D6/D14 硬约束「所有模型推理调用走集团推理平台统一 SDK，禁止直连第三方 LLM」在产品形态
  + 代码路径均已就位；但真实推理质量/延迟/配额/鉴权未经真网关链路验证。E6 AC2 停止条件「真实模式 + mock 模式
  双跑通」中 platform 真链路一段未验——属外部依赖阻塞（缺凭据/endpoint），非工程内可推进项。
- **Why deferred**: 集团推理平台网关凭据 / endpoint 尚未同步到位（D14 已记此前提）；mock 模式保留给本机/演示。
- **Trigger to re-evaluate**: 集团推理平台网关凭据 / endpoint 到位日 → 跑 platform 真连通 e2e
  （`tests/integration/test_inference_client.py` 已有 platform case 骨架）+ preflight 段 10（禁直连第三方）回归确认。

## 2026-05-25 — 客户机房部署 + 监控对接未落地（E6 AC7）

- **Where**: 无 `scripts/deploy_*.sh`；`Dockerfile` / `Dockerfile_v1.0.0` 存在，CI（`ci.yml` / `security.yml`）
  覆盖 lint/test/build wheel，但**客户机房 dry-run 部署脚本 + 对接集团运维监控的证据缺位**。
- **Implication**: E6 AC7「CI/CD + 客户机房部署 + 监控对接集团运维监控」只完成 CI 段；现场部署 + 监控对接未做。
- **Why deferred**: 用户 2026-05-25 明确本期只登记 debt + trigger，不写部署脚本。客户机房环境 / 集团监控接入口径
  未明确前提前写 deploy 脚本属"为未验证需求盖楼"。
- **Trigger to re-evaluate**: 首个客户机房部署立项 → 落地 `scripts/deploy_*.sh` + 监控对接 + dry-run sign-off；
  与「dev-iam-bypass 生产守卫」「真数据进 CI」同属"首个客户上线前"批次触发，可一并处理。

## 2026-05-24 — AgentRuntime runtime 触发式延后（D30 retrofit）

- **Where**: 协议规范 `docs/agent-runtime/product-integration-guide.md` + `agent-runtime-api-cn.md` 完整；
  Registry schema 4 新字段（`runtime_spec_version` / `agent_yaml_ref` / `trust_level` / `workspace_required`）
  + `scripts/agentruntime_validate.py` + `scripts/agentruntime_doctor.py` + 内置 Agent `AGENT.yaml` 样本
  **均未创建**。
- **Implication**: 架构基线 §8 / R15 描述了外部 Agent 通过 AgentRuntime 接入的产品决策；但运行时未实现。
  原 §10.2 "Wave 1 必达 ≥1 内置 Agent 用 AGENT.yaml 通过 validate+doctor"（产品负责人 sign-off 2026-05-22）
  已 D30 撤回为触发式（架构 §8.6）。
- **Why deferred**: 当前 zw-brain 无外部 Agent 接入排队，按确定性自动化运营和运维「只为真实需求建复杂度」拒绝提前盖楼；
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
- **Reserved names (taken)**: `trust_level` (业务字段，能力包内置元数据，enum baseline/reviewed/restricted/revoked)
  — 触发 T1 时 AgentRuntime Registry trust_level (platform/verified/untrusted) 撞名，必须 rename 其中一方
  （建议把 AgentRuntime 字段改名为 `package_trust_level` 或 `runtime_trust_level`，业务字段已写进 2 manifest
  + policy 校验难翻盘）。

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

## 2026-05-24 — Wave 2 R14 三引擎已落地，待 T1 客户演练验证（D-31d，2026-05-25 更新）

- **Status (2026-05-25 更新)**: 不再是 "0% 实现 / deferred"。三引擎已在 **PR #92** 落地：检索
  `zw_brain/skill_registration/registered/` 现有 10 个三引擎 capability（`approval_flow.*` 4 +
  `form_schema.*` 4 + `recommendation.*` 2；总 manifest <!-- stat:zwbrain.manifest-total -->230<!-- /stat -->）。`config_change_class` preview/draft
  流已激活（当前 preview 2 / draft 4）。
- **What remains**: 代码侧已交付；**未完成的是 T1 真实客户演练验证**——用三引擎在 ≤1 周内不改代码
  完成"鞍山 4 级审批 + 四川 7 字段表单 + 荆州 5 条推荐规则"项目级定制，由业务方 sign-off。
  acceptance 材料 `docs/wave2-acceptance/SIGN_OFF.md`（tracked，PR reviewer 可见）已备，等真人门禁（属 R13 业务流程类决策）。
- **Trigger to re-evaluate**: 首位真实客户演练。届时跑通三引擎项目级定制并由业务方（红军 / 海若产品部）
  sign-off → 本 entry 关闭并写入 D-编号；若演练暴露引擎缺口（节点/字段/推荐规则不够表达）→ 升级为 P1 fix。
- **No mechanical preflight check (now)**: `config_change_class` 取值已由 `validate_manifest` 强制校验
  （∈ {live, preview, draft}）；三引擎 preview/draft 实例增减不需要新增 preflight 段。

## 2026-05-26 — BFF session Redis backend（P0-E 关闭）

- **Where**: `zw_brain/shared/auth_session.py` — `RedisAuthSessionStore` + `create_auth_session_store()`;
  `zw_brain/entry/rest/server.py` startup calls `validate_session_store_for_deploy()`.
- **Implication**: 多 REST worker / 非 sticky LB 部署时，设置 `ZW_BRAIN_SESSION_REDIS_URL` 即可共享
  HttpOnly BFF 会话；未设置时仍走单进程 `InMemoryAuthSessionStore`（`start-local.sh` 默认路径不变）。
- **Prod guard**: `ZW_BRAIN_DEPLOY_MODE=prod|production` 且未配置 `ZW_BRAIN_SESSION_REDIS_URL` →
  `zw-brain-rest` 启动即 `SystemExit`。
- **Mechanical check (now)**: `tests/test_auth_session_redis.py`（fakeredis 双实例共享会话 + prod guard）。
- **Ops**: 生产镜像需 `uv pip install 'zw-brain[redis]'` 或等价安装 `redis>=5.0`；可选
  `ZW_BRAIN_SESSION_REDIS_KEY_PREFIX`（默认 `zw-brain:session:`）。

## 2026-05-18 — BFF session store is single-process in-memory — **已 superseded 2026-05-26**

> 历史条目保留审计链。实现已升级为 Redis 可选 + 内存 fallback；见上条 P0-E 关闭记录。

- **Where (was)**: in-memory only.
- **Trigger (was)**: multi-replica → **已落地 Redis backend**。

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

## 2026-05-27 — customer_acceptance_up.sh strict 模式与真实 dump 设计脱节

- **Where**: `scripts/customer_acceptance_up.sh` 用 `MigrationOptions(strict=True)` 重建 `.data/zw_brain.db`；
  `legacy.bsp.governance` adapter 在真实 `old/10示例数据/dump-dsp_bsp-202604271139.sql` 上 52241 行
  → 44261 ok / 7980 跳过（15%）→ status=`partial_failure` → strict 抛 `MigrationError`。
  `adapter_run_record.error_summary = None`（**silent swallow**——失败原因不被记录）。
- **Root cause**: `governance.py:141` 对 `_PUB_GOVERNANCE_TABLES` 缺 `iaf_binding_manifest` /
  `role_mapping_manifest` 的行调 `stats.add_issue("missing_manifest", ...)` 然后 `continue`，
  跳过的行计入 `failure_count` 但不写 `error_summary`。**设计上是 fail-closed**，但 strict 永远拒
  绝任何 missing_manifest——除非 dump 完美（不现实）。
- **Implication**: (a) 任何人在本机用 `scripts/customer_acceptance_up.sh` 重建 seed DB 都会失败；
  (b) error_summary=None 违反 CLAUDE.md §2 「禁止 silent error swallow」。**但 canonical 投影 0
  conflicted / J1+J2 demo 全过 / verify report failed=False —— 业务零影响**。
- **Why deferred**: 修复方向有两个，都超 PR #128（god-object 解耦）范围：
  (a) 改 `customer_acceptance_up.sh` 默认 non-strict + warn（保留 strict-flag 给完美 dump）
  (b) 修 governance adapter 让 missing_manifest 写 `adapter_run_record.error_summary`（消除 silent
  swallow），同时维持 fail-closed 语义。
- **CI 为何 PASS**: `.github/workflows/ci.yml` 的 `legacy-import-smoke` 用合成 dump (10 行
  dsp_example)，不跑真实 445MB dump corpus —— CI **不抓** 这条 debt。
- **Trigger to re-evaluate**: (a) 客户现场用真实 dump 部署时 strict 卡住 → P0 fix；
  (b) 下次有 PR 触动 `zw_brain/adapters/legacy/mappers/governance.py` 或
  `customer_acceptance_up.sh` 时顺手清理；(c) 主动 retrofit 修 silent swallow（CLAUDE.md
  全局宪法明禁，应排在 next refactor wave 优先位）。
- **No mechanical preflight check (now)**: preflight 不跑真实 dump（CI 也不跑），加 check 等于强
  推 1.3GB seed DB 进 CI runner。Debt 条目兜底，单独 PR 修。
- **Reserved names (taken)**: 无（修复方向是改 script 默认 flag + 加 error_summary 字段填充逻辑，
  不引入新字段/枚举）。
