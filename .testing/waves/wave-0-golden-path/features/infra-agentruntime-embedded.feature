# Wave: 0
# Journey: Cross
# Pages: None (infrastructure)
# Consumer-faces: Internal Agent
# Roles: ROLE_SYSTEM
# Trace: D2 / R15 / 基线 §八 AgentRuntime 声明式协议 / §10.1
# Priority: P0
# Status: Draft

Feature: Infra — AgentRuntime Embedded SDK 最小集成
  As a 平台架构师 / Wave 0 守门人
  I want 至少 1 个 zw-brain 内置 Agent 用 AGENT.yaml 描述并通过 validate + doctor
  So that 后续 Wave 1+ 外部 Agent 接入路径与 Embedded SDK 形态先内部跑通

  Background:
    Given AgentRuntime Embedded SDK 已集成
    And 内置 Agent 候选：`agents/zw_search_helper/`（P2 自然语言意图解析）
    And `AGENT.yaml` runtime_spec_version = anp-agent/v1.2（基线 R15）

  Scenario: 正向 — AGENT.yaml 字段齐全可 validate
    When 我执行 `agentruntime validate agents/zw_search_helper/AGENT.yaml`
    Then validate 通过
    And AGENT.yaml 必含字段：
      | 字段                 | 期望值                            |
      | runtime_spec_version | anp-agent/v1.2                    |
      | trust_level          | platform（内置 Agent）             |
      | tools                | 引用 zw-brain Capability slug      |
      | model.provider       | 集团推理平台 gateway URL（D6/D14） |
      | auth_mode            | trusted_gateway                    |
      | tenant_id            | sd-default                         |
      | context.policy       | regulated_minimal                  |
      | admin:runtime scope  | 仅 ROLE_SYSTEM                    |

  Scenario: 正向 — doctor 检查所有 readiness gate（生产形态）
    When 我执行 `agentruntime doctor agents/zw_search_helper/`
    Then 所有 readiness gate 通过：
      | gate                              | 期望                                  |
      | model.provider points to inspur gateway | ✓                                |
      | auth_mode ≠ none                  | ✓                                   |
      | tools 全部存在于 Capability Registry | ✓                                   |
      | tools 全部 audit_class 已声明       | ✓                                   |
      | trust_level 与 Registry 一致      | ✓                                   |

  Scenario: 正向 — 内置 Agent 通过 Embedded SDK 调用 Capability
    Given Capability `resource.search` 已注册，exposure 含 "internal-agent"
    When 内置 Agent zw_search_helper 调用 tool resource.search(keyword="户籍")
    Then 调用回到 zw-brain 统一审计面，actor_role=ROLE_SYSTEM（内置 Agent 触发对应 ROLE_SYSTEM，与 R10 7 角色码集合一致；见 cross-cutting/role-task-skill-trace.md §6）
    And 调用结果与人类 ROLE_ORGAN_OPERATER 调同一接口一致（同 Capability 投影）

  Scenario: 负向 — AGENT.yaml runtime_spec_version 错误 → 拒绝注册
    Given AGENT.yaml runtime_spec_version = anp-agent/v1.0（旧版本）
    When 我执行 validate
    Then validate 失败
    And 错误信息含 "runtime_spec_version must be anp-agent/v1.2" (R15 硬约束)
    And Registry 拒绝注册

  Scenario: 负向 — 直连第三方 LLM 的 AGENT.yaml 被拒
    Given AGENT.yaml model.provider = "https://api.openai.com/v1"
    When 我执行 doctor
    Then doctor 失败
    And 错误信息含 "model.provider must point to inspur inference gateway" (D6 硬约束)

  Scenario: 负向 — auth_mode=none 在生产 gate 阻断
    Given AGENT.yaml auth_mode = "none"
    When 我执行 doctor --target production
    Then doctor 失败
    And 错误信息含 "auth_mode=none is rejected by production readiness gate" (基线 §8.2)

  Scenario: 回归 — Embedded SDK 不引入 Standalone HTTP 形态（Wave 3 才评估）
    Then `agents/zw_search_helper/` 目录下不出现 HTTP server 启动入口
    And 调用路径都是进程内 in-process 调用
    And 基线 §8.2 决策"Phase 1 默认 Embedded SDK；Standalone HTTP 留 Wave 3+ 评估"对齐
