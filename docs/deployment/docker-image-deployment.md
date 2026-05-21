# Docker 镜像文件部署手册

本文说明如何从源码构建 `zw-brain` Docker 镜像、导出镜像文件，并在目标服务器通过镜像文件部署 REST WebUI/API。

## 1. 构建镜像

在仓库根目录执行：

```bash
docker build -t zw-brain:1.0.0 .
```

镜像默认启动 `zw-brain-rest`，同时内置以下运行入口，可通过 `docker run ... <command>` 覆盖：

- `zw-brain-rest`：REST API + WebUI，默认端口 `8800`
- `zw-brain-cli`：命令行调用 Skill
- `zw-brain-mcp`：MCP 入口
- `zw-brain-a2a`：A2A 入口
- `zw-brain-migrate-legacy`：旧平台数据迁移入口

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

```bash
docker run -d \
  --name zw-brain-rest \
  --restart unless-stopped \
  --add-host iaf.example.internal:127.0.0.1 \
  -p 8800:8800 \
  -v /opt/zw-brain/data:/data/zw-brain \
  -e ZW_BRAIN_DB_PATH=/data/zw-brain/zw_brain.db \
  -e ZW_BRAIN_IAF_AUTH_SERVER_URL=https://iaf.example.internal/auth \
  -e ZW_BRAIN_IAF_REALM=replace-me-realm \
  -e ZW_BRAIN_IAF_CLIENT_ID=replace-me-client-id \
  -e ZW_BRAIN_IAF_CLIENT_SECRET=replace-me-client-secret \
  zw-brain:1.0.0
```

其中 `--add-host` 和 IAF 相关变量仅用于本地或联调示例；生产环境应按实际 DNS、证书和密钥管理方案替换，不要把真实密钥写入文档或镜像。

健康检查：

```bash
curl http://127.0.0.1:8800/health
```

WebUI 访问地址：

```text
http://<服务器IP>:8800/
```

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
| `ZW_BRAIN_TENANT_ID` | 默认租户标识 | 按运行配置解析 |
| `ZW_BRAIN_IAF_CA_FILE` | IAF HTTPS 自定义 CA 证书文件路径（容器内路径），用于挂载内部 CA bundle | 未设置（使用系统默认信任链） |
| `ZW_BRAIN_IAF_VERIFY_SSL` | 设为 `false` 时完全跳过 IAF 端点 SSL 验证（仅限测试/内网无证书环境） | `true` |
| `ZW_BRAIN_DEV_IAM_BYPASS` | 研发期 IAM 网络不可达时临时跳过登录与 token-healthz；仅 `1` 生效，生产部署不得设置 | 未设置 |

如需接入 IAF/OIDC、外部数据库或集团推理平台，应通过环境变量注入对应配置，不要把密钥、连接串或证书写入镜像。内网部署若 IAF 使用自签名证书，优先挂载 CA bundle（`ZW_BRAIN_IAF_CA_FILE`）；仅在无法提供证书时才使用 `ZW_BRAIN_IAF_VERIFY_SSL=false`。

REST WebUI 登录采用 IAM 授权码流程：前端未发现 `sessionStorage` token 且 URL 无 `code` 时会跳转到 IAM 授权端点；回跳首页后由后端 `/auth/iaf/token` 代理 code 换取 token，`client_secret` 只在后端环境变量中使用。前端每 5 分钟检查 access token 过期时间，剩余小于 60 秒时调用 `/auth/iaf/refresh`；所有 `/api/*` 请求都会携带 `Authorization: Bearer <access_token>`，后端透传到 `{ZW_BRAIN_IAF_AUTH_SERVER_URL}/v1/token-healthz` 校验，校验不可用时按 503 失败关闭。退出登录会清理前端 `sessionStorage`，再跳转 IAM `/protocol/openid-connect/logout?redirect_uri=...` 清除 SSO 会话。

开发环境若无法连通 IAM 服务端，可临时设置 `ZW_BRAIN_DEV_IAM_BYPASS=1`：WebUI 不跳转 IAM，后端 `/api/snapshot` 与 `/api/skills/*` 不再强制 token-healthz，但仍执行 Skill manifest、角色、租户和人工确认等业务门禁。该变量只用于研发调试，生产部署清单不要设置；正式上线前应移除 `ZW_BRAIN_DEV_IAM_BYPASS` 及 `development_iam_bypass` / `dev-iam-bypass` / `developmentBypassEnabled` 相关临时代码。

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
