# User / IAM 接入后的 WebUI 与快照加固（ backlog ）

## 背景

PR #23（及后续小提交）已落地：

- 主 WebUI：`ZW_PAGE_ACCESS`、路由门禁、`review/` 与 `request/` 同源刷新、详情页禁止静默回退到列表首条。
- 服务端：`zw_brain/domain/web_snapshot_redaction.py` 按岗位裁剪 `system.snapshot` / `GET /api/snapshot` 预加载；浏览器换岗后调用 `refreshSnapshot()` 对齐内存态。

当前环境与「真实用户 + IAM」未对接，以下项**刻意保留为技术债**，待 User / IAM 接入后一并收口。

## 待办（IAM 后必须或强烈建议）

### P0 — 岗位不得仅由客户端声明

- **现象**：`/api/snapshot?role=` 与各 `GET /api/skills/...?role=` 仍信任请求方传入的 `role`（经 `policy.resolve_role` 校验合法枚举，但无登录主体绑定）。
- **目标**：岗位（及租户）从 **IAM 颁发的会话 / token** 解析；客户端可只读展示当前岗位，不可通过改 Query 放大快照面。
- **涉及**：`zw_brain/entry/rest/server.py`（`/api/snapshot`）、`BrainService.invoke_skill` 入口、未来 BFF/网关。

### P1 — 前端门禁与 Python 裁剪「单一事实来源」

- **现象**：`zw-brain-web/js/pages.js` 的 `ZW_PAGE_ACCESS` 与 `web_snapshot_redaction.py` 中 frozenset 双份维护，仅靠注释互指。
- **目标**：生成或共享一份岗位到数据面矩阵（JSON / 代码生成），或由 CI 断言两端一致，避免漂移导致「页禁了但快照仍下发」或相反。

### P2 — 路由门禁与侧栏 `shell` nav 完全一致（可选）

- **现象**：`assertRouteAccessParity` 只检查 `ROUTES[].page` 在 `ZW_PAGE_ACCESS` 有键，未校验与 `shell()` 内 `nav[].roles` 数组逐段相等。
- **目标**：机械对齐或单测覆盖，防止侧栏与 `dispatch` 行为分叉。

### P3 — `hydrateSnapshot` 与持久 `state.role`（可选）

- **现象**：`hydrateSnapshot` 使用 `currentRole = currentRole || state.role || 'r1'`，若服务端持久化 `state.role` 与 UI 短暂不一致，存在边界竞态。
- **目标**：IAM 后明确「会话岗位」与「快照内 state」的写入顺序与权威来源。

## 参考实现位置

| 主题 | 路径 |
|------|------|
| 快照裁剪 | `zw_brain/domain/web_snapshot_redaction.py` |
| 快照技能 | `zw_brain/command/brain.py`（`system.snapshot`） |
| REST 快照 | `zw_brain/entry/rest/server.py`（`GET /api/snapshot`） |
| 前端门禁与换岗刷新 | `zw-brain-web/js/app.js`、`zw-brain-web/js/pages.js` |

## 状态

- **Status**：blocked on **User 服务** + **IAM** 接入
- **Close 条件**：上述 P0 完成且 P1 有机械门禁；P2/P3 按产品排期
