# zw-brain-web 路由表（F1 spike → F2/F3 全量重建参照）

> 单一事实来源：本文件记录旧 vanilla JS bundle（js/app.js 的 `ROUTES` 数组）→ 设计基线 §5.2
> 主入口枚举（P1-P5/P7 + B1.1/B1.2）的映射，供 F2 框架替换 / F3 成品化阶段沿用。
>
> 主入口边界引用：docs/approved/zw-brain-architecture.md §5.2（"每加一个主入口都要回答为什么不是已有 P/B 的子页"）。
> R12 工程术语黑名单：本表 / Vue 组件 / 路由 name 字段，**不得**出现
> `package / projection / capability / write-with-audit / register-version / apply-tenant-policy /
> reconcile-receipt / submit-evidence / policy_decision`。新 router 用业务语义命名。

## 主旅程页（普通用户）

| 旧 hash 路由（已存在）             | 旧 render 函数                          | 新产品页面            | 归属旅程 |
| ----------------------------- | ------------------------------------- | ---------------- | ---- |
| `#/workbench`                 | `PAGES.workbench`                     | **P1 工作台**       | 全局入口 |
| `#/discovery`                 | `PAGES.discovery`                     | **P2 资源发现**      | J1   |
| `#/discovery/catalog-browse`  | `PAGES.catalogBrowse`                 | P2 目录浏览子页        | J1   |
| `#/discovery/resource/:id`    | `PAGES.resourceDetail`                | P2 资源详情          | J1   |
| `#/request-flow`              | `PAGES.requestFlow`                   | **P3 申请/审批/跟踪**  | J1   |
| `#/request-flow/request/:id`  | `PAGES.requestDetail`                 | P3 申请详情          | J1   |
| `#/request-flow/review/:id`   | `PAGES.reviewDetail`                  | P3 审批详情          | J1   |
| `#/delivery-exchange`         | `PAGES.deliveryExchange`              | **P4 交付/交换/直达**  | J1   |
| `#/delivery-exchange/task/:id`     | `PAGES.deliveryTaskDetail`        | P4 任务详情          | J1   |
| `#/delivery-exchange/credential/:id` | `PAGES.deliveryCredential`      | P4 凭据领取（API Key + curl/Python 样例） | J1 |
| `#/provider`                  | `PAGES.provider`                      | **P5 提供方管理**     | J2   |
| `#/provider/wizard/reverse-catalog`  | `PAGES.providerWizardReverseCatalog` | P5 反向编目向导    | J2   |
| `#/provider/wizard/api-service`      | `PAGES.providerWizardApiService`     | P5 API 服务化向导  | J2   |
| `#/provider/wizard/quality-rule`     | `PAGES.providerWizardQualityRule`    | P5 质量规则向导    | J2   |
| `#/provider/inbox/field-decision`        | `PAGES.providerInboxFieldDecision`        | P5 反向编目审核收件箱 | J2 |
| `#/provider/inbox/field-decision/:id`    | `PAGES.providerInboxFieldDecisionDetail`  | P5 反向编目审核详情   | J2 |
| `#/provider/inbox/hookup-review`         | `PAGES.providerInboxHookupReview`         | P5 挂接审核收件箱  | J2 |
| `#/provider/inbox/demand-match`          | `PAGES.providerInboxDemandMatch`          | P5 供需对接收件箱  | J2 |
| `#/provider/inbox/demand-match/:id`      | `PAGES.providerInboxDemandMatchDetail`    | P5 供需对接详情   | J2 |
| `#/zones-pack`                | `PAGES.zonesPack`                     | **P7 共享专区/专题包** | J1 + J2 |
| `#/zones-pack/zone/:id`       | `PAGES.zoneDetail`                    | P7 专题包详情        | J1 + J2 |

## 后台支撑面（仅管理员 / 审计员）

| 旧 hash 路由                    | 旧 render 函数                          | 新产品页面            | 归属 |
| ------------------------------ | ------------------------------------- | ---------------- | ---- |
| `#/compliance-ops`             | `PAGES.complianceOps`                 | **B1.1 合规与运营**（查审计：审计日志/证据回放/审计事件，业务运营员+安全审计员） | B1 后台 |
| `#/compliance-ops/dispute/:id` | `PAGES.disputeDetail`                 | B1.1 异议详情        | B1 后台 |
| `#/service-ops`                | `PAGES.serviceOps`                    | **B1.3 服务调用监控**（网关运行只读，平台运维员+业务运营员+管理员/审计只读，D55/P8） | B1 后台 |
| `#/integration-admin`          | `PAGES.integrationAdmin`              | **B1.2 平台接入与扩展中心** | B1 后台 |
| `#/integration-admin/engines`        | `PAGES.enginesAdmin`            | B1.2 三引擎配置（审批流 / 表单 / 推荐） | B1 后台 |
| `#/integration-admin/iam-governance` | `PAGES.iamGovernance`           | B1.2 身份治理        | B1 后台 |
| `#/integration-admin/package/:id`    | `PAGES.packageDetail`            | B1.2 能力包详情       | B1 后台 |

## 辅助页（不计入主入口枚举）

| 旧 hash 路由             | 新页面             | 备注 |
| ----------------------- | ----------------- | --- |
| `#/login`               | 登录中转页         | iaf 跳转后回调 |
| `#/profile`             | 个人中心          | 用户菜单入口 |
| `#/migration-acceptance`| M0 迁移验收（admin）| 实施工程师 |

## §5.4.4 嵌入式自然语言加速器（F7 接入位）

| 嵌入页面    | 减摩组件名（待 F7 实现） |
| ---------- | ---------------------- |
| P2 资源发现 | NLAcceleratorPanel · 意图解析 + 缺口追问 |
| P3 申请形成 | NLAcceleratorPanel · 草拟摘要 + 补件建议 |
| B1.1 合规  | NLAcceleratorPanel · 调查摘要 |
| B1.2 接入  | NLAcceleratorPanel · 审核缺项 |

> 反约束（设计基线 §5.4.5）：加速器**不替代**主页面结构（目录树 / 申请表 / 审计证据 / 接入流程），仅在右侧或顶部独立组件中辅助。
