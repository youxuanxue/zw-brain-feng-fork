# Docker 镜像文件部署手册

> **权威源对齐**（基线 `docs/approved/zw-brain-architecture.md`）：
> - 单租户：`tenant_id=sd-default`（不启用 multi-tenant；基线 §8.2 + MEMORY sd-default）
> - schema：**alembic baseline stamp → upgrade head**（D58，反转 D23）。容器首次启动 `ensure_runtime_schema()`：空库 → 建全部表；存量库（无版本表、schema 与模型一致）→ baseline-stamp（零 DDL、**不 DROP**）后向前迁移；真实漂移无迁移可上 → 拒启（绝不清库）。破坏性重置仅 `ZW_BRAIN_ALLOW_SCHEMA_RESET=1` 显式开关下可走
> - 模型调用：由独立 AgentRuntime 服务经集团推理平台承载；zw-brain REST 不持有推理 SDK/env
> - 外部依赖：IAF IAM / 集团推理平台 / 区块链 adapter / 集团数据治理中心 / 集团数据安全中心 / 集团运维监控（基线 §3.4）
> - WebUI 页面：P1-P5/P7 + B1.1/B1.2 共 8 页面（基线 §5.2 硬上限 ≤8）；本镜像不构建大屏 / 指挥中心 / 演示页面（基线 §1.3）

本文说明如何从源码构建 `zw-brain` Docker 镜像、导出镜像文件，并在目标服务器通过镜像文件部署 REST WebUI/API。

## 1. 构建镜像

**D68 单一模型**：zw-brain 镜像**不再内置 agent-runtime**（embedded 退役，进程内零 SDK），只含 `agents/`（供能力列出）。AgentRuntime 是**独立服务**——单独构建 `Dockerfile.agent-runtime`（来自 `vendor/agent-runtime/release/v1.1.3/` 离线包）或用 `docker-compose` 的 `agent-runtime` 服务；zw-brain 运行时设 `ZW_BRAIN_AGENT_RUNTIME_ENABLED=1` + `ZW_BRAIN_AGENT_RUNTIME_URL` 指向它。`ZW_BRAIN_AGENT_RUNTIME_MODE=http` 只保留为 `start-local.sh` 本地兼容启动开关，不是生产运行形态选择。zw-brain 镜像在仓库根构建即可：

```bash
cd /path/to/zw-brain
docker build -t zw-brain:1.0.0 .
```

离线包路径与升级说明见 [`vendor/agent-runtime/README.md`](../../vendor/agent-runtime/README.md)。

> 构建阶段会解压 tar.gz、执行 `./install.sh` 并安装 `requirements.txt` 中的运行时依赖；镜像内 `agent.schema.json` 来自仓库 `schemas/`。  
> **WebUI**：`Dockerfile` 的 `web-builder` 阶段在镜像内执行 `npm ci` + `npm run build`，生成 `zw-brain-web/dist-vite/` 并打入 Python wheel；**无需**在宿主机先手动构建前端。本地非 Docker 开发仍可用 `scripts/start-local.sh`（缺产物时自动 build）或 `cd zw-brain-web && npm ci && npm run build`。

镜像默认启动 `zw-brain-rest`，同时内置以下运行入口，可通过 `docker run ... <command>` 覆盖：

- `zw-brain-rest`：REST API + WebUI，默认端口 `8800`
- `zw-brain-cli`：命令行调用 Skill
- `zw-brain-mcp`：MCP 入口
- `zw-brain-a2a`：A2A 入口
- `zw-brain-migrate-legacy`：旧平台数据迁移入口

> 外部 Agent 接入不需独立容器入口：`AGENT.yaml` 由**独立的 AgentRuntime 服务**运行（D68 单一模型），协议规范以 `docs/agent-runtime/*` 为准。  
> AgentRuntime 镜像单独构建：`docker build -f Dockerfile.agent-runtime -t zw-brain-agent-runtime:1.1.3 .`（离线包 + `agents/` + entrypoint 渲染 openapi servers）。两服务**一起部署**最简路径见 §1.1（`docker-compose`）。embedded（进程内 SDK）形态已随 D68 退役（决策见 decision-log D68 + `docs/decisions/agentruntime-formfactor-proposal.md`）。

