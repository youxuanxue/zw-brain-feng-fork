# Web/UI/文案客户交付审查（2026-05-12）

审查目标：以“今天就要交给客户试用”的标准，而不是“给研发解释系统”的标准，审查当前 `zw-brain` 主 WebUI、只读大屏和原 UI spec。

范围：
- `zw-brain-web/index.html`
- `zw-brain-web/js/pages.js`
- `zw-brain-web/js/app.js`
- `zw-brain-web/css/app.css`
- `zw-brain-dashboard/index.html`
- `zw-brain-dashboard/src/dashboard.js`
- `spec/ui/gov-ui-spec-b-service.html`

一句话结论：当前版本已经有一条“找数据 → 申请 → 补录 → 汇总 → 交付 → 审计”的产品骨架，但还没有达到客户交付观感；最大问题不是功能缺，而是客户仍会看到内部工程、演示身份、规范术语和解释型文案。

## P0：交付前必须处理

### 1. 顶部“当前身份”下拉仍是演示产品，不是客户产品

证据：`zw-brain-web/index.html:20-37`

问题：页面顶部同时出现“登录”和“当前身份”岗位下拉，客户会立即判断这是原型/演示环境。真实交付版本应显示已登录经办人、所属单位、岗位范围；不应让普通用户手工切换成“审批承接人员 / 目录管理员 / 合规与减负治理”。

建议：
- 生产交付隐藏岗位下拉，只保留当前账号身份摘要。
- 如需演示模式，必须由环境开关控制，并在非客户交付包中启用。
- 权限切换应来自 IAM 登录态和本地授权投影，而不是浏览器下拉。

### 2. 登录页直接暴露环境变量、OIDC、Actor 投影和“占位”语义

证据：
- `zw-brain-web/index.html:21`
- `zw-brain-web/js/pages.js:767-787`
- `zw-brain-web/js/pages.js:803-805`
- `zw-brain-web/js/app.js:162`

问题：登录相关文案出现 `IAF IAM`、`OpenID Connect`、`ZW_BRAIN_IAF_AUTH_SERVER_URL`、`/auth/iaf/callback`、`演示环境`、`岗位演示身份`、`占位`、`Actor 投影`。这不是客户语言，是研发/运维语言。客户需要知道“使用统一身份登录”，不需要看到协议、变量名和内部同步模型。

建议：
- 对客户统一写成：“请使用主管部门统一身份账号登录；如无法登录，请联系系统管理员确认账号授权。”
- 未配置 IAM 时不要展示变量名；展示“统一身份服务暂不可用，请联系管理员”。
- `Actor 投影` 改为“账号权限已同步”或完全不展示。

### 3. 只读大屏泄露内部决策编号和故障语气

证据：
- `zw-brain-dashboard/index.html:314-315`
- `zw-brain-dashboard/src/dashboard.js:30-32`

问题：客户可见文案出现 `D15`，并用“主应用故障”“所有数字停止刷新”描述状态。客户不应看到设计决策编号，也不应在大屏上被技术故障语言吓到。

建议：
- `只读态势 · 与办事主应用故障隔离（D15）` 改为“只读态势 · 与办事系统独立运行”。
- “主应用故障”改为“主办事服务维护中，当前展示最近一次核验快照”。
- 同时展示快照时间和数据时效，不用“所有数字停止刷新”。

### 4. 首页分区 Tab 是假交互，客户会点穿原型感

证据：`zw-brain-web/js/pages.js:700-714`

问题：“常用办理 / 待我确认 / 专题共享 / 交付与审计”看起来是 Tab，但只是锚点链接；页面只渲染 `id="service-common"` 的列表，没有对应 `service-confirm`、`service-topic`、`service-evidence` 内容，也没有真正切换状态。Spec 要求 Tab 需要明确交互语义和可访问性（`spec/ui/gov-ui-spec-b-service.html:670-675`）。

