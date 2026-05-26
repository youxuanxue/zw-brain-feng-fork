# Wave: 3
# Journey: Cross
# Pages: All
# Consumer-faces: All
# Roles: All
# Trace: R8, 基线 §3.3 (多级区划), §10.4 多租户深化
# Priority: P1
# Status: Draft

Feature: 多租户 / 多部门 / 多区域策略深化
  As a 平台架构师 + 客户运营
  I want 同一仓库通过策略支持多个客户（多省 / 多市），不通过代码 fork
  So that R8（反 per-tenant fork）持续硬约束

  Background:
    Given 仓库默认配置 tenant_id="sd-default"（山东省单租户）
    And Wave 0/1/2 已基于单租户充分验证主旅程
    And Wave 3 引入第二租户 yn-default（云南省）做多租户深化

  Scenario: 正向 — 第二租户上线 + 完整隔离
    When 我新增 tenant_id="yn-default"，配置 root_org_code / IAM realm
    Then 两个租户的 catalog / resource / application / audit_event 完全隔离
    And U_SD 用户在 yn-default 下检索结果为空
    And U_YN 用户在 sd-default 下检索结果为空

  Scenario: 正向 — 同一 IAM 账号在多租户持不同角色
    Given U_GLOBAL 在 sd-default 持 ROLE_ORGAN_OPERATER × 部门A
    And 在 yn-default 持 ROLE_BUSIAUDIT × 云南省大数据局
    When U_GLOBAL 登录
    Then UI 显示"租户切换器"
    And 选定租户后，role / org / 菜单按当前租户解析
    And 审计 actor_role / tenant_id 一同落库

  Scenario: 正向 — 多级区划策略（基线 §3.3 多级区划 + 跨地市）
    Given 山东省下有 济南市 / 青岛市 / 烟台市
    And catalog C_6001 owner_org_code=济南市X部门
    When 青岛市 ROLE_ORGAN_OPERATER 检索"户籍"
    Then 是否可见 C_6001 由跨地市策略决定（默认：同省可见、跨省不可见）
    And 策略可在 B1.2 配置（区域可见性矩阵 + AI 草稿 → 确认）

  Scenario: 正向 — 部门策略（跨部门数据可见性）
    Given 部门"公安"与"民政"互为对方的潜在使用方
    When 配置部门可见性策略 "公安数据对民政默认可见但需有条件审批"
    Then J1 申请流转自动选取对应的有条件分支
    And 配置变更经"草稿 → 预览 → 确认"

  Scenario: 负向 — 不能通过代码 fork 实现租户差异（R8）
    Then 仓库 grep 不出现 if tenant_id=="sd-default" 这类**业务逻辑分叉**
    And 任意租户差异通过配置 / 多租户策略 / 外部能力包承接
    And preflight 段（待接入）反向探测 hard-coded tenant fork

  Scenario: 负向 — 跨租户 actor 不能写另一租户
    Given U_GLOBAL 当前 session.tenant_id=sd-default
    When U_GLOBAL 试图通过 API 直接 POST 数据到 tenant=yn-default
    Then 拒绝
    And 审计 reject + reason="cross_tenant_write_attempt"

  Scenario: 回归 — sd-default 在多租户引入后行为不变
    Then 单租户 sd-default 主旅程的所有 Wave 0/1/2 用例**仍 100% 通过**
    And 多租户引入是叠加而非破坏（确定性自动化运营和运维反碎片化）

  Scenario: 回归 — 通用隔离对子能力的传递性覆盖（接收从 Wave 0-2 移除的 specific 跨租户场景）
    # 本 Scenario 是 PR #71 review R-003 的对接点：Wave 0-2 中 4 个 specific 跨租户场景
    # (j1-resource-discovery / p7-shared-zones / adapter-yibiaotong / engine-recommend-prefer)
    # 在单租户哲学下移除并 sign-post 推到 Wave 3，本 Scenario 显式验证通用隔离对每个子能力都传递生效。
    Given sd-default + yn-default 两租户已并存，各自含完整 catalog / resource / application 种子
    And U_SD 用户 session.tenant_id=sd-default；U_YN 用户 session.tenant_id=yn-default

    When U_SD 在 P2 资源发现页检索（命中 yn-default 的关键词）
    Then 结果集不含 yn-default 的 catalog（基础隔离传递到资源发现）

    When U_SD 打开 P7 共享专区
    Then 不显示 yn-default 的专题包（隔离传递到专题聚合层）

    When 一表通 adapter 返回的字段含 yn-default 租户的业务编号
    Then zw-brain adapter 拒绝预填到 sd-default 的申请草稿（隔离传递到 adapter 层）

    When U_SD 触发智能推荐引擎，历史样本池仅来自 sd-default
    Then 推荐结果不含 yn-default 的资源（隔离传递到推荐层）

    And 任意一项失败 → 该子能力存在跨租户泄露 → 阻塞 multi-tenant 上线
    And 审计 capability_call 均带正确 tenant_id 字段，不混租户
