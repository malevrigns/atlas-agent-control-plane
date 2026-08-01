# 第四十六章. 生产构建、一键即起与 Nginx

## 46.1 本章目标

​        学完本章后，你将能够：

​        换句话说，第一，理解为什么项目需要一键启动和停止脚本；第二，让 API 容器启动时自动执行数据库迁移；第三，使用 Docker Compose 健康检查控制服务启动顺序；第四，为 Nginx 补齐 SSE、WebSocket 和上传文件静态路径配置；第五，区分本地开发命令和 Compose 生产化启动命令；第六，使用轻量测试检查生产启动配置是否完整。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 46.2 最终效果

​        本章结束后，项目根目录会新增：

```Plain
scripts/start.sh
scripts/stop.sh
```

​        启动服务：

```Bash
./scripts/start.sh
```

​        如果需要重新构建镜像：

```Bash
BUILD=true ./scripts/start.sh
```

​        停止服务：

```Bash
./scripts/stop.sh
```

​        API 容器启动时会自动执行：

```Bash
uv run alembic upgrade head
```

​        Nginx 会继续作为统一入口：

```Plain
http://localhost:8088
```

​        并支持：

```Plain
/                -> UI
/api             -> API
/sandbox-api     -> Sandbox API
/sandbox-vnc     -> VNC WebSocket
/uploads         -> 上传文件静态访问预留
```

## 46.3 本章要解决的问题

​        到第 45 章为止，项目已经有很多服务：

```Plain
PostgreSQL
Redis
API
UI
Sandbox
Nginx
```

​        如果每次启动都靠手动记命令，就会出现几个问题：

​        从实现顺序看，第一，忘记执行数据库迁移；第二，启动顺序不稳定，Nginx 先起来但 API 还没健康；第三，SSE 流式响应被 Nginx 缓冲，前端看起来像“一次性返回”；第四，VNC WebSocket 需要升级请求头，普通 HTTP 代理不够；第五，Docker Compose 命令越来越长，不适合最终项目验收。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        所以本章把“能跑”升级成“更像一个可交付项目的启动方式”。

## 46.4 本章技术方案

​        本章新增三类能力：

```Plain
启动脚本
  |
  +-- scripts/start.sh
  +-- scripts/stop.sh

API 容器启动脚本
  |
  +-- api/scripts/start.sh
  +-- 先迁移，再启动 uvicorn

网关和 Compose 增强
  |
  +-- Nginx SSE / WebSocket / uploads
  +-- Compose healthcheck
  +-- depends_on condition: service_healthy
```

​        本章暂时不做：

​        放到工程语境里看，第一，不配置 HTTPS 证书；第二，不做生产域名；第三，不做容器日志采集；第四，不做蓝绿部署；第五，不做 CI/CD。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这些内容会在后续测试、可观测性、安全和验收章节继续增强。

## 46.5 新增和修改的文件

```Plain
.env.example
README.md
api/README.md
api/Dockerfile
api/scripts/start.sh
docker-compose.yml
nginx/README.md
nginx/default.conf
scripts/start.sh
scripts/stop.sh
tests/test_production_startup_config.py
docs/course/chapters/46-production-startup-nginx.md
```

## 46.6 实施步骤
### 46.6.1 先写生产启动配置测试

​        创建：

```Plain
tests/test_production_startup_config.py
```

​        完整代码如下：

