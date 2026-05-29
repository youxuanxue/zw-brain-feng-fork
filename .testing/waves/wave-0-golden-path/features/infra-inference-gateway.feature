# Wave: 0
# Journey: Cross
# Pages: None (infrastructure)
# Consumer-faces: All
# Roles: All
# Trace: D6 / D14 / 基线 §3.4 (集团推理平台外部依赖) / §10.1 / preflight 段 10
# Priority: P0
# Status: Ready
# Owner: e6
# Pytest: pending
# Twin-F: e6.F2
# InTest-Scope: tests/test_wave0_infra.py 覆盖 4 项（check_no_direct_llm.py 段 10 守卫通过 / 单一 client 出口
#   文件无第三方 host 字面量 / chat 强制 request_id D4 审计 / 缺 gateway 配置 raise 不回退第三方）；
#   circuit-breaker 降级 + 各 AI 减摩点 fallback + 提示词注入系统前缀归 W0-07/Wave1。

Feature: Infra — 模型调用走集团推理平台统一入口
  As a 平台架构师 / 安全合规
  I want 所有 LLM / Embedding / ASR / Rerank / OCR 调用收口到集团推理平台 SDK
  So that 政务场景的"模型调用统一接入边界"不被任何模块绕过

  Background:
    Given zw_brain/shared/inference/client.py 已就绪（Phase 0 mock 实现，文档到位后只换内部实现）
    And 集团推理平台 gateway mock 已启动，listening at INFERENCE_GATEWAY_URL

  Scenario: 正向 — 业务代码通过 client 调用 LLM
    When 业务模块（如 P2 自然语言意图解析）调用 client.chat(messages=[...], model="qwen-7b")
    Then 请求**最终**指向 INFERENCE_GATEWAY_URL，**不**直连 OpenAI / Anthropic / 百川 / 智谱 / 通义
    And client 自动附加 tenant_id / actor_id / capability_call 上下文（便于推理平台审计）
    And 调用结果含 inference_id（可回溯到集团推理平台日志）

  Scenario: 正向 — 推理调用全链路审计
    When 业务调 client.chat 一次
    Then audit_event 一条 capability_call=inference.chat，audit_class=read
    And 推理参数（model / token 用量 / latency）写入审计 metadata

  Scenario: 负向 — preflight 段 10 检测直连第三方 API
    Given 我提交一个包含 `import openai` 或 `requests.post("https://api.anthropic.com/...")` 的 commit
    When 我运行 `bash scripts/preflight.sh`
    Then preflight 段 10 失败
    And 失败信息明确指出违规文件 + 行号
    And commit 被 pre-commit hook 拦下

  Scenario: 负向 — 推理平台不可达时业务有明确降级路径
    Given INFERENCE_GATEWAY_URL 返回 ConnectionError 持续 60s
    When 业务模块调 client.chat
    Then 触发熔断（circuit breaker open）
    And 业务模块根据自己的 AI 减摩定位决定降级：
      | AI 减摩点              | 降级行为                          |
      | P2 自然语言意图解析     | UI 提示"AI 助手暂不可用"，结构化检索仍可用 |
      | P3 申请草拟助手         | 不显示草拟建议，主表单仍可填写            |
      | B1.1 调查摘要助手       | 显示"AI 助手暂不可用"，原始审计证据仍可读 |
    And **业务主任务仍可独立完成**（一票否决 §5.4.5）

  Scenario: 负向 — 提示词注入防御边界
    When 业务调 client.chat，messages 含恶意 prompt（试图越权）
    Then client 至少注入系统级前缀（限制 capability 范围 / 限制 user）
    And 模型输出不直接作为责任性写操作的 trigger（业务侧仍需结构化确认 — 反约束 §5.4.5）

  Scenario: 回归 — 推理客户端是单一文件入口（确定性自动化运营和运维）
    Then 仓库中**仅一个** client 入口文件：`zw_brain/shared/inference/client.py`
    And `grep -r "import openai\|import anthropic\|import baichuan\|import zhipuai\|import dashscope" zw_brain/` 返回 0 条
    And preflight 段 10 持续守卫此约束
