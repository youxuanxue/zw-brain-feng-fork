---
doc_id: testing-cross-cutting-legacy-mapping
status: navigation
driven_by:
  - old/共享平台V5.0.2-冒烟.xlsx
  - docs/approved/zw-brain-architecture.md §5.6 "不进 IA 13 项" + §5.2.1 收敛逻辑
---

# 旧平台 128 冒烟用例 → 新平台 wave/feature 映射

> **目的**：保证 zw-brain 重构后旧平台真实用过的业务路径**要么有映射**，要么有明示"不复刻"理由（基线 §5.6）。
> 旧文件：`old/共享平台V5.0.2-冒烟.xlsx`（**xlsx 原始 131 数据行**，header 在 xlsx 行 1，数据行从 xlsx 行 2 起）。
>
> **128 distinct 用例的来源**：本 mapping 表共 ~116 行表项，其中 3 行是多 case 合并行（融合服务 65/70/63/68/66/67/69/64 一行涵盖 8 case；应用中心 121/120/122/123 一行涵盖 4 case；消息中心 36/37/38b 一行涵盖 3 case）= 116 - 3 + 8 + 4 + 3 = **128 distinct 用例处置**。
>
> **行号体系警告（R-002 / PR #71 review 引入）**：mapping doc 表内的 row 编号是**人工维护**的，主体与 xlsx 数据行 1-based 对齐，但已知至少 4 处局部漂移（mapping row 17 ≠ xlsx data row 17；mapping row 19 错位；mapping row 53/54 大漂移）。`.feature` Trace 中的"旧 xlsx 行 N"采用 **xlsx 数据行 1-based**（数据行 N = xlsx 行 N+1）。当 .feature Trace 与本表行号不一致时，**以"用例名"字面值为对照锚点**，不要按行号数字直接索引。后续 PR 应统一校准两套体系（目前列入 follow-up）。

## 一、统计

> **2026-05-27 D31/D32 修订**：业务方 PR #129 sign-off 触发 24 条 ❌ → ⏸（A 类 20 含合并行 8 case + D 类 4 直接行 — 行 1/2/5/6/7/22/23/24/26/63-70/71/74/79/80/98/100）。⏸ 类细分两小类：原"国家通道 P2 延后"（12 条）+ "业务方 PR #129 复活按既存 reconstruction plan 落地"（24 条；A 类 → `docs/reconstructs/dsp-dataservice-reconstruction-plan-v1.md`；D 类 → `docs/reconstructs/dsp-sharezone-topic-package-reconstruction-plan-v1.md`）。

| 类别 | 行数 | 占比 | 备注 |
|---|---|---|---|
| ✅ 映射到新 .feature（J1/J2/B1/Cross） | 60 | 47% | 不变 |
| ❌ 不复刻（接受类） | 26 | 20% | 50 → 26（24 条业务方复活转 ⏸）|
| ⏸️ 占位延后 / 按 plan 落地 | 36 | 28% | 12 原国家通道 + 24 D31/D32 复活（A→dsp-dataservice plan / D→sharezone-topic plan）|
| ⚠️ 外部依赖（集团运维监控 / 消息中心 / IAM） | 6 | 5% | 不变 |

合计 **128 distinct 用例处置**（见本节顶部说明：表 116 行 - 3 合并行 + 15 合并 case 展开 = 128），**全部**有处置（无暗债）。

## 二、详细映射

> 表头：行号 / 系统 / 模块 / 二级模块 / 用例名 / 优先级 / 处置 / 映射

### 系统：门户（32 行 → J1 主链路）

