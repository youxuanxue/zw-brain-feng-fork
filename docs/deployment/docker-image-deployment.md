# Docker 镜像文件部署手册

> **权威源对齐**（基线 `docs/approved/zw-brain-architecture.md`）：
> - 单租户：`tenant_id=sd-default`（不启用 multi-tenant；基线 §8.2 + MEMORY sd-default）
> - schema：SQLAlchemy `Base.metadata.drop_all + create_all` 容器首次启动自动重建（基线 §9.6），alembic 不进入产品基线
> - 模型调用：必须经集团推理平台，禁止直连第三方 LLM（基线 §3.4 / preflight 段 10）
> - 外部依赖：IAF IAM / 集团推理平台 / 区块链 adapter / 集团数据治理中心 / 集团数据安全中心 / 集团运维监控（基线 §3.4）
> - WebUI 页面：P1-P5/P7 + B1.1/B1.2 共 8 页面（基线 §5.2 硬上限 ≤8）；本镜像不构建大屏 / 指挥中心 / 演示页面（基线 §1.3）

本文说明如何从源码构建 `zw-brain` Docker 镜像、导出镜像文件，并在目标服务器通过镜像文件部署 REST WebUI/API。

## 1. 构建镜像

镜像默认内置 **agent-runtime**（Embedded SDK 依赖，来自 `vendor/agent-runtime/release/v0.1/` 离线包）与 `agents/`。在 **zw-brain 仓库根目录** 构建即可，**无需**同级 `agent-runtime` 源码仓库：

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

> 外部 Agent 接入不需独立容器入口：通过 `AGENT.yaml` 经 AgentRuntime 内核运行（基线 §8.1 / R15），协议规范以 `docs/agent-runtime/*` 为准；如未来出 Standalone HTTP 形态再扩入口。  
> Embedded 启用与环境变量见 [`agent-runtime-embedded.md`](agent-runtime-embedded.md)（勿直接 `source` 旧环境 `agent-runtime/.env.local` 中的路径项）。

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

> Schema 生命周期：容器启动时 `zw_brain.shared.migrate.ensure_runtime_schema()` 校验必需表/列是否齐全——**齐全则跳过**，**缺失列/表时执行 `drop_all + create_all`**（**会清空所有数据**，基线 §9.6）。挂载持久化目录可用于跨升级保留数据；**当模型 schema 发生不向后兼容变更时（缺列触发 reset），数据将被清空**——升级前必须由运维评估是否备份。首客户上线 + 首次生产 schema 变更后再启 alembic baseline。

SQLite 数据库默认建议挂载到宿主机目录，避免容器重建导致数据丢失：

```bash
sudo mkdir -p /opt/zw-brain/data
```

容器内固定数据目录为 `/data/zw-brain`，默认数据库路径为：

```text
/data/zw-brain/zw_brain.db
```

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
  -v /opt/zw-brain/data:/data/zw-brain \
  --env-file /opt/zw-brain/.env \
  zw-brain:1.0.0
```

> `.env` 里至少填：`ZW_BRAIN_INFERENCE_GATEWAY_URL` / `ZW_BRAIN_INFERENCE_API_KEY`(或 `_REF`) /
> `ZW_BRAIN_INFERENCE_MODEL` + IAF 一组 + 生产的 `ZW_BRAIN_SESSION_REDIS_URL`；清单见 `.env.example`。
> 单条覆盖可继续追加 `-e KEY=VALUE`（`-e` 优先于 `--env-file`）。

个别变量临时覆盖示例（在 `--env-file` 基础上追加）：

```bash
docker run -d --name zw-brain-rest -p 8800:8800 \
  -v /opt/zw-brain/data:/data/zw-brain \
  --env-file /opt/zw-brain/.env \
  -e ZW_BRAIN_DB_PATH=/data/zw-brain/zw_brain.db \
  zw-brain:1.0.0
```

其中 IAF 相关地址/密钥仅为示例；生产环境按实际 DNS、证书和密钥管理方案替换（密钥走 `*_REF` 指针，
不把真实密钥写入文档或镜像）。`.env.example` 是本机与 docker 共用的外部变量单一清单。

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
   被判 `redirect origin mismatch`。IAF 侧 `redirect_uri` 白名单也要登记到外部 `https://<host>:<port>/zw-brain/`。

> 健康检查在反代后为 `https://<host>:<port>/zw-brain/health`；裸 `/health` 仅供容器内直连探活。

