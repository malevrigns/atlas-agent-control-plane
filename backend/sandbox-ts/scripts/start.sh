#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

export DISPLAY="${VNC_DISPLAY:-:99}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8100}"
export WORKSPACE_DIR="${WORKSPACE_DIR:-/workspace}"
mkdir -p "${WORKSPACE_DIR}"

if [[ "${VNC_ENABLED:-true}" == "true" ]]; then
  Xvfb "${DISPLAY}" -screen 0 1280x720x24 >/tmp/xvfb.log 2>&1 &
  fluxbox >/tmp/fluxbox.log 2>&1 &
  x11vnc -display "${DISPLAY}" -forever -shared -rfbport "${VNC_PORT:-5900}" -nopw >/tmp/x11vnc.log 2>&1 &
  websockify --web=/usr/share/novnc "${VNC_WEB_PORT:-6080}" "127.0.0.1:${VNC_PORT:-5900}" >/tmp/websockify.log 2>&1 &
fi

exec pnpm start
