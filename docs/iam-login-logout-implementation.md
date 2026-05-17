# 用户登录与退出实现总结

本文总结当前项目中基于 IAM/IAF 的用户登录、token 刷新、请求鉴权、用户信息展示、首次登录落库与退出登录实现。

## 1. 总体实现形态

当前实现采用 **前端持 token + 后端代理 IAM + 后端每次请求校验 token** 的模式。

- 前端负责：未登录拦截、跳转 IAM、接收授权码 `code/state`、保存 token、定时刷新 token、展示用户信息、发起登出。
- 后端负责：生成 IAM 授权地址、代理 code 换 token、代理 refresh token、透传 `Authorization` 到 IAM token-healthz 校验、写入请求级用户上下文、首次登录用户落库。
- IAM 仍是统一认证的唯一认证源；项目本身不保存账号口令。

## 2. 前端登录主流程

前端认证入口在 `zw-brain-web/js/auth.js`。

关键函数：

- `bootstrapAuth()`：应用启动认证引导。
- `startLogin()`：请求后端生成 IAM 授权地址并跳转。
- `exchangeCodeForToken(code, state)`：将 IAM 回跳 URL 中的授权码交给后端换 token。
- `safeDecodeJwtPayload()`：安全解码 JWT payload，仅用于展示和过期时间判断。

启动时，`zw-brain-web/js/app.js` 会先调用：

```js
await window.ZW_AUTH.bootstrapAuth();
```

登录流程如下：

1. 页面启动时检查 URL 是否携带 `code/state`。
2. 如果有 `code/state`，前端调用：

```http
POST /auth/iaf/token
```

请求体：

```json
{
  "code": "...",
  "state": "..."
}
```

3. 后端校验 state，并用 code 向 IAM token endpoint 换取 token。
4. 前端将返回的 token 写入 `sessionStorage`。
5. 清理 URL 中的 `code/state`。
6. 如果没有 token 且 URL 无 code，前端调用：

```http
GET /auth/iaf/login?redirect_uri={origin}/&format=json
```

7. 后端返回 `authorization_url`，前端跳转到 IAM 统一认证中心。

## 3. 前端 token 存储与用户信息解析

前端 token 存储在 `sessionStorage`，key 为：

```text
zw-brain.auth.v1
```

实现位置：`zw-brain-web/js/auth.js`。

存储内容包括：

- `access_token`
- `refresh_token`
- `expires_in`
- `token_type`
- `scope`
- 解码后的 `claims`
- 白名单化后的 `user` 展示对象
- `actor_snapshot`

每次拿到 token 后，前端会安全解码 JWT payload，提取用户展示字段：

- `sub`
- `preferred_username`
- `email`
- `phone`
- `project`
- `project_id`
- `org_code`
- `realm_access`
- `resource_access`

前端解码结果只用于展示与过期时间判断，不作为后端授权依据。

## 4. 前端 token 定时刷新

刷新策略在 `zw-brain-web/js/auth.js`：

- 每 5 分钟检查一次 token 过期时间。
- 当 access token 剩余有效期小于 60 秒时，调用后端刷新接口。

刷新接口：

```http
POST /auth/iaf/refresh
```

请求体：

```json
{
  "refresh_token": "..."
}
```

后端使用 IAM refresh token grant 换取新的 access token，并返回给前端更新 `sessionStorage`。

## 5. 前端业务请求拦截

项目未使用 axios，业务请求基于 `fetch`。

统一封装在：

```js
window.ZW_AUTH.authFetch(input, init)
```

业务请求统一改为走 `authFetch()`：

- `/api/snapshot`
- `/api/skills/{skill_id}` GET
- `/api/skills/{skill_id}` POST

`authFetch()` 会：

1. 检查 token 是否需要刷新。
2. 从 `sessionStorage` 读取 `access_token`。
3. 自动添加请求头：

```http
Authorization: Bearer <access_token>
```

4. 如果后端返回 401，清理本地登录态。

## 6. 前端用户菜单与个人中心

顶部 UI 在 `zw-brain-web/index.html` 中实现：

- 未登录时显示“登录”按钮。
- 登录后显示用户名按钮。
- 点击用户名可打开菜单。
- 菜单包含：
  - 个人中心
  - 退出登录

