# R7 数据共享/目录管理员：让发布真正可发现、可申请、可授权

## 这一页解决什么事

你负责把完整承接后的目录、资源、申请、授权能力组织成用户愿意用的入口。旧共享专区、目录分组、权限、开放统计都要承接，但它们在 zw-brain 中是专题与可见性 projection，不是第二套权限事实源。

## 你手上拿到的真实输入

- 高频目录：民生协同 `医疗救助信息`、`医保码信息`、`异地就医统筹区开通信息`、`参保信息`、`城乡居民养老保险参保登记`；行政管理 `省编办党政群赋码信息`、`博士及以上学历人员户籍地信息`；监管业务 `产品质量监督抽查信息`、`必需经水路运输医疗废物审批信息`、`案件信息`、`辐射安全许可证首次申请信息`、`停车场信息`。
- 专题入口：民生保障、医保协同、党政群赋码、教育服务、市场监管、生态环境、公共安全等共享主题，按 sd-default 业务场景重组，不复刻旧菜单层级。
- 目录运营对象：目录维护、分类关联、目录分级授权、资源挂接、国家目录资源挂接、反向编目草稿。
- 目录后台工作队列：旧 `catalog-front` 的 dispatch、claim、approve、authorize、examine、statistics、atlas、open 在新平台沉淀为稳态目录运营视图；import 已在 M0 关闭。
- 国家目录通道：旧 `catalog-front /country-catalog` 与"国家目录资源挂接"先由 M0 验收来源和映射，R7 只承接验收后的目录运营。
- 派发认领工作队列：旧 `catalog-front` 的 `/catalog-dispatch`、`/catalog-claim`、`/catalog-claim-dispatch` 在 R7 集中显现，处理目录责任分派和认领闭环。
- 在线目录定义：旧 `catalog-front /catalog-define-online` 是 R7 的运营工作队列。
- 开放目录工作队列：旧 `catalog-front /open/catalog-config`、`/open/catalog-publish` 由 R7 主责；`/open/resource-config` 等资源侧由 R6 主、R7 审核。
- 挂接审核视角：旧 `catalog-front /res-hook-examine` 在 R7 承接为"挂接审核"，挂接 / 发布 / 维护本身（`/res-hook`、`/res-hook-publish`、`/res-maintenance`）属 R6。
- 状态：目录已 `发布`、投影生成中、投影失败、可申请、授权待确认、撤回待确认。旧 `dump-dsp_catalog` 真实状态枚举仅 `审核中(2)/发布(3)/撤销`，新平台扩展态 `draft/pending_review/approved_pending_publish/active/changing/revoked` 与旧三档的映射以 catalog3-metadata3 重构方案 §八 为准。
- 策略证据：共享条件、可见组织、申请边界、授权类型、级联授权、订阅更新。
- 问题模式：发布成功但门户不可见、同主题目录重复、挂接资源不显示列、推荐展示不合理。
- 数据直达双 catalog：旧 `dsp_catalog.data_catalog` 是承重目录事实源，旧 `dsp_connect.dc_catalog` / `dc_datasource` 是已审批数据直达独立链路；新平台只保留 `catalog_entry` 一份事实源，dc_catalog 沉淀为"数据直达交付清单 projection"，由 R7 解释两者关系，禁止用户在 dc_catalog 上重新建目录。
- 供需对接证据：旧 `dsp_require` 的 `data_original_require` / `data_business` / `data_require_resource` / `data_require_resolve_link` / `data_require_task_link` 真实包含"原始需求 → 业务需求 → 需求资源对接 → 需求任务 → 反馈"链路，由 R7 在目录运营侧承接"需求与资源的对接判断"。
- API 服务化审核证据：R6 提交的 API 草稿、IP 白名单范围、限流阈值、订阅应用清单、字段脱敏档位。
- 反向编目字段确认证据：R6 提交的目录项草稿（字段中英文名、类型、长度、敏感建议）、来源 schema 引用。

## 一条主旅程

