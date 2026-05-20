# 用户登录与退出实现总结

> **2026-05-19 retrofit (D23-D29)**：本文 7 角色 角色矩阵已退役。
> - 角色权威源：`docs/approved/zw-brain-roles.md`
> - 信息架构权威源：`docs/approved/zw-brain-architecture.md`
> - 评审决策记录：`docs/approved/zw-brain-architecture.md`
> - 原版 R 编号见 git blame。

本文描述当前 zw-brain 基于 IAM/IAF 的用户登录、会话刷新、请求鉴权、用户信息展示、首次登录落库与退出登录实现。

> 演进基线：本实现自 PR #53（feat: BFF session cookie + 多标签页 auth 同步）起采用 **BFF 模型**——
> 取代 PR #45 早期的「前端 sessionStorage 持 token + Authorization: Bearer 透传」做法。
> PR #45 落地的鉴权防御层（access_token 本地验签、healthz 双层防御、双因子 bypass / TLS 守护）
> 全部保留并在 BFF 模型下继续生效。

## 1. 总体实现形态

当前实现采用 **BFF（Backend-for-Frontend）会话 + 后端代理 IAM + 后端每次请求校验 token** 的模式。

- IAM access_token / refresh_token / id_token **从不出现在浏览器**——它们仅存活于后端进程内的
  `AuthSessionStore` 中，由 HttpOnly Cookie `zw_brain_session=<session_id>` 绑定到浏览器。
- 前端 `sessionStorage` 仅保留可公开的会话信息：
  `{authenticated, user, actor_snapshot, audit_id, csrf_token, expires_at, development_iam_bypass}`。
  其中 `csrf_token` 是写操作的双因子防御（double-submit）。
- 后端每次请求都重做 PR #45 落地的双层防御：
  ① 用 session 中的 access_token 透传到 IAM `/v1/token-healthz` 做撤销检查；
  ② 后端本地 RS256+JWKS 验签 access_token，校验 `iss/aud/exp`。
  因此即使 cookie 持续有效，只要 IAM 侧 token 被撤销或签名异常，本次请求即被拒。
- IAM 仍是统一认证的唯一认证源；项目本身不保存账号口令。
- `/api/*` 同时接受两种鉴权：
  - **Cookie 路径**（浏览器主路径）：`Cookie: zw_brain_session=...` + 写操作携带 `X-CSRF-Token` header。
  - **Bearer 路径**（CLI / 测试 / 直连 API 消费者）：`Authorization: Bearer <jwt>`。

## 2. 前端登录主流程

前端认证入口在 `zw-brain-web/js/auth.js`。

关键函数：

- `bootstrapAuth()`：应用启动认证引导。
- `startLogin()`：请求后端生成 IAM 授权地址并跳转。
- `exchangeCodeForToken(code, state)`：把 IAM 回跳 URL 中的授权码交给后端换会话。
- `readCurrentSession()`：用现有 cookie 拉取当前会话的 public payload，用于新开标签页 bootstrap 与
  BroadcastChannel `login` 事件回调。

启动时，`zw-brain-web/js/app.js` 调用：

```js
await window.ZW_AUTH.bootstrapAuth();
```

`bootstrapAuth()` 顺序：

1. 注册 BroadcastChannel `zw-brain-auth` 监听器（多标签页同步）。
2. 如果 URL 携带 `code/state` → 调 `exchangeCodeForToken()`，进入步骤 3。
3. 否则读 `sessionStorage`：若 snapshot 未过期则启动周期刷新。
4. 若 snapshot 缺失或过期 → 调 `GET /auth/iaf/session`（凭 cookie）尝试复用现有 BFF 会话；
   命中即写 snapshot 后启动周期刷新（**这条路径是 R-001 修复后的多标签页协同关键**）。
5. 仍无会话 → 读 `/auth/iaf/config`：若开启研发期 bypass 则调 `/auth/iaf/dev-bypass-login`，
   否则调 `startLogin()` 跳到 IAM 统一认证中心。

授权码换会话：

```http
POST /auth/iaf/token
Content-Type: application/json

{ "code": "...", "state": "..." }
```

成功响应：

- Header：`Set-Cookie: zw_brain_session=<session_id>; Path=/; Max-Age=...; HttpOnly; SameSite=Lax; Secure`
  （`Secure` 仅在 `X-Forwarded-Proto=https` 时附加）。
- Body：

```json
{
  "authenticated": true,
  "csrf_token": "<random>",
  "expires_at": 1715040000,
  "actor_snapshot": { "...": "..." },
  "audit_id": "...",
  "development_iam_bypass": false
}
```

**响应体不包含** `access_token` / `refresh_token` / `id_token`。

## 3. 前端会话存储与用户信息

前端把响应 body 写入 `sessionStorage`，key 为：

```
zw-brain.auth.v1
```

存储字段：

