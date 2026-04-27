# zw-brain-dashboard

政务大脑可视化大屏——独立部署单元，当前实现为 **K12 指挥中心只读大屏**。

## 架构定位（design baseline §7.7 + D15）

- **独立部署**：与主大脑（`zw_brain/`）分离，故障互不影响
- **只读消费**：仅订阅 `dashboard.*` Skill 输出，禁止任何写操作
- **当前实现范围**：交付 K12 指挥中心大屏；部门版 / 资源池版保留为后续扩展，而不是当前运行面承诺
- **机械约束**：`scripts/check_dashboard_readonly.py`（preflight 段 11）扫描本目录，禁止
  HTTP `POST/PUT/PATCH/DELETE` / DB write / 含 `.create(` `.update(` `.delete(` `.submit(`
  `.approve(` `.reject(` 等动词的 Skill 调用

## 目录

```
src/
  dashboard.js     — K12 指挥中心只读页面脚本
  api/             — read-only HTTP client + dashboard.* Skill 调用封装
bff/               — Python BFF：统一提供静态页面与 `dashboard.*` 只读代理
index.html         — K12 大屏入口页
```

## 当前运行方式

- 本目录不是通用前端脚手架，而是当前可运行的大屏交付物
- 在仓库根目录运行：`python zw-brain-dashboard/bff/main.py`
- 或进入本目录运行：`python bff/main.py`
- 一键本地启动：`bash scripts/start-local.sh`
- 可通过环境变量覆盖默认端口：
  - `ZW_BRAIN_REST_PORT`（默认 `8800`）
  - `ZW_BRAIN_DASHBOARD_BFF_PORT`（默认 `8801`）
  - `ZW_BRAIN_REST_BASE_URL`（用于 A2A contract 投影，默认跟随 REST 端口）
- Docker 镜像会一起带上 `zw_brain/`、迁移文件和静态资源，直接启动同一 BFF 入口
- BFF 提供：
  - `/health`
  - `/api/skills/dashboard.*`
  - `/index.html`
  - `/src/*` 静态文件

## 当前验收

- [x] 独立部署路径成立
- [x] `dashboard.*` 只读约束通过机械检查
- [x] Python BFF 提供静态页面与只读 skill 代理
- [x] `dashboard.render_command_center` 端到端 demo 已接通
- [x] 测试覆盖 `/health`、只读 skill、静态资源可达性
