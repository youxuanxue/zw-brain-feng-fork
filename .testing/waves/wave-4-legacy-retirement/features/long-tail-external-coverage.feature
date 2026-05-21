# Wave: 4
# Journey: Cross
# Pages: B1.2
# Consumer-faces: A2A | MCP
# Roles: ROLE_SYSTEM
# Trace: R7 / R15, 基线 §10.5 退役判据 + §5.6 "不进 IA" 13 项处置
# Priority: P1
# Status: Draft

Feature: 长尾需求由外部能力包覆盖
  As a 客户成功
  I want 旧 18 项一级目录中"不复造"+ "占位延后"项都有处置
  So that 不留"长尾在 zw-brain 内重造"的暗债

  Background:
    Given 基线 §5.6 列出"不进 IA 13 项"
    And 基线 §5.2.1 列出 "占位延后 2 项（国家通道）"

  Scenario: 正向 — 不进 IA 13 项处置完成
    Then 13 项中每一项都有以下处置之一：
      | 处置                                    | 项数 |
      | 集团外部依赖（监控 / 数据治理 / 数据安全 / 消息）   | 4   |
      | 外部能力包注册（如有客户场景需要）              | 0-N |
      | 业务方明确"不需要"（备案 sign-off）           | 剩余 |
    And 没有任何一项滞留在 "暗债待处理"

  Scenario: 正向 — 占位延后 2 项（国家通道）
    Then "国家目录治理" + "数据直达" 二项要么进入 Wave 3 实施，要么明示推后 Wave 5+
    And 不留暗示性 "TODO"

  Scenario: 正向 — 外部能力包注册数量与客户场景匹配
    Given 客户经过 90 天使用
    When 我盘点客户运营记录
    Then 任意客户提出的"想要 X"需求都映射到"已有内建" / "外部 Agent 已注册" / "排期立项" 三类
    And 没有"待评估"的悬空项

  Scenario: 负向 — 长尾不能反过来侵蚀主仓
    Then 仓库 zw_brain/ 下不出现以"补丁"形式承接长尾的代码
    And 任何"长尾代码" 必须在外部能力包（zw_brain/skill_registration/registered/ 注册指针外部 SKill）

  Scenario: 回归 — R7 持续硬约束
    Then 仓库中只有高频核心 + 底座
    And 任何新增的"项目特化能力" 走外部 Agent 路径
    And preflight 段对此做反向探测（如 zw_brain/skills/ 下增长率高于内核增长率触发告警）
