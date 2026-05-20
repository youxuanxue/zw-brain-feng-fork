# docs/reconstructs 旧仓库迁移映射执行级文档（v4.1 视角）

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
| 合规运营 + 安全 + 标准 + 指标 + 监控（P6） | [compliance-ops-adapters-reconstruction-plan-v1.md](compliance-ops-adapters-reconstruction-plan-v1.md) |
| 旧样例数据 → zw-brain 一键导入映射 | [legacy-import-mapping-v1.md](legacy-import-mapping-v1.md) |

## v4.1 视角下的状态

| 文件 | v4.1 状态 | 说明 |
|---|---|---|
| legacy-repository-reconstruction-priorities-v1.md | **保留权威** | 全局优先级总览 |
| dsp-catalog3-metadata3-reconstruction-plan-v1.md | **保留**（D23 retrofit 注脚已加） | catalog/metadata 仍是 J2 挂数→维数 的核心 |
| dsp-exchange-reconstruction-plan-v1.md | **保留**（D23 retrofit 注脚已加） | require/exchange 是 J1 找数→用数 的核心 |
| dsp-dataservice-reconstruction-plan-v1.md | **保留** | dataservice 是 J1 交付通道 |
| dsp-data-connect-cascade-reconstruction-plan-v1.md | **保留**（D23 retrofit 注脚已加） | 国家直达 = Wave 3 延后实施（业务方反馈 #13） |
| dsp-objection-handling-reconstruction-plan-v1.md | **保留** | 异议闭环是 J1 子流程 |
| dsp-sharezone-topic-package-reconstruction-plan-v1.md | **保留** | 共享专区 P7 = K11 必保留（D9） |
| dsp-bsp-manage-governance-reconstruction-plan-v1.md | **保留** | IAF IAM 接入边界；本期 dev-iam-bypass 兜底 |
| compliance-ops-adapters-reconstruction-plan-v1.md | **保留** | B1.1 合规运营后台支撑面（v4.1 反转后归属） |
| legacy-import-mapping-v1.md | **保留**（D23 retrofit 注脚已加） | 一次性迁移映射；用 SQLAlchemy `create_all` 替代 alembic（R15） |

## v4.1 反转对本目录的影响

- **K12 大屏退役（R17）**：原 [compliance-ops-adapters](compliance-ops-adapters-reconstruction-plan-v1.md) §"Dashboard 只读隔离"段落中关于独立大屏的设计**已退役**；合规运营改为 B1.1 后台支撑面（普通用户主导航不可见）
- **alembic 删除（R15）**：[legacy-import-mapping-v1.md](legacy-import-mapping-v1.md) 中所有"alembic 迁移"提及作历史快照保留；实际执行用 SQLAlchemy `Base.metadata.create_all()`（详见 [`zw_brain/shared/migrate.py`](../../zw_brain/shared/migrate.py)）
- **2 旅程 + 后台支撑面（R16 pending sign-off）**：本目录各专题文档仍按"3 旅程 J1/J2/J3"措辞（GATE-1.1 sign-off 版本）；待业务方下次 review 二次 sign-off 后再统一收敛

## 单一事实来源原则与漂移防御

- 跨专题事实冲突时，**legacy-repository-reconstruction-priorities-v1.md** 是仲裁源
- 涉及 IAF IAM / 租户 / 角色 / 组织时，**dsp-bsp-manage-governance-reconstruction-plan-v1.md** 是仲裁源
- 涉及业务流程 / 状态机 / 用户角色定义时，**[docs/approved/zw-brain-architecture.md](../approved/zw-brain-architecture.md) + [zw-brain-roles.md](../approved/zw-brain-roles.md) + [zw-brain-architecture.md](../approved/zw-brain-architecture.md)** 是仲裁源（高于本目录）
