#!/usr/bin/env bash
set -euo pipefail

# ===================== 第1步：进入项目根目录 =====================
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# ===================== 第2步：停止 Compose 服务 =====================
# CLEAN_VOLUMES=true ./scripts/stop.sh 会同时删除数据库、Redis 和上传文件卷。
if [[ "${CLEAN_VOLUMES:-false}" == "true" ]]; then
  docker compose down -v
else
  docker compose down
fi