## 1.1 docker-compose：一起部署 pg + agent-runtime + zw-brain（dev/演示推荐）

D68 单一模型下，**两个服务一起部署**：仓库根 `docker-compose.yml` 已含三件套——`postgres`（库）、
`agent-runtime`（独立 AR 服务，:8001）、`zw-brain`（REST + WebUI，:8800，经 HTTP 驱动 AR）。一条命令同起：

```bash
cd /path/to/zw-brain
cp .env.example .env          # 填集团推理网关（决定 Agent 是否“真的会思考”），其余用默认
docker compose up -d          # 起 postgres → agent-runtime（healthy）→ zw-brain（depends_on healthy）
docker compose ps             # 三个容器 healthy
curl http://127.0.0.1:8800/health        # zw-brain REST
curl http://127.0.0.1:8001/runtime/health # 独立 AR
```

> ⚠️ compose 的 `zw-brain` 服务是 **dev/演示姿态**（`ZW_BRAIN_DEPLOY_MODE=dev` + IAM 免登录），仅本地看效果。
> 生产用 §4 的 `docker run --env-file`（真 IAF/OIDC + Redis 会话 + prod fail-closed 守卫）。

**agents 单一源（一处维护，两服务共读）**：`agents/*/AGENT.yaml` 已纳入 zw-brain git，是被两边共读的**单一事实源**——
AR 用它**跑** Agent，zw-brain 用它**列** Agent。compose 把 `./agents` 以**只读卷**挂进两个服务（`./agents:/app/agents:ro`
给 zw-brain 列、`./agents:/srv/agents-src:ro` 给 AR 跑），加一个 Agent 两边即时同步、无需重建镜像。

- **AR 容器 entrypoint** 把只读源拷到可写 `/app/agents`，再按 `ZW_BRAIN_REST_BASE_URL`（compose 内 = `http://zw-brain:8800`）
  渲染各 `*.openapi.yaml` 的 `servers.url`——因为 AgentRuntime **不解析** spec 内 `${env:}`，跨容器回调地址须在部署期落成字面量（见 `scripts/render-agent-specs.sh`）。本地 start-local 用 committed 默认 `http://127.0.0.1:8800`，无需渲染。
- **智能体页自动派生**：WebUI【智能体】页从 `/api/agent-runtime/agents` 的 `category`、`agent_class`、`agent_type_label` 渲染 A 类平台内副驾与 B 类外部用数方智能体——给新 Agent 打 `labels.surface: agent`、`labels.scenario_class: A/B` 即自动进对应分组并可跳转对话，**零前端改动**。

> 渲染只在 **AR 容器**发生（跨容器服务名不同）；zw-brain 容器只「列」不回调，无需渲染。生产把 `agent-runtime` 服务的
> `command` 切回默认 CMD（`agent-runtime.yaml` / `trusted_gateway`；compose 默认的 `agent-runtime.dev.yaml` 也走 trusted_gateway，只是存储更轻）。

## 2. 导出与导入镜像文件

在构建机导出：

```bash
docker save zw-brain:1.0.0 -o zw-brain-1.0.0.tar
```

将 `zw-brain-1.0.0.tar` 拷贝到目标服务器后导入：

```bash
docker load -i zw-brain-1.0.0.tar
```

确认镜像存在：

```bash
docker images zw-brain
```

## 3. 准备持久化目录