建议：
- 要么做成真正 Tab：切换不同列表、同步选中态、补 `role="tablist" / role="tab"`。
- 要么删除 Tab，把“按办理阶段进入”改成普通分组列表。
- 交付版本不能保留“看起来能点、实际不切换”的控件。

### 5. 动态数据大量直接拼进 `innerHTML`，客户数据接入后有 XSS/脏数据显示风险

证据：
- 主 WebUI：`zw-brain-web/js/pages.js:226-234`、`zw-brain-web/js/pages.js:872-880`、`zw-brain-web/js/pages.js:1049-1052`、`zw-brain-web/js/pages.js:1448-1452`、`zw-brain-web/js/pages.js:1551`
- 大屏：`zw-brain-dashboard/src/dashboard.js:15-21`、`zw-brain-dashboard/src/dashboard.js:42-44`、`zw-brain-dashboard/src/dashboard.js:66-71`、`zw-brain-dashboard/src/dashboard.js:77-78`

问题：代码里有 `escapeHtml`，但只在少数位置使用；大量来自 snapshot/API/legacy import 的名称、说明、AI 摘要、证据、错误信息直接进入 HTML。当前 seed 数据安全不代表客户真实数据安全。政务系统里字段名、部门名、备注、导入异常都必须按不可信输入处理。

建议：
- 所有外部/数据库/API 字段默认 escape；只有经过白名单的内部 HTML 片段允许原样渲染。
- 大屏也要加 `escapeHtml`，尤其是 `suggestions`、`burdenMetrics`、错误信息。
- 禁止把 `err.message` 原样渲染到客户页面。

### 6. 页脚仍是占位式法定信息

证据：`zw-brain-web/index.html:48-52`

问题：“网站标识、备案、监督入口、主办单位和联系方式以主管单位最终发布信息为准。”这句话像交付前备注，不像产品。客户交付版本要么填真实主管单位和备案信息，要么隐藏到部署配置完成后再显示。

建议：
- 配置化主办单位、联系方式、备案/监督入口。
- 没有正式信息时不要显示“以最终发布为准”这种内部交付提示。

## P1：影响客户信任与易用性的产品问题

### 7. 浏览器标题和品牌仍带工程代号

证据：`zw-brain-web/index.html:6`

问题：`政务数据大脑 · zw-brain` 把仓库代号暴露给客户。客户买的是“政务数据共享服务/政务数据大脑”，不是 `zw-brain`。

建议：浏览器标题、元信息、可见品牌均去掉工程代号；工程代号只留在代码、日志、运维内部文档。

### 8. 首屏口号过长，像流程说明，不像产品承诺

证据：
- `zw-brain-web/index.html:15-16`
- `zw-brain-web/js/pages.js:669-684`

问题：当前品牌副标题“先找可复用数据，再办共享申请，交付与审计同链可查”是对的，但偏流程解释。Jobs 标准下，首屏应先给一个清晰承诺，再让流程藏在交互里。

建议：
- 品牌副标题可收敛为：“让数据共享少填、快办、可追溯。”
- 首屏标题保留“先找可复用数据”，副标题减少分号式解释。

### 9. 信息架构仍偏“把所有能力摊开”，不是“帮客户完成今天这件事”

证据：`zw-brain-web/js/pages.js:286-352`、`zw-brain-web/js/pages.js:632-657`、`zw-brain-web/js/pages.js:687-755`

问题：左侧 8 个主入口、首页 6 个服务卡、阶段列表、链路图、待办、辅助建议、证据概览同时出现。每个模块都有理由，但首屏认知负担偏高。

建议：
- 首页只保留 3 个主动作：找数据、看待办、查进度。
- 交付/审计/专题包作为上下文入口出现，不要同时平铺。
- 管理员入口只在管理员登录后展示；普通经办人不需要看到治理世界。

### 10. 多处文案仍像说明书/规范，不像真实业务工作流

证据：`zw-brain-web/js/pages.js:691-705`、`zw-brain-web/js/pages.js:722-725`、`zw-brain-web/js/pages.js:1041-1052`

