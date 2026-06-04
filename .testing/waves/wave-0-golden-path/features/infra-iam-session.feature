# Wave: 0
# Journey: Cross
# Pages: None (infrastructure)
# Consumer-faces: WebUI | API | CLI
# Roles: All
# Trace: 基线 §3.4 (IAF IAM 外部依赖), docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md
# Priority: P0
# Owner: e6
# Pytest: tests/test_wave0_infra.py, tests/test_iam_identity_claim.py
# InTest-Scope: tests/test_wave0_infra.py 覆盖 7 项（OIDC 端点派生 / 缺 auth_server_url 报错 /
#   realm_access.roles → role_codes 映射 / 未知角色码不静默扩权 / 默认租户 sd-default /
#   会话生命周期 + token 不回传浏览器体 / 无 bearer 401）；
#   tests/test_iam_identity_claim.py 覆盖「存量用户首登单行身份认领」6 项（sub/account 认领既有行不增行 /
#   保 legacy profile + 搬 binding+mapping / 多命中 fail-closed / 不认领 disabled 行 / 登录不 disable 导入 binding /
#   同 sub 二次登录幂等）；
#   D-2 红线：session 主动写 actor_org_role_binding 投影 + valid_to 软删除依赖 D-2 解冻（GovernanceMapper
#   投影 0 行），本期 skip 不实现——登录只在「认领既有 legacy 行」时一次性搬移 binding，绝不新写/禁用；
#   id_token RS256 全链路验签需 jwks 加密 fixture，归 W0-07。