> Schema 生命周期（D58，反转 D23）：容器启动 `zw_brain.shared.migrate.ensure_runtime_schema()` 走 **alembic forward-migration**，**绝不再 `drop_all`**：
> - **空库** → `alembic upgrade head` 建全部表；
> - **存量库**（有数据、无 `alembic_version`、schema 与当前模型一致）→ `alembic stamp <baseline>`（**零 DDL、保数据**）后 `upgrade head`；
> - **已纳管库**（有 `alembic_version`）→ `upgrade head` 幂等续迁；
> - **真实漂移**（有数据、无版本表、schema 与模型不一致、且无迁移可向前应用）→ **拒启**（`SchemaDriftError`，绝不清库）。正确演进路径是补一条 alembic 向前迁移再 `upgrade head`。
>
> 破坏性重置（`drop_all + create_all`）已退役出自动路径，仅在**显式**设置 `ZW_BRAIN_ALLOW_SCHEMA_RESET=1` 时可走（M5 fail-closed）；生产/试用库严禁。后端 PG-only，数据持久化在 PG 实例侧（卷 / 备份），容器本身无状态；升级前由运维评估是否备份 PG。

**后端 = PostgreSQL only**（`postgresql+psycopg://...`，镜像须含 `zw-brain[postgres]`；SQLite 已退役）：
经 `ZW_BRAIN_DATABASE_URL` 指向托管 PG 实例，数据持久化由 PG 侧负责（卷 / 备份），容器本身无状态。
镜像不自带 PG，本地开发用仓库根 `docker-compose.yml` 起一个；生产指向运维托管的 PG 实例。

> 容器内连 PG 须用宿主机 / 内网可达地址（`127.0.0.1` 在容器内指向容器自身）；用 `--add-host`
> 或内网 DNS 解析 PG host。

## 4. 启动 REST WebUI/API

项目统一使用 uv 进行 Python 构建与包管理，因此容器镜像也沿用 uv，保证本地、CI 和生产工具链一致。

**推荐：用 `--env-file` 读同一份 `.env`**（与本机 `start-local.sh` 共用 `.env.example` 契约，
单一事实来源，避免 docker 与本机两套 `-e` 手维护漂移）：

```bash
# 由 .env.example 派生：cp .env.example .env && 填真实值（.env 不进版本库/镜像）
docker run -d \
  --name zw-brain-rest \
  --restart unless-stopped \
  -p 8800:8800 \
  --env-file /opt/zw-brain/.env \
  zw-brain:1.0.0
```

> `.env` 里至少填：`ZW_BRAIN_DATABASE_URL`（指向托管 PG，须容器内可达） +
> IAF 一组 + 生产的 `ZW_BRAIN_SESSION_REDIS_URL` + AgentRuntime 指向
> `ZW_BRAIN_AGENT_RUNTIME_URL` + zw-brain 与 AgentRuntime 共用的 `AGENT_RUNTIME_GATEWAY_SIGNING_SECRET`。
> 模型网关变量只给独立 `agent-runtime` 服务：
> `OPENAI_COMPATIBLE_BASE_URL` / `OPENAI_COMPATIBLE_API_KEY` / `AGENT_RUNTIME_DEFAULT_MODEL`。
> 清单见 `.env.example`。
> 单条覆盖可继续追加 `-e KEY=VALUE`（`-e` 优先于 `--env-file`）。后端 PG-only，容器无本地数据卷。

个别变量临时覆盖示例（在 `--env-file` 基础上追加）：

```bash
docker run -d --name zw-brain-rest -p 8800:8800 \
  --env-file /opt/zw-brain/.env \
  -e ZW_BRAIN_DATABASE_URL=postgresql+psycopg://zw_brain:***@db.intranet:5432/zw_brain \
  zw-brain:1.0.0
```

其中 IAF 相关地址/密钥仅为示例；生产环境按实际 DNS、证书和密钥管理方案替换（密钥走 `*_REF` 指针，
不把真实密钥写入文档或镜像）。`.env.example` 是本机与 docker 共用的外部变量单一清单。

> 排障日志：容器内不设 `ZW_BRAIN_LOG_DIR`、设 `ZW_BRAIN_LOG_FORMAT=json`，结构化日志走
> stdout/stderr 由 `docker logs zw-brain-rest` 收集；落文件需求挂卷后设 `ZW_BRAIN_LOG_DIR`。
> 字段字典与排障剧本见 [`../ops/logging.md`](../ops/logging.md)。