- `authenticated`：会话是否有效。
- `csrf_token`：双因子防御 token，写操作必须以 `X-CSRF-Token` header 回传。
- `expires_at`：Unix 秒，访问窗口到期时间，用于决定刷新时机。
- `user`：派生展示信息（`subject`/`username`/`displayName`/`email`/`phone`/`project`/`roles`/`exp`）。
- `actor_snapshot`：服务端落库的 actor 投影。
- `audit_id`：首登落库的审计追踪号。
- `development_iam_bypass`：是否为研发期 bypass 会话。
- `saved_at`：本地写入时间戳。

页面渲染、权限裁剪等仅依赖 `sessionStorage` 中的 public 信息；任何写操作必须经 `authFetch()`
注入 `X-CSRF-Token` header。

## 4. 业务请求鉴权（/api/\*）

前端通过 `window.ZW_AUTH.authFetch()` 统一发请求：

```js
const resp = await window.ZW_AUTH.authFetch('/api/snapshot?role=ROLE_ORGAN_OPERATER');
```

`authFetch` 行为：

1. 调用 `refreshTokenIfNeeded(false)`，如果 expires_at 临近则触发 refresh。
2. 浏览器自动随同源请求携带 `zw_brain_session` cookie；`credentials: 'include'` 显式打开。
3. 写方法（POST/PUT/PATCH/DELETE）自动注入 `X-CSRF-Token: <sessionStorage.csrf_token>` header。
4. 收到 401 → 清本地 snapshot；收到 403 + `error=csrf_token_invalid` → 同样清 snapshot
   （R-005 修复，避免 cookie 被其他标签页覆盖后陷入 403 死循环）。

服务端 `_with_authenticated_request` 优先级：

1. **Cookie 路径**：解析 cookie → `AuthSessionStore.get(session_id)` → 取 session.access_token
   → 走 PR #45 的双层防御（healthz + 本地 RS256 验签）。写方法另外校验
   `secrets.compare_digest(X-CSRF-Token, session.csrf_token)`。
2. **Dev IAM bypass**（无 cookie 但 bypass 启用）：合成 claims，标 `development_iam_bypass=True`。
   双因子守护仍然生效（必须同时设置 `ZW_BRAIN_DEV_IAM_BYPASS=1` 与
   `ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only`）。
3. **Bearer 路径**：读 `Authorization` header → 同样走双层防御。

## 5. Token 刷新

前端周期任务（`setInterval`，5 分钟一次）调用：

```http
POST /auth/iaf/refresh
X-CSRF-Token: <csrf_token>
Cookie: zw_brain_session=...
```

请求体被忽略——服务端从 session 中读 `refresh_token` 调用 IAM，再用新 token 更新 store，并下发
更新后的 public payload。失败（401）会清前端 snapshot，下一次 `bootstrapAuth` 重走流程。

研发期 bypass 会话不真正持 IAM token，refresh 直接回 echo 当前 payload。

## 6. 用户信息展示

`getCurrentUser()` 从 sessionStorage 派生：

```json
{
  "subject": "...",
  "username": "preferred_username",
  "displayName": "actor.display_name",
  "email": "...",
  "phone": "...",
  "project": "...",
  "projectId": "...",
  "orgCode": "...",
  "roles": ["ROLE_BUSIAUDIT", ...],
  "exp": 1715040000
}
```

`roles` 合并 `actor_snapshot.role_codes` + `realm_access.roles` + `resource_access.<client>.roles`，
去重排序。

## 7. 首次登录落库

`/auth/iaf/token` 在 token 校验通过后调用 `actor.projection.sync` Skill，以 `role="system"` 触发——
IAM 触发的首登投影是 system-origin 写入，不再被错误标记为 ROLE_BUSIAUDIT 用户行为。该 Skill 的执行权限在
`zw_brain/domain/policy.py` 中显式授权给 `system` role。

研发期 bypass 会话**不**调用 `actor.projection.sync`，因为合成身份没有真实 IAM `exp/iat`。

## 8. 退出登录

```http
GET /auth/iaf/logout?redirect_uri=https://app.example/
Cookie: zw_brain_session=...
```

服务端：

1. 从 cookie 取 session，读出 `id_token`（用于 IAM RP-Initiated Logout 的 `id_token_hint`）。
2. `AuthSessionStore.delete(session_id)`。
3. 构造 IAM 登出 URL：

```
{logout_endpoint}?post_logout_redirect_uri=<redirect_uri>&id_token_hint=<id_token>
```

4. 响应 `Set-Cookie: zw_brain_session=; Max-Age=0`，body `{logout_url, local_auth_cleared: true}`。

前端 `logout()`：

1. 发请求。
2. `clearSession()`（清 sessionStorage + 派 `zw-auth-change` 事件）。
3. `broadcastAuthEvent('logout')` 通过 BroadcastChannel 广播给其他标签页（事件只带 `type`，不带凭证）。
4. `window.location.href = data.logout_url || redirectUri`。

