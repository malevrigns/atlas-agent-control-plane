#!/usr/bin/env bash
set -euo pipefail

# ===================== 第1步：进入项目根目录 =====================
# 这样无论用户从哪个目录执行脚本，docker compose 都能读到正确的配置文件。
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# ===================== 第2步：生成本机部署密钥 =====================
if [[ ! -f .env ]]; then
  cp .env.example .env
fi

random_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    python3 -c 'import secrets; print(secrets.token_hex(32))'
  fi
}

upsert_env() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" .env; then
    if sed --version >/dev/null 2>&1; then
      sed -i "s|^${key}=.*|${key}=${value}|" .env
    else
      sed -i '' "s|^${key}=.*|${key}=${value}|" .env
    fi
  else
    printf '\n%s=%s\n' "${key}" "${value}" >> .env
  fi
}

ATLAS_KEY="$(sed -n 's/^ATLAS_API_KEY=//p' .env | tail -n 1)"
if [[ -z "${ATLAS_KEY}" || "${ATLAS_KEY}" == "change-me" ]]; then
  ATLAS_KEY="$(random_hex)"
  upsert_env ATLAS_API_KEY "${ATLAS_KEY}"
fi

POSTGRES_SECRET="$(sed -n 's/^POSTGRES_PASSWORD=//p' .env | tail -n 1)"
if [[ "${POSTGRES_SECRET}" == "postgres" ]]; then
  cat >&2 <<'EOF'
Legacy POSTGRES_PASSWORD=postgres detected. AtlasAgent will not rotate an existing
database password automatically. Back up or migrate the database, then set a strong
POSTGRES_PASSWORD and matching DATABASE_URL in .env. For disposable local data, run
CLEAN_VOLUMES=true ./scripts/stop.sh first, then replace postgres with change-me.
EOF
  exit 1
fi
if [[ -z "${POSTGRES_SECRET}" || "${POSTGRES_SECRET}" == "change-me" ]]; then
  POSTGRES_SECRET="$(random_hex)"
  upsert_env POSTGRES_PASSWORD "${POSTGRES_SECRET}"
fi

DATABASE_URL_VALUE="$(sed -n 's/^DATABASE_URL=//p' .env | tail -n 1)"
if [[ -z "${DATABASE_URL_VALUE}" || "${DATABASE_URL_VALUE}" == *":change-me@postgres:5432/atlas_agents" ]]; then
  upsert_env DATABASE_URL "postgresql+asyncpg://postgres:${POSTGRES_SECRET}@postgres:5432/atlas_agents"
fi

# ===================== 第3步：按需选择是否重新构建镜像 =====================
# BUILD=true ./scripts/start.sh 会在启动前重新构建 API、UI 和 Sandbox。
if [[ "${BUILD:-false}" == "true" ]]; then
  docker compose up -d --build
else
  docker compose up -d
fi

# ===================== 第4步：展示服务状态，方便用户确认入口是否可用 =====================
docker compose ps

GATEWAY_PORT="${NGINX_PORT:-8088}"

cat <<EOF

AtlasAgent is starting.

Gateway:
  http://localhost:${GATEWAY_PORT}

Useful checks:
  curl http://localhost:${GATEWAY_PORT}/api/status
  curl -H "X-Atlas-API-Key: ${ATLAS_KEY}" http://localhost:${GATEWAY_PORT}/api/status/database

Web login API Key:
  ${ATLAS_KEY}
EOF
