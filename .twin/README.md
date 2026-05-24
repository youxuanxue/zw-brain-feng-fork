# 6 worker twin workspaces — zw-brain 完整产品交付分工

本目录承载 zw-brain 完整产品交付的 6 个 worker workspace，每个 worker 端到端 owns 一个用户价值闭环或解锁层。schema 契约见 [dev-rules/docs/twin-design.md](../../../Codes/dev-rules/docs/twin-design.md)「workspace 契约」节；模板见 [dev-rules/templates/twin-workspace/](../../../Codes/dev-rules/templates/twin-workspace/)。

## 6 个 workspace

| Worker | 用户价值闭环 |
|---|---|
| `e1-j1-journey` | J1 找数→用数（异议 5 维 + 供需对接 + P4 凭据 + 3 AI 减摩） |
| `e2-j2-journey` | J2 挂数→维数（3 层默认审 + 3 物化形式 + 异议响应） |
| `e3-wave2-engines` | R14 三引擎（审批流可视化 + 表单 schema + 智能推荐前置） |
| `e4-b1-agentruntime` | B1.1/B1.2 + 审计总线生产化 + AgentRuntime 触发式 |
| `e5-webui-projections` | 前端工程化重建 + 8 页面 + 5 消费面投影器 + CLI/MCP/A2A |
| `e6-platform-m0` | brain.py 拆分 + 推理生产化 + M0 现场实施面 + CI/CD |

## 6 worker 共享纪律（非冗余声明，每个 worker 默认遵守）

1. **共享 M0 数据底座**——所有 worker 基于 [docs/deployment/m0-site-migration.md](../docs/deployment/m0-site-migration.md) + [old/10示例数据/](../old/10示例数据/)（438MB / 17 dump）的 sd-default canonical 落地产品功能。
2. **撞 M0 墙提 PR 修 M0**——发现 M0 mapper / 模型 / fixture 缺口直接提 PR 改 M0；禁止在 worker 内造 fixture 或复造迁移逻辑。M0 PR 经常路径：catalog→E1、governance→E4、exchange→E2、projections→E5、objection→E2/E1。
3. **AI 调用必须走 `shared/inference/client`**——经集团推理平台 gateway；preflight 段 10 自动兜底，禁止直连第三方 LLM。
4. **写操作必须有运行时确认边界**——`human_confirmation_required: true` 的 capability 必须在 brain.invoke_skill 链路有运行时校验点。
5. **R12 工程术语黑名单**——`package` / `projection` / `capability` 等 9 词不进 UI；preflight 段 24 自动兜底。
6. **反 per-tenant fork**（架构基线 §11 反 fork 主张）——客户差异由 R14 三引擎（项目级配置）+ 多租户策略 + 外部能力包承接，不通过 fork 后端。

## 启动

```bash
/twin .twin/e6-platform-m0          # P0 解锁项先启动（brain.py 拆分 + webui 重建解锁）
/twin .twin/e5-webui-projections    # 与 E6 并行
/twin .twin/e1-j1-journey           # E6/E5 land 后启动
/twin .twin/e2-j2-journey
/twin .twin/e3-wave2-engines
/twin .twin/e4-b1-agentruntime
```

## 跨 worker 协作

- **跨 workspace 依赖**：twin schema 当前不支持跨 workspace 阻塞表达。本目录约定在 `plan.yaml` 的 `blocked_reason` 字段用人类可读 prose 描述（"等 E5 webui 重建 F2 完成后接入"），不引入 token 化 schema。
- **M0 PR review**：跨 worker M0 PR 路由通过 GitHub PR @reviewer 机制（提 M0 PR 时 @ E6 worker 持有人），不依赖定期同步会议。

## 已知未机械化保护点（trigger 化 pending）

- **.twin/ schema 检查 deferred**：当前 12 yaml commit 进仓库但无 preflight 段保护（schema valid / 12 文件存在性）。Trigger：再次出现"yaml 误删 / schema 漂移"事故时加 preflight 段。