```Python
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProductionStartupConfigTest(unittest.TestCase):
    def test_root_start_stop_scripts_exist_and_use_compose(self) -> None:
        start_script = ROOT / "scripts" / "start.sh"
        stop_script = ROOT / "scripts" / "stop.sh"

        self.assertTrue(start_script.exists())
        self.assertTrue(stop_script.exists())
        self.assertIn("docker compose up -d", start_script.read_text())
        self.assertIn("docker compose down", stop_script.read_text())

    def test_api_container_runs_start_script_with_migrations(self) -> None:
        dockerfile = (ROOT / "api" / "Dockerfile").read_text()
        start_script = (ROOT / "api" / "scripts" / "start.sh").read_text()

        self.assertIn("COPY scripts ./scripts", dockerfile)
        self.assertIn('CMD ["./scripts/start.sh"]', dockerfile)
        self.assertIn("alembic upgrade head", start_script)
        self.assertIn("uvicorn app.main:app", start_script)

    def test_nginx_has_stream_websocket_and_upload_rules(self) -> None:
        config = (ROOT / "nginx" / "default.conf").read_text()

        self.assertIn("proxy_read_timeout", config)
        self.assertIn("X-Accel-Buffering", config)
        self.assertIn("location /sandbox-vnc/", config)
        self.assertIn("proxy_set_header Upgrade $http_upgrade", config)
        self.assertIn("location /uploads/", config)


if __name__ == "__main__":
    unittest.main()
```

#### 46.6.1.1 代码讲解

​        这个测试不启动 Docker，也不访问网络。

​        它只检查生产启动最容易遗漏的配置：

​        展开来看，第一，根目录是否有启动和停止脚本；第二，API 容器是否使用启动脚本；第三，API 启动脚本是否会执行迁移；第四，Nginx 是否有流式响应、WebSocket 和上传静态路径配置。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这种测试很轻，但很实用。以后如果有人误删脚本或改坏 Nginx 配置，测试会直接失败。

### 46.6.2 新增根目录启动脚本

​        创建：

```Plain
scripts/start.sh
```

​        完整代码如下：

```Bash
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
```

​        执行：

```Bash
chmod +x scripts/start.sh
```

#### 46.6.2.1 代码讲解

​        `set -euo pipefail` 用来让脚本遇到错误时尽快退出。

​        `ROOT_DIR` 让脚本可以从任意目录执行。

​        `BUILD=true` 是一个轻量开关：

```Bash
BUILD=true ./scripts/start.sh
```

​        表示启动前先重新构建镜像。

​        如果只是普通启动：

```Bash
./scripts/start.sh
```

​        脚本会直接复用已有镜像和容器。

### 46.6.3 新增停止脚本

​        创建：

```Plain
scripts/stop.sh
```

​        完整代码如下：

```Bash
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
```

​        执行：

```Bash
chmod +x scripts/stop.sh
```

#### 46.6.3.1 代码讲解

​        默认停止服务时不删除数据卷：

```Bash
./scripts/stop.sh
```

​        这样 PostgreSQL、Redis、上传文件还会保留。

​        如果确实想清空本地数据，可以执行：

```Bash
CLEAN_VOLUMES=true ./scripts/stop.sh
```

​        这个命令会删除数据卷，下一次启动会得到一个更干净的环境。

### 46.6.4 新增 API 容器启动脚本

​        创建：

```Plain
api/scripts/start.sh
```

​        完整代码如下：

```Bash
#!/usr/bin/env bash
set -euo pipefail

# ===================== 第1步：按需执行数据库迁移 =====================
# 容器启动时先执行迁移，避免用户忘记手动运行 alembic upgrade head。
# 本地排查时可以通过 RUN_MIGRATIONS=false 临时跳过。
if [[ "${RUN_MIGRATIONS:-true}" == "true" ]]; then
  uv run alembic upgrade head
fi

# ===================== 第2步：启动 FastAPI 服务 =====================
# 使用 exec 让 uvicorn 成为容器主进程，Docker 停止容器时信号能正确传递。
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

​        执行：

```Bash
chmod +x api/scripts/start.sh
```

#### 46.6.4.1 代码讲解

​        以前启动 API 容器时，容器只做一件事：

```Plain
启动 uvicorn
```

​        这会带来一个问题：如果数据库迁移没有执行，新接口访问到新表时会报错。

​        现在容器启动流程变成：

```Plain
执行 alembic upgrade head
  |
  v
