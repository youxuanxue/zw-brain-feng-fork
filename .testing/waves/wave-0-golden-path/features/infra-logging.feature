# Wave: 0
# Journey: Cross
# Pages: None (infrastructure)
# Consumer-faces: All
# Roles: All
# Trace: 排障观测基建 / D4 边界（审计≠日志，日志可丢审计不可丢）/ 段 7a 审计熔断不可降级 / 段 25 日志不写业务库
# Priority: P1
# Owner: e4
# Pytest: tests/test_infra_logging.py
# InTest-Scope: tests/test_infra_logging.py 覆盖：setup 幂等 + JSON lines 落盘 + 不碰 root logger /
#   request_id 生成·校验·注入拒收·reset 不串味 / formatter 带 request_id+actor+完整堆栈 /
#   redaction 密钥与 PII 掩码·截断·限深 / REST X-Request-Id 回显与生成 / access log 字段 /
#   _handle_error 5xx 落堆栈而响应不变·预期拒绝只记 INFO / CapabilityLogMiddleware 耗时与
#   outcome·异常原样 re-raise / 段 7a 回归（AuditWriteError 穿透）/ 段 42 守卫过 /
#   /api/client-logs 落日志不落库·413/400/429·白名单外字段不泄漏。
#   CLI/MCP/A2A 注入与浏览器端上报属人工走查（docs/ops/logging.md §验证）。

Feature: Infra — 结构化排障日志 + request_id 全链贯穿
  As a 平台运维/研发
  I want 四消费入口统一结构化日志、request_id 贯穿、异常带堆栈、能力调用带耗时
  So that 任何一次失败请求都能用一个 ID 在日志文件里串出完整链路，排查问题不再靠盲猜

  Background:
    Given 入口 main() 调用 setup_logging(service) 完成一次性初始化
    And ZW_BRAIN_LOG_DIR 指向落盘目录（文件侧恒为 JSON lines）

  Scenario: 正向 — REST 请求回显 X-Request-Id 且 access log 结构化
    When 客户端携带 X-Request-Id 调用任意 API
    Then 响应头原样回显该 X-Request-Id
    And 日志出现一条 event=http_access 行，含 method/path/status/duration_ms/request_id

  Scenario: 正向 — 未带 X-Request-Id 时服务端生成
    When 客户端不带 X-Request-Id 调用 /health
    Then 响应头含服务端生成的 req-* 格式 X-Request-Id
    And 携带非法字符的客户端 id 被拒收并重新生成（不回显注入向量）

  Scenario: 正向 — capability 调用日志含耗时与结果
    When 经 pipeline 执行任一 capability（成功或失败）
    Then 日志出现 event=capability_call 行，含 skill_id/actor/audit_id/duration_ms/outcome
    And outcome 为 ok 或 error:<异常类名>
    And 该行只记元数据，不含 payload/result 本体

  Scenario: 负向 — 未预期异常落完整堆栈但客户端响应不变
    Given 某 handler 抛出未映射异常
    When 请求该 API
    Then 客户端仍收到既有 {"error": <类名>, "detail": ...} 500 envelope（契约不变）
    And 日志出现 event=unhandled_error 行且含完整 traceback
    And 预期内拒绝（403/404/409/422 一族）只记一行 INFO、不落堆栈

  Scenario: 负向 — 日志红线：密钥与 PII 被掩码
    When 日志记录包含 api_key/token/password/phone/idcard 等键的结构
    Then 落盘值为 [REDACTED]（保留 key 名便于排障）
    And 原文不出现在任何日志输出

  Scenario: 负向 — 审计失败仍熔断（日志不改变控制流，段 7a）
    Given 审计写入抛出 AuditWriteError
    When 执行写 capability
    Then 异常原样向上抛出且业务不提交（D4 熔断语义零改变）
    And 日志仅多一条 outcome=error:AuditWriteError 观测行，无任何降级吞错

  Scenario: 正向 — 前端错误上报落日志文件不落业务库
    When POST /api/client-logs 携带 message/stack/request_id
    Then 返回 200 且日志出现 event=client_error 行（request_id 与前端一致）
    And 上报模块不触碰任何业务库写入口（段 25）
    And 超 16KiB 返回 413、坏 JSON 返回 400、超限流阈值返回 429 且不落日志
