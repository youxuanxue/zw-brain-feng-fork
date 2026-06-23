#!/bin/bash
set -e

# ==========================================
#  Start zw-brain + agent-runtime + postgres
#  Usage:
#    EXTRA_HOSTS="host:ip ..." bash scripts/start-docker.sh
#    SKIP_BUILD=1                        bash scripts/start-docker.sh  # 跳过镜像构建
#
#  Variables:
#    EXTRA_HOSTS  容器 extra_hosts 映射，空格分隔 host:ip（内网 IP 不入库）
#                 例：EXTRA_HOSTS="iaf-jn-rgzn.inspurcloud.cn:10.0.0.1 portal.inspur.com:10.0.0.1"
#    ENV_FILE     传给容器的 --env-file                默认 .env
#    SKIP_BUILD   设为 1 跳过 docker build              默认空（构建）
#    OS_PATCH_REMOTE_IMAGE OS 补丁层远端镜像（内网 registry，不入库）默认空=本地构建
# ===========================================

ENV_FILE="${ENV_FILE:-.env}"
SKIP_BUILD="${SKIP_BUILD:-}"
EXTRA_HOSTS="${EXTRA_HOSTS:-}"
OS_PATCH_LOCAL_TAG="zw-brain-os-patch:3.12-slim"
OS_PATCH_REMOTE_IMAGE="${OS_PATCH_REMOTE_IMAGE:-}"
OS_PATCH_DOCKERFILE="Dockerfile.os-patch"
COMPOSE_OVERRIDE_FILE=".compose.override.yml"

header() {
  echo ""
  echo "======================================"
  echo "  $1"
  echo "======================================"
}

ensure_os_patch() {
  if docker image inspect "$OS_PATCH_LOCAL_TAG" >/dev/null 2>&1; then
    echo "  [ok]  $OS_PATCH_LOCAL_TAG already exists locally, skipping"
    return 0
  fi

  if [[ -n "$OS_PATCH_REMOTE_IMAGE" ]]; then
    echo "  [info] $OS_PATCH_LOCAL_TAG not found locally, trying remote image..."
    if docker pull "$OS_PATCH_REMOTE_IMAGE"; then
      docker tag "$OS_PATCH_REMOTE_IMAGE" "$OS_PATCH_LOCAL_TAG"
      echo "  [ok]  pulled and tagged as $OS_PATCH_LOCAL_TAG"
      return 0
    fi
    echo "  [warn] remote pull failed, building from $OS_PATCH_DOCKERFILE"
  else
    echo "  [info] OS_PATCH_REMOTE_IMAGE unset, building from $OS_PATCH_DOCKERFILE"
  fi

  docker build -t "$OS_PATCH_LOCAL_TAG" \
    --build-arg BUILD_DATE="$(date -u +%Y-%m-%d)" -f "$OS_PATCH_DOCKERFILE" .
  echo "  [ok]  built $OS_PATCH_LOCAL_TAG"
}

# ---- Generate compose override for EXTRA_HOSTS (if set) ----
# Docker Compose 不支持 extra_hosts 的环境变量插值，故用 override 文件注入。
# override 文件已加入 .gitignore，不入库。
if [[ -n "$EXTRA_HOSTS" ]]; then
  header "Generating compose override for EXTRA_HOSTS"
  EXTRA_HOSTS_YAML=""
  for hp in $EXTRA_HOSTS; do
    host="${hp%%:*}"
    ip="${hp##*:}"
    EXTRA_HOSTS_YAML="${EXTRA_HOSTS_YAML}      - \"${host}:${ip}\"\n"
  done

  cat > "$COMPOSE_OVERRIDE_FILE" <<OVERRIDEYAML
# 由 start-docker.sh 自动生成（EXTRA_HOSTS 注入）。已 gitignore，手动修改会被覆盖。
services:
  zw-brain:
    extra_hosts:
$(printf '%b' "$EXTRA_HOSTS_YAML")
OVERRIDEYAML
  echo "  [ok] generated $COMPOSE_OVERRIDE_FILE"
else
  rm -f "$COMPOSE_OVERRIDE_FILE"
fi

# ---- Build ----
if [[ "$SKIP_BUILD" != "1" ]]; then
  header "Preparing OS patch base image"
  ensure_os_patch

  header "Building Docker image"
  docker build -t zw-brain:latest .
fi

# ---- Start via docker compose ----
header "Starting containers"
export ENV_FILE

COMPOSE_ARGS=()
if [[ -f "$COMPOSE_OVERRIDE_FILE" ]]; then
  COMPOSE_ARGS+=(-f docker-compose.yml -f "$COMPOSE_OVERRIDE_FILE")
fi

docker compose "${COMPOSE_ARGS[@]}" up -d postgres agent-runtime zw-brain 2>&1

# ---- Done ----
header "Container started! Tailing logs..."
docker compose "${COMPOSE_ARGS[@]}" logs -f zw-brain