## 5. 常用环境变量

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `ZW_BRAIN_IAF_AUTH_SERVER_URL` | IAF/OIDC 认证服务地址，例如 `https://iaf.example.internal/auth`；部署时替换为目标环境地址 | 必填（接入 IAF/OIDC 时） |
| `ZW_BRAIN_IAF_REALM` | IAF realm，例如 `replace-me-realm` | 按运行配置解析 |
| `ZW_BRAIN_IAF_CLIENT_ID` | IAF client id，例如 `replace-me-client-id` | 按运行配置解析 |
| `ZW_BRAIN_IAF_CLIENT_SECRET` | IAF client secret；只允许通过运行时环境变量注入，示例中使用 `replace-me-client-secret` 占位 | 未设置 |
| `ZW_BRAIN_DB_PATH` | SQLite 数据库文件路径 | `/data/zw-brain/zw_brain.db` |
| `ZW_BRAIN_DATABASE_URL` | SQLAlchemy 数据库 URL；设置后优先于 `ZW_BRAIN_DB_PATH` | 未设置 |
| `ZW_BRAIN_REST_HOST` | REST 监听地址 | `0.0.0.0` |
| `ZW_BRAIN_REST_PORT` | REST 监听端口 | `8800` |
| `ZW_BRAIN_REST_BASE_URL` | REST 对外基础 URL，用于契约投影等场景 | `http://127.0.0.1:<REST端口>` |
| `ZW_BRAIN_TENANT_ID` | 默认租户标识；Phase 1 固定 `sd-default`（单租户单省山东；基线 §8.2） | `sd-default` |
| `ZW_BRAIN_INFERENCE_GATEWAY_URL` | 集团推理平台 gateway URL；所有 LLM / Embedding / ASR / Rerank / OCR 调用必须经此入口（基线 §3.4 + preflight 段 10） | 必填（生产环境） |
| `ZW_BRAIN_INFERENCE_API_KEY_REF` | 集团推理平台 API key 引用（密钥引用，非明文）；密钥材料不进入镜像；部署层解析后注入字面 `ZW_BRAIN_INFERENCE_API_KEY` 供运行时读取 | 必填（生产环境） |
| `ZW_BRAIN_IAF_CA_FILE` | IAF HTTPS 自定义 CA 证书文件路径（容器内路径），用于挂载内部 CA bundle | 未设置（使用系统默认信任链） |
| `ZW_BRAIN_IAF_VERIFY_SSL` | 设为 `false` 时完全跳过 IAF 端点 SSL 验证（仅限测试/内网无证书环境） | `true` |
| `ZW_BRAIN_DEV_IAM_BYPASS` | 研发期 IAM 网络不可达时临时跳过登录与 token-healthz；须与 `ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only` 同时设置才生效；生产部署不得设置 | 未设置 |
| `ZW_BRAIN_DEV_IAM_BYPASS_ACK` | bypass 双因子确认字；仅 `development-only` 与 `ZW_BRAIN_DEV_IAM_BYPASS=1` 联用 | 未设置 |
| `ZW_BRAIN_SESSION_REDIS_URL` | BFF 会话 Redis URL；**多 REST 副本 / 生产必填**（例如 `redis://redis:6379/0`） | 未设置（单 worker 内存会话） |
| `ZW_BRAIN_SESSION_REDIS_KEY_PREFIX` | Redis session key 前缀 | `zw-brain:session:` |
| `ZW_BRAIN_DEPLOY_MODE` | 设为 `prod` / `production` 时强制要求 `ZW_BRAIN_SESSION_REDIS_URL` | 未设置 |
| `ZW_BRAIN_AGENT_RUNTIME_ENABLED` | 启用 Embedded AgentRuntime 与 `/api/agent-runtime/*` 任务接口 | 未设置（关闭） |
| `ZW_BRAIN_AGENT_RUNTIME_PROFILE` | `local_dev` 或 `embedded_single_tenant` | 镜像内按环境配置 |
| `ZW_BRAIN_AGENT_RUNTIME_CONFIG` | `agent-runtime.yaml` 路径 | 镜像内 `/app/agent-runtime.yaml` |
| `ZW_BRAIN_AGENTS_DIR` | 内置 Agent 清单目录 | 镜像内 `/app/agents` |
| `ZW_BRAIN_AGENT_RUNTIME_SCHEMA` | `agent.schema.json` 路径 | 镜像内 `/app/schemas/agent.schema.json` |
| `ZW_BRAIN_INFERENCE_GATEWAY_URL` | Embedded Agent 经集团推理网关（与 zw-brain LLM 同一约束） | 启用 AgentRuntime 时必填 |
| `ZW_BRAIN_INFERENCE_MODEL` | 推理模型名 | 启用 AgentRuntime 时必填 |
| `ZW_BRAIN_INFERENCE_API_KEY` | 集团推理网关 API Key；Embedded 启动时写入 `OPENAI_COMPATIBLE_API_KEY` | 网关需鉴权时必填；不鉴权可设任意非空占位（如 `unused`）或配合 `ZW_BRAIN_INFERENCE_API_KEY_OPTIONAL=1` |
| `ZW_BRAIN_INFERENCE_API_KEY_OPTIONAL` | `1` 表示网关不要求 API Key，自动使用占位 `unused` | 未设置 |
| `ZW_BRAIN_PLATFORM_DOCS_ROOTS` | 平台指南 Agent 可读文档根目录（`os.pathsep` 分隔）；Docker 默认 `/app/docs` | 未设置时为本机仓库 `docs/` |