| 行 | 用例名 | 优先级 | 处置 | 映射 |
|---|---|---|---|---|
|1 | 代理服务资源申请暂存 | 最高 | ⏸ D32 按 dsp-dataservice-reconstruction-plan-v1.md 落地（代理服务不进 IA，§5.6 #1 #11） | — |
|2 | 代理服务资源申请-有期限 | 最高 | ⏸ D32 按 dsp-dataservice-reconstruction-plan-v1.md 落地（同上） | — |
| 3 | 库表资源申请暂存 | 最高 | ✅ 库表是 J1 主路径 | wave-0 j1-application-draft (Scenario: 正向 — 暂存草稿) |
| 4 | 库表资源申请-有期限 | 最高 | ✅ | wave-0 j1-application-draft (Scenario: 正向 — 提交申请) |
|5 | 融合服务资源申请-有期限 | 最高 | ⏸ D32 按 dsp-dataservice-reconstruction-plan-v1.md 落地（融合服务不进 IA（§5.6 #12） | — |
|6 | 通用服务资源申请暂存 | 中 | ⏸ D32 按 dsp-dataservice-reconstruction-plan-v1.md 落地（通用服务不进 IA（§5.6 #12） | — |
|7 | 通用服务资源申请-有期限 | 中 | ⏸ D32 按 dsp-dataservice-reconstruction-plan-v1.md 落地（同上） | — |
| 8 | 文件夹资源申请暂存 | 最高 | ✅ 文件夹 = data_resource_file 之一 | wave-1 j2-resource-mount (file 物化) + wave-0 j1-application-draft |
| 9 | 文件夹资源申请-有期限 | 最高 | ✅ | 同上 |
| 10 | 文件资源申请暂存 | 最高 | ✅ data_resource_file | 同上 |
| 11 | 文件资源申请-有期限 | 最高 | ✅ | 同上 |
| 12 | 查看首页 | 高 | ✅ P1 工作台 | wave-0 j1-resource-discovery (背景：首页) + 后续 wave-2 b1-1-* （管理员首页） |
| 13 | 查看数据目录 | 高 | ✅ P2 目录树 | wave-0 j1-resource-discovery |
| 14 | 查看数据资源 | 高 | ✅ P2 资源详情 | wave-0 j1-resource-discovery (Scenario: 资源详情进入申请页) |
| 15 | 查看知识中心页面 | 高 | ❌ 知识中心合并入 B1.1（§5.2.1） | wave-2 b1-1-compliance-audit (合规知识库段) |
| 17 | 典型应用案例列表查看 | 高 | ❌ 应用案例不复造（§5.6 #11 #12 业务反馈） | — |
| 18 | 典型应用案例申请 | 中 | ❌ 同上 | — |
| 19 | 访问各个子系统 | 高 | ❌ 多 SPA 拼接是反模式（§3.5 #6），收敛单一 WebUI | wave-0 infra-contract-projection (单一 WebUI 验证) |
| 20 | 访问用户工作台 | 高 | ✅ P1 工作台 | wave-0 j1-resource-discovery + wave-0 j1-approval-unconditional (Scenario: 工作台排序) |
| 21 | 访问用户中心 | 高 | ⚠️ IAM 外部依赖（含个人信息页） | wave-0 infra-iam-session |
|22 | 融合服务列表查看 | 中 | ⏸ D32 按 dsp-dataservice-reconstruction-plan-v1.md 落地（§5.6 #12） | — |
|23 | 通用服务列表查看 | 中 | ⏸ D32 按 dsp-dataservice-reconstruction-plan-v1.md 落地（同上） | — |
|24 | 服务申请 | 高 | ⏸ D32 按 dsp-dataservice-reconstruction-plan-v1.md 落地（"服务"概念合并到 resource.api 物化（§3.3 / §5.6） | wave-1 j2-resource-mount (api 物化) |
| 25 | 首页 | 高 | ✅ 同行 12 | wave-0 j1-resource-discovery |
|26 | 数购车申请 | 最高 | ⏸ D32.a 按 dsp-sharezone-topic-package-reconstruction-plan-v1.md 落地（Wave 2 P7）（"数购车" 是应用中心子能力（§5.6 #11） | — |
| 27 | 应用列表查看 | 高 | ❌ §5.6 #11 应用中心不进 IA | — |
| 28 | 用户登录 | 高 | ⚠️ IAM 外部依赖 | wave-0 infra-iam-session |
| 29 | 用户退出 | 高 | ⚠️ 同上 | wave-0 infra-iam-session (session 过期 + 重新登录) |
| 30 | 政务信息资源分布情况 | 中 | ❌ "数字化运营" 大屏不复造（§1.3 / §5.6） | — |
| 31 | 申请审核情况 | 中 | ❌ 同上 | — |
| 32a | 资源申请授权情况 | 中 | ❌ 同上 | — |
| 32b | 资源统计 | 中 | ❌ 同上 | — |