健康检查：

```bash
curl http://127.0.0.1:8800/health
```

WebUI 访问地址（前缀部署，见 §4.1）：

```text
http://<服务器IP>:8800/zw-brain/
```

> WebUI 构建 base 为 `/zw-brain/`（`zw-brain-web/vite.config.ts`），正规入口带 `/zw-brain/` 前缀。
> 直连容器访问裸 `/` 仍可打开（后端对无前缀路径保留 back-compat），但反代网关后必须走前缀，见下。

## 4.1 反代前缀部署（/zw-brain/）

本服务设计为可挂在反向代理子路径 `/zw-brain/` 下（前后端前缀单一事实源：
前端 `vite base=/zw-brain/`、后端 `zw_brain/entry/rest/server.py::APP_PATH_PREFIX`）。
网关（如 nginx）需满足两点，否则 WebUI 资产或 OIDC 登录回跳会失败：

1. **把 `/zw-brain/` 子路径转发到容器 8800**（路径前缀保留，不要 strip）：

```nginx
location /zw-brain/ {
    proxy_pass http://127.0.0.1:8800;          # 末尾不加 /，保留 /zw-brain/ 前缀
    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-Host  $host;   # 含外部端口，如 aip.example.cn:9443
    proxy_set_header X-Forwarded-Port  $server_port;
    proxy_set_header X-Forwarded-Proto $scheme; # https 时务必为 https
}
```

2. **必须转发 `X-Forwarded-Host` / `X-Forwarded-Port` / `X-Forwarded-Proto`**：后端用它们还原
   外部 origin 来做 OIDC `redirect_uri` 同源校验（精确比对 scheme+host:port）。缺失会导致登录回跳
   被判 `redirect origin mismatch`。BFF 只接受同源且路径位于 `/zw-brain/` 下的登录/登出回跳，并在授权码流程
   使用 PKCE S256；IAF 侧 `Valid Redirect URIs` 也必须精确登记外部 `https://<host>:<port>/zw-brain/`，
   不允许 `*`、外部域名、`javascript:`、`file:` 或带 fragment 的回调。

### 4.1 生产安全基线（0624 渗透整改）

完整整改矩阵与复扫口径见 `docs/deployment/security-hardening-0623-pentest.md`；本节只列部署必须满足的基线。

本仓应用层已收口以下边界：

- `ZW_BRAIN_DEPLOY_MODE=prod|production` 时，`/openapi.json` 不再匿名公开；必须携带有效 BFF session cookie 或 Bearer token，且身份具备 `ROLE_SYSTEM`，否则返回 401/403。dev/演示模式保留匿名读取，供本地工具链使用。
- `/auth/iaf/login` 与 `/auth/iaf/logout` 的 `redirect_uri` 只接受当前外部 origin + `/zw-brain/` 应用前缀，拒绝跨域、跨端口、非应用路径和 fragment。
- BFF 发起授权码登录时带 `code_challenge_method=S256`，换票时提交对应 `code_verifier`；浏览器响应体仍不暴露 access/refresh/id token，也不暴露 client secret 环境变量名。

以下项属于 IAF/Keycloak 与其前置 nginx 配置，必须由客户 IAM/网关侧同步完成；zw-brain 仓内只能提供 BFF 侧防线，不能替代授权服务器配置：

- Keycloak 客户端 `zw-brain` 的 `Valid Redirect URIs` 仅保留 `https://<host>:<port>/zw-brain/`，删除 `*` 和任何外部域名通配；启用严格 redirect 校验。
- Keycloak 客户端启用 PKCE，要求 `S256`，禁用/不接受 `plain`。
- Keycloak/nginx CORS 只允许 `https://<host>:<port>`，不得反射任意 `Origin`，不得允许 `null` origin；若返回 `Access-Control-Allow-Credentials: true`，必须同时返回精确白名单 origin，并加 `Vary: Origin`。
- 登录失败文案使用统一错误，不区分“用户名不存在 / 密码错误 / 账户锁定”；认证端点配置速率限制。
- Keycloak 4.6.0 属过旧版本，生产应升级到受维护版本；升级前至少用网关/WAF 拦截异常 `redirect_uri` payload，避免授权端点 500。