1. 检查本周新发布、待撤回、待派发、待认领、待审批、待授权、国家目录认领、在线目录定义、开放目录配置 / 发布等目录，确认它们处在正确工作队列里。
2. 对 dispatch、claim、claim-dispatch、approve、business-examine、manager-examine、authorize、examine 这些旧目录后台动作，只暴露给目录运营人员；M0 验收结果只作为来源证据引用，不进入日常操作。
3. 确认 `catalog_entry` active 后是否生成搜索、共享专区、订阅和推荐 projection；`/statistics`、`/atlas`、`/open` 的结果作为可重算运营 projection，不反向改目录事实。
4. 把 `医疗救助信息`、`医保码信息` 放入民生保障专题，减少 R1 从一堆相似目录里猜。
5. 复核目录说明、字段口径、申请条件、更新周期、开放条件和提供方责任，确保用户看得懂能否申请。
6. 做分类关联和相似目录治理：能合并入口的合并入口，不能合并事实的保留来源引用、合并依据和审计回执。
7. 检查目录项到资源字段的 `resource_schema_mapping`，避免“目录能看到但资源交不了”；对 `/res-hook-examine` 提交的挂接审核做裁决。
8. 对国家目录资源挂接（旧 `/country-catalog` 与上级通道目录），只保存对接摘要和责任边界，不改变 canonical 主事实源。
9. 对反向编目结果，只作为目录草稿和字段建议，最终写入必须经过目录确认、审批和审计。
10. 调整可见策略时，只改 projection 或策略解释，不绕过统一租户策略和授权链。
11. 对高频失败申请做归因：边界不清、字段冲突、授权策略过严、投影延迟、推荐展示不合理或资源证据缺失。
12. 把 `/inventory`（已授权清单）作为 `delivery_task` projection 抽查，发现超期、未生效或废弃授权，交回 R2 处置。
13. 将 statistics、atlas、open 的结果解释为运营 projection：用于看发现、申请、授权、挂接、开放和共享效果，不反向改目录事实。
14. 发布调整后跟踪发现率、申请成功率、授权生效率、重复申请下降、订阅使用和投影失败率。
15. 对 R6 提交的反向编目草稿做字段口径确认：字段中英文名是否一致、敏感建议是否准确、与已有目录主键是否冲突；通过后回到 R6 做 `resource_schema_mapping` 挂接；驳回则回 R6 补 schema 证据。
16. 对资源挂接审核（旧 `/res-hook-examine`），按字段绑定证据、共享条件一致性、目录项可解释性做裁决；通过后写 `resource_schema_mapping.status=active`，驳回回到 R6 修复；本端只审挂接，不替 R6 改字段。
17. 对撤回审核（旧 `/res-revoke-examine`），由 R7 主审业务影响、R8 主审审计独立性、提交方写撤回理由；本端只决定"是否同意撤回"，不在共享专区单独撤一个目录。
18. 对资源发布审核（旧 `/open/resource-config-examine`），按字段脱敏档位、API 边界、IP 白名单范围、限流阈值、订阅应用清单做审核；通过后允许 R6 上线 API；驳回回 R6 修字段或拆 API。
19. 对目录分级授权（旧 `/authorize` 中"实施分组与可见组织"半边），只把 R2 已决策的授权策略落到可见组织、专题分组与策略解释；不替 R2 决定"允许哪一档授权"，本端只决定"R2 那一档在哪些组织里看得到"。
20. 对供需对接（旧 `dsp_require`），按 R1 提交的"原始需求 / 业务需求"先判断是否能用现有目录复用；可复用则形成"需求 ↔ 资源对接"记录、关闭原始需求；不能复用则进入"目录建议"或"基层补差任务派发"链路（派给 R5）。
21. 对数据直达双 catalog 关系，把已审批的"数据直达交付清单"沉淀为 projection 给 R5/R8 看；任何想直接对 dc_catalog 写数据的请求都退回 `catalog_entry` 主链路；用户看不到 dc_catalog 这一层。

## 工作队列卡片

| 工作队列 | 何时进 | 谁批 | 何时出 | 留在哪 |
| --- | --- | --- | --- | --- |
| 目录派发与认领 | 新目录待派 / 部门变更 | R7 派发，部门认领 | 通过：进入"待审"队列；超期未认领：升级提醒 | dispatch receipt + owner snapshot |
| 目录审核（业务审 + 管理员审） | 提交审核或发布后变更待审 | R2 业务审 + R7 管理员审 | 通过 → 待发布；驳回回到草稿 | `approval_case` + `approval_step` |
| 目录发布 / 撤回 | 审核通过待上线、需下架 | R7 发布；撤回需 R8 监督审计独立性 | 上线：`catalog_entry.status=active`；撤回：`revoked` 并保留订阅影响范围 | catalog version + audit |
| 资源挂接审核 | R6 提交挂接 | R7 主审字段绑定 | 通过：mapping active；驳回回 R6 | mapping evidence + audit |
| 资源发布审核（含 API 边界审核） | R6 提交资源草稿或 API 草稿 | R7 主审 + R2 授权策略复核 | 通过：资源 active；API 上线；驳回回 R6 | resource/api version + audit |
| 资源撤回审核 | R6 申请撤回、active 版本切换 | R7 业务影响 + R8 审计独立性 | 通过：`resource_asset.status=suspended/revoked`；驳回保留 active | revoke audit + 影响清单 |
| 反向编目字段确认 | R6 提交草稿 | R7 字段口径裁决 | 通过：回 R6 挂接；驳回：补 schema 证据 | draft confirmation + audit |
| 在线目录定义 | 新模板待维护 | R7 模板裁决 | 通过：模板 active；下版本启用 | `CatalogModel` version + audit |
| 国家目录认领 | 上级通道下发 | R7 认领并标责任部门 | 通过：本地建议草稿；不改本地 active | adapter receipt + draft |
| 开放目录配置与发布 | 目录需对外开放 | R7 主审；开放资源配置由 R6 主 + R7 审 | 通过：开放投影生效 | open projection + audit |
| 分类关联维护 | 分类调整、专题重组 | R7 裁决专题入口 | 通过：分组投影更新 | topic projection + audit |
| 需求资源对接 | R1 提交原始/业务需求 | R7 判断复用或转 R5 | 复用：写需求-资源对接；不可复用：派发 R5 补差 | demand-resource link + audit |
| 数据直达交付清单 | 申请已审批且需直达 | R7 解释；R8 抽查绕行 | projection 持续刷新 | direct-access projection |
| 分级授权可见性实施 | R2 决定授权策略变更 | R7 只实施可见组织/专题分组 | 通过：策略解释更新；不替 R2 决策 | policy projection + audit |