研发期 bypass 会话只做本地 + 服务端 session 清理，不走 IAM endpoint。

## 9. 多标签页同步

`BroadcastChannel('zw-brain-auth')` 在所有标签页间转发**事件**（绝不转发凭证）：

- `{type: 'login'}`：其他标签页收到后调 `readCurrentSession()`（即 `GET /auth/iaf/session`）从共享
  cookie 拉 csrf_token 与 actor snapshot 写入本 tab 的 sessionStorage，并启动周期刷新。
  **不**调 `window.location.reload()`——空 sessionStorage 下 reload 会重入 OAuth 流程并覆盖 cookie。
- `{type: 'logout'}`：其他标签页清本地 snapshot 并 reload，bootstrap 自动走回登录。

`GET /auth/iaf/session`（R-001 新增）是无副作用读端点：凭 cookie 命中即回 public payload；
无 cookie 或 session 失效返回 401。

## 10. 研发期 IAM bypass

适用网络不可达 IAM 的开发环境。**两个**环境变量必须同时设置才生效：

```bash
ZW_BRAIN_DEV_IAM_BYPASS=1
ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only
```

任一缺失 → bypass 不生效。这是 PR #45 R-002 加固，本 PR 完全保留。

bypass 启用时：

- `/auth/iaf/config` 返回 `development_iam_bypass_enabled: true` 与 `development_iam_bypass_user`。
- `POST /auth/iaf/dev-bypass-login`：服务端签发 bypass session，Set-Cookie 同正式流程。
  bypass 关闭时此路由返回 404（与未知路由一致，避免暴露存在性）。
- 服务端日志 `logging.warning` 在启动时显著告警。
- 业务请求路径上 actor 字符串追加 `[bypass]` 后缀，audit payload 含
  `development_iam_bypass: true` 结构化标记。

## 11. TLS 验证关闭（双因子）

同样需要双因子（PR #45 R-004 加固，本 PR 完全保留）：

```bash
ZW_BRAIN_IAF_VERIFY_SSL=false
ZW_BRAIN_IAF_INSECURE_TLS_DEV_ACK=development-only
```

任一缺失 → TLS 验证保持开启；启动时 `logging.warning`。

## 12. 涉及代码与端点速查

| 模块 | 路径 | 职责 |
|---|---|---|
| 前端 | `zw-brain-web/js/auth.js` | bootstrap、login/refresh/logout、authFetch、BroadcastChannel |
| 后端入口 | `zw_brain/entry/rest/server.py` | 路由、cookie/CSRF、session store 集成 |
| BFF 会话 | `zw_brain/shared/auth_session.py` | `AuthSessionStore` + `AuthSession` |
| IAM 客户端 | `zw_brain/shared/iaf_oidc.py` | OIDC 客户端、JWKS、token 验签 |
| Auth 上下文 | `zw_brain/shared/auth_context.py` | 请求级 `AuthContext` + `set/get/reset` |
| 运行时配置 | `zw_brain/shared/runtime_config.py` | 双因子 bypass / TLS 开关 |

REST 端点：

| Method | Path | 用途 |
|---|---|---|
| GET | `/auth/iaf/config` | IAM 公开配置 + bypass 用户 |
| GET | `/auth/iaf/login` | 启动授权流（JSON envelope 或 302） |
| POST | `/auth/iaf/token` | 授权码换会话，下发 cookie |
| GET | `/auth/iaf/session` | 凭 cookie 复用现有 session（无副作用） |
| POST | `/auth/iaf/refresh` | 凭 cookie + CSRF 刷新 |
| POST | `/auth/iaf/dev-bypass-login` | 研发期 bypass 签发会话（404 if disabled） |
| GET | `/auth/iaf/logout` | 删 session、清 cookie、构造 IAM 登出 URL |

## 13. 测试覆盖

- `tests/test_auth_session_store.py`：会话 CRUD、过期清理、CSRF token 生成、refresh 阈值。
- `tests/test_rest_session_lifecycle.py`：登录回调 cookie 属性、CSRF 必填、cookie/Bearer 双路径、
  /auth/iaf/session 复用、bypass 双因子。
- `tests/test_iaf_iam_e2e_offline.py`：BFF 模式下 cookie 设置、不返回 token、PR #45 安全断言保留。
- `tests/test_rest_runtime.py`：Bearer 路径回归、bypass 路径回归。
- `tests/test_webui_journey_contract.py`：auth.js 字符串契约（X-CSRF-Token、`credentials:'include'`、
  BroadcastChannel、`readCurrentSession`、`csrf_token_invalid` 处理）。

## 14. 已知 debt

详见 `docs/preflight-debt.md`：当前 `AuthSessionStore` 为单进程内存实现，多副本部署前需切 Redis/DB。