个人中心路由为：

```text
#/profile
```

页面实现在 `zw-brain-web/js/pages.js`，展示：

- 用户名称
- IAM Subject
- 邮箱
- 手机号
- 所属主用户
- 所属主用户 ID
- 组织编码
- 角色

个人中心不展示 access token 或 refresh token。

## 7. 前端退出登录

退出逻辑在 `zw-brain-web/js/auth.js` 的 `logout()` 中。

流程：

1. 清理 `sessionStorage`。
2. 调用后端：

```http
GET /auth/iaf/logout?redirect_uri={origin}/
```

3. 后端返回 IAM logout URL。
4. 前端跳转到 IAM logout endpoint。
5. IAM 清除 SSO 会话后，通过 `redirect_uri` 回到应用首页。

IAM logout URL 形态：

```text
{IAM}/auth/realms/{realm}/protocol/openid-connect/logout?redirect_uri=...
```

## 8. 后端 IAM/OIDC 工具层

核心实现文件：

```text
zw_brain/shared/iaf_oidc.py
```

主要能力：

- `IafIamConfig`：从环境变量读取 IAM 配置。
- `IafOidcEndpoints`：推导 IAM OIDC endpoints。
- `IafOidcStateStore`：生成与消费 `state/nonce`。
- `exchange_authorization_code()`：authorization code 换 token。
- `refresh_access_token()`：refresh token 换新 access token。
- `validate_access_token_health()`：将 `Authorization` 头透传到 IAM token-healthz。
- `verify_iaf_id_token()`：使用 JWKS 校验 id_token。
- `decode_jwt_payload_unverified()`：安全解码 JWT payload。

endpoint 推导规则：

```text
issuer = {ZW_BRAIN_IAF_AUTH_SERVER_URL}/realms/{ZW_BRAIN_IAF_REALM}
authorization_endpoint = {issuer}/protocol/openid-connect/auth
token_endpoint = {issuer}/protocol/openid-connect/token
logout_endpoint = {issuer}/protocol/openid-connect/logout
jwks_uri = {issuer}/protocol/openid-connect/certs
token_healthz_endpoint = {ZW_BRAIN_IAF_AUTH_SERVER_URL}/v1/token-healthz
```

## 9. 后端 REST 认证端点

核心实现文件：

```text
zw_brain/entry/rest/server.py
```

### `/auth/iaf/config`

返回 IAM 公开配置状态，不包含 `client_secret`。

### `/auth/iaf/login`

生成 IAM 授权地址。

行为：

1. 校验 `redirect_uri` 必须同源。
2. 生成 `state/nonce`。
3. 记录 redirect_uri。
4. 返回或重定向到 IAM authorization endpoint。

### `/auth/iaf/token`

前端拿到 IAM 回跳的 `code/state` 后调用。

行为：

1. 消费并校验 state。
2. 使用记录的 redirect_uri 调 IAM token endpoint。
3. 要求 token 响应中存在 `access_token`。
4. 优先校验 `id_token`。
5. 如只返回 access token，则调用 token-healthz 后再解码 payload。
6. 调用 `actor.projection.sync` 完成首次登录落库。
7. 返回 token 包与 `actor_snapshot`。

### `/auth/iaf/refresh`

代理 refresh token grant。

行为：

1. 接收前端传来的 `refresh_token`。
2. 后端调用 IAM token endpoint。
3. 返回新的 token 包。
4. refresh token 失效时返回 401。

### `/auth/iaf/logout`

生成 IAM logout URL。

行为：

1. 校验 `redirect_uri` 必须同源。
2. 拼接 IAM logout endpoint。
3. 返回 `logout_url` 给前端跳转。

## 10. 后端业务请求鉴权

业务接口包括：

- `/api/snapshot`
- `/api/skills/*`

所有业务接口都会进入统一认证包装：

```python
_with_authenticated_request(...)
```

处理流程：

1. 读取请求头 `Authorization`。
2. 要求格式为：

```http
Authorization: Bearer <access_token>
```

