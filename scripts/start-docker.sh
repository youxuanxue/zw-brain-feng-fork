#!/bin/bash
set -e

# ==========================================
#  可覆盖环境变量（脚本旋钮，非应用 .env）
#  本脚本不 source .env；以下旋钮须作为 shell 环境传入，如：
#    EXTRA_HOSTS="host:ip ..." HOST_PORT=9901 bash scripts/start-docker.sh
#
#    IMAGE_TAG              业务镜像 tag                 默认 zw-brain:1.0.1
#    CONTAINER_NAME         容器名                      默认 zw-brain-rest
#    HOST_PORT             宿主机映射端口（→容器 8800）  默认 8800
#    ENV_FILE              传给容器的 --env-file（应用 env）默认 .env
#    ZW_BRAIN_DATABASE_URL PostgreSQL SQLAlchemy URL；留空=由 ENV_FILE 或 compose 默认值提供
#    OS_PATCH_REMOTE_IMAGE OS 补丁层远端镜像（内网 registry，不入库）  默认空=本地构建
#    EXTRA_HOSTS           容器 --add-host 映射，空格分隔 host:ip（内网 IP 不入库）默认空
#  ⚠ 迁移提醒：旧版曾硬编码 iaf-jn-rgzn / portal.inspur.com 的 hosts 映射，
#    现已下放到 EXTRA_HOSTS——内网部署须显式设置，否则容器内这些主机不可达。
#
#  ⚠ 方案 A（2026-06-22）：rest 服务整合进 docker-compose.yml，与 postgres 同网络
#    （zw-brain-net），容器内通过服务名 zw-brain-pg 访问 PostgreSQL。
#    不再单独 docker run，统一走 docker compose up -d rest。
# ==========================================

# ==========================================
#  Configuration — customize before running
# ==========================================
IMAGE_TAG="${IMAGE_TAG:-zw-brain:1.0.1}"
CONTAINER_NAME="${CONTAINER_NAME:-zw-brain-rest}"
HOST_PORT="${HOST_PORT:-8800}"
ENV_FILE="${ENV_FILE:-.env}"
# PostgreSQL connection URL for the container. Default backend is PG (zw_brain[postgres]).
# Leave empty to let ENV_FILE or docker-compose.yml default carry ZW_BRAIN_DATABASE_URL.
# In compose network, the default URL reaches postgres by service name "zw-brain-pg".
ZW_BRAIN_DATABASE_URL="${ZW_BRAIN_DATABASE_URL:-}"

OS_PATCH_LOCAL_TAG="zw-brain-os-patch:3.12-slim"
# 内网 registry 因主机不入库：通过 OS_PATCH_REMOTE_IMAGE 注入（如
#   docker.harbor.com:8086/library/zw-brain-os-patch:3.12-slim）。未设置则跳过 pull、直接本地构建。
OS_PATCH_REMOTE_IMAGE="${OS_PATCH_REMOTE_IMAGE:-}"
OS_PATCH_DOCKERFILE="Dockerfile.os-patch"

# 容器内 hosts 映射（内网 IP 不入库）：空格分隔的 host:ip 对，经 EXTRA_HOSTS 注入，如
#   EXTRA_HOSTS="iaf-jn-rgzn.inspurcloud.cn:10.0.0.1 portal.inspur.com:10.0.0.1"
# 注：EXTRA_HOSTS 通过动态生成的 docker-compose override 文件注入（而非 docker exec 改
# /etc/hosts），确保重启后映射保留。
EXTRA_HOSTS="${EXTRA_HOSTS:-}"

COMPOSE_OVERRIDE_FILE=".compose.override.yml"

# ==========================================
#  Helper: print a section header
# ==========================================
header() {
  echo ""
  echo "======================================"
  echo "  $1"
  echo "======================================"
}