启动 uvicorn
```

​        `RUN_MIGRATIONS=false` 是排查开关。

​        例如你只想临时验证 API 代码，不想让容器碰数据库迁移：

```Bash
RUN_MIGRATIONS=false docker compose up -d api
```

### 46.6.5 更新 API Dockerfile

​        打开：

```Plain
api/Dockerfile
```

​        加入脚本复制和执行权限：

```Dockerfile
COPY scripts ./scripts
RUN chmod +x ./scripts/start.sh
```

​        最后把 `CMD` 改成：

```Dockerfile
CMD ["./scripts/start.sh"]
```

#### 46.6.5.1 为什么这样设计

​        把迁移逻辑放进 Dockerfile 的 `RUN` 阶段是不对的。

​        因为镜像构建时还没有连接运行中的 PostgreSQL。

​        迁移应该发生在容器启动时，也就是 `CMD` 执行的阶段。

​        所以这里使用：

```Plain
Dockerfile CMD -> api/scripts/start.sh -> alembic -> uvicorn
```

### 46.6.6 更新 Docker Compose 健康检查和依赖

​        打开：

```Plain
docker-compose.yml
```

​        在 API 环境变量中加入：

```YAML
RUN_MIGRATIONS: ${RUN_MIGRATIONS:-true}
```

​        API 依赖 PostgreSQL 和 Redis 健康：

```YAML
depends_on:
  postgres:
    condition: service_healthy
  redis:
    condition: service_healthy
```

​        UI 等 API 健康后再启动：

```YAML
depends_on:
  api:
    condition: service_healthy
```

​        Nginx 等 UI、API、Sandbox 健康后再启动：

```YAML
depends_on:
  ui:
    condition: service_healthy
  api:
    condition: service_healthy
  sandbox:
    condition: service_healthy
```

#### 46.6.6.1 代码讲解

​        `depends_on` 的普通写法只保证“创建顺序”，不保证服务已经可用。

​        本章改成：

```Plain
condition: service_healthy
```

​        这样启动链路更稳：

```Plain
postgres / redis healthy
  |
  v
api healthy
  |
  v
ui healthy
  |
  v
nginx healthy
```

​        这不是生产编排的全部能力，但已经比“盲目按顺序启动”可靠很多。

### 46.6.7 增强 Nginx 配置

​        打开：

```Plain
nginx/default.conf
```

​        在 server 中加入长连接超时：

```Nginx
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
```

​        在 `/api/` 和 `/sandbox-api/` 中关闭缓冲：

```Nginx
proxy_buffering off;
proxy_cache off;
proxy_set_header X-Accel-Buffering no;
```

​        保留 VNC WebSocket 升级头：

```Nginx
location /sandbox-vnc/ {
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_pass http://sandbox:6080/;
}
```

​        新增上传文件静态路径预留：

```Nginx
location /uploads/ {
    alias /var/www/uploads/;
    add_header Cache-Control "private, max-age=3600";
    try_files $uri =404;
}
```

#### 46.6.7.1 代码讲解

​        SSE 流式事件最怕代理缓冲。

​        如果 Nginx 把后端返回的事件先攒起来，前端就会看到“等待很久后一次性出现”，体验会非常差。

​        所以 `/api/` 需要：

```Nginx
proxy_buffering off;
proxy_set_header X-Accel-Buffering no;
```

​        VNC 使用 WebSocket，所以 `/sandbox-vnc/` 必须保留：

```Nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

​        `/uploads/` 当前是静态访问预留。现阶段文件下载仍然主要通过：

```Plain
/api/files/{file_id}/download
```

​        后续如果要让 Nginx 直接服务公开文件，可以把文件 URL 切到 `/uploads/...`。

### 46.6.8 更新环境变量模板

​        打开：

```Plain
.env.example
```

​        加入：

```Plain
RUN_MIGRATIONS=true
```

#### 46.6.8.1 字段含义

​        `RUN_MIGRATIONS` 控制 API 容器启动时是否自动迁移数据库。

