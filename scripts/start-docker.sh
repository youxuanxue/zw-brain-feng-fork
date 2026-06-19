#!/bin/bash
set -e

# ==========================================
#  可覆盖环境变量（脚本旋钮，非应用 .env）
#  本脚本不 source .env；以下旋钮须作为 shell 环境传入，如：
#    EXTRA_HOSTS="host:ip ..." HOST_PORT=9901 bash scripts/start-docker.sh
#
#    IMAGE_TAG              业务镜像 tag                 默认 zw-brain:1.0.1
#    CONTAINER_NAME         容器名                      默认 zw-brain-rest
#    HOST_PORT             宿主机映射端口（→容器 8800）  默认 9900
#    ENV_FILE              传给容器的 --env-file（应用 env）默认 .env
#    ZW_BRAIN_DATABASE_URL PostgreSQL SQLAlchemy URL（容器内连得到的 PG，须用宿主机/内网可达
#                          地址，不能是 127.0.0.1）；留空=由 ENV_FILE 内的同名变量提供
#    OS_PATCH_REMOTE_IMAGE OS 补丁层远端镜像（内网 registry，不入库）  默认空=本地构建
#    EXTRA_HOSTS           容器 --add-host 映射，空格分隔 host:ip（内网 IP 不入库）默认空
#  ⚠ 迁移提醒：旧版曾硬编码 iaf-jn-rgzn / portal.inspur.com 的 hosts 映射，
#    现已下放到 EXTRA_HOSTS——内网部署须显式设置，否则容器内这些主机不可达。
# ==========================================

# ==========================================
#  Configuration — customize before running
# ==========================================
IMAGE_TAG="${IMAGE_TAG:-zw-brain:1.0.1}"
CONTAINER_NAME="${CONTAINER_NAME:-zw-brain-rest}"
HOST_PORT="${HOST_PORT:-8800}"
ENV_FILE="${ENV_FILE:-.env}"
# PostgreSQL connection URL for the container. Default backend is PG (zw_brain[postgres]).
# Leave empty to let ENV_FILE carry ZW_BRAIN_DATABASE_URL; set here to override per-run.
# Must be reachable from inside the container — 127.0.0.1 won't work; use the host/intranet
# PG address (e.g. postgresql+psycopg://zw_brain:***@db.intranet:5432/zw_brain).
ZW_BRAIN_DATABASE_URL="${ZW_BRAIN_DATABASE_URL:-}"

OS_PATCH_LOCAL_TAG="zw-brain-os-patch:3.12-slim"
# 内网 registry 因主机不入库：通过 OS_PATCH_REMOTE_IMAGE 注入（如
#   docker.harbor.com:8086/library/zw-brain-os-patch:3.12-slim）。未设置则跳过 pull、直接本地构建。
OS_PATCH_REMOTE_IMAGE="${OS_PATCH_REMOTE_IMAGE:-}"
OS_PATCH_DOCKERFILE="Dockerfile.os-patch"

# 容器内 hosts 映射（内网 IP 不入库）：空格分隔的 host:ip 对，经 EXTRA_HOSTS 注入，如
#   EXTRA_HOSTS="iaf-jn-rgzn.inspurcloud.cn:10.0.0.1 portal.inspur.com:10.0.0.1"
EXTRA_HOSTS="${EXTRA_HOSTS:-}"

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

# ---- Clean old container ----
header "Stopping & removing old container..."
docker stop "$CONTAINER_NAME" 2>/dev/null || echo "  (container not running, skipping stop)"
docker rm "$CONTAINER_NAME" 2>/dev/null || echo "  (container doesn't exist, skipping rm)"

# ---- Run ----
header "Starting new container..."
add_host_args=()
for hp in $EXTRA_HOSTS; do
  add_host_args+=(--add-host "$hp")
done
# PG-only: pass ZW_BRAIN_DATABASE_URL through only if set here (otherwise ENV_FILE
# supplies it). No SQLite file path / data volume — PG persistence lives in the PG
# instance (managed externally), not a container-local file.
db_url_args=()
if [[ -n "$ZW_BRAIN_DATABASE_URL" ]]; then
  db_url_args+=(-e "ZW_BRAIN_DATABASE_URL=$ZW_BRAIN_DATABASE_URL")
fi
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  "${add_host_args[@]}" \
  -v ./docs:/app/docs \
  -p "${HOST_PORT}:8800" \
  --env-file "./${ENV_FILE}" \
  "${db_url_args[@]}" \
  "$IMAGE_TAG"

# ---- Done ----
header "Container started! Tailing logs..."
docker logs -f "$CONTAINER_NAME"