# ---- Ensure OS patch base image exists ----
ensure_os_patch() {
  if docker image inspect "$OS_PATCH_LOCAL_TAG" >/dev/null 2>&1; then
    echo "  [ok]  $OS_PATCH_LOCAL_TAG  already exists locally, skipping"
    return 0
  fi

  if [ -n "$OS_PATCH_REMOTE_IMAGE" ]; then
    echo "  [info] $OS_PATCH_LOCAL_TAG  not found locally, trying to pull from remote..."
    if docker pull "$OS_PATCH_REMOTE_IMAGE"; then
      docker tag "$OS_PATCH_REMOTE_IMAGE" "$OS_PATCH_LOCAL_TAG"
      echo "  [ok]  pulled & tagged as  $OS_PATCH_LOCAL_TAG"
      return 0
    fi
    echo "  [warn] pull failed, building from $OS_PATCH_DOCKERFILE ..."
  else
    echo "  [info] OS_PATCH_REMOTE_IMAGE unset, building from $OS_PATCH_DOCKERFILE ..."
  fi

  docker build -t "$OS_PATCH_LOCAL_TAG" \
    --build-arg BUILD_DATE="$(date -u +%Y-%m-%d)" -f "$OS_PATCH_DOCKERFILE" .
  echo "  [ok]  built $OS_PATCH_LOCAL_TAG from $OS_PATCH_DOCKERFILE"
}

ensure_os_patch

# ---- Build ----
header "Building Docker image..."
docker build -t "$IMAGE_TAG" .

# ---- Generate compose override for EXTRA_HOSTS (if set) ----
# 用 YAML override 文件注入 extra_hosts，比 docker exec 改 /etc/hosts 更可靠（持久化）。
# EXTRA_HOSTS 为空时不生成 override 文件，直接使用 docker-compose.yml。
header "Generating compose override..."
if [[ -n "$EXTRA_HOSTS" ]]; then
  EXTRA_HOSTS_YAML=""
  for hp in $EXTRA_HOSTS; do
    host="${hp%%:*}"
    ip="${hp##*:}"
    EXTRA_HOSTS_YAML="${EXTRA_HOSTS_YAML}      - \"${host}:${ip}\"\n"
  done

  cat > "$COMPOSE_OVERRIDE_FILE" <<OVERRIDEYAML
# 由 start-docker.sh 自动生成——EXTRA_HOSTS 注入
# 手动修改会被覆盖；若要持久化 extra_hosts，请直接编辑 docker-compose.yml。
# 本文件已加入 .gitignore。
services:
  rest:
    extra_hosts:
$(printf '%b' "$EXTRA_HOSTS_YAML")
OVERRIDEYAML
  echo "  [ok] generated $COMPOSE_OVERRIDE_FILE with EXTRA_HOSTS"
else
  # 清理上次残留的 override 文件（如有）
  rm -f "$COMPOSE_OVERRIDE_FILE"
  echo "  [ok] EXTRA_HOSTS empty, no override needed"
fi

# ---- Stop & remove old standalone container (legacy) ----
# 兼容旧版遗留的 docker run 容器，防止容器名冲突
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "  [info] removing legacy standalone container '${CONTAINER_NAME}'..."
  docker stop "$CONTAINER_NAME" 2>/dev/null || true
  docker rm "$CONTAINER_NAME" 2>/dev/null || true
fi

# ---- Start via docker compose ----
header "Starting via docker compose..."
# export 这些变量让 docker compose 读取到 ${IMAGE_TAG} 等插值
export IMAGE_TAG CONTAINER_NAME HOST_PORT ENV_FILE
if [[ -n "$ZW_BRAIN_DATABASE_URL" ]]; then
  export ZW_BRAIN_DATABASE_URL
fi

# 停止旧 compose rest 服务（如有）
docker compose down rest 2>/dev/null || true

# 启动 postgres（确保数据库就绪）和 rest
# -f 指定主文件 + override 文件（若 EXTRA_HOSTS 为空则 override 中 extra_hosts: []）
if [[ -f "$COMPOSE_OVERRIDE_FILE" ]]; then
  echo "  [info] using override file: $COMPOSE_OVERRIDE_FILE"
  docker compose -f docker-compose.yml -f "$COMPOSE_OVERRIDE_FILE" up -d postgres rest 2>&1
else
  docker compose up -d postgres rest 2>&1
fi

# ---- Done ----
header "Container started! Tailing logs..."
if [[ -f "$COMPOSE_OVERRIDE_FILE" ]]; then
  docker compose -f docker-compose.yml -f "$COMPOSE_OVERRIDE_FILE" logs -f rest
else
  docker compose logs -f rest
fi
