# Wave: Cross (跨 wave 回归)
# Journey: All
# Pages: All
# Consumer-faces: All
# Roles: All
# Trace: 基线 §5.4.5 一票否决项 + §5.5 R12 + §4.4 AI 不能承担清单
# Priority: P0
# Owner: e6
# Pytest: preflight 段 10/24/25 + tests/test_capability_boundary.py

Feature: 系统级护栏 + AI 一票否决项（跨 wave 回归）
  As a 平台架构师
  I want 一组 cross-cutting 回归用例守卫"AI 减摩不夺权 + 工程术语不进 UI + 写操作必须人工确认"等硬约束
  So that 任何 Wave 的实施 PR 都被强制跑过这组回归

  Background:
    Given 任意 Wave 的实施完成
    And 仓库已构建可运行的客户演示环境（含 WebUI + API + CLI + MCP + A2A 五消费面）

  # ========== AI 一票否决项（基线 §5.4.5） ==========

  Scenario: 一票否决 #1 — 首页不以聊天框作为默认主入口
    Then 8 个页面（P1-P5, P7, B1.1, B1.2）首屏渲染时
    And 主区域是结构化（目录树 / 表单 / 列表 / 时间线 / 卡片）
    And 聊天 / AI 输入框**不**占据视觉主位置
    And 关闭 AI 助手后所有主任务可独立完成

  Scenario: 一票否决 #2 — AI 不替代结构化页面或状态机
    Then 任意状态机迁移（Catalog 6 态 / Application 5 节点 / Objection 5 维度 / trust_level 3 级）
    And 都**不**由 AI 触发
    And AI 只能"草拟 + 解释"，不能"决策 + 提交"

  Scenario: 一票否决 #3 — AI 不直接触发责任性写操作
    Given 任意 capability human_confirmation_required=true
    Then UI 中"提交 / 通过 / 驳回 / 发布 / 撤销 / 下线 / 跨租户放行"等按钮**不由** AI 自动触发
    And API 调用层面 AI 调用必须经 human_confirmation_token

  Scenario: 一票否决 #4 — 审批/交付/合规结论必须有证据支撑
    Then BUSIAUDIT 审批决策必须含 actor + 决策时间 + 备注（可选）
    And ObjectionCase 处理结论必须含 process_result + 处理过程链
    And 合规调查结论必须含证据 audit_event 引用
    And 任何"模糊结论"被 review 拒绝

  Scenario: 一票否决 #5 — 用户始终能感知"我在哪一步"
    Then 任意旅程页面顶部有结构化进度指示（步骤条 / 状态徽标 / 面包屑）
    And 关闭 AI 助手后进度指示**仍可见**

  Scenario: 一票否决 #6 — AI 视觉权重不压过本体
    Then AI 助手在所有页面 z-index ≤ 主体内容
    And AI 助手在所有页面尺寸 ≤ 主体内容的 1/3

  Scenario: 一票否决 #7 — 每页不机械塞 AI 模块（基线 §5.4.6）
    Then 不为"看起来 AI 原生"在每个页面塞一个 AI 模块
    And AI 模块只出现在 §5.4.4 列出的 5-6 个精准落点页

  # ========== 工程术语黑名单（R12 / 基线 §5.5） ==========

  Scenario: R12 — UI 不出现工程术语
    Then 8 页面 + 任意外部弹窗 DOM 文本不含：
      | term                |
      | package             |
      | projection          |
      | capability          |
      | policy_decision     |
      | write-with-audit    |
      | register-version    |
      | apply-tenant-policy |
      | reconcile-receipt   |
      | submit-evidence     |
    And 例外：B1.2 接入扩展中心可使用 "能力包"（业务化中文表述）

  # ========== 角色码硬约束（R10） ==========

  Scenario: R10 — 角色码集合冻结
    Then 数据库 / 审计 / Capability / UI 文案中
    And actor_role / role_code 字段值**只能**属于：
      | ROLE_SYSTEM | ROLE_BUSIAUDIT | ROLE_ORGAN_MANAGER | ROLE_ORGAN_OPERATER | ROLE_SECURITY_ADMIN | ROLE_SECURITY_AUDIT |
    And 任何 r1-r8 字面值被启动检查 + CHECK 约束 + preflight 段三重拒绝
    And 任何新增角色码尝试需走 GATE + R13 业务方 sign-off

  # ========== 反 per-tenant fork（R8） ==========

  Scenario: R8 — 仓库代码不含 hard-coded tenant fork
    Then `grep -rE 'if.*tenant_id.*==.*"' zw_brain/` 不命中"业务逻辑分叉"行
    And 任意租户差异通过配置 / 多租户策略 / 外部能力包承接

  # ========== 推理统一入口（D6 / D14） ==========

  Scenario: D6 / D14 — 模型调用走集团推理平台
    Then `grep -rE 'import openai|import anthropic|import baichuan|import zhipuai|import dashscope|requests.post.*api.openai|requests.post.*api.anthropic' zw_brain/` = 0 命中
    And 仓库中**仅**一个 client 入口 `zw_brain/shared/inference/client.py`
    And preflight 段 10 持续守卫

  # ========== 审计同步落库（D4） ==========

  Scenario: D4 — 审计写失败必须熔断业务（write-critical）
    Given Capability audit_class=write-critical
    When audit_event 写入失败
    Then 业务事务回滚
    And HTTP 返回 5xx
    And **不存在**"审计失败但业务继续"代码路径
    And wave-0 infra-audit-bus.feature 是细化覆盖

  # ========== 敏感数据脱敏 ==========

  Scenario: 敏感数据脱敏 — 凭据 / 密钥 / 身份证号 / 手机号
    Then 任意 audit_event / 日志 / Web 快照中
    And 凭据明文仅在 首次签发 + P4 一次显示
    And 后续显示形如 K_xxx_***xx
    And ObjectionCase content 维度仅存 request_id + 字段名，不全量存响应

  # ========== 不复造判定（基线 §3.4 / §5.6） ==========

  Scenario: 不复造硬约束 — 长尾外部化
    Then 仓库 zw_brain/ 下不存在以下模块的"内部实现"：
      - 数据治理（清洗 / 质量 / 血缘）
      - 数据安全（分类分级 / 敏感识别 / 脱敏策略）
      - 大屏 / 指挥中心
      - 主题库 / 专题库 / 人口库
      - 运行监控（独立体系；只暴露 metrics）
      - 国家目录治理 / 国家直达（独立子旅程，feature flag 控制）
      - 数据存证 / 区块链（adapter 形态，非内核）
      - 标准服务 / 指标平台 / 应用案例 / 脚本管理 / 通用服务 / 融合服务编排
      - 基础主题库（dsp_basesubject 81 表）
    And 任何尝试在 zw_brain/ 内创建上述模块的目录被 preflight 段反向探测拦下
