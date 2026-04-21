# zw-brain-dashboard

政务大脑可视化大屏——独立部署单元（Phase-0 骨架）。

## 架构定位（design baseline §7.7 + D15）

- **独立部署**：与主大脑（`zw_brain/`）分离，故障互不影响
- **只读消费**：仅订阅 `dashboard.*` Skill 输出，禁止任何写操作
- **三种内置模板**：指挥中心 / 部门版 / 资源池版（Phase-0 占位 ≤ 1 个组件壳子）
- **机械约束**：`scripts/check_dashboard_readonly.py`（preflight 段 11）扫描本目录，禁止
  HTTP `POST/PUT/PATCH/DELETE` / DB write / 含 `.create(` `.update(` `.delete(` `.submit(`
  `.approve(` `.reject(` 等动词的 Skill 调用

## 目录

```
src/
  views/          — 路由级页面（command-center / department / resource-pool）
  api/            — read-only HTTP client + dashboard.* Skill 调用封装
  components/     — 复用图表/卡片/状态徽章
bff/              — Backend-for-Frontend 网关（Phase-0 占位）
```

## 技术选型

❌ 暂未敲定。前端框架（Vue 3 vs React vs Svelte）+ 图表库（ECharts vs vega-lite）
+ BFF 框架（FastAPI vs Hono vs Express）均延后到 Phase-0 PoC（与主大脑一致，
设计基线 D19）。本骨架只声明目录结构与契约，不绑定具体框架。

## Phase-0 阶段验收

- [x] 目录骨架就位
- [x] `package.json` + `bff/` 占位文件存在
- [x] `scripts/check_dashboard_readonly.py` 能扫到本目录且通过（无写操作）
- [ ] Phase-1 起：接通 `dashboard.render_command_center` Skill 端到端 demo
