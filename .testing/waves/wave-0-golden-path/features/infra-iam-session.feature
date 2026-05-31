# Wave: 0
# Journey: Cross
# Pages: None (infrastructure)
# Consumer-faces: WebUI | API | CLI
# Roles: All
# Trace: 基线 §3.4 (IAF IAM 外部依赖), docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md
# Priority: P0
# Owner: e6
# Pytest: tests/test_wave0_infra.py
# InTest-Scope: tests/test_wave0_infra.py 覆盖 7 项（OIDC 端点派生 / 缺 auth_server_url 报错 /
#   realm_access.roles → role_codes 映射 / 未知角色码不静默扩权 / 默认租户 sd-default /
#   会话生命周期 + token 不回传浏览器体 / 无 bearer 401）；
#   D-2 红线：session → actor_org_role_binding 投影写入 + valid_to 软删除依赖 D-2 解冻（GovernanceMapper
#   投影 0 行），本期 skip 不实现；id_token RS256 全链路验签需 jwks 加密 fixture，归 W0-07。

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