### 系统：目录管理（21 行 → J2 主链路 + 国家通道延后）

| 行 | 用例名 | 优先级 | 处置 | 映射 |
|---|---|---|---|---|
| 50 | 目录首页统计信息查看 | 高 | ✅ P5 概览 | wave-1 j2-online-catalog-compile (Background) |
| 34 | 反向编目资源提供方搜索 | 最高 | ✅ J2 反向编目 | wave-1 j2-online-catalog-compile (Scenario: 反向编目) |
| 51 | 目录在线编制提交 | 高 | ✅ J2 主线 | wave-1 j2-online-catalog-compile |
| 41 | 导入目录 | 高 | ✅ J2 批量导入 | wave-1 j2-online-catalog-compile (基线 §5.6 提及) |
| 45 | 目录编辑 | 高 | ✅ J2 维护 | wave-1 j2-online-catalog-compile + wave-1 j2-department-review (round 计数) |
| 46 | 目录导出 | 高 | ✅ J2 工具 | wave-1 j2-platform-publish (导出能力的轻量验证) |
| 47 | 目录发布 | 高 | ✅ J2 平台发布主线 | wave-1 j2-platform-publish |
| 48 | 目录批量发布 | 高 | ✅ J2 批量 | wave-1 j2-department-review (Scenario: 同一会话内批量审核) |
| 49 | 目录删除 | 高 | ✅ J2 下线（不删，5 下线） | wave-1 j2-platform-publish (Scenario: 下线) |
| 39 | 待审核目录批量审核 | 高 | ✅ J2 部门审 + 平台复核 | wave-1 j2-department-review |
| 40 | 待审核目录审核 | 高 | ✅ | wave-1 j2-department-review |
| 42 | 地方基本要素导入 | 高 | ⏸️ 国家通道延后（§10.4 Wave 3） | wave-3 national-ext-elements |
| 43 | 国家基本要素导入--按目录维度 | 高 | ⏸️ | 同上 |
| 44 | 国家基本要素导入--按信息项维度 | 高 | ⏸️ | 同上 |
| 38a | 代认领基本要素导入 | 高 | ⏸️ | 同上 |
| 35a | 基本要素下发、代认领下发 | 最高 | ⏸️ | 同上 |
| 35b | 基本要素认领 | 最高 | ⏸️ | 同上 |
| 35c | 国家目录治理扩展要素编制 | 最高 | ⏸️ | wave-3 national-ext-elements |
| 35d | 业务部门扩展要素目录审核 | 最高 | ⏸️ | 同上 |
| 35e | 主管部门扩展要素目录审核 | 最高 | ⏸️ | 同上 |
| 33 | 目录质量检测 | 最高 | ❌ 数据治理不进本平台（§3.4 集团数据治理中心） | — |

### 系统：资源管理（12 行 → J2 主链路）