复扫验证口径：

```bash
# 只读 live check：OpenAPI、BFF redirect、Keycloak redirect/CORS 一次性核验
python3 scripts/security/check_pentest_0623.py \
  --app-base https://<host>:<port>/zw-brain \
  --iam-base https://<iaf-host>:9443/auth \
  --realm picp \
  --client-id zw-brain \
  --expected-origin https://<host>:<port>
# 若目标是内网地址且执行环境设置了 HTTP(S)_PROXY，在内网机/跳板上加 --no-proxy。

# 匿名生产 OpenAPI 应拒绝（401 或 403，不应 200）
curl -s -o /dev/null -w "%{http_code}\n" https://<host>:<port>/zw-brain/openapi.json

# IAF 授权端点恶意 redirect_uri 应在 Keycloak 侧拒绝，不应跳转到外域
curl -I 'https://<iaf-host>:9443/auth/realms/picp/protocol/openid-connect/auth?client_id=zw-brain&redirect_uri=https%3A%2F%2Fevil.example%2Fsteal&response_type=code&scope=openid'

# Keycloak CORS 不得反射恶意 Origin + credentials
curl -sI -H 'Origin: https://evil.example' 'https://<iaf-host>:9443/auth/realms/picp' | grep -Ei 'access-control-allow-origin|access-control-allow-credentials|vary'
```

> 健康检查在反代后为 `https://<host>:<port>/zw-brain/health`；裸 `/health` 仅供容器内直连探活。

