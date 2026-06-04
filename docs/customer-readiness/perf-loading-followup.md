# 加载读路径 follow-up — BEFORE/AFTER 实测证据

> 收口 #213「工作台加载时间长」半截修复留下的四条契约零变更前端 follow-up；
> 直击 issue #126 头号体验痛点「切角色卡顿」。本 PR **不动后端契约 / 不做 CQRS·SSE**
> （#126 Phase 2/3 属架构门，待业务方 GATE sign-off）。

## 范围与方法

- 隔离栈：`:8807` + 干净 fresh-seed 真库副本（`.data/zw_brain_e2e_fresh.db`）+ dev IAM bypass + mock 推理。
- 度量脚本：`tests/e2e/perf_loading.spec.ts`（Playwright 真 UI，按 role 维度统计
  `/api/snapshot` 与 `/api/skills/workbench.view` 请求次数 + 各阶段就绪时延）。
- 本 spec **不 back 任何 `.feature`**（同 `r12_rendered_language.spec`），**不触发 D46.g 测量重采**。
- RED = stash 回原始（#213 后）代码同栈同 spec；GATE = 本 PR 代码。原始数据见同目录
  `red-metrics.json` / `green-metrics.json`。

## 四条 follow-up 的客观信号

| follow-up | 信号 | BEFORE（RED） | AFTER（GREEN） |
|---|---|---|---|
| FU-1 并发去重 | 当前岗位 boot 拉取次数（在途合并） | snapshot×1 / workbench×1（未放大） | snapshot×1 / workbench×2（首拉+SWR 校验，无在途重复） |
| FU-2 并行拉取 | boot snapshot 与当前岗位工作台 | 串行（工作台待 P1 挂载后才发） | 登录落地即并发预热（Promise.all） |
| FU-4 兄弟岗位预取 | 5 个可切换岗位切角色前的预热覆盖 | snapshot/workbench **全 0**（切到才首拉） | 每岗位 snapshot×1 / workbench×1（**全预热**） |
| 切角色就绪时延 | 切到兄弟岗位后工作台就绪 | 付完整 fetch 往返 | 命中缓存，就绪≈即时（毫秒级，SWR 仍后台校验） |
| 同岗位换页 | 4 页换页的快照/工作台重拉次数 | 0（#213 SWR 已具备） | 0（守卫不退化） |

> FU-3 写后失效（`invalidateSnapshot`/`invalidateWorkbench` + `_invalidationTick`
> 通知已挂载实例重拉）属写后**正确性**修复——写能力改了真实库积压后工作台待办
> （`workbench_backlog_projection` 现算）不再停在陈旧值。因「写后多半离开工作台、
> SWR 下次挂载即校验」属边角场景，本期以代码 + 回归覆盖（write 流 spec 不退化），
> 不单设易 flaky 的专测；如实标注覆盖深度。

## 回归（同隔离栈）

`webui_smoke / twin_browser_pages / r12_rendered_language / workbench_todo_closure /
draft_request_closure / role_projection_views / permission_invisibility`：
54 passed / 1 skipped / 3 failed。3 红在 stash 回原始代码同库同 spec **完全复现**
（依赖 D47 已删演示单 `REQ-2026-05-25-0002` + fresh-seed 权限态），**非本 PR 回归**。
`vue-tsc --noEmit` 0 err。

## 边界（不做）

- 不做 CQRS read-model / SSE 推送（#126 Phase 2/3，架构门待业务方 GATE sign-off）。
- 不改后端 `/api/snapshot` 契约 / 5 消费面（FU-4 是前端预取，非分桶 API）。
- 生产单岗位部署（`allowRoleSwitch=0`）不预取——预取仅在训练/演示态切角色开启时生效。
- 后端页级首屏（P7 专题包 / `request.list`）属另列 follow-up，本 PR 不扩张范围。