| 行 | 用例名 | 优先级 | 处置 | 映射 |
|---|---|---|---|---|
| 54 | 概览查看 | 中 | ✅ P5 概览 | wave-1 j2-online-catalog-compile (Background) |
| 53 | 元数据采集 | 最高 | ❌ 数据治理不进本平台 / 部分作为 J2 反向编目 | wave-1 j2-online-catalog-compile (Scenario: 反向编目) |
| 52 | 库表资源注册-视图 | 最高 | ✅ data_resource_table | wave-1 j2-resource-mount (table 物化) |
| 56 | 注册库表资源 | 高 | ✅ 同上 | 同上 |
| 57 | 注册链接资源 | 高 | ✅ data_resource_api / file 之一 | wave-1 j2-resource-mount |
| 58a | 注册文件资源 | 高 | ✅ data_resource_file | wave-1 j2-resource-mount (file 物化) |
| 58b | 注册文件夹资源 | 高 | ✅ 同上 | 同上 |
| 62 | 资源提交审核 | 高 | ✅ J2 部门审 | wave-1 j2-department-review (Scenario: 资源审核同步联动) |
| 60 | 资源发布审核 | 高 | ✅ J2 平台复核 | wave-1 j2-platform-publish |
| 59 | 资源发布 | 高 | ✅ J2 主线 | wave-1 j2-platform-publish |
| 61 | 资源批量发布 | 高 | ✅ | wave-1 j2-department-review (批量) + wave-1 j2-platform-publish |
| 55 | 目录物化 | 高 | ✅ 3 物化形式（table/file/api） | wave-1 j2-resource-mount |

### 系统：融合服务（8 行 → 不复造）

| 行 | 用例名 | 优先级 | 处置 |
|---|---|---|---|
| 65 / 70 / 63 / 68 / 66 / 67 / 69 / 64 | 创建代理服务 / 通用服务 / 简易融合服务 / 服务审核 / 服务发布等 | 最高 / 高 | ⏸ D32 按 dsp-dataservice-reconstruction-plan-v1.md 落地（§二.1 mgmt→J1+J2+B1.1；§3.5 resource.api.* + ops.gateway.* + ops.service.* Capability） |

### 系统：申请审核（8 行 → J1 主链路变更与续期）

| 行 | 用例名 | 优先级 | 处置 | 映射 |
|---|---|---|---|---|
|71 | 代理服务申请变更 | 最高 | ⏸ D32 按 dsp-dataservice-reconstruction-plan-v1.md 落地（代理服务不进 IA） | — |
| 72 | 库表申请变更 | 最高 | ✅ 申请变更 = J1 申请回退 → 重新提交 | wave-0 j1-approval-conditional (Scenario: 第一步驳回 + 申请人补件) |
| 73 | 库表申请续期 | 最高 | ✅ 申请续期 = J1 申请新一轮 | wave-0 j1-application-draft (新轮 round 计数) |
|74 | 通用服务申请变更 | 最高 | ⏸ D32 按 dsp-dataservice-reconstruction-plan-v1.md 落地（通用服务不进 IA） | — |
| 75 | 文件夹申请变更 | 最高 | ✅ | wave-0 j1-approval-conditional |
| 76 | 文件夹申请续期 | 最高 | ✅ | wave-0 j1-application-draft (续期) |
| 77 | 文件申请变更 | 最高 | ✅ | 同上 |
| 78 | 文件申请续期 | 最高 | ✅ | 同上 |

### 系统：申请授权（9 行 → J1 审批）

| 行 | 用例名 | 优先级 | 处置 | 映射 |
|---|---|---|---|---|
| 87 | 我的申请查看 | 中 | ✅ P3 跟踪 | wave-0 j1-application-draft + wave-0 j1-approval-* |
|79 | 待审核融合服务审核 | 高 | ⏸ D32 按 dsp-dataservice-reconstruction-plan-v1.md 落地（融合服务不进 IA） | — |
|80 | 待审核融合服务受理 | 高 | ⏸ D32 按 dsp-dataservice-reconstruction-plan-v1.md 落地（同上） | — |
| 81 | 待审核资源驳回 | 最高 | ✅ 审批驳回 | wave-0 j1-approval-conditional (Scenario: 部门驳回) |
| 82 | 待审核资源驳回补正 | 最高 | ✅ 驳回 + 补正 | 同上 |
| 83 | 待审核资源审核 | 最高 | ✅ J1 审批主线 | wave-0 j1-approval-unconditional / wave-0 j1-approval-conditional |
| 84 | 待审核资源受理 | 最高 | ✅ 同上 | 同上 |
| 85 | 待审核资源受理并审核 | 高 | ✅ 同上 | 同上 |
| 86 | 申请变更待审核资源审核 | 高 | ✅ 申请变更复用主审批流 | wave-0 j1-approval-conditional |