## 5. 常用环境变量

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `ZW_BRAIN_IAF_AUTH_SERVER_URL` | IAF/OIDC 认证服务地址，例如 `https://iaf.example.internal/auth`；部署时替换为目标环境地址 | 必填（接入 IAF/OIDC 时） |
| `ZW_BRAIN_IAF_REALM` | IAF realm，例如 `replace-me-realm` | 按运行配置解析 |
| `ZW_BRAIN_IAF_CLIENT_ID` | IAF client id，例如 `replace-me-client-id` | 按运行配置解析 |
| `ZW_BRAIN_IAF_CLIENT_SECRET` | IAF client secret；只允许通过运行时环境变量注入，示例中使用 `replace-me-client-secret` 占位 | 未设置 |
| `ZW_BRAIN_DATABASE_URL` | PostgreSQL SQLAlchemy URL（**唯一 DB 旋钮**，后端 PG-only）；不设时默认本地 PostgreSQL `postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5432/zw_brain`，须装 `zw-brain[postgres]`（psycopg v3）。容器内须用宿主机/内网可达地址（非 `127.0.0.1`） | 默认本地 PG |
| `ZW_BRAIN_REST_HOST` | REST 监听地址 | `0.0.0.0` |
| `ZW_BRAIN_REST_PORT` | REST 监听端口 | `8800` |
| `ZW_BRAIN_REST_BASE_URL` | REST 对外基础 URL，用于契约投影等场景 | `http://127.0.0.1:<REST端口>` |
| `ZW_BRAIN_TENANT_ID` | 默认租户标识；Phase 1 固定 `sd-default`（单租户单省山东；基线 §8.2） | `sd-default` |
| `ZW_BRAIN_IAF_CA_FILE` | IAF HTTPS 自定义 CA 证书文件路径（容器内路径），用于挂载内部 CA bundle | 未设置（使用系统默认信任链） |
| `ZW_BRAIN_IAF_VERIFY_SSL` | 设为 `false` 时跳过 IAF 端点 SSL 验证（仅限测试/内网无证书环境）；须与 `ZW_BRAIN_IAF_INSECURE_TLS_DEV_ACK=development-only` 联用才生效。**`ZW_BRAIN_DEPLOY_MODE=prod` 下二者联用会 fail-closed 拒绝启动（M5：关闭 IAM TLS 校验=MITM 面）** | `true` |
| `ZW_BRAIN_IAF_INSECURE_TLS_DEV_ACK` | 关闭 IAF TLS 校验的双因子确认字；仅 `development-only` 与 `ZW_BRAIN_IAF_VERIFY_SSL=false` 联用；prod 部署不得设置 | 未设置 |
| `ZW_BRAIN_DEV_IAM_BYPASS` | 研发期 IAM 网络不可达时临时跳过登录与 token-healthz；须与 `ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only` 同时设置才生效；生产部署不得设置 | 未设置 |
| `ZW_BRAIN_DEV_IAM_BYPASS_ACK` | bypass 双因子确认字；仅 `development-only` 与 `ZW_BRAIN_DEV_IAM_BYPASS=1` 联用 | 未设置 |
| `ZW_BRAIN_SESSION_REDIS_URL` | BFF 会话 Redis URL；**多 REST 副本 / 生产必填**（例如 `redis://redis:6379/0`） | 未设置（单 worker 内存会话） |
| `ZW_BRAIN_SESSION_REDIS_KEY_PREFIX` | Redis session key 前缀 | `zw-brain:session:` |
| `ZW_BRAIN_DEPLOY_MODE` | **镜像默认 `prod`**（生产姿态：M5 fail-closed 守卫激活——拒 dev-iam-bypass、拒 insecure-TLS；并强制要求 `ZW_BRAIN_SESSION_REDIS_URL`）。本地/演示部署须在 env-file 显式覆盖为 `dev`（或非 prod 值）才能用 dev bypass | **`prod`（镜像 ENV 默认；env-file 可覆盖）** |
| `ZW_BRAIN_AGENT_RUNTIME_ENABLED` | 启用 `/api/agent-runtime/*` 任务接口（zw-brain → 独立 AR） | 未设置（关闭） |
| `ZW_BRAIN_AGENT_RUNTIME_URL` | **独立 AgentRuntime 服务地址**，zw-brain 经 HTTP 驱动它；compose 内 = `http://agent-runtime:8001` | 启用时必填（单一模型） |
| `ZW_BRAIN_AGENTS_DIR` | Agent 清单目录（**单一源**：zw-brain 用它「列」、AR 用它「跑」） | 镜像内 `/app/agents` |
| `AGENT_RUNTIME_GATEWAY_SIGNING_SECRET` | zw-brain 调 AgentRuntime trusted_gateway 的共享签名密钥；两边必须一致，平台运维的重载/体检依赖它获得 `admin:runtime` | 生产必填 |
| `OPENAI_COMPATIBLE_BASE_URL` | **AgentRuntime 服务侧** OpenAI 兼容网关 base URL；zw-brain REST 不读取 | AR 启用模型时必填 |
| `OPENAI_COMPATIBLE_API_KEY` | **AgentRuntime 服务侧**网关 Bearer key；密钥只注入 AR 服务 | AR 启用模型时必填 |
| `AGENT_RUNTIME_DEFAULT_MODEL` | **AgentRuntime 服务侧**默认模型名 | AR 启用模型时必填 |

> D68 单一模型：`ZW_BRAIN_AGENT_RUNTIME_PROFILE` / `_CONFIG` / `_SCHEMA` 等 **embedded（进程内 SDK）配置已退役**（zw-brain 进程不再读）。
> Agent 的**模型凭据**配在**独立 AR 服务**（`agent-runtime` 容器 / `Dockerfile.agent-runtime`），不在 zw-brain 容器；平台指南 Agent 的文档根 `ZW_BRAIN_PLATFORM_DOCS_ROOTS` 同样配在 AR 服务侧（compose 已注入）。

