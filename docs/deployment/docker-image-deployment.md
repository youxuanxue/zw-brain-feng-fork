# Docker 镜像文件部署手册

本文说明如何从源码构建 `zw-brain` Docker 镜像、导出镜像文件，并在目标服务器通过镜像文件部署 REST WebUI/API 与只读 Dashboard BFF。

## 1. 构建镜像

在仓库根目录执行：

```bash
docker build -t zw-brain:1.0.0 .
```

镜像默认启动 `zw-brain-rest`，同时内置以下运行入口，可通过 `docker run ... <command>` 覆盖：

- `zw-brain-rest`：REST API + WebUI，默认端口 `8800`
- `zw-brain-dashboard-bff`：只读 Dashboard BFF，默认端口 `8801`
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

## 5. 启动只读 Dashboard BFF

Dashboard 是独立部署、只读消费 `dashboard.*` Skill 的运行面。建议与 REST 使用同一个镜像、同一个数据卷，但作为单独容器启动：

```bash
docker run -d \
  --name zw-brain-dashboard \
  --restart unless-stopped \
  --add-host iaf.example.internal:127.0.0.1 \
  -p 8801:8801 \
  -v /opt/zw-brain/data:/data/zw-brain \
  -e ZW_BRAIN_DB_PATH=/data/zw-brain/zw_brain.db \
  -e ZW_BRAIN_IAF_AUTH_SERVER_URL=https://iaf.example.internal/auth \
  -e ZW_BRAIN_IAF_REALM=replace-me-realm \
  -e ZW_BRAIN_IAF_CLIENT_ID=replace-me-client-id \
  -e ZW_BRAIN_IAF_CLIENT_SECRET=replace-me-client-secret \
  -e ZW_BRAIN_DASHBOARD_BFF_PORT=8801 \
  zw-brain:1.0.0 \
  zw-brain-dashboard-bff
```

健康检查：

```bash
curl http://127.0.0.1:8801/health
```

Dashboard 访问地址：

```text
http://<服务器IP>:8801/
```

## 6. 常用环境变量

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
| `ZW_BRAIN_DASHBOARD_BFF_HOST` | Dashboard BFF 监听地址 | `0.0.0.0` |
| `ZW_BRAIN_DASHBOARD_BFF_PORT` | Dashboard BFF 监听端口 | `8801` |
| `ZW_BRAIN_REST_BASE_URL` | REST 对外基础 URL，用于契约投影等场景 | `http://127.0.0.1:<REST端口>` |
| `ZW_BRAIN_WEBUI_DASHBOARD_URL` | WebUI 中 Dashboard 入口地址；可设为绝对 URL、相对路径或 `off` 禁用 | `/dashboard/` |
| `ZW_BRAIN_TENANT_ID` | 默认租户标识 | 按运行配置解析 |
| `ZW_BRAIN_IAF_AUTH_SERVER_URL` | IAF/OIDC 认证服务地址，例如 `https://iaf.example.internal/auth`；部署时替换为目标环境地址 | 必填（接入 IAF/OIDC 时） |
| `ZW_BRAIN_IAF_REALM` | IAF realm，例如 `replace-me-realm` | 按运行配置解析 |
| `ZW_BRAIN_IAF_CLIENT_ID` | IAF client id，例如 `replace-me-client-id` | 按运行配置解析 |
| `ZW_BRAIN_IAF_CLIENT_SECRET` | IAF client secret；只允许通过运行时环境变量注入，示例中使用 `replace-me-client-secret` 占位 | 未设置 |
| `ZW_BRAIN_IAF_CA_FILE` | IAF HTTPS 自定义 CA 证书文件路径（容器内路径），用于挂载内部 CA bundle | 未设置（使用系统默认信任链） |
| `ZW_BRAIN_IAF_VERIFY_SSL` | 设为 `false` 时完全跳过 IAF 端点 SSL 验证（仅限测试/内网无证书环境） | `true` |

如需接入 IAF/OIDC、外部数据库或集团推理平台，应通过环境变量注入对应配置，不要把密钥、连接串或证书写入镜像。内网部署若 IAF 使用自签名证书，优先挂载 CA bundle（`ZW_BRAIN_IAF_CA_FILE`）；仅在无法提供证书时才使用 `ZW_BRAIN_IAF_VERIFY_SSL=false`。

## 7. 旧平台数据迁移

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

## 8. 运维命令

查看日志：

```bash
docker logs -f zw-brain-rest
docker logs -f zw-brain-dashboard
```

停止容器：

```bash
docker stop zw-brain-rest zw-brain-dashboard
```

删除容器：

```bash
docker rm zw-brain-rest zw-brain-dashboard
```

升级镜像时，先导入新镜像，再停止并重建容器；保留 `/opt/zw-brain/data` 数据目录即可复用数据库。

## 9. 构建后自检命令

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

docker run -d \
  --name zw-brain-dashboard-test \
  -p 8801:8801 \
  -v /tmp/zw-brain-docker-data:/data/zw-brain \
  zw-brain:1.0.0 \
  zw-brain-dashboard-bff
curl http://127.0.0.1:8801/health
docker rm -f zw-brain-dashboard-test
```