## 关键判断点

| 你看到什么 | 该怎么判断 | 系统证据 |
| --- | --- | --- |
| 目录 active 但搜索不到 | 是 projection 问题，不是重新发布目录 | projection status、审计回执 |
| 同主题目录过多 | 合并入口或调整专题说明 | `catalog_entry.tags_snapshot`、共享专题 projection |
| 申请人看不懂边界 | 改目录说明和字段解释 | `catalog_item`、申请失败原因 |
| 授权策略争议 | 不能在共享专区单独放权 | `tenant_capability_policy`、`delivery_task` |
| 挂接资源不显示列 | 转 R6 修复字段绑定 | `resource_schema_mapping`、schema snapshot |
| 分类关联让用户更难找 | 按用户任务重组入口，不按旧菜单层级堆叠 | topic projection、搜索日志 |
| 反向编目生成草稿 | 必须人工确认后进入审批 | draft catalog entry、audit receipt |
| 国家目录资源挂接失败 | 记录外部通道状态，不改本地事实 | adapter receipt、projection status |
| 推荐展示不合理 | 调整排序证据或专题说明 | search projection、订阅/申请转化 |
| 派发后无人认领 | 这是运营队列问题，不是用户重新申请 | dispatch receipt、owner snapshot |
| 统计或图谱与目录事实不一致 | 修 projection，不改 active 目录 | statistics/atlas projection status |
| 反向编目草稿字段中英文不一致 | 驳回回 R6 补 schema 证据 | draft confirmation、字段证据 |
| 资源挂接审核多次驳回同一字段 | 升级为目录项口径变更 | mapping evidence、approval step |
| 资源撤回会影响在途授权与订阅 | 退回 R6 评估替代资源；不让撤回静默断订阅 | 撤回影响范围、`delivery_task` |
| API 服务化字段越权 | 退回 R6 改字段脱敏档位；同时回 R2 复核授权策略 | API 草稿、字段策略快照 |
| R1 原始需求与现有目录高度相似 | 直接对接复用，不另起新目录 | demand-resource link、目录详情 |
| R1 业务需求无法用现有目录满足 | 派发 R5 补差任务，不允许在共享专区"新建一个目录占位" | demand task link、R5 任务派发 |
| 数据直达交付清单出现没有审批回执的条目 | 视为绕行风险，转 R8 抽查 | direct-access projection、approval case |
| dc_catalog 出现独立写入 | 退回 `catalog_entry` 主链路；锁定 dc_catalog 只读 | dc_catalog source flag |
| R2 已收紧授权策略但可见组织没同步 | 立即更新策略解释；不让 active 可见性比 R2 决策宽 | policy projection、access grant snapshot |

## 异常分支