问题：例如“入口按当前身份开放，不能办理的事项会明确提示，不伪装成可办”“每一行都说明下一步动作、责任边界和可追踪证据”。这是在解释设计意图，不是业务现场语言。

建议：
- “今天能办的共享服务”下方说明改为“只显示你当前岗位可办理的事项”。
- “按办理阶段进入”改为“继续办理中的事项”。
- 把“责任边界、可追踪证据”藏到详情页，不放在首页说明里。

### 11. 技术治理页把企业 IAM/RBAC 内幕直接端给客户

证据：`zw-brain-web/js/pages.js:1592-1699`

问题：`租户`、`Capability Policy`、`fail-closed`、`tenant.policy.evaluate`、`bound / disabled / unmatched / iam_account_missing`、`Actor 投影` 等词对研发是准确的，但对客户管理员仍然过硬。客户需要看到“账号是否绑定、岗位是否授权、为什么拒绝”，不是策略引擎内部对象名。

建议：
- 管理页分两层：客户可见“账号授权 / 岗位范围 / 异常账号 / 审计记录”；技术诊断信息折叠到“高级诊断”。
- 英文状态统一映射为中文业务状态。
- `fail-closed` 改为“未确认授权时默认拒绝”。

### 12. 大屏指标语言偏运维，不偏领导/业务

证据：`zw-brain-dashboard/src/dashboard.js:34-37`

问题：“实时查询压力”“在线协同单元”“异常责任链”有运维味；客户领导更关心“办结、响应、协同、异常”。

建议：
- “实时查询压力”改为“查询响应”。
- “在线协同单元”改为“协同岗位/协同单位”。
- “异常告警”改为“待处置异常”。
- 大屏主标题从“一屏看清……”压短，保留业务结果，不堆三个判断句。

### 13. 禁用导航承诺“明确提示”，但 CSS 让提示无法触发

证据：
- `zw-brain-web/js/pages.js:500-505`
- `zw-brain-web/css/app.css:1711-1718`

问题：禁用导航项写了 `onclick` toast，但 `.product-nav-link.is-disabled` 设置了 `pointer-events: none`，用户点不到，也就看不到原因。这会让“受限”显得像坏掉。

建议：
- 禁用项保留可点击/可聚焦，只弹出“当前岗位暂无权限，请联系管理员或切换账号”。
- 或完全不展示不可访问入口，不要半禁用。

### 14. AI 被过度展示为“AI”，削弱经办人信任

证据：`zw-brain-web/js/pages.js:1202`、`zw-brain-web/js/pages.js:1437`、`zw-brain-web/js/pages.js:1623`、`zw-brain-web/js/pages.js:1753`

问题：“AI 建议的审批 / 汇总意见草稿”“系统审核意见”“AI 草拟的审核意见”会让客户把注意力放到 AI 是否可靠，而不是业务证据是否充分。

建议：
- 面向经办人写“建议意见草稿”“判断依据”“可编辑说明”。
- AI 作为能力来源可以在产品介绍中说明，不必在每个业务卡片上反复喊出来。

## P2：Spec 与实现一致性问题

### 15. 原 UI spec 的“Spec B · 一网通办服务”定位会误导当前产品

证据：`spec/ui/gov-ui-spec-b-service.html:393-407`、`spec/ui/gov-ui-spec-b-service.html:697-754`

问题：Spec B 的参考骨架是“一网通办 / 办事指南 / 事项名称 / 社保医保不动产”等公共办事大厅模式；当前 zw-brain 的核心是部门间数据共享、复用申请、基层补录和审计回流。这个 spec 给了“服务化、低干扰、检索优先”的正确方向，但业务心智不是同一个。

建议：
- 保留 Spec B 的视觉 token 和低干扰原则。
- 将业务骨架改成“数据共享服务首页”：搜数据需求、可复用资源、待我处理、共享申请进度、交付回执。
- Spec 文件标题从“一网通办服务”改为“数据共享服务 UI 规范”，避免后续继续套错场景。