### 系统：供需系统（13 行 → 供需对接子流程）

| 行 | 用例名 | 优先级 | 处置 | 映射 |
|---|---|---|---|---|
| 89 | 业务需求梳理关联资源 | 最高 | ✅ J1 供需 | wave-1 j1-supply-demand-meta-merge |
| 93 | 原始需求梳理 | 最高 | ✅ | 同上 |
| 90 | 导出原始需求清单 | 最高 | ✅ 导出能力 | 同上 (Background 衍生) |
| 91 | 国家需求处理 | 最高 | ⏸️ 国家通道延后 | wave-3 national-direct (Scenario: 国家通道独立子旅程入口) |
| 92 | 数据需求汇总状态 | 最高 | ✅ | wave-1 j1-supply-demand-meta-merge |
| 88 | 数据需求清单详情认领 | 最高 | ✅ | 同上 |
| 96 | 评价需求详情查看 | 高 | ✅ 供需评价 = data_objection_evaluate 类 | wave-1 j1-supply-demand-meta-merge (Scenario: 最后一步评价) |
| 94 | 待启动任务进行启动 | 高 | ✅ | 同上 (Scenario: 工作任务派发) |
| 95 | 发布基础/主体需求梳理任务 | 高 | ✅ | 同上 |
| 97 | 任务查看 | 高 | ✅ | 同上 |
|98 | 事项/主题库查看 | 高 | ⏸ D32.a 按 dsp-sharezone-topic-package-reconstruction-plan-v1.md 落地（Wave 2 P7）（"主题库" 不复造（§5.6 #11） | — |
| 99 | 已办任务详情查看 | 高 | ✅ P1 工作台已办 | wave-0 j1-resource-discovery (P1) |
|100 | 主题库信息提交 | 高 | ⏸ D32.a 按 dsp-sharezone-topic-package-reconstruction-plan-v1.md 落地（Wave 2 P7）（§5.6 #11） | — |

### 系统：数据交换（5 行 → J1 交付 P4）

| 行 | 用例名 | 优先级 | 处置 | 映射 |
|---|---|---|---|---|
| 101 | 库表订阅 | 高 | ✅ P7 + 库表订阅是交换形式 | wave-2 p7-shared-zones + wave-0 j1-credential-issue |
| 102 | 库表订阅任务-发布 | 高 | ✅ | 同上 |
| 103 | 库表直接交换任务-发布 | 高 | ✅ P4 交付 | wave-0 j1-credential-issue + wave-0 j1-api-call-monitoring |
| 104 | 库表直接交换任务-新增 | 高 | ✅ | 同上 |
| 105 | 文件下载 | 高 | ✅ data_resource_file 调用 | wave-0 j1-api-call-monitoring (文件物化变体) |

### 系统：案例系统（1 行 → 不复造）

| 行 | 用例名 | 优先级 | 处置 |
|---|---|---|---|
| 106 | 案例提出页 | 最高 | ❌ 应用案例不进 IA（§5.6 #11） |

### 系统：运行管理（8 行 → B1.1 / B1.2 后台）

| 行 | 用例名 | 优先级 | 处置 | 映射 |
|---|---|---|---|---|
| 107 | 栏目内容新增 pptx | 最高 | ❌ "栏目管理" 是旧门户运营，新平台不重做 | — |
| 108 | 栏目发布 | 最高 | ❌ 同上 | — |
| 109 | 栏目管理列表查看 | 高 | ❌ 同上 | — |
| 110 | 栏目新增 | 最高 | ❌ 同上 | — |
| 111 | 新增应用事项 | 最高 | ❌ §5.6 #11 | — |
| 112 | 责任清单关联 | 最高 | ✅ 类比 J2 资源挂接 metadata | wave-1 j2-online-catalog-compile (责任部门字段) |
| 113 | 责任清单新增 | 最高 | ✅ | 同上 |
| 114 | 资源申请督办 | 高 | ✅ B1.1 督查段 | wave-2 b1-1-compliance-audit (Scenario: 督查段) |