3. 将 Authorization 头原样透传到 IAM token-healthz（撤销/在线检查）。
4. IAM 返回 200：进入第 5 步；401：返回前端 401；503 或校验服务不可用：返回前端 503，失败关闭。
5. **后端在本地用 IAM JWKS 对 access token 做 RS256 验签**，校验 `iss / aud / exp / sub`；签名不通过或 audience 不匹配返回 401。
6. 验签通过后再读取 claims，写入请求级用户上下文。

JWKS 在进程内按 `_JWKS_CACHE_TTL_SECONDS = 600` 缓存，遇到 `kid` 不命中时触发一次强制刷新；测试可通过 `configure_iaf_auth_runtime(jwks=...)` 直接注入。

### 10.1 研发期 IAM 绕过

研发环境无法连通 IAM 时，可临时启用 IAM 绕过。开关需要 **同时设置两个环境变量** 才生效，避免单一变量 typo 误关认证：

```bash
ZW_BRAIN_DEV_IAM_BYPASS=1
ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only
```

仅设置其中一个不会生效（启动时会有 warning 日志）。开启后：

- 启动时 `zw_brain.entry.rest.server` 打 `logging.warning`，明确告知 IAM 绕过已生效。
- 前端通过 `/auth/iaf/config` 识别绕过状态，从同一接口返回的 `development_iam_bypass_user`（subject/username/role_codes/display_name 等）渲染身份，不再硬编码角色列表。
- 后端在 `/api/snapshot` 与 `/api/skills/*` 上跳过 IAM 校验，并注入服务端合成的开发调试上下文。
- `AuthContext.development_iam_bypass=True` 透传给业务层。`BrainService._actor_for_role` 在 bypass 激活时给 actor 字符串追加 `[bypass]` 后缀（例如 `user:gov:r1:周处长[bypass]`），并在 `_emit_audit` 的 `payload.development_iam_bypass` 与 `actor_snapshot.development_iam_bypass` 上同时设置 `True`，使审计/能力调用流可同时按字符串后缀与结构化字段过滤。
- 仍保留 Skill manifest、角色、租户、人工确认等业务门禁。
- 生产部署不得设置上述变量；正式上线前应删除 `ZW_BRAIN_DEV_IAM_BYPASS*`、`development_iam_bypass`、`dev-iam-bypass`、`developmentBypassEnabled` 相关临时代码与文档。

### 10.2 研发期 IAM TLS 校验关闭

类似地，关闭 IAM HTTPS 证书校验也需要双变量确认：

```bash
ZW_BRAIN_IAF_VERIFY_SSL=false
ZW_BRAIN_IAF_INSECURE_TLS_DEV_ACK=development-only
```

只设置 `ZW_BRAIN_IAF_VERIFY_SSL=false` 而缺少 ack，TLS 校验依然开启（启动时会有 warning 日志）。生产不得使用。

## 11. 请求级用户上下文

新增文件：

```text
zw_brain/shared/auth_context.py
```

核心对象：

```python
AuthContext
```

字段：

- `subject`
- `username`
- `tenant_id`
- `org_code`
- `role_codes`
- `claims`
- `development_iam_bypass`（布尔，绕过开关激活时为 `True`，便于审计/日志区分）

底层使用 Python `ContextVar`，作用类似 Java ThreadLocal。

提供方法：

- `set_auth_context()`
- `get_auth_context()`
- `reset_auth_context()`
- `auth_context_from_claims()`

每个请求认证成功后写入上下文，请求结束后 reset，避免线程复用污染。

## 12. 首次登录用户落库

首次登录不新增独立 user 表，而是复用现有 actor projection 体系。

触发点：

```text
/auth/iaf/token -> _sync_actor_from_claims() -> actor.projection.sync (role="system")
```

actor projection 落库本质是 IAM 触发的系统级写入，使用 `policy.ACTOR_NAMES` 中专门保留的 `system` 角色调用，使审计/capability_call 的 actor 不再被错误标注为某个业务用户（如 r7）。

落库逻辑在：

```text
zw_brain/command/brain.py
```

核心函数：

```python
_build_actor_projection_from_claims(...)
```

落库信息包括：

- `tenant_id`
- `external_actor_id = sub`
- `display_name = preferred_username or sub`
- `org_code`
- `role_codes`
- `status = active`
- `source_ref = iaf:claims`
- `profile_json`

