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

- **2 旅程 + 1 后台支撑面**：J1 找数→用数 / J2 挂数→维数 / B1 看全局→处异常（B1.1 合规运营 / B1.2 接入扩展中心）。详见 [docs/approved/zw-brain-architecture.md §5.1](../approved/zw-brain-architecture.md)
- **7 角色码 + tag_lead_dept 标签**（沿用旧平台 ROLE_* 码）。详见 [docs/approved/zw-brain-roles.md](../approved/zw-brain-roles.md)
- **schema 全新创建（drop_all + create_all）**：不维护 alembic 迁移链；新功能 drop & recreate 替代。详见 [架构基线 §9.6](../approved/zw-brain-architecture.md)
- **大屏 / 国家通道独立子旅程 / 一表通预填**：本期不实施；外部依赖或延后 Wave 3

## 冲突仲裁

- 跨专题事实冲突时，[legacy-repository-reconstruction-priorities-v1.md](legacy-repository-reconstruction-priorities-v1.md) 是仲裁源
- 涉及 IAF IAM / 租户 / 角色 / 组织时，[dsp-bsp-manage-governance-reconstruction-plan-v1.md](dsp-bsp-manage-governance-reconstruction-plan-v1.md) 是仲裁源
- 涉及业务流程 / 状态机 / 用户角色定义时，[docs/approved/zw-brain-architecture.md](../approved/zw-brain-architecture.md) + [zw-brain-roles.md](../approved/zw-brain-roles.md) 是仲裁源（高于本目录）
