# Wave: 2
# Journey: B1.2
# Pages: B1.2
# Consumer-faces: WebUI
# Roles: ROLE_SYSTEM
# Trace: R15, 基线 §8.3 Registry 最小字段, §8.4 注册流水线 UI 化, §10.3
# Priority: P1
# Owner: e4
# Pytest: tests/integration/test_b12_intake.py
# Unfreeze-Note: PR #91 (E4 B1.2 后端) + PR #97 (B1.2 UI panel)：能力包审核注册流水线
#   (manifest → lint → audit → 注册) 后端 capability + UI panel 落地。
#   pytest:
#     tests/integration/test_b12_intake.py — exposure matrix filter / lifecycle transition validate /
#       package metadata trust_level 字段 / cross-tenant 拒绝 / 8 cases
#   (注：trust_level 升降级走 b1-2-trust-level-upgrade.feature；本 feature 聚焦
#   package 注册流水线本身 — manifest 字段、生命周期态转换合法性、cross-tenant 隔离)

Feature: B1.2 能力包审核注册（UI 化的 §8.4 流水线）
  As a 平台运维员
  I want 在 B1.2 外部系统模块 UI 完整地审核 + 注册外部 Agent 能力包
  So that 不需要命令行能完成 7 步流水线（基线 §8.4）

  Background:
    Given 我以 ROLE_SYSTEM 登录，进入 B1.2 外部系统模块
    And 已收到一份外部 Agent AGENT.yaml (runtime_spec_version=anp-agent/v1.2)

  Scenario: 正向 — UI 完整完成 7 步流水线
    When 我上传 AGENT.yaml + 描述资料
    Then UI 显示 "Step 1/7：声明已收"
    When 我点击 "Step 2: 校验"
    Then 系统自动执行 validate + doctor
    And 显示 readiness gate 通过/失败明细
    When 我点击 "Step 3: 配置 Capability 映射"
    Then UI 展示 AGENT.yaml 中 tools/skills 与 zw-brain Capability 的映射关系
    And 我可调整 tenant_scope / auth_policy / audit_class / human_confirmation_required
    When 我点击 "Step 4: 申请升级到 verified"
    Then 进入审核状态，等待 SECURITY_AUDIT 协同
    When SECURITY_AUDIT 协同确认（另一会话）
    Then 状态机进入 "审核通过"
    When 我点击 "Step 5: 注册进 Registry"
    Then Registry 新增 record，review_status=approved
    When 我点击 "Step 6: 配置 exposure"
    Then exposure 默认 [mcp, a2a]，我可选择性收紧（不可放宽）
    When 我点击 "Step 7: 上线 + 监控"
    Then Registry record 进入 active 状态
    And UI 跳转到该能力包的运行监控页

  Scenario: 正向 — Registry 最小字段齐全
    When 我打开任意已注册能力包详情
    Then 字段齐全（基线 §8.3）：
      | slug | version | package_kind | source_type | review_status | tenant_scope | auth_policy | audit_class | human_confirmation_required | compatibility | runtime_binding | rollback_target | runtime_spec_version | agent_yaml_ref | trust_level | workspace_required |

  Scenario: 负向 — 未通过 doctor 不能进入下一步
    Given AGENT.yaml model.provider 直连第三方 API
    When 我尝试推进到 Step 3
    Then UI 拦下，错误信息明示 D6 / D14 硬约束

  Scenario: 负向 — 不能跳步注册
    When 我尝试直接调用 API POST /registry/packages，跳过 SECURITY_AUDIT 协同
    Then 拒绝
    And 任何 untrusted → verified 升级**必须**经过 §8.2 协同审核

  Scenario: 负向 — 注册不能覆盖已禁用的 slug
    Given slug=foo.bar 之前 review_status=disabled
    When 我尝试以同 slug 新版本注册
    Then 提示已禁用 slug，需要先恢复或换名
    And 审计记录尝试

  Scenario: 回归 — UI 操作与 CLI 等价
    Then 同一流水线**也**可以通过 zw-brain-cli registry register / approve / activate 命令完成
    And UI 与 CLI 共用同一 Capability（R3 投影一致）
    And 审计落同一 audit_event 表
