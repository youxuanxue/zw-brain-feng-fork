# docs/reconstructs 旧仓库迁移映射执行级文档

> 本目录是**旧平台代码仓库** → zw-brain 新基线的**执行级映射文档**。
> 与 [`docs/approved/`](../approved/README.md) 的关系：approved/ = 架构基线 + 设计原则；reconstructs/ = 旧仓库**专题级**字段映射、不做清单、能力边界。
> 全局导航请先读 [`legacy-repository-reconstruction-priorities-v1.md`](legacy-repository-reconstruction-priorities-v1.md)（旧仓库去向总览）。

## 单一事实来源原则

| 主题 | 单一事实来源 |
|---|---|
| 全局重构优先级 / 进入条件 | [legacy-repository-reconstruction-priorities-v1.md](legacy-repository-reconstruction-priorities-v1.md) |
| BSP / manage / ucenter 治理底座 | [dsp-bsp-manage-governance-reconstruction-plan-v1.md](dsp-bsp-manage-governance-reconstruction-plan-v1.md) |
| catalog3 + metadata3（目录元数据） | [dsp-catalog3-metadata3-reconstruction-plan-v1.md](dsp-catalog3-metadata3-reconstruction-plan-v1.md) |
| dataservice（数据服务/网关） | [dsp-dataservice-reconstruction-plan-v1.md](dsp-dataservice-reconstruction-plan-v1.md) |
| require + supply + exchange（需求/申请/交换） | [dsp-exchange-reconstruction-plan-v1.md](dsp-exchange-reconstruction-plan-v1.md) |
| data-connect + cascade（国家直达/级联） | [dsp-data-connect-cascade-reconstruction-plan-v1.md](dsp-data-connect-cascade-reconstruction-plan-v1.md) |
| objection-handling（异议闭环） | [dsp-objection-handling-reconstruction-plan-v1.md](dsp-objection-handling-reconstruction-plan-v1.md) |
| sharezone + example + basesubject（共享专区/专题包） | [dsp-sharezone-topic-package-reconstruction-plan-v1.md](dsp-sharezone-topic-package-reconstruction-plan-v1.md) |
| 合规运营 + 安全 + 标准 + 指标 + 监控（B1.1） | [compliance-ops-adapters-reconstruction-plan-v1.md](compliance-ops-adapters-reconstruction-plan-v1.md) |
| 旧样例数据 → zw-brain 一键导入映射 | [legacy-import-mapping-v1.md](legacy-import-mapping-v1.md) |

## 当前实施口径

- **2 旅程 + 1 后台支撑面**：J1 找数→用数 / J2 挂数→维数 / B1 看全局→处异常（B1.1 合规运营 / B1.2 接入扩展中心——**已随 D52(2026-06-05) 解体为后台四独立模块**：查审计/外部系统/流程表单/身份治理，见 [docs/decisions/integration-admin-governance-axis-refactor.md](../decisions/integration-admin-governance-axis-refactor.md)）。详见 [docs/approved/zw-brain-architecture.md §5.1](../approved/zw-brain-architecture.md)
- **大屏 / 指挥中心 / 演示页面不进产品形态**（基线 §1.3）；如未来有客户重启此类需求，按 Wave 3+ 独立产品立项
- **7 角色码 + tag_lead_dept 标签**（沿用旧平台 ROLE_* 码，基线 §11 R10/R11）。详见 [docs/approved/zw-brain-roles.md](../approved/zw-brain-roles.md)
- **schema 全新创建（drop_all + create_all）**：不维护 alembic 迁移链；新功能 drop & recreate 替代。详见 [架构基线 §9.6](../approved/zw-brain-architecture.md)
- **默认租户 `sd-default`**（单租户单省山东）：不启用 `tenant_mode=multi`（基线 §8.2 + AgentRuntime 接入边界）
- **R14 三引擎**（审批流可视化 + 表单 schema 化 + 智能推荐前置）：Wave 2 必达；本目录任何业务专题文档涉及"项目级流程 / 表单 / 推荐"定制时，统一回指三引擎，不再各文档独立定义
- **R15 AgentRuntime 唯一桥接面**：外部 Agent 通过 `AGENT.yaml` 接入，协议规范以 `docs/agent-runtime/*` 为单一事实源
- **国家通道（直达 + 级联）/ 一表通预填**：本期不实施；前者延后 Wave 3，后者降级为可选 adapter

## 冲突仲裁

| 优先级 | 仲裁源 | 适用情境 |
|---|---|---|
| 1（最高） | [docs/approved/zw-brain-architecture.md](../approved/zw-brain-architecture.md) | 架构主张 / 路线图 / R-编号 / 产品形态 / 业务流程 / 状态机 |
| 2 | [docs/approved/zw-brain-roles.md](../approved/zw-brain-roles.md) | 7 角色码 / tag_lead_dept / 角色与方向解耦 |
| 3 | [docs/approved/zw-brain-data-model.md](../approved/zw-brain-data-model.md) | 概念层聚合 / Wave 0-2 物理表集 / canonical schema 边界 |
| 4 | [legacy-repository-reconstruction-priorities-v1.md](legacy-repository-reconstruction-priorities-v1.md) | 旧仓库去向总览 / 跨专题事实冲突 |
| 5 | [dsp-bsp-manage-governance-reconstruction-plan-v1.md](dsp-bsp-manage-governance-reconstruction-plan-v1.md) | IAF IAM / 租户 / 角色 / 组织治理边界 |
| 6（外部规范） | [docs/agent-runtime/*](../agent-runtime/) | AgentRuntime `anp-agent/v1.2` 协议规范、Embedded SDK / Standalone HTTP 形态 |