- **发布成功但入口不可见**：先查投影状态、生成时间和失败摘要，不让提供方重复发布。
- **共享专区分组混乱**：按用户任务合并入口，保留旧目录映射证据。
- **申请边界不清导致大量退回**：重写目录说明、字段解释和申请条件。
- **授权未生效**：回到 `approval_case` 和 `delivery_task`，确认审批通过、授权回写、策略快照是否一致。
- **目录重复建设**：推动合并为统一目录资产，保留来源引用、合并依据和审计回执。
- **目录撤回影响订阅用户**：先提示影响范围和替代目录，再进入撤回审批。
- **反向编目口径与在线目录不一致**：只保留草稿建议，交由 R6/R7 确认字段和共享边界。
- **国家目录挂接与本地目录冲突**：保留外部通道摘要，不让上级通道覆盖本地 canonical 事实。
- **反向编目草稿主键冲突**：草稿改"目录变更建议"，由 R7 决定合并、撤回或新建，禁止覆盖 active。
- **资源挂接审核驳回理由不可执行**：必须给出明确字段、口径或证据缺口，避免 R6 无从修复。
- **撤回审核被绕过**：拒绝任何"不走撤回审批就下线"动作；订阅用户必须收到撤回影响摘要。
- **API 上线后被多个应用滥用**：先调限流/熔断/IP 白名单，再评估是否拆分为多 API；不直接下线整接口。
- **供需对接被当作"批量要数"通道**：要求 R1 把原始需求拆为最小必要，重复主题转目录建议或专题。
- **数据直达请求绕过审批**：dc_catalog 锁只读；任何写请求退回 `application_record` 主链路。
- **分级授权策略与可见组织不同步**：以 R2 决策为准，立即同步可见性；不允许"分组里看得到，R2 没批"。

## 成功判据

- 目录发布后能被稳定发现、理解和申请。
- 共享专区减少选择成本，而不是制造第二套目录。
- 可见性、申请边界、授权结果都有证据链。
- 高频失败申请下降，R1 不需要靠线下问人找数据。

## 旧平台能力在这里怎么落地

| 旧平台能力 | zw-brain 表达 | 用户感知 |
| --- | --- | --- |
| 目录分组 `catalog_share_group` | 共享专题 projection | 按任务找目录 |
| 目录维护 / 发布 / 撤回 | `catalog_entry_version` + approval case | 目录版本和责任边界可回放 |
| 分类关联 / 订阅 / 推荐展示 | topic/search projection | 少猜目录，多按任务发现 |
| 共享专区 `share_zone_catalog_link` | topic projection | 发布后进入可见入口 |
| 分组权限 `share_group_permission` | 策略解释 + 租户权限 | 不创建第二套权限事实源 |
| 资源挂接与预览 | `resource_schema_mapping` / schema snapshot | 知道目录是否真能交付 |
| 国家目录资源挂接 | external channel adapter + mapping evidence | 上级通道可追踪，不改本地事实源 |
| 反向编目 | draft catalog entry + audit confirmation | 自动草拟，人工确认后才发布 |
| dispatch / approve / authorize / examine / business-examine / manager-examine | catalog operation queue + approval case | 目录后台变成稳态运营队列；业务审 / 管理员审是同一 `approval_case` 两类视角 |
| catalog-import | M0 acceptance receipt | 只作为来源证据入口，不进入 R7 日常动作 |
| catalog-claim / catalog-claim-dispatch | 派发与认领工作队列 | 不暴露给 R1 |
| catalog-define-online | 在线目录定义工作队列 | R7 主责 |
| open/catalog-config / open/catalog-publish | 开放目录配置与发布工作队列 | R7 主责 |
| res-hook-examine | 挂接审核（监督） | 挂接事实属 R6 |
| inventory | 已授权清单 projection | 抽查超期 / 未生效 / 废弃授权 |
| country-catalog | 国家目录通道（M0 验收后由 R7 运营） | 上级通道，不改本地事实 |
| statistics / atlas / open | ops / relationship / open projection | 看发现、申请、授权、挂接和开放效果 |
| 目录统计与开放数 | ops projection | 看发现、申请、授权效果 |
| 反向编目 `CatalogCompileServiceImpl` | R7 字段口径确认 + 入库审批 | 草稿不静默入库，确认后才发布 |
| 资源挂接审核 `/res-hook-examine` | R7 主审挂接证据 | 通过/驳回都进 `approval_case` |
| 资源撤回审核 `/res-revoke-examine` | R7 业务影响 + R8 审计独立性 | 撤回不能绕过审批，订阅用户收到影响摘要 |
| 开放资源配置 `/open/resource-config-examine`、`/open/resource-publish` | R7 审字段脱敏档位 + API 边界 | 通过后才允许 R6 上线 API |
| 数据直达 `dsp_connect / dc_catalog / dc_datasource / dc_objection_*` | 数据直达交付清单 projection | dc_catalog 只读，事实源仍是 `catalog_entry` |
| 供需对接 `dsp_require / data_original_require / data_business / data_require_resource / data_require_resolve_link / data_require_task_link` | 需求-资源对接记录 + R5 任务派发 | 需求不是申请；可复用先复用，不可复用派任务 |
| 分级授权可见性实施 | R2 策略 → R7 可见组织/专题分组 | R7 只实施 R2 决策，不替 R2 决定授权档位 |