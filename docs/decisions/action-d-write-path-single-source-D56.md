---
title: Action D 写路径单源化（申请/审批/交付三聚合唯一事实源收口 DB）
scope: action-d-write-path-single-source
status: approved  # 架构门：产品研发负责人 sign-off（D56，账本 .testing/signoff/action-d-write-path-single-source.signoff.yaml，2026-06-11）
date: 2026-06-11
deciders: 海若产品部产品研发负责人（架构决策门）
related_docs:
  - docs/approved/zw-brain-architecture.md   # §9.5 adapter 写禁区 / §九 数据模型
  - CLAUDE.md D56 决策索引（承 D47/D55/D49/方案B）
---

# D56 — Action D 写路径单源化（j1-runtime-write-path-dual-track 收账）

- **日期**：2026-06-11
- **门类**：架构门（D28：架构决策，产品研发负责人 sign-off）
- **承接**：方案 B（#246 状态词汇桥接，负责人 2026-06-11 裁「B 先 A 后」）→ 本条兑现方案 A
- **签字**：`.testing/signoff/action-d-write-path-single-source.signoff.yaml`

## 一、问题

运行时申请写路径仍走演示时代双轨：`request.create` / `application.resource.submit`
先写 BrainService 内存快照 dict（铸 `REQ-YYYY-MM-DD-NNNN`），再经
PersistMiddleware → `sync_aggregate_tables` 镜像 upsert 进 `application_record`；
读写双轨靠桥接与回写过渡件（`_sync_snapshot_request_status`，fail-soft 吞异常）
勉力同步。已实证的代价：凭据自动签发 hook 读陈旧态把成功终审炸成 409、
管理员待办不投影、绿门禁只测快照单对真实单结构盲（permission-matrix-0610 实锤）。

## 二、裁决

**申请 / 审批 / 交付三聚合的唯一事实源收口到 DB**（`application_record` /
`approval_case` / `delivery_task` 的 payload 列），内存快照
`requests` / `approvals` / `delivery_tasks` 三键整体退役。

### D56.a CardSession（写会话）

per-dispatch identity map：`find_by_id` 类查找从 DB 载入 payload 卡（权威
status/state 列覆盖）、登记 load 指纹；同一 dispatch 内重复查找返回同一 dict
实例——处理器「写括号外预取、闭包内就地变更」的既有形态零改动；
PersistMiddleware 在投影前 flush（指纹变化才 upsert，申请卡配对刷新
approval_case）；顶层 `invoke_skill` 进入时清纪元，嵌套 dispatch（审批后自动
签发凭据）复用同一会话。运行时/导入判别机械化：legacy payload 一律带
`kind`，运行时卡从不带。legacy 导入实体保持只读合成投影（不进会话、不被回写）。

### D56.b 申请编码统一不透明 hex

REQ-* 编号序列（扫快照取当日最大号）退役 → 新铸 `uuid4().hex`，与导入单同形
（一种申请、一种编码）。存量 REQ-* 行作历史编码继续可读；前端编号提取
（导航 / NL 加速器）双形并认，hex 不大写归一。`DLV-` 交付派生改
`f"DLV-{request_id}"`（REQ→DLV 文本替换在 hex 上不命中）。

### D56.c 凭据 secret 永不落库（承 D47 凭据诚实）

快照时代凭据明文躺在 `RuntimeStateRecord.snapshot_json`，而
`delivery_task.payload_json` 经 `safe_json` 剥除 `credential` 键——「半签发」
双轨。收口：DB 只存**签发事实**（`issued_audit_id` / `credential_seed` /
issued_at / issued_by），凭据本体按 `(request_id, seed)` 确定性重导出
（`credential_for_request` 同种子永生同一凭据），读时现算。legacy granted
无签发事实 → `not_issued` 口径不变（D47）。

### D56.d 投影写者不毁条件审步（修潜伏 SPEC 违约）

`upsert_from_request_and_approval`（单步演示流投影）原本删除重建
approval_case steps，违反 j1-approval-conditional SPEC Scenario 4「部门审
通过的记录仍保留」——Action D 前仅因镜像与条件引擎写不同 case 而未暴露。
收口：case 带条件引擎审步（步锚 `audit_id`）→ 只同步状态与审批卡，绝不碰 steps。

### D56.e 退役清单

`_sync_snapshot_request_status` 回写过渡件、`sync_aggregate_tables` 三聚合
镜像循环、`ids.next_request_id`、`demo_state_sync.maybe_request/maybe_delivery/
sync_demo_state_views`、seed 三键、`build_true_data_seed.py` 演示链拼接
（D47 删演示单口径的未爆雷）、`bench_write_path.py`（基准对象已不存在）。
存量已部署库的 snapshot_json 三键在加载时一次性剥离（幽灵行免疫）。

## 三、不变量（机械守卫）

- 工作台待办投影（`sync_request_todos`）按 `application_record` 现算（store 直读）。
- `_record_to_request_card` status 列权威（`update_status` 类写者只写列）。
- 测试锚：`tests/test_write_path_aggregate_delta.py`（flush 脏检 O(touched)、
  配对语义）、`tests/test_j1_conditional_status_bridge.py`（受理两级全链 +
  凭据读时重导出）、`tests/test_read_views.py`（会话卡契约）。
- 债 `j1-runtime-write-path-dual-track` 收账删除（修复史归 git）。

## 四、刻意不做

- 流程/状态机语义零变更：D55 受理两级、D49 审批 schema 驱动、方案 B 状态
  词汇全部原样（本条纯架构轴，不触 D28 业务签字面）。
- legacy 导入单仍只读合成（在线动作混合门控 = D47.b 既有债，不在本期）。
- approval_case 单步投影与条件引擎共写一表的进一步归一（如单步流也改
  append 模型）延后——本期只消除破坏性互踩。