Feature: Infra — IAM 认证 + 会话生命周期
  As a 平台架构师
  I want IAF IAM 作为唯一身份提供方，zw-brain 仅承接本地业务治理
  So that 边界与 docs/reconstructs 收敛方案对齐，不在 zw-brain 内复造 IAM

  Background:
    Given IAF IAM OIDC discovery 端点已配置
    And 用户 U1 在 IAM 注册，realm_roles 含映射到 zw-brain ROLE_ORGAN_OPERATER
    And 单租户 sd-default 已初始化
    And 默认 DEV ZW_BRAIN_DEV_IAM_BYPASS=0（生产路径生效）

  Scenario: 正向 — 标准 OIDC 登录获得 session
    When U1 通过 IAM 完成 OIDC code 交换
    Then zw-brain 收到 id_token + access_token
    And 本地建立 session（含 actor_id=sub / current_org_code / role_codes / valid_to）
    And session 写入 actor_org_role_binding 投影表

  Scenario: 正向 — 多组织 / 多角色用户登录显式切换上下文
    Given U2 持 IAM realm_roles 映射 ROLE_ORGAN_MANAGER × 部门B 与 ROLE_BUSIAUDIT × 省大数据局
    When U2 登录后访问任何业务页
    Then UI 强制展示"组织切换器"，用户必须显式选择 current_org_code
    And session.current_org_code 设置后才能继续业务（基线 §六 角色 ≠ 方向）

  Scenario: 正向 — actor_role 与 actor_org_code 同时进入审计
    When U2 切换到 部门B / ROLE_ORGAN_MANAGER 上下文，执行任意 Capability
    Then audit_event 一条记录：actor_id=U2.sub / actor_org_code=部门B / actor_role=ROLE_ORGAN_MANAGER

  Scenario: 负向 — 未携带有效 access_token 的请求被拒
    When 任意 capability 调用未携带 Authorization header
    Then API 返回 401
    And 不进入业务层
    And 审计总线**不**记录该请求（避免日志污染）

  Scenario: 负向 — access_token 过期触发 refresh / 重新登录
    Given U1 session 已过期
    When U1 继续调用任意 capability
    Then API 返回 401 + reason="token_expired"
    And UI 引导重新登录

  Scenario: 负向 — IAM realm_roles 含 zw-brain 不认识的角色码
    Given U3 realm_roles 含 "ROLE_LEGACY_FOO"（不在 7 角色码集合）
    When U3 登录
    Then 不识别的角色码被**丢弃**（不报错也不静默扩权）
    And 如最终结果 U3 无有效角色码，session 建立失败 + UI 提示"无访问权限"
    And 审计总线记录 reason="unknown_role_code_dropped" + 具体角色码

  Scenario: 负向 — IAM 端 realm_roles 与 zw-brain 域字段同步
    Given U1 在 IAM 端被移除 ROLE_ORGAN_OPERATER
    When U1 下次刷新 token 或登录
    Then session 不再包含 ROLE_ORGAN_OPERATER
    And actor_org_role_binding 投影表对应行打 valid_to=now（不物理删除，保审计）

  Scenario: 回归 — DEV ZW_BRAIN_DEV_IAM_BYPASS=1 仅本机生效
    Given 环境变量 ZW_BRAIN_DEV_IAM_BYPASS=1
    Then `docs/preflight-debt.md` 记录"prod guard deferred to first customer deployment"
    And 部署到生产环境前**必须**清零该环境变量（运维 checklist 强制）

  Scenario: 回归 — IAM 是外部依赖，zw-brain 不实现密码 / MFA 等认证逻辑
    Then 仓库代码不包含 password hashing / MFA / OTP / 第三方 social login 实现
    And 仅保留 OIDC code 交换 + token 校验 + realm_roles → role_codes 映射

  # ── 存量用户首次 IAM 登录：单行身份认领（消除两套用户数据，D28 负责人 sign-off）──
  Scenario: 正向 — 存量用户首登按 sub 认领既有行，actor_projection 不增行
    Given 存量用户 L1 由 legacy import 落为 actor_projection 一行（external_actor_id=pub_user.ID，status=iam_account_missing）
    And IAM 已为 L1 注入真实 sub（其 external_actor_id 已是该 sub）
    When L1 二次/换票登录，claims.sub 命中该行
    Then 该行原地刷新（同 PK），不新建第二行
    And actor_projection 该租户行数不变

  Scenario: 正向 — 缺 sub 时按 account 辅助匹配唯一命中即就地 rekey
    Given 存量用户 L2 落为 actor_projection（external_actor_id=pub_user.ID，profile.account=L2 账号，已挂角色绑定）
    When L2 首次 IAM 登录，claims.preferred_username 唯一匹配 profile.account
    Then 该存量行被 rekey 到 claims.sub（同 PK，保留 account/legacy_actor_ref/region 等 legacy profile）
    And 其 actor_org_role_binding 与 legacy_object_mapping 同事务搬到新 sub 键
    And **不**产生第二行（修复"两套用户数据"）

  Scenario: 负向 — 辅助匹配命中多条存量行，fail-closed 不自动认领
    Given 两条 status∈{iam_account_missing,unmatched} 的存量行 profile.account 相同
    When 某 IAM 身份按该 account 辅助匹配
    Then 抛 ActorMatchError，登录接口返回 403 error="actor_identity_ambiguous"
    And 不新建行、不 rekey 任何行（等人工裁决）

  Scenario: 负向 — 不认领 disabled 存量行（不继承其角色）
    Given 一条 status=disabled 的存量行 profile.account 与某 IAM 身份匹配
    When 该 IAM 身份首次登录
    Then disabled 行保持不变（不被 rekey）
    And 登录身份落为全新 sub 键行，不继承 disabled 行的任何角色绑定

  Scenario: 回归 — 登录认领不禁用 import 写入的多组织绑定
    Given 存量用户 L3 由 import 写入多条 actor_org_role_binding（多组织/多角色）
    When L3 首次 IAM 登录被认领（token 未携带产品角色）
    Then L3 的全部导入绑定原样搬到 sub 键且仍 active（登录不 disable 任何 binding）

  Scenario: 回归 — 同 sub 二次登录幂等
    When 同一 sub 连续两次登录
    Then 第二次为"原地刷新既有 sub 行"，actor_projection 不增行，绑定不变
