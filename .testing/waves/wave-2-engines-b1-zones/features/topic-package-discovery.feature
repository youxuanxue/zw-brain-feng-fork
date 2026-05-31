# Wave: 2
# Journey: J1
# Pages: P7
# Consumer-faces: WebUI | API | CLI | MCP | A2A
# Roles: ROLE_ORGAN_OPERATER | ROLE_ORGAN_MANAGER | ROLE_BUSIAUDIT
# Trace: D31 / D32 / D32.a / 业务反馈 #PR129 / 基线 §5.2 P7 / dsp-sharezone-topic-package-reconstruction-plan-v1.md §3.1 / §3.2 / §六 / 旧 xlsx 行 26 (数购车申请) / 行 98 (事项/主题库查看)
# Priority: P1
# Owner: e3
# Pytest: tests/integration/test_wave2_topic_package_discovery.py

Feature: Wave 2 P7 主题包发现
  As a 部门操作员 / 部门管理员 (ROLE_ORGAN_OPERATER / ROLE_ORGAN_MANAGER)
  I want 在 P7 共享专区按主题树 / 标签快速发现一组可复用目录、资源、案例
  So that 旧"数购车"+"主题库"两个高频入口在 zw-brain 收敛为单一主题包发现入口，不复刻旧门户

  Background:
    Given 单租户 sd-default 已初始化，7 角色码 CHECK 约束已生效
    And 集团推理平台 mock 已就绪（基线 §6 / D14；preflight 段 10 守 LLM 直连禁令）
    And TopicPackage 6 张物理表（topic_package / topic_package_item / topic_package_visibility / topic_package_review_record / topic_package_evidence / topic_package_metric_projection）已通过 `Base.metadata.create_all` 建出（基线 §9.6 不进 alembic；plan §3.1）
    And 已注入 3 个 sd-default 山东省高频专题包：`tp-yiliao-jiuzhu`（医疗救助信息）/ `tp-yibao-code`（医保码信息）/ `tp-yidi-jiuyi`（异地就医统筹区开通信息），状态均 `published`
    And Capability `topic.package.query` / `topic.package.subscribe` / `topic.package.metric.query` 已注册（audit_class 见 plan §四）
    And TopicPackage **是投影非事实源** — 不复制 catalog_entry / resource_asset / application_record 事实（plan §1.2 / §3.1）
    And 单租户假设：跨租户专题不可见的回归用例见 wave-3-protocol-tenant-national/features/multi-tenant-policy.feature

  Scenario: 正向 — 用户按主题树发现专题包并查看引用清单（旧 xlsx 行 98 收敛入口）
    Given 我以 ROLE_ORGAN_OPERATER 登录，组织在 `tp-yiliao-jiuzhu.visibility.org_snapshot` 可见范围内
    When 我打开 P7 主题导航并选择"医疗救助"主题
    Then 列表返回包含 `tp-yiliao-jiuzhu`，展示卡片含名称 / 场景说明 / 发布方 / 引用项计数 / 订阅数
    And 点开详情，看到 `topic_package_item` 引用清单分类（catalog / resource / model / application_template / case_evidence）
    And 每个引用项展示 ref_type + ref_id + 关联 canonical 对象快照（不复制 canonical 事实）
    And 审计总线记录一条 `capability_call=topic.package.query`，audit_class=read-trace

  Scenario: 正向 — 用户订阅专题包（多选加购批量申请，旧 xlsx 行 26 数购车收敛）
    Given 我在专题包 `tp-yiliao-jiuzhu` 详情页，看到 3 个 resource 引用项
    When 我多选 3 个 resource 项并点击"批量发起申请"
    Then `topic.package.subscribe` 为每个 resource 引用生成独立的 `application_record` 草稿（基线 §3.2 申请 / 交付主链路；plan §6.2 第 3-4 步）
    And 每个 `application_record.intent_snapshot` 含 `source_topic_package_id=tp-yiliao-jiuzhu`（来源专题包可追溯，plan §6.2 第 4 步）
    And 不直接授予资源使用权 — 审批 / 授权 / 交付 / 回执仍走 J1 主链路（plan §6.2 第 5 步）
    And 审计总线记录 `capability_call=topic.package.subscribe`，audit_class=approval-trace

  Scenario: 正向 — 主题导航附标签筛选 + 运营指标读面
    Given 3 个山东专题包分别带标签 `tag=民生` / `tag=营商` / `tag=应急`
    When 我用 `topic.package.query` 带 filter=`tag=民生`
    Then 返回 `tp-yiliao-jiuzhu` + `tp-yibao-code`（民生主题命中 2 条）
    And 列表附 `topic_package_metric_projection` 的运营指标（浏览 / 订阅 / 申请转化 / 异议率），从 read model 取（plan §3.1 + §6.2 第 6 步）
    And 指标 projection **不作为可写事实源**（plan §1.2 / §八 第 9 条）

  Scenario: 负向 — 组织不在可见范围内的专题包，5 消费面均不可见
    Given 我所在 `org_snapshot` 不在 `tp-yiliao-jiuzhu.visibility.org_snapshot` 允许列表
    When 我用 `topic.package.query` 查询主题包列表
    Then 返回结果不含 `tp-yiliao-jiuzhu`
    And `tenant_capability_policy` 评估输出 `allowed=false`，decision_reason 含 `org_snapshot not in visibility scope`
    And WebUI / API / CLI / MCP / A2A 5 消费面对同一查询结果一致（无差别裁决，plan §六.1）

  Scenario: 负向 — 跨租户专题包绝不可见（单租户 sd-default 假设硬保护）
    Given 测试夹具引入另一租户 `other-tenant` 的专题包 `tp-other-yiliao`
    When 我（sd-default）通过 `topic.package.query` 查询
    Then 结果不含 `tp-other-yiliao`
    And 跨租户隔离的完整回归见 wave-3-protocol-tenant-national/features/multi-tenant-policy.feature

  Scenario: 负向 — 订阅未发布（draft / submitted / offline）状态的专题包被拒
    Given 专题包 `tp-draft-demo` 状态=draft；专题包 `tp-offline-demo` 状态=offline（plan §3.3 状态机）
    When 我尝试对这两个专题包调用 `topic.package.subscribe`
    Then 调用被拒，返回 policy decision=reject，原因 `topic package not in published state`
    And 不生成 `application_record` 草稿
    And 审计总线记录 reject 事件

  Scenario: 回归 — Capability 投影到 5 消费面契约一致（R15 桥接面 / plan §〇）
    When 我导出 WebUI 路由表 / OpenAPI / CLI commands / MCP tool manifest / A2A agent card
    Then 五份导出文件中 `topic.package.query` / `topic.package.subscribe` / `topic.package.metric.query` 三个 capability slug 一致出现
    And 五消费面 input_schema 字段集合一致（含 tenant_id / topic_package_id / actor_snapshot / org_snapshot / surface / intent）
    And `export_agent_contract.py --check` 无 drift
    And 前端 UI 文案禁用 `package` / `projection` 等工程术语（基线 §11 R12；preflight 段 24）

  Scenario: 回归 — basesubject 81 表硬保护（D7 forbidden-zone / §5.6 #13）
    Then 主题包发现链路全程不读 / 不写 `dsp_basesubject` 系列 81 张独立表
    And `dsp_basesubject` 任何 schema/resource/archive/standard 内容只能作为专题素材 evidence **候选输入**，不生成新事实源（plan §1.2 / §1.5）
    And preflight 段 25 (adapter-write-ban) 守 `zw_brain/adapters/legacy/` 之外的写禁区
