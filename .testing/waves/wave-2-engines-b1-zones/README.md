---
wave: 2
title: 三引擎 (R14) + B1 合规底线 + 共享专区 + 一表通预填
driven_by: docs/approved/zw-brain-architecture.md §10.3
---

# Wave 2 — 三引擎 + B1 合规底线 + 共享专区 P7

## 目标

**R14 兑现**：项目级个性化不再改代码 / 改库，全部走配置 + AI 草稿生成。

- **审批流可视化引擎**（业务反馈 #4）：替代硬编码状态机；节点 + 选人规则 + 条件分支可配置
- **表单 schema 化引擎**（业务反馈 #17）：字段、校验、布局 schema 化
- **智能推荐前置引擎**（业务反馈 #6）：相似目录推荐 → 推荐失败再转人工需求登记
- **B1.1 合规与运营**：异常 + 抽查 + 督查三段
- **B1.2 接入扩展中心**：能力包审核注册 + trust_level 升降级 + §8.4 流水线 UI 化
- **共享专区 P7**：主题化聚合与订阅入口
- **一表通可选预填 adapter**：基层补差任务出现时才挂载

## Scope

| Feature | 类型 | 优先级 | 主要角色 |
|---|---|---|---|
| engine-approval-flow | 三引擎 | P1 | ROLE_SYSTEM + BUSIAUDIT |
| engine-form-schema | 三引擎 | P1 | ROLE_SYSTEM + BUSIAUDIT |
| engine-recommend-prefer | 三引擎 | P1 | ROLE_ORGAN_OPERATER |
| engine-ai-config-draft | 三引擎 共用 | P1 | ROLE_SYSTEM + BUSIAUDIT |
| b1-1-compliance-audit | B1.1 | P1 | BUSIAUDIT + SECURITY_AUDIT |
| b1-1-anomaly-detection | B1.1 | P1 | BUSIAUDIT |
| b1-2-package-registration | B1.2 | P1 | ROLE_SYSTEM |
| b1-2-trust-level-upgrade | B1.2 | P1 | ROLE_SYSTEM |
| p7-shared-zones | P7 | P1 | All users |
| adapter-yibiaotong | adapter | P2 | ROLE_ORGAN_OPERATER 基层 |

## 完成判据

- 项目级流程 / 表单 / 推荐通过配置完成，不改代码（鞍山 / 四川 / 荆州案例）
- 三引擎中 AI 角色严格"生成草稿 → 管理员确认入库"
- B1.1 / B1.2 提供给管理员/审计员，**不进**普通用户主导航
- P7 共享专区可订阅
- 一表通仅在基层补差任务存在时作为可选预填 adapter（不默认）

## 不在 Wave 2 内

- MCP / A2A 生产硬化（Wave 3）
- 国家通道独立子旅程（Wave 3）
- 多租户深化（Wave 3）

## Trace 索引

- 基线 §10.3 Wave 2 必做清单 + R14
- 基线 §5.4.4 P3 / P4 / B1.1 / B1.2 AI 反约束
- 基线 §8.4 注册流水线 UI 化
- D24 / D27 业务反馈 #4 / #6 / #17
- 旧 xlsx 行 [99..107] 运行管理 + [108..118] 应用中心/案例/消息
