# E3 F9 起手清单 — Wave 2 P7 TopicPackage（D32.a 复活触发）

> **状态**：⏸ pending F8 sign-off。本文不立项，不动代码；仅在 F8 业务方签字落盘后
> 启动时供 assignee 走清单不查 plan。
>
> **真值源**：`docs/reconstructs/dsp-sharezone-topic-package-reconstruction-plan-v1.md`
> （以下行号引用都对这份；该 plan 由 D32.a 触发升级为 active，详见 CLAUDE.md
> [2026-05-27] D32 §四）。
>
> **架构约束 R8 反 per-tenant fork + R14 三引擎守护**：复活路径必须走三引擎；
> preflight 段 22 capability-boundary + 段 25 adapter-write-ban 全程绿。

## 一、F8 sign-off 落盘检查（启动前必做）

- [ ] `docs/wave2-acceptance/SIGN_OFF.md` § 3 业务方签字栏 4 项全部签字（鞍山 4
      级审批流 / 四川 7 字段表单 / 荆州 5 条推荐规则 / 「1 周内不改代码」承诺）
- [ ] `.twin/e3-wave2-engines/plan.yaml` F8 status: completed + actual_evidence
      追加 sign-off commit ID
- [ ] PR 评论或 issue label 留 `business-signoff: <角色> <日期>` 永久附属

任一项未满足 → **不启动 F9**，回 R13 元规则等下次 review。

## 二、6 表 schema 起手位置（参 plan §3.1 L148-164）

不进 alembic（基线 §9.6 全新项目 drop & recreate），走 `Base.metadata.create_all`。
建议放在 `zw_brain/domain/models/topic_package.py`：

| 表名 | 关键列（草稿，详见 plan §3.1） |
|---|---|
| `topic_package` | id / tenant_id / status / owner_org_snapshot / display_snapshot |
| `topic_package_item` | package_id / ref_type / ref_id / ref_snapshot |
| `topic_package_visibility` | package_id / policy_condition (org/role/surface) |
| `topic_package_review_record` | package_id / decision / reviewer / opinion |
| `topic_package_evidence` | package_id / evidence_type / content_snapshot |
| `topic_package_metric_projection` | package_id / metric_name / value / period |

⚠️ 不复造 `catalog_entry` / `resource_asset` / `catalog_model` / `dsp_basesubject`
（D7 forbidden-zone + §5.6 #13 + plan §3.1 L159-163「不拥有权威状态」）。

## 三、10 Capability slug 注册起手位置（参 plan §四 L202-211）

注册路径：`zw_brain/skill_registration/registered/topic.package.*.json` ×10：

写类：
- [ ] `topic.package.create` (write-trace)
- [ ] `topic.package.configure` (write-trace)
- [ ] `topic.package.submit` (approval-trace)
- [ ] `topic.package.review` (approval-trace)
- [ ] `topic.package.publish` (approval-trace)
- [ ] `topic.package.policy.update` (approval-trace)
- [ ] `topic.package.subscribe` (approval-trace)
- [ ] `topic.package.evidence.attach` (write-trace)

读类：
- [ ] `topic.package.query` (read-trace)
- [ ] `topic.package.metric.query` (read-trace)

每个 manifest 必须含 `product_scope.journey=j1` 或 `journey=b1` + `status=live` +
`config_change_class=live`（默认值，三引擎 capability 改 preview/draft）；走
`export_agent_contract.py --check` 零漂移。

## 四、首批 sd-default 山东标杆 fixture（参 plan §四 L213）

`tests/fixtures/topic_package/`（新建目录）：

- [ ] `medical_assistance.json` — 医疗救助专题包（catalog 医疗救助信息 + resource）
- [ ] `medical_insurance_code.json` — 医保码专题包
- [ ] `cross_region_settlement.json` — 异地就医统筹区开通专题包

每条 fixture 至少含：1 个 canonical catalog 引用 + 1 个 resource 引用 +
1 个 visibility policy（限 sd-default 租户 + 政务角色 OPERATER/MANAGER）。

## 五、5 消费面投影 + preflight 守护

- [ ] WebUI P7 共享专区页（zw-brain-web/src/pages/P7TopicPackage.vue）
- [ ] REST：`/api/skills/topic.package.{create,configure,...}`（自动注册）
- [ ] CLI：`zw-brain topic-package list / curate`（自动注册）
- [ ] MCP：tools 自动注册
- [ ] A2A：services 自动注册（外部 Agent 上报专题素材必经审核）

preflight 段必须全过：
- [ ] 段 10（forbidden-zone：basesubject 81 表）
- [ ] 段 22（capability-boundary）
- [ ] 段 25（adapter-write-ban：只有 `zw_brain/adapters/legacy/` 可写）
- [ ] 段 28（5 消费面三一致）
- [ ] 段 29（无手维护投影）

## 六、e2e 验证清单（参 plan §6.2 + §7.2）

- [ ] `tests/integration/test_wave2_topic_package_discovery.py` — J1 找数路径：
      P2 搜专题 → 命中专题包详情页 → 从专题包发起资源复用申请
- [ ] `tests/integration/test_wave2_topic_package_curation.py` — J2 运营方：
      创建草稿 → configure 绑 catalog/resource → submit → review approve → publish
- [ ] `tests/integration/test_wave2_topic_package_basesubject_forbidden.py` —
      D7 守护回归（任何写 `dsp_basesubject*` 表的尝试被段 10 拦下）

## 七、F9 sign-off 准入（启动前与业务方确认）

参 CLAUDE.md D28 元规则：复活范围归属 / 业务流程 / 状态机变更需业务方 sign-off
才能进 D-编号。F9 启动需 30 分钟 review 业务方明确：

- [ ] 首批 3 个山东专题（医疗救助 / 医保码 / 异地就医）业务方点头优先级
- [ ] 6 态发布状态机（plan §3.3）业务方对齐含义（含 offline_pending 是否需要）
- [ ] 三维可见性策略（组织 + 角色 + 消费面）业务方确认岗位授权矩阵
- [ ] D32 复活范围只走 P7 共享专区 + B1.2 注册路径；旧专区后台 / 旧基础主题库 /
      旧示范应用门户 不复造（plan §一.3 L44-50 已经写死，但 review 时再过一次
      避免业务方对「复活」边界理解偏差）

## 八、不做清单（卡边界）

参 plan §八 L319-329。简版：

- ❌ basesubject 81 表事实源
- ❌ 旧专区后台单独 UI
- ❌ 旧示范应用门户独立站点
- ❌ 旧基础主题库页面引擎
- ❌ catalog/resource/model 权威状态镜像（只投影，不持有）
