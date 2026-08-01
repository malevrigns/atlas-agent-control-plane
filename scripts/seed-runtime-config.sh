#!/usr/bin/env bash
set -euo pipefail

# ===================== 第1步：进入项目根目录 =====================
# 无论从哪个目录执行脚本，都先回到仓库根目录，避免 docker compose 找不到配置。
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# ===================== 第2步：确认默认配置文件存在 =====================
# 这些文件是运行时配置卷的种子文件。页面保存配置后，会写入 runtime-config 卷。
for file in llm.yaml mcp.yaml a2a.yaml; do
  if [[ ! -f "api/config/${file}" ]]; then
    echo "Missing seed config: api/config/${file}" >&2
    exit 1
  fi
done

# ===================== 第3步：把默认配置复制进 Docker volume =====================
# 默认不覆盖已有运行时配置，避免把用户在设置页保存过的 LLM/MCP/A2A 配置冲掉。
# 如果确实要重置，可以执行：OVERWRITE=true ./scripts/seed-runtime-config.sh
OVERWRITE="${OVERWRITE:-false}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-atlas-agents}"
RUNTIME_CONFIG_VOLUME="${RUNTIME_CONFIG_VOLUME:-${COMPOSE_PROJECT_NAME}_api_runtime_config}"

docker run --rm \
  -v "${RUNTIME_CONFIG_VOLUME}:/runtime-config" \
  -v "${ROOT_DIR}/api/config:/seed:ro" \
  alpine:3.20 \
  sh -eu -c '
    for file in llm.yaml mcp.yaml a2a.yaml; do
      if [ "'"${OVERWRITE}"'" = "true" ] || [ ! -f "/runtime-config/${file}" ]; then
        cp "/seed/${file}" "/runtime-config/${file}"
        echo "seeded ${file}"
      else
        echo "kept existing ${file}"
      fi
    done
    echo
    echo "runtime-config files:"
    ls -la /runtime-config
  '
