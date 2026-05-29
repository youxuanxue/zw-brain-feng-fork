# Wave: 0
# Journey: J1
# Pages: P3
# Consumer-faces: WebUI | API
# Roles: ROLE_ORGAN_OPERATER
# Trace: R9, 基线 §5.4.4 P3 申请草拟助手反约束, 旧 xlsx 行 [3..4] 库表 + [8..11] 文件夹/文件 (代理服务/融合服务/通用服务申请 ❌ 不复刻，详见 cross-cutting/legacy-128-mapping.md), 业务反馈 #17
# Priority: P0
# Status: Ready
# Owner: e1
# Pytest: tests/test_wave0_j1_discover_draft.py + tests/test_wave1_p3_application_assistants.py
# Twin-F: e1.F7

Feature: J1 申请草稿（P3 申请/审批/跟踪页）
  As a 部门操作员 (ROLE_ORGAN_OPERATER)
  I want 在 P3 页面快速填好一份资源申请并提交
  So that 不漏字段、不重复填、提交后能跟踪

  Background:
    Given 单租户 sd-default 已初始化
    And 我以 ROLE_ORGAN_OPERATER 登录，org_code=部门A_公安
    And 资源 C101 / C102 已发布
    And 资源 C101 shared_type=1 无条件共享；C102 shared_type=2 有条件共享

  Scenario: 正向 — 从 P2 跳入 P3 草稿，主体信息自动预填（旧 xlsx 行 4 "库表资源申请-有期限"）
    When 我从 P2 点击 C101 的 "申请使用"
    Then P3 草稿页打开，资源信息预填：
      | 字段             | 期望                |
      | resource_id      | C101              |
      | applicant_org    | 部门A_公安          |
      | applicant_name   | 当前登录账号姓名      |
    And 使用方信息按当前账号 org 自动预填
    And 申请单 status=0 草稿

  Scenario: 正向 — 暂存草稿（旧 xlsx 行 3 "库表资源申请暂存"）
    Given 字典 apply.temporarily_store 已开启
    When 我在草稿页填入部分字段后点击 "暂存"
    Then 草稿写入数据库，application.status=0
    And 我刷新页面，草稿被还原
    And 必填字段未完整时**仍可暂存**（与"提交"区分开）

  Scenario: 正向 — 提交申请（无条件共享分支，旧 xlsx 行 4 "库表资源申请-有期限"）
    When 我完整填写：
      | 数据用途       | 业务系统查询接口          |
      | 业务系统       | 公安治安管理系统          |
      | 办事场景       | 户籍证明在线办理          |
      | 堵点场景       | 群众跨省办理户籍证明      |
      | 申请依据       | 公安部户籍管理办法 第X条  |
      | 使用期限       | 有期限 / 180 天          |
      | 附件          | 申请依据.pdf            |
    And 我点击 "提交申请"
    Then application.status 从 0 草稿 → 1 待审
    And 审计总线记录 capability_call=application.submit，audit_class=write-critical
    And UI 显示提交回执号 + "跳转至我的申请"按钮

  Scenario: 正向 — AI 草拟助手填写建议（基线 §5.4.4 P3）
    When 我在 "申请依据" 输入框获得焦点
    Then AI 草拟助手在右侧弹出
    And 助手基于资源 metadata + 历史相似申请给出 3 条候选申请依据
    And 我点击 "采纳建议 #2"，"申请依据" 输入框被填入
    And 助手输出**不替我提交**（提交按钮仍需手动点击 — 反约束 P3）

  Scenario: 负向 — 必填缺失拒绝提交（旧 xlsx 行 3 暂存场景的反向 — 必填校验在"提交"步骤强生效）
    Given 我已暂存但 "申请依据" 为空
    When 我点击 "提交申请"
    Then 拒绝提交
    And UI 显示具体缺失字段名（不是模糊提示）
    And application.status 仍为 0 草稿

  Scenario: 负向 — 不能为他人提交申请（applicant_org 强校验）
    When 我尝试通过 API 直接 PUT application.applicant_org=部门X
    Then 返回 403 或写入被拒
    And 审计总线记录 policy decision=reject，原因="applicant_org ≠ session.org"
    And R11：方向由 applicant_org_code 计算，不靠角色拆分

  Scenario: 负向 — 已下线资源不能再申请
    Given 资源 C101 状态变更为 5 下线
    When 我尝试为 C101 创建申请草稿
    Then 拒绝创建
    And UI 提示 "该资源已下线"

  Scenario: 回归 — AI 减摩不夺权（基线 §5.4.5 一票否决）
    Then "提交申请" 按钮**不由 AI 触发**
    And AI 助手区域不覆盖审批人 / 资源详情等关键责任性字段
    And 关闭 AI 助手后主任务仍能完成
