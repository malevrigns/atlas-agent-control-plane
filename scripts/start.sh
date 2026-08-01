#!/usr/bin/env bash
set -euo pipefail

# ===================== 第1步：进入项目根目录 =====================
# 这样无论用户从哪个目录执行脚本，docker compose 都能读到正确的配置文件。
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# ===================== 第2步：按需选择是否重新构建镜像 =====================
# BUILD=true ./scripts/start.sh 会在启动前重新构建 API、UI 和 Sandbox。
if [[ "${BUILD:-false}" == "true" ]]; then
  docker compose up -d --build
else
  docker compose up -d
fi

# ===================== 第3步：展示服务状态，方便用户确认入口是否可用 =====================
docker compose ps

GATEWAY_PORT="${NGINX_PORT:-8088}"

cat <<EOF

AtlasAgent is starting.

Gateway:
  http://localhost:${GATEWAY_PORT}

Useful checks:
  curl http://localhost:${GATEWAY_PORT}/api/status
  curl http://localhost:${GATEWAY_PORT}/api/status/database
EOF