### 系统：运行监控（3 行 → 外部依赖）

| 行 | 用例名 | 优先级 | 处置 | 映射 |
|---|---|---|---|---|
| 117 | 操作审计概览 | 高 | ✅ B1.1 + 集团运维监控 | wave-2 b1-1-compliance-audit + wave-3 observability-cost-quota |
| 118 | 登录日志概览 | 高 | ⚠️ IAM 端 / 集团运维监控（§3.4） | wave-3 observability-cost-quota |
| 119 | 运维管理工作台 | 高 | ⚠️ 集团运维监控外部依赖 | wave-3 observability-cost-quota |

### 系统：应用中心（4 行 → 不复造）

| 行 | 用例名 | 优先级 | 处置 |
|---|---|---|---|
| 121 / 120 / 122 / 123 | 新增应用 / 发布审核 / 验收审核 / 应用发布 | 最高 | ❌ §5.6 #11 应用中心不进 IA |

### 系统：消息中心（3 行 → 外部依赖）

| 行 | 用例名 | 优先级 | 处置 |
|---|---|---|---|
| 36 / 37 / 38b | 消息模板 / 业务类型配置 / 我的站内信 | 最高 | ⚠️ 集团统一消息（§3.4 #2），shared/notification 极薄封装；不重造 |

### 系统：BSP（1 行 → 外部依赖）

| 行 | 用例名 | 优先级 | 处置 |
|---|---|---|---|
| 37 | 新增组织机构 | 最高 | ⚠️ IAM 外部依赖（IAF IAM；本地保留 actor_org_role_binding 投影） |

## 三、不复刻清单的反查

按基线 §5.6 + §3.4 "不进 IA / 外部依赖"，旧 128 用例中以下类型的当前处置（**2026-05-27 D31 业务方 PR #129 sign-off 后修订**）：

| 类型 | 不复刻理由 | 原 ❌ 行数 | D31 后处置 |
|---|---|---|---|
| 融合服务 / 通用服务 / 代理服务 / 应用案例 | §5.6 #11 #12 业务反馈 "几乎不用" | 21 行 (16%) | **20 条 ⏸ 按 dsp-dataservice plan 落地 + 1 条 ❌（106 案例提出页）** |
| 数字化运营 / 大屏 | §1.3 不做大屏 | 4 行 | 4 条 ❌ 接受（业务方 B 类）|
| 数据质量检测 / 元数据采集（除 J2 反向编目） | §3.4 集团数据治理中心外部 | 2 行 | 2 条 ❌ 接受（业务方 C 类）|
| 主题库 / 专题库 / 数购车 | §5.6 #11 | 3 行 | **3 条 ⏸ 按 sharezone-topic plan 落地（业务方 D 类）** |
| 栏目管理 | 旧门户运营，新平台不重做 | 4 行 | 4 条 ❌ 接受（业务方 E 类）|
| 知识中心独立模块 | §5.2.1 合并入 B1.1 | 1 行 | 1 条 ❌ 接受（业务方 F 类）|
| 多 SPA 拼接（"访问各子系统"） | §3.5 #6 反模式 | 1 行 | 1 条 ❌ 接受（业务方 G 类）|
| 应用中心 / 服务流程残项 | §5.6 #11 | 13 行 | 13 条 ❌ 接受（业务方 H 类）|

合计原 ❌ 不复刻 = 50 行 → D31 修订后 **❌ 接受 26 行 + ⏸ 复活按 plan 落地 24 行**（A 类 20 → dsp-dataservice plan / D 类 3 直接行 + D 类 1 合并行 → sharezone-topic plan；详见业务方 [PR #129](https://github.com/feng222666888/zw-brain/pull/129) + D32）。

## 四、维护原则

- 任何 .feature 含"旧 xlsx 行 N"引用，必须出现在本表中
- 新增 wave 或基线变更时必须重新审视此映射
- "不复刻"理由必须可追溯到基线章节（§5.6 / §3.4 / 业务反馈编号）
- 旧 xlsx 重新版本化时本表同步刷新