​        默认：

```Plain
true
```

​        这是课程项目更友好的默认值，避免用户忘记迁移。

## 46.7 关键理解

​        本章最重要的是理解“启动流程也是产品的一部分”。

​        一个 Agent 项目不只是代码能跑，还要做到：

```Plain
新环境能启动
数据库能迁移
网关能代理
长连接不断
停止和清理有明确命令
```

​        第二个重点是 Nginx 对流式响应的影响。

​        Agent 执行过程依赖 SSE：

```Plain
message_created
plan_created
step_started
tool_called
task_done
```

​        如果 Nginx 缓冲这些事件，前端就无法像实时任务一样展示。

​        第三个重点是健康检查。

​        `depends_on` 不应该只看“容器创建了没有”，还应该看“服务是否真的能响应”。

## 46.8 运行验证

​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

### 46.8.1 运行生产配置测试

```Bash
python3 -m unittest tests/test_production_startup_config.py -v
```

​        预期看到：

```Plain
OK
```

### 46.8.2 检查 Compose 配置

```Bash
docker compose config
```

​        预期能看到：

```Plain
RUN_MIGRATIONS: "true"
condition: service_healthy
/var/www/uploads
```

### 46.8.3 构建并启动

​        如果你已经有镜像：

```Bash
./scripts/start.sh
```

​        如果本章改动后需要重新构建：

```Bash
BUILD=true ./scripts/start.sh
```

### 46.8.4 验证网关

```Bash
curl http://localhost:8088/api/status
curl http://localhost:8088/api/status/database
curl http://localhost:8088/sandbox-api/status
curl http://localhost:8088/api/harness/cases
```

​        访问页面：

```Plain
http://localhost:8088
```

### 46.8.5 停止服务

```Bash
./scripts/stop.sh
```

​        如果想清空数据卷：

```Bash
CLEAN_VOLUMES=true ./scripts/stop.sh
```

## 46.9 常见问题

- 问题：启动时 API 迁移失败怎么办？

​        解释：先看 PostgreSQL 是否健康：`docker compose ps postgres`。如果只是想临时启动 API 排查，可以执行 `RUN_MIGRATIONS=false docker compose up -d api`。

- 问题：`BUILD=true ./scripts/start.sh` 很慢怎么办？

​        解释：它会重新构建镜像。网络慢时，Python、Node、Playwright、系统包下载都会影响速度。如果只是重启服务，用 `./scripts/start.sh`。

- 问题：页面还是一次性输出，不像流式怎么办？

​        解释：检查 Nginx 配置中 `/api/` 是否有 `proxy_buffering off` 和 `X-Accel-Buffering no`，并确认容器已重建或 Nginx 已重启。

- 问题：VNC 连不上怎么办？

​        解释：确认 `/sandbox-vnc/` 代理中有 `Upgrade` 和 `Connection` 请求头，再查看 `docker compose logs --tail=80 sandbox nginx`。

- 问题：什么时候用 `CLEAN_VOLUMES=true`？

​        解释：只有在你明确想删除 PostgreSQL、Redis 和上传文件数据时使用。普通停止服务不要加它。

## 46.10 本章小结

​        本章把项目启动方式向生产化推进了一步：

​        具体来说，第一，新增根目录一键启动脚本；第二，新增根目录停止脚本；第三，API 容器启动时自动执行数据库迁移；第四，Compose 增加健康检查依赖；第五，Nginx 增强 SSE、WebSocket 和上传静态路径配置；第六，新增生产启动配置测试；第七，README、Nginx README 和环境变量模板同步更新。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        从这一章开始，项目不再依赖一串容易忘的手动命令，而是有了更稳定的一键启动入口。

## 46.11 下一章预告

​        第 47 章会进入测试、调试与可观测性，补齐 API、数据库、Sandbox、Browser、VNC、MCP、A2A、Harness 和 Agent Runner 的系统化验证方法。