如需接入 IAF/OIDC、外部数据库或集团推理平台，应通过环境变量注入对应配置，不要把密钥、连接串或证书写入镜像。内网部署若 IAF 使用自签名证书，优先挂载 CA bundle（`ZW_BRAIN_IAF_CA_FILE`）；仅在无法提供证书时才使用 `ZW_BRAIN_IAF_VERIFY_SSL=false`。

启用 Embedded AgentRuntime 示例（在 §4 `docker run` 基础上追加）：

```bash
docker run -d \
  ... \
  -e ZW_BRAIN_AGENT_RUNTIME_ENABLED=1 \
  -e ZW_BRAIN_AGENT_RUNTIME_PROFILE=embedded_single_tenant \
  -e ZW_BRAIN_INFERENCE_GATEWAY_URL=https://<集团推理网关>/v1 \
  -e ZW_BRAIN_INFERENCE_MODEL=<模型名> \
  -e ZW_BRAIN_INFERENCE_API_KEY=unused \
  # 或网关需鉴权：-e ZW_BRAIN_INFERENCE_API_KEY=<真实密钥>
  # 或不鉴权且不想传 Key：-e ZW_BRAIN_INFERENCE_API_KEY_OPTIONAL=1
  # 注意：docker -e 用 VAR=value，不要写 VAR=='value'（会把引号传入容器）
  zw-brain:1.0.0
```

校验：`curl http://127.0.0.1:8800/health` 的 `agent_runtime.enabled` 应为 `true`；`curl http://127.0.0.1:8800/api/agent-runtime/status` 列出内置 Agent（需 IAM 会话或 dev bypass，见 [`agent-runtime-embedded.md`](agent-runtime-embedded.md)）。

REST WebUI 登录采用 **IAM 授权码 + BFF 会话**（详见 `docs/iam-login-logout-implementation.md`）：前端 URL 无 `code` 且后端 `/auth/iaf/session` 未返回有效会话时会跳转到 IAM 授权端点；回跳后由后端 `/auth/iaf/token` 代理 code 换取 IAM token 并写入服务端 session。浏览器仅通过 `zw_brain_session` HttpOnly cookie 携带不透明 session id；前端 JavaScript 只保存公开会话摘要与 CSRF token，**不接收、不保存、不发送** IAM access token 或 refresh token。前端每 5 分钟请求 `/auth/iaf/refresh` 由后端刷新 session 内 token；所有 `/api/*` 浏览器请求使用同源 cookie 鉴权，写请求额外携带 `X-CSRF-Token`，后端仍透传 session 内 access token 到 `{ZW_BRAIN_IAF_AUTH_SERVER_URL}/v1/token-healthz` 校验并本地 RS256 验签，校验不可用时按 503 失败关闭。退出登录会清理服务端 session 与 HttpOnly cookie，再跳转 IAM `/protocol/openid-connect/logout?redirect_uri=...` 清除 SSO 会话。

开发环境若无法连通 IAM 服务端，须**同时**设置 `ZW_BRAIN_DEV_IAM_BYPASS=1` 与 `ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only`：WebUI 不跳转 IAM，后端 `/api/snapshot` 与 `/api/skills/*` 走 bypass 路径，但仍执行 Skill manifest、角色、租户和人工确认等业务门禁。该开关只用于研发调试，生产部署清单不要设置。

> **prod guard**：`scripts/check_iam_prod_guard.py`（preflight 段 23）拦截 prod 部署清单中的 dev-iam-bypass 关键字；`ZW_BRAIN_DEPLOY_MODE=prod` 时 `zw-brain-rest` 启动还要求 `ZW_BRAIN_SESSION_REDIS_URL`（见 §5 环境变量表与 `docs/preflight-debt.md`）。

## 6. 旧平台数据迁移

如果需要在部署后导入脱敏旧平台 dump，可将 dump 目录挂载到容器中运行迁移命令：

```bash
docker run --rm \
  -v /opt/zw-brain/data:/data/zw-brain \
  -v /path/to/desensitized-legacy-dumps:/legacy-dumps:ro \
  -e ZW_BRAIN_DB_PATH=/data/zw-brain/zw_brain.db \
  zw-brain:1.0.0 \
  zw-brain-migrate-legacy \
    --dumps-dir /legacy-dumps \
    --db-path /data/zw-brain/zw_brain.db \
    --profile customer-core-v1 \
    --strict \
    --acceptance \
    --report /data/zw-brain/migration-acceptance-report.json
```

如需清空并重建目标库，可在确认数据可丢弃后追加 `--reset-db`。

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

升级镜像时，先导入新镜像，再停止并重建容器；保留 `/opt/zw-brain/data` 数据目录即可复用数据库。

## 8. 构建后自检命令

```bash
docker run --rm zw-brain:1.0.0 zw-brain-cli --help

mkdir -p /tmp/zw-brain-docker-data

docker run -d \
  --name zw-brain-rest-test \
  -p 8800:8800 \
  -v /tmp/zw-brain-docker-data:/data/zw-brain \
  zw-brain:1.0.0
curl http://127.0.0.1:8800/health
docker rm -f zw-brain-rest-test
```