如需接入 IAF/OIDC、外部数据库或 AgentRuntime 模型网关，应通过环境变量注入对应配置，不要把密钥、连接串或证书写入镜像。内网部署若 IAF 使用自签名证书，优先挂载 CA bundle（`ZW_BRAIN_IAF_CA_FILE`）；仅在无法提供证书时才使用 `ZW_BRAIN_IAF_VERIFY_SSL=false`。

启用 AgentRuntime（D68 单一模型，独立 AR 服务）示例——zw-brain 容器只需指向独立 AR：

```bash
# (a) 先起独立 AgentRuntime 服务（:8001）；模型凭据配在 AR 侧
docker run -d --name zw-brain-agent-runtime -p 8001:8001 \
  -e OPENAI_COMPATIBLE_BASE_URL=https://<集团推理网关>/api/v3 \
  -e OPENAI_COMPATIBLE_API_KEY=<网关密钥或 unused> \
  -e AGENT_RUNTIME_DEFAULT_MODEL=<模型名> \
  -e AGENT_RUNTIME_GATEWAY_SIGNING_SECRET=<强随机共享密钥> \
  -e ZW_BRAIN_REST_BASE_URL=http://<zw-brain 容器可达地址>:8800 \
  zw-brain-agent-runtime:1.1.3
  # 注意：docker -e 用 VAR=value，不要写 VAR=='value'（会把引号传入容器）

# (b) zw-brain 容器经 HTTP 驱动它（在 §4 docker run 基础上追加）
docker run -d \
  ... \
  -e ZW_BRAIN_AGENT_RUNTIME_ENABLED=1 \
  -e ZW_BRAIN_AGENT_RUNTIME_URL=http://<AR 容器可达地址>:8001 \
  -e AGENT_RUNTIME_GATEWAY_SIGNING_SECRET=<同一个强随机共享密钥> \
  zw-brain:1.0.0
```

> 两容器互达地址按部署网络解析（同 host 用 `--add-host host.docker.internal:host-gateway` 或共用一个 docker 网络）；
> dev/演示直接用 §1.1 的 `docker compose up`（服务名 `agent-runtime` / `zw-brain` 自动互达，免手配地址）。

校验：`curl http://127.0.0.1:8800/health` 的 `agent_runtime.enabled` 应为 `true`；`curl http://127.0.0.1:8800/api/agent-runtime/agents` 列出 Agent（需 IAM 会话或 dev bypass）。

REST WebUI 登录采用 **IAM 授权码 + BFF 会话**（详见 `docs/iam-login-logout-implementation.md`）：前端 URL 无 `code` 且后端 `/auth/iaf/session` 未返回有效会话时会跳转到 IAM 授权端点；回跳后由后端 `/auth/iaf/token` 代理 code 换取 IAM token 并写入服务端 session。浏览器仅通过 `zw_brain_session` HttpOnly cookie 携带不透明 session id；前端 JavaScript 只保存公开会话摘要与 CSRF token，**不接收、不保存、不发送** IAM access token 或 refresh token。前端每 5 分钟请求 `/auth/iaf/refresh` 由后端刷新 session 内 token；所有 `/api/*` 浏览器请求使用同源 cookie 鉴权，写请求额外携带 `X-CSRF-Token`，后端仍透传 session 内 access token 到 `{ZW_BRAIN_IAF_AUTH_SERVER_URL}/v1/token-healthz` 校验并本地 RS256 验签，校验不可用时按 503 失败关闭。退出登录会清理服务端 session 与 HttpOnly cookie，再跳转 IAM `/protocol/openid-connect/logout?redirect_uri=...` 清除 SSO 会话。

开发环境若无法连通 IAM 服务端，须**同时**设置 `ZW_BRAIN_DEV_IAM_BYPASS=1` 与 `ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only`：WebUI 不跳转 IAM，后端 `/api/snapshot` 与 `/api/skills/*` 走 bypass 路径，但仍执行 Skill manifest、角色、租户和人工确认等业务门禁。该开关只用于研发调试，生产部署清单不要设置。

