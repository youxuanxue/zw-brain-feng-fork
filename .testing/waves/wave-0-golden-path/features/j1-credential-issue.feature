# Wave: 0
# Journey: J1
# Pages: P4
# Consumer-faces: WebUI | CLI
# Roles: ROLE_ORGAN_OPERATER
# Trace: R1, 基线 §5.2 P4「必含凭据领取页（授权码 / API Key + curl/Python/Java 调用样例 + 配额 + 监控入口）」
# Priority: P0
# Owner: e1
# Pytest: tests/test_wave0_j1_credential_call.py + tests/test_wave1_j1_credential.py + tests/test_credential_legacy_import_readonly.py
# InTest-Scope: 5 个 Scenario 由 tests/test_wave0_j1_credential_call.py 覆盖（凭据签发幂等 /
#   撤销 / expires_at 携带 / 签发后状态机 / payload 工程术语黑名单——以 delivery_repo.upsert_from_delivery
#   合成数据走 canonical runtime contract）；
#   P4 前端四件套（CLI 消费面 / 首次明文后续脱敏 / 非 owner 403）归 W0-07 浏览器验收。
# Cross-Wave-Note: tests/test_wave0_j1_credential_call.py::test_cross_wave_approval_to_delivery_consistency
#   断言失败 — sample N=10 的 approved approval_case 中 0/10 (0.0%) 有 delivery_task 行；
#   全量 approved=244 → with_delivery=26 (10.7%) << 阈值 60%。
#   根因：W0-02 legacy `dsp_catalog.data_apply_authrization`=2 行 + `data_apply`=68 行 pending-delivery
#   候选 → canonical delivery_task=68，未覆盖已 approved 244 条。属 W0-02 ↔ W0-04 结构性数据缺口，
#   非本期 W0-05 可修。详见 .data/customer-acceptance/wave0/W0-05-deferred-additions.md → D-5。
#   needs_human 决策路径：
#     (a) 解冻 D-1 + 新增 mapper 全量映射 data_apply_authrization → 重灌；
#     (b) 接受 legacy 缺口，断言阈值下调至 ≥10% + runtime issue 路径补齐 J1 forward flow；
#     (c) 本 .feature 整体降级 Deferred(W0-08) 同 conditional 处置。

Feature: J1 凭据领取（P4 交付/交换/直达页）
  As a 部门操作员 (ROLE_ORGAN_OPERATER)
  I want 在 P4 一站式领取调用凭据 + 调用样例 + 监控入口
  So that 不需要离开平台、不需要问技术支持就能开始使用数据

  Background:
    Given 单租户 sd-default 已初始化
    And 申请单 A201 / C101 已 application.status=6 已授权
    And 我以 ROLE_ORGAN_OPERATER (申请人本人) 登录

  Scenario: 正向 — 申请通过后凭据自动签发
    When 申请单 A201 被审批通过
    Then 后台异步签发凭据 cred=K_A201_xxx
    And 凭据记录 owner=A201.applicant_user_id / scope=C101 / expires_at（按申请单使用期限）
    And 审计总线记录 capability_call=credential.issue，audit_class=write-critical

  Scenario: 正向 — P4 凭据领取页四件套齐全（基线 §5.2 P4 硬要求）
    When 我打开 A201 的 P4 凭据领取页
    Then 页面同时显示：
      | 区块            | 内容                                                     |
      | 授权码 / API Key | K_A201_xxx（首次显示完整，后续脱敏，含"复制"按钮）              |
      | curl 样例       | curl -H "Authorization: Bearer K_A201_xxx" https://api/.../C101  |
      | Python 样例      | requests.get(..., headers={"Authorization": "Bearer K_A201_xxx"}) |
      | Java 样例        | OkHttp 或 HttpClient 风格代码                              |
      | 配额            | 峰值 / 平均调用频次（来自申请单）+ 当前已用                     |
      | 监控入口        | "查看调用监控" 链接，跳转 P4 调用监控段                       |
    And 不出现工程术语（R12 黑名单）

  Scenario: 正向 — CLI 消费面获取凭据（5 消费面一致性）
    When 我执行 `zw-brain-cli credential get --application A201`
    Then 标准输出包含 API Key + curl 样例
    And 标准输出与 WebUI 显示的字段一致（同 capability 投影）

  Scenario: 负向 — 凭据首次复制后再次访问不显示明文（凭据保护）
    Given 我已经在 P4 首次查看了凭据
    When 我刷新页面或重新进入 P4
    Then 凭据显示为脱敏形式（如 K_A201_***xx）
    And 提供 "重新生成凭据" 按钮（带二次确认）
    And 审计总线记录 capability_call=credential.view，audit_class=read-sensitive

  Scenario: 负向 — 非申请人本人不能查看凭据
    Given 用户 U_OTHER 与 A201.applicant_user_id 不同
    When U_OTHER 访问 A201 凭据领取页
    Then 返回 403
    And 审计总线记录 policy decision=reject，原因="credential.owner ≠ session.user"

  Scenario: 负向 — 申请被撤销后凭据立即失效
    Given 已签发凭据 K_A201_xxx
    When ROLE_BUSIAUDIT 在 P3 收回 A201 授权
    Then 凭据 K_A201_xxx 立即 revoked
    And 后续 API 调用返回 401 + reason="credential_revoked"
    And 审计总线记录 capability_call=credential.revoke

  Scenario: 回归 — 凭据 expires_at 自动按使用期限设置
    Given A201 申请单"使用期限"=有期限 180 天
    Then 凭据 expires_at = approved_at + 180 天
    And 过期后自动 revoked（后台调度）

  Scenario: 回归 — 凭据签发幂等性
    When 我对 A201 重复触发凭据签发 3 次
    Then 仅签发 1 条有效凭据（idempotency_key = application_id）
    And 审计总线 2 条 credential.issue duplicate 标记

  Scenario: 负向 — 历史导入申请凭据面诚实只读（不报错、不可签发）
    Given 一条历史导入（M0 一次性迁移）申请，无运行时交付实体
    When 我打开该申请的 P4 凭据领取页
    Then 页面诚实显示「历史导入·凭据未签发」空态，而非报错
    And 不渲染「重新签发」入口（历史导入是只读迁移记录，运行时动作不可见）
    And 对该申请触发凭据签发被拒为无效状态（只读迁移记录无在线交付实体）
    And 真正不存在的申请查询仍诚实报「未找到」