`profile_json` 包含：

- `username`
- `project_id`
- `project`
- `iam_role_codes`
- `realm_roles`
- `account_admin`
- `email`
- `phone`

角色提取兼容：

```json
{
  "realm_access": {"roles": ["..."]}
}
```

以及：

```json
{
  "realm_access": ["..."]
}
```

同时提取：

```json
{
  "resource_access": {
    "client_id": {
      "roles": ["..."]
    }
  }
}
```

## 13. 安全边界

当前实现遵循以下安全边界：

- `client_secret` 只通过后端环境变量注入，不进入前端。
- 前端 JWT 解码只用于展示，不用于授权。
- 默认情况下，所有业务请求必须带 Bearer token。
- 每次业务请求：① 透传 token 到 IAM token-healthz（撤销/在线检查）；② **后端用 JWKS 本地 RS256 验签 + iss/aud/exp 校验**；任一关失败，请求被拒。即使 healthz 语义变松也不会让伪造 claims 通过。
- token-healthz 不可用时返回 503，失败关闭，不绕过认证。
- `ZW_BRAIN_DEV_IAM_BYPASS=1` 仅用于研发调试 IAM 网络不可达场景，且必须同时设置 `ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only` 才生效；启动时打 warning。生产部署不得设置。
- `ZW_BRAIN_IAF_VERIFY_SSL=false` 同样要求 `ZW_BRAIN_IAF_INSECURE_TLS_DEV_ACK=development-only` 双因子，生产部署不得设置。
- 登出请求会把前端持有的 `id_token` 作为 `id_token_hint` 一起转发给 IAM `logout_endpoint`，配合 `post_logout_redirect_uri` 才能无确认页跳转回业务页。
- `sessionStorage` 只在当前浏览器会话内保存 token。
- 用户展示字段经过 `textContent` 或 `escapeHtml()` 输出，避免直接拼接未处理 HTML。
- 登出同时清理前端 token 和 IAM SSO 会话。
- `redirect_uri` 必须同源，避免 open redirect。

## 14. 配置项

主要环境变量：

| 变量 | 说明 |
| --- | --- |
| `ZW_BRAIN_IAF_AUTH_SERVER_URL` | IAM/IAF 认证服务基础地址，例如 `https://iaf.example.internal/auth` |
| `ZW_BRAIN_IAF_REALM` | IAM realm |
| `ZW_BRAIN_IAF_CLIENT_ID` | IAM client id |
| `ZW_BRAIN_IAF_CLIENT_SECRET` | IAM client secret，仅后端使用 |
| `ZW_BRAIN_IAF_CA_FILE` | 内部 CA bundle 文件路径 |
| `ZW_BRAIN_IAF_VERIFY_SSL` | 是否校验 IAM HTTPS 证书；设为 `false` 需配合下一行 ack 才生效 |
| `ZW_BRAIN_IAF_INSECURE_TLS_DEV_ACK` | 必须设置为 `development-only` 才允许关闭 TLS 校验；生产不得设置 |
| `ZW_BRAIN_DEV_IAM_BYPASS` | 研发期 IAM 网络不可达时临时绕过登录与 token-healthz；仅 `1` 生效；需要配合下一行 ack 才真正激活 |
| `ZW_BRAIN_DEV_IAM_BYPASS_ACK` | 必须设置为 `development-only` 才允许绕过激活；生产不得设置 |

## 15. API 契约与验证

OpenAPI 已同步以下端点：

- `/auth/iaf/config`
- `/auth/iaf/login`
- `/auth/iaf/token`
- `/auth/iaf/refresh`
- `/auth/iaf/logout`

`/api/snapshot` 与 `/api/skills/*` 已标记 BearerAuth，并包含 401、503 响应。

已验证测试：

```bash
python -m pytest tests/test_iaf_oidc.py tests/test_iaf_iam_e2e_offline.py tests/test_rest_runtime.py tests/test_webui_journey_contract.py tests/test_contract_projection.py -q
python -m pytest tests/test_brain_service.py -q
git diff --check
```

说明：当前环境无 `uv` 命令，实际使用 `python -m pytest` 运行同等测试集。