### 16. Spec 禁止项没有覆盖当前泄露出来的内部术语

证据：`spec/ui/gov-ui-spec-b-service.html:644-649`

问题：Spec 禁止 `Spec B / 一网通办 / Command View`，但当前真正泄露的是 `D15`、`Actor 投影`、`Capability Policy`、`fail-closed`、环境变量、OIDC callback、演示身份等。

建议：把“客户可见禁用词”扩成可机械检查清单，至少覆盖：
- `D\d+` 设计决策编号
- `Actor 投影`
- `Capability Policy`
- `fail-closed`
- `OIDC` / `OpenID Connect`
- `ZW_BRAIN_` 环境变量
- `演示环境` / `占位`
- `/auth/` 技术路径

### 17. Spec 禁止 inline theme，但 dashboard 使用整页内联样式

证据：
- `spec/ui/gov-ui-spec-b-service.html:647`
- `zw-brain-dashboard/index.html:9-306`

问题：大屏 `index.html` 内联了完整 CSS token 和组件样式。短期可运行，但与“token 单一来源”和“禁止 inline theme”冲突，后续主 WebUI 与大屏会视觉漂移。

建议：
- 抽出 `zw-brain-dashboard/css/app.css` 或共享 `zw-brain-web/css/app.css` 的 token 子集。
- 只允许 HTML 保留结构，不在页面里复制主题。

### 18. Spec 要求组件先登记，但实现已有大量未登记业务组件

证据：
- `spec/ui/gov-ui-spec-b-service.html:590-640`
- `zw-brain-web/css/app.css:1401-1892`

问题：实现已有 `login-gate-*`、`service-entry`、`service-tabs`、`service-row`、`product-nav-*` 等关键组件，但 Spec 的组件契约表没有同步登记。规范如果不跟着真实产品演进，就会变成摆设。

建议：
- 将当前真实组件补进 spec，或把 spec 改成“基础视觉规范 + 组件登记入口”。
- 对客户交付版本，优先登记首页、登录、左侧导航、服务入口、状态卡、详情表格这些真实组件。

### 19. Spec 的 Tab 可访问性要求未落到实现

证据：
- `spec/ui/gov-ui-spec-b-service.html:670-675`
- `zw-brain-web/js/pages.js:707-712`

问题：Spec 要求分区 Tab 使用 `role="tablist" / role="tab"` 或路由同步按钮组；实现用普通 `<a>` 且没有真实切换。

建议：同 P0-4，删除假 Tab 或实现完整 Tab 行为。

### 20. 暗色代码块样式留在主 CSS 中，和“服务型低干扰”方向不一致

证据：`zw-brain-web/css/app.css:1376-1384`

问题：`pre.code` 使用深色背景。它现在不一定出现在核心页面，但一旦错误/诊断内容进入客户页，会和 Spec 禁止 dark cockpit 氛围的方向冲突。

建议：客户 WebUI 不展示代码块；诊断信息进入管理员高级诊断页，并使用浅色服务风格。

## 建议的交付前最小改造顺序

1. 先清除客户可见内部术语：登录页、大屏、IAM 治理页、footer、browser title。
2. 关闭生产岗位下拉，改为真实登录身份摘要。
3. 删除或实现首页假 Tab。
4. 给主 WebUI 和 dashboard 的所有动态字段加统一 escape。
5. 收敛首页：只保留“搜数据 / 待我办 / 查进度”三件事，管理和治理入口按角色后置。
6. 把 `spec/ui/gov-ui-spec-b-service.html` 从“一网通办”改成“数据共享服务 UI 规范”，并补齐当前真实组件与禁用词。

## Jobs 标准下的判断

客户不会因为页面里有 8 个入口而觉得产品强大；客户会因为第一眼知道该点哪里、看不到工程痕迹、每个按钮都真的工作，而觉得产品可信。当前版本的产品方向是对的，但交付前要做一次“去解释化、去演示化、去内部术语化”的收口。