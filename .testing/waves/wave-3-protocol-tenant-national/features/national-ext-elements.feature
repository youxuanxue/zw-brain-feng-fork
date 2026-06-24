# Wave: 3
# Journey: J2 (独立子旅程)
# Pages: P5 (国家扩展要素 tab)
# Consumer-faces: WebUI
# Roles: ROLE_ORGAN_MANAGER | ROLE_BUSIAUDIT
# Trace: 基线 §3.3 双轨编制, §10.4 国家扩展要素 (P2), §5.6 #9
# Priority: P2
# Owner: e6
# Pytest: tests/test_national_ext_elem.py + tests/test_national_channel_webui_snapshot.py + tests/e2e/national_channel.spec.ts

Feature: 国家扩展要素目录编制独立子旅程
  As a 部门管理员 / 业务运营员
  I want 走与政务目录编制完全独立的国家扩展要素编制流程
  So that 双轨独立，不污染主线 catalog 状态机

  Background:
    Given 国家扩展要素 CatalogModel 模板已预置
    And data_ext_elem_catalog_compile_task 流程已实现
    And 我以 ROLE_ORGAN_MANAGER 登录，org_code=部门A

  Scenario: 正向 — 编制国家扩展要素目录
    When 我打开 P5 → "国家扩展要素" tab
    Then 进入独立编制流程（与政务目录入口分离）
    When 我新建国家扩展要素目录 C_NAT_001
    Then 创建独立 task，使用 data_ext_elem_catalog_compile_task 流程
    And 状态机与政务目录**完全独立**

  Scenario: 正向 — 业务部门审核 → 主管部门审核
    Given C_NAT_001 已草拟提交
    When 业务部门管理员审核通过
    Then task.status → 业务部门通过
    When ROLE_BUSIAUDIT 主管部门审核通过
    Then task.status → 待同步国家平台
    When 国家通道接入配置与上线资料均确认后执行同步
    Then task.status → 已发布
    And 不在同步完成前标记已同步国家平台

  Scenario: 正向 — 历史目录处理审核
    Given 存在历史国家扩展要素目录 C_NAT_OLD
    When 我对 C_NAT_OLD 发起 "历史目录处理"（修订 / 撤销）
    Then 进入独立审核流程
    And 不影响政务目录主线状态机

  Scenario: 负向 — 国家扩展要素流程不能复用政务目录状态机
    When 我尝试通过 API 把国家扩展要素 task 写入 data_catalog 表
    Then 拒绝
    And 两套表 / 两套状态机的独立性硬约束

  Scenario: 负向 — 不能在国家通道未就绪时强制发布
    Given 国家通道未开启，或接入配置 / 上线资料未补齐
    Then 国家扩展要素同步按钮置灰
    And API 只能把主管审核通过的任务推进到「待同步国家平台」
    And 不能把任务强制写成「已发布」
    And 草拟编辑仍可（草稿不发布国家通道）

  Scenario: 回归 — 与 national-direct.feature 边界
    Then 国家扩展要素是 "目录编制" 双轨之一
    And 国家直达是 "申请转报" 子旅程
    And 两者**独立**：一个走 J2 编制；一个走 J1 申请审批
    And 都标 P2 优先级，默认 feature flag 关闭
