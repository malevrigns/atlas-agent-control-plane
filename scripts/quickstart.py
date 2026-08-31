#!/usr/bin/env python3
"""零依赖启动：一条命令跑起完整控制面，不需要 Docker / PostgreSQL / Redis。

``scripts/start.sh`` 面向真实部署——Postgres、Redis、Nginx、沙箱容器一应
俱全，那是对的。但「想先看一眼」的人不该先装一套编排系统：那是评估阶段
最高的一道门槛，也是绝大多数人放弃的地方。

这个脚本换掉两个适配器（数据库走 SQLite、任务队列走进程内 + SQLite 持久
化），其余一行代码都不改，然后：

1. 建虚拟环境、装依赖（用 uv，没有就退回 venv + pip）；
2. ``alembic upgrade head`` 建库——和生产走同一条迁移链，不用 create_all；
3. 起 uvicorn。

跨平台用 Python 而不是 shell 写：Windows 用户占了相当比例，让他们先装
WSL 才能试用是没有必要的。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "backend" / "api"
VENV_DIR = API_DIR / ".venv"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run(command: list[str], **kwargs) -> None:
    print(f"  $ {' '.join(str(part) for part in command)}", flush=True)
    subprocess.run(command, check=True, cwd=API_DIR, **kwargs)


def ensure_environment() -> Path:
    """准备可用的解释器。uv 优先，因为仓库里有 uv.lock，装出来是锁定版本。"""

    if shutil.which("uv"):
        print("[1/3] 同步依赖（uv）")
        run(["uv", "sync", "--frozen"])
        return venv_python()

    print("[1/3] 未找到 uv，退回 venv + pip")
    if not venv_python().exists():
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
    python = venv_python()
    run([str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    run([str(python), "-m", "pip", "install", "--quiet", "-e", "."])
    return python


def standalone_env(data_dir: Path) -> dict[str, str]:
    """把「单机」表达成一组环境变量——可插拔的实际含义就是这个。"""

    data_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite+aiosqlite:///{(data_dir / 'atlas.db').as_posix()}",
            "AGENT_TASK_BACKEND": "local",
            "AGENT_TASK_LOCAL_PATH": str(data_dir / "agent-tasks.db"),
            "RAG_VECTOR_BACKEND": "auto",
            "API_AUTH_ENABLED": "false",
            "UPLOAD_DIR": str(data_dir / "uploads"),
            "ARTIFACT_DIR": str(data_dir / "artifacts"),
        }
    )
    # 没有 LLM key 时用确定性的本地哈希向量，检索链路依然完整可跑。
    env.setdefault("RAG_EMBEDDING_PROVIDER", "local_hash" if not env.get("LLM_API_KEY") else "auto")
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=API_DIR / "var" / "standalone",
        help="SQLite 数据库与上传目录的位置（默认 backend/api/var/standalone）",
    )
    parser.add_argument("--reload", action="store_true", help="改代码自动重启")
    parser.add_argument(
        "--check",
        action="store_true",
        help="只做依赖安装与建库，不启动服务（CI 用）",
    )
    args = parser.parse_args()

    python = ensure_environment()
    env = standalone_env(args.data_dir.resolve())

    print("[2/3] 建库（与生产同一条迁移链）")
    run([str(python), "-m", "alembic", "upgrade", "head"], env=env)

    if args.check:
        print("[3/3] --check：跳过启动")
        return 0

    print("[3/3] 启动 API")
    print()
    print(f"  API   http://{args.host}:{args.port}/api/status")
    print(f"  Docs  http://{args.host}:{args.port}/docs")
    print(f"  Data  {args.data_dir.resolve()}")
    print()
    print("  数据库 SQLite，队列进程内，鉴权已关闭——仅供本机试用。")
    print("  要多副本部署或接 PostgreSQL / Redis，用 ./scripts/start.sh。")
    print()

    command = [
        str(python),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.reload:
        command.append("--reload")
    try:
        run(command, env=env)
    except KeyboardInterrupt:
        print("\n已停止。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        print(f"\n命令失败（退出码 {error.returncode}）：{' '.join(map(str, error.cmd))}", file=sys.stderr)
        raise SystemExit(error.returncode) from error