> **prod guard**：`scripts/check_iam_prod_guard.py`（preflight 段 23）拦截 prod 部署清单中的 dev-iam-bypass 关键字；`ZW_BRAIN_DEPLOY_MODE=prod` 时 `zw-brain-rest` 启动还要求 `ZW_BRAIN_SESSION_REDIS_URL`（见 §5 环境变量表与 `docs/preflight-debt.md`）。

## 6. 旧平台数据迁移

如果需要在部署后导入脱敏旧平台 dump，可将 dump 目录挂载到容器中运行迁移命令（目标库经
`ZW_BRAIN_DATABASE_URL` 指向托管 PG，报告落到挂载的卷或经 stdout 收集）：

```bash
docker run --rm \
  -v /path/to/desensitized-legacy-dumps:/legacy-dumps:ro \
  -v /opt/zw-brain/reports:/reports \
  -e ZW_BRAIN_DATABASE_URL=postgresql+psycopg://zw_brain:***@db.intranet:5432/zw_brain \
  zw-brain:1.0.0 \
  zw-brain-migrate-legacy \
    --dumps-dir /legacy-dumps \
    --profile customer-core-v1 \
    --strict \
    --acceptance \
    --report /reports/legacy-migration-report.json
```

如需清空并重建目标库，可在确认数据可丢弃后追加 `--reset-db`（该路径会自动设置 `ZW_BRAIN_ALLOW_SCHEMA_RESET=1` 走显式破坏性重置；不带 `--reset-db` 时迁移批走 `ensure_runtime_schema()` 的 alembic 向前迁移、**不 DROP**，D58）。

如旧平台 dump 含脏业务记录（测试/未命名标题、纯数字或「测试」用途、缺机构、悬空引用…），可追加 `--only-clean` 只导入符合 zw-brain 标准的干净业务记录（目录/资源/申请），不达标的在导入时跳过且记 `stats.skip`（行级、可审计，承 D11：不是造假，是只收够格的真实数据）；治理基线（机构/区划/字典/actor）不过滤。判据集中在 `zw_brain/adapters/legacy/clean_filter.is_clean_record`（业务方可调）。报告会记录 `only_clean: true`。全量 vs 干净的差异对照见 `docs/deployment/clean-vs-full-seed.md`。

```bash
docker run --rm \
  -v /path/to/desensitized-legacy-dumps:/legacy-dumps:ro \
  -v /opt/zw-brain/reports:/reports \
  -e ZW_BRAIN_DATABASE_URL=postgresql+psycopg://zw_brain:***@db.intranet:5432/zw_brain \
  zw-brain:1.0.0 \
  zw-brain-migrate-legacy \
    --dumps-dir /legacy-dumps --profile customer-core-v1 \
    --strict --acceptance --only-clean \
    --report /reports/legacy-migration-clean-report.json
```

## 7. 运维命令

查看日志：

```bash
docker logs -f zw-brain-rest
```

停止容器：

```bash
docker stop zw-brain-rest
```

删除容器：

```bash
docker rm zw-brain-rest
```

升级镜像时，先导入新镜像，再停止并重建容器；数据在托管 PG 实例侧，容器无状态，重建不丢数据（升级前按需备份 PG）。

## 8. 构建后自检命令

```bash
docker run --rm zw-brain:1.0.0 zw-brain-cli --help

# 自检需一个可达的 PG（本地用 docker compose up -d postgres，再用 host-gateway 让容器连到宿主机）
docker run -d \
  --name zw-brain-rest-test \
  -p 8800:8800 \
  --add-host host.docker.internal:host-gateway \
  -e ZW_BRAIN_DATABASE_URL=postgresql+psycopg://zw_brain:zw_brain@host.docker.internal:5432/zw_brain \
  zw-brain:1.0.0
curl http://127.0.0.1:8800/health
docker rm -f zw-brain-rest-test
```
