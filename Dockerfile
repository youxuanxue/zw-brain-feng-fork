# 在 zw-brain 仓库根目录构建（无需同级 agent-runtime 源码仓库）：
#   cd /path/to/zw-brain
#   docker build -t zw-brain:1.0.0 .
#
# WebUI：web-builder 阶段自动 npm ci + npm run build → zw-brain-web/dist-vite/
# AgentRuntime 来自 vendor 离线包：
#   vendor/agent-runtime/release/v0.1/agent-runtime-0.1.0-py312-pyc-only.tar.gz

FROM node:20-bookworm-slim AS web-builder

WORKDIR /build/zw-brain-web
COPY zw-brain-web/package.json zw-brain-web/package-lock.json ./
RUN npm ci
COPY zw-brain-web/ ./
RUN npm run build

FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ARG AGENT_RUNTIME_TARBALL=vendor/agent-runtime/release/v0.1/agent-runtime-0.1.0-py312-pyc-only.tar.gz
ARG AGENT_RUNTIME_EXTRACT_DIR=agent-runtime-0.1.0-py312-pyc-only

WORKDIR /build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY vendor/agent-runtime/requirements-deepagents.txt /tmp/agent-runtime-deepagents.txt
COPY ${AGENT_RUNTIME_TARBALL} /tmp/agent-runtime.tar.gz
COPY ${AGENT_RUNTIME_TARBALL}.sha256 /tmp/agent-runtime.tar.gz.sha256
RUN cd /tmp && \
    sed 's|  .*|  agent-runtime.tar.gz|' agent-runtime.tar.gz.sha256 | sha256sum -c - && \
    mkdir -p /tmp/agent-runtime-pkg && \
    tar -xzf /tmp/agent-runtime.tar.gz -C /tmp/agent-runtime-pkg && \
    cd "/tmp/agent-runtime-pkg/${AGENT_RUNTIME_EXTRACT_DIR}" && \
    uv pip install --system -r requirements.txt -r /tmp/agent-runtime-deepagents.txt && \
    ./install.sh

COPY . /build/zw-brain/
COPY --from=web-builder /build/zw-brain-web/dist-vite /build/zw-brain/zw-brain-web/dist-vite
WORKDIR /build/zw-brain
RUN uv build --wheel --out-dir /dist

# 安全姿态（漏扫 0609 Layer 2，详见 docs/deployment/security-hardening-0609.md）：
# - CPython "Python DoS" 发现按版本 banner 匹配；真正补丁靠**周期性重建本镜像**拉取最新 python:3.12-slim
#   （Docker Hub 持续滚动 3.12.x patch）；应用层另已在 stdlib http.server 去版本化 Server banner。
# - 下面 runtime 阶段加一次性 OS 包安全升级，拉平基础镜像里 openssl/zlib 等系统库 CVE。
# - 容器非 root 化（USER）与 /data 卷首启建 schema 的权限耦合，列为后续债（docs/preflight-debt.md），本期不引入。
FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 拉取基础镜像 OS 库安全补丁（确定性：构建即固化当时最新补丁层）。
RUN apt-get update && apt-get upgrade -y && apt-get clean && rm -rf /var/lib/apt/lists/*

ARG AGENT_RUNTIME_TARBALL=vendor/agent-runtime/release/v0.1/agent-runtime-0.1.0-py312-pyc-only.tar.gz
ARG AGENT_RUNTIME_EXTRACT_DIR=agent-runtime-0.1.0-py312-pyc-only

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ZW_BRAIN_DB_PATH=/data/zw-brain/zw_brain.db \
    ZW_BRAIN_AGENTS_DIR=/app/agents \
    ZW_BRAIN_AGENT_RUNTIME_CONFIG=/app/agent-runtime.yaml \
    ZW_BRAIN_AGENT_RUNTIME_SCHEMA=/app/schemas/agent.schema.json \
    ZW_BRAIN_PLATFORM_DOCS_ROOTS=/app/docs

WORKDIR /app

COPY vendor/agent-runtime/requirements-deepagents.txt /tmp/agent-runtime-deepagents.txt
COPY ${AGENT_RUNTIME_TARBALL} /tmp/agent-runtime.tar.gz
COPY ${AGENT_RUNTIME_TARBALL}.sha256 /tmp/agent-runtime.tar.gz.sha256
RUN cd /tmp && \
    sed 's|  .*|  agent-runtime.tar.gz|' agent-runtime.tar.gz.sha256 | sha256sum -c - && \
    mkdir -p /tmp/agent-runtime-pkg && \
    tar -xzf /tmp/agent-runtime.tar.gz -C /tmp/agent-runtime-pkg && \
    cd "/tmp/agent-runtime-pkg/${AGENT_RUNTIME_EXTRACT_DIR}" && \
    uv pip install --system -r requirements.txt -r /tmp/agent-runtime-deepagents.txt && \
    ./install.sh && \
    rm -rf /tmp/agent-runtime-pkg /tmp/agent-runtime.tar.gz /tmp/agent-runtime.tar.gz.sha256 /tmp/agent-runtime-deepagents.txt

COPY schemas /app/schemas
COPY agents /app/agents
COPY docs /app/docs
COPY agent-runtime.yaml /app/agent-runtime.yaml
COPY --from=builder /dist/*.whl /tmp/

RUN uv pip install --system /tmp/*.whl && uv pip install --system 'redis>=5.0' && rm -f /tmp/*.whl

VOLUME ["/data/zw-brain"]
EXPOSE 8800 8801
CMD ["zw-brain-rest"]
