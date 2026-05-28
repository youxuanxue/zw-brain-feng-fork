# 在 zw-brain 仓库根目录构建（无需同级 agent-runtime 源码仓库）：
#   cd /path/to/zw-brain
#   docker build -t zw-brain:1.0.0 .
#
# AgentRuntime 来自 vendor 离线包：
#   vendor/agent-runtime/release/v0.1/agent-runtime-0.1.0-py312-pyc-only.tar.gz

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
WORKDIR /build/zw-brain
RUN uv build --wheel --out-dir /dist

FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ARG AGENT_RUNTIME_TARBALL=vendor/agent-runtime/release/v0.1/agent-runtime-0.1.0-py312-pyc-only.tar.gz
ARG AGENT_RUNTIME_EXTRACT_DIR=agent-runtime-0.1.0-py312-pyc-only

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ZW_BRAIN_DB_PATH=/data/zw-brain/zw_brain.db \
    ZW_BRAIN_AGENTS_DIR=/app/agents \
    ZW_BRAIN_AGENT_RUNTIME_CONFIG=/app/agent-runtime.yaml \
    ZW_BRAIN_AGENT_RUNTIME_SCHEMA=/app/schemas/agent.schema.json

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
COPY agent-runtime.yaml /app/agent-runtime.yaml
COPY --from=builder /dist/*.whl /tmp/

RUN uv pip install --system /tmp/*.whl && uv pip install --system 'redis>=5.0' && rm -f /tmp/*.whl

VOLUME ["/data/zw-brain"]
EXPOSE 8800 8801
CMD ["zw-brain-rest"]
