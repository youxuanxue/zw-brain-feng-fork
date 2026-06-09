# Wave: 2
# Journey: J2
# Pages: P7
# Consumer-faces: WebUI | API | CLI | MCP | A2A
# Roles: ROLE_BUSIAUDIT | ROLE_ORGAN_MANAGER | ROLE_ORGAN_OPERATER
# Trace: D31 / D32 / D32.a / 业务反馈 #PR129 / 基线 §5.2 P7 / dsp-sharezone-topic-package-reconstruction-plan-v1.md §3.2 / §3.3 / §四 / 旧 xlsx 行 100 (主题库信息提交) / 基线 §5.6 #13 basesubject 硬保护
# Priority: P1
# Owner: e3
# Pytest: tests/integration/test_wave2_topic_package_curation.py
# Deferred: 专题包整面退出本期（D55/P6，业务方 2026-06-09 sign-off）。下线整面、保数据不删库——capability 注册保留、seed 数据保留，仅去 PERMISSION_ROLES 角色授权（全员 fail-closed）+ 前端入口/路由。backing 测试已翻为退役不变量（策展/发布链 capability 对所有角色 fail-closed）。待专题包重新立项时恢复角色授权与入口、撤本 Deferred。

Feature: Wave 2 P7 专题包编制
  As a 业务运营方 (ROLE_BUSIAUDIT) 或部门管理员 / 操作员 (ROLE_ORGAN_MANAGER / ROLE_ORGAN_OPERATER)
  I want 把现有目录、资源、模型、案例、申请模板组织成主题包，走 6 态发布流程上线
  So that 旧"主题库信息提交"链路（高频 xlsx 行 100）收敛为单一编制入口，且不复造目录 / 资源 / basesubject 事实

  Background:
    Given 单租户 sd-default 已初始化，7 角色码 CHECK 约束已生效
    And 集团推理平台 mock 已就绪（基线 §6 / D14；preflight 段 10 守 LLM 直连禁令）
    And TopicPackage 6 张物理表已通过 `Base.metadata.create_all` 建出（plan §3.1）
    And 已有 sd-default 山东 catalog_entry / resource_asset / catalog_model / topic_package_evidence 种子数据可被引用
    And Capability `topic.package.create` / `topic.package.configure` / `topic.package.submit` / `topic.package.review` / `topic.package.publish` / `topic.package.policy.update` / `topic.package.evidence.attach` 已注册（audit_class 见 plan §四）
    And 6 态发布状态机已就位：draft → configuring → configured → submitted → published / rejected → offline_pending → offline（plan §3.3）
    And 我以 ROLE_BUSIAUDIT 登录（plan §〇 专题包运营 = ROLE_BUSIAUDIT）

  Scenario: 正向 — 创建专题包草稿并组织引用项（6 引用类型，plan §3.2）
    When 我调用 `topic.package.create` 创建 `tp-yiliao-jiuzhu`，name="医疗救助信息" / scenario_desc="跨民政+卫健的医疗救助场景"
    Then `topic_package` 写入一条记录，status=draft / owner_org_snapshot 含创建人组织
    When 我调用 `topic.package.configure` 绑定 catalog_entry / resource_asset / catalog_model / application_template / case_evidence / objection 6 类引用项
    Then `topic_package_item` 按 ref_type 分组写入；每项 ref_id 指向 canonical 对象，**不复制 canonical 事实**（plan §1.2 / §3.1）
    And status 从 draft 推进到 configuring，再到 configured（plan §3.3）
    And 审计总线记录 `capability_call=topic.package.create` / `topic.package.configure`，audit_class=write-trace（plan §四）

  Scenario: 正向 — 配置可见性策略（组织 + 角色 + 消费面三维，plan §六.1 Phase 1）
    Given 专题包 `tp-yiliao-jiuzhu` 状态=configured
    When 我调用 `topic.package.policy.update` 配置可见性：
      | 维度          | 值                                                       |
      | tenant_id    | sd-default                                               |
      | org_snapshot | 山东省民政厅 / 山东省卫健委 / 各地级市民政局                |
      | role_codes   | ROLE_ORGAN_OPERATER / ROLE_ORGAN_MANAGER / ROLE_BUSIAUDIT |
      | surface      | webui / api / mcp                                        |
    Then `topic_package_visibility` 写入对应策略；`tenant_capability_policy` 同步候选写入
    And 不支持的维度（如分级授权 / 业务条线 / 岗位）被拒：policy decision=reject，原因 `dimension not supported in Phase 1`（plan §〇 + §六.1 + T2）
    And 分级授权延后至 R14 表单 schema 化引擎 Wave 2 后再评估（基线 §5.6 #3）

  Scenario: 正向 — 提交审核 → 发布 → 下线 6 态完整流程（plan §3.3）
    Given 专题包 `tp-yiliao-jiuzhu` 状态=configured，已绑定 ≥1 canonical 引用 + ≥1 可见性策略（plan §3.3 推进规则 1）
    When 我调用 `topic.package.submit`
    Then status 从 configured 推进到 submitted
    And `topic_package_review_record` 写入一条审核任务记录
    When ROLE_BUSIAUDIT 调用 `topic.package.review` 通过审核 + `topic.package.publish` 发布
    Then status 从 submitted 推进到 published
    And `topic_package_review_record` 追加审核结果（plan §3.3 推进规则 2）
    When 运营方下线该专题包
    Then status 从 published 推进到 offline_pending（plan §3.3 状态机）；审核后推进到 offline
    And published 后目录 / 资源状态变化由读模型刷新反映，专题包**不反向覆盖源状态**（plan §3.3 推进规则 4）
    And 审计总线全程记录 `capability_call`，audit_class=approval-trace

  Scenario: 正向 — 关联应用案例 evidence + 复用成效（plan §3.2 case_evidence + §六.3）
    Given 专题包 `tp-yiliao-jiuzhu` 状态=published
    When 我调用 `topic.package.evidence.attach`，attach_type=`case_evidence`，关联 Example 旧表迁入的 evidence + 多个 resource_asset 调用回执
    Then `topic_package_evidence` 写入一条记录，附 actor_snapshot / org_snapshot / 关联的 canonical 引用清单
    And 案例必须可追溯到事实证据：复用了哪些目录 / 资源 / 模型 / 服务 + 覆盖了哪些组织 / 岗位 / 报表场景 + 产生了哪些申请 / 交付 / 订阅 / 调用回执（plan §六.3 4 维证据）
    And 联系人 / 电话 / 邮箱按敏感信息策略脱敏（plan §五 ExampleContact 行 + §九 T5）

  Scenario: 负向 — 不能创建复制目录事实（TopicPackage 是投影非事实源）
    When 我尝试通过 `topic.package.configure` 直接修改 catalog_entry 字段（如 name / owner_org）而非引用
    Then 调用被拒，policy decision=reject，原因 `topic_package is projection, cannot mutate canonical catalog_entry`
    And `catalog_entry` 表数据无任何变化
    And preflight 段 25 (adapter-write-ban) 守 zw_brain/adapters/legacy/ 之外的写禁区
    And 目录事实仍归属 `catalog_entry` / `catalog_item` / `catalog_model`（plan §1.2）

  Scenario: 负向 — 不能创建或写入 dsp_basesubject 81 表内容（D7 forbidden-zone / §5.6 #13）
    When 任何 Capability 试图在专题包链路中 INSERT / UPDATE / DELETE `dsp_basesubject` 81 张独立表中的任何一张
    Then 调用被拒；`dsp_basesubject` 仅作为专题素材 evidence **候选输入**，不生成新事实源（plan §1.2 / §1.5）
    And preflight 段 25 (adapter-write-ban) 在 `zw_brain/adapters/legacy/` 之外的写 token 直接拦下
    And `dsp-basesubject` 的 schema/resource/archive/standard 内容仅可作为 catalog_model evidence 或 standard asset 输入（plan §2.4）

  Scenario: 负向 — published 前必须满足绑定 + 策略前提（plan §3.3 推进规则 1）
    Given 专题包 `tp-empty-demo` 状态=configured 但未绑定任何 canonical 引用项
    When 我调用 `topic.package.submit` 试图提交审核
    Then 调用被拒，原因 `published 前必须至少绑定一个 canonical 引用项和一条可见性策略`
    And status 不推进，仍停留在 configured
    And 审计总线记录 reject 事件

  Scenario: 回归 — 不复造旧专区后台 / 旧示范应用门户 / 旧基础主题库页面引擎（plan §八）
    Then 编制链路 0 处实现旧 `share_zone_*` 后台 / 旧 `dsp-example` 门户 / 旧 `dsp-basesubject` 页面 / 流程 / 数据库配置
    And `share_zone_appkey.app_key` / 数据库连接 / 内部文件路径 / 联系人敏感信息 / 任务配置均不迁入（plan §八 第 3 条）
    And 旧 `share_zone_resource_auth` 资源授权规则只作为策略模板候选，不自动生效（plan §九 T3）

  Scenario: 回归 — Capability 投影到 5 消费面契约一致（R15 桥接面 / plan §〇）
    When 我导出 WebUI 路由表 / OpenAPI / CLI commands / MCP tool manifest / A2A agent card
    Then 5 份导出文件中 7 个编制类 capability slug（create / configure / submit / review / publish / policy.update / evidence.attach）一致出现
    And 5 消费面 input_schema 一致；`export_agent_contract.py --check` 无 drift
    And 前端 UI 文案禁用 `package` / `projection` 等工程术语（R12；preflight 段 24）
