from dataclasses import dataclass
from time import sleep

import httpx

from app.core.config import Settings
from app.infrastructure.sandbox.file_client import SandboxFileClient
from app.infrastructure.sandbox.shell_client import SandboxShellClient


@dataclass(slots=True)
class SandboxInstance:
    """主 API 视角下的当前 DockerSandbox 实例。"""

    id: str  # 当前阶段固定为 default；后续可替换成任务 ID 或容器 ID。
    name: str  # Docker Compose 中的容器名，方便前端和日志定位。
    base_url: str  # 主 API 访问 Sandbox 的服务地址，不直接暴露给用户输入。
    status: str  # ready/unavailable/released，前端据此展示不同状态。
    message: str  # 面向前端的状态说明，避免只展示冷冰冰的状态码。


class DockerSandboxManager:
    """主 API 视角下的沙箱适配层。

    路由、工具和前端都通过这个 manager 理解“当前沙箱”。
    本章先适配 Docker Compose 中的 atlas-sandbox；后续一任务一容器时，
    优先替换这里的实现，而不是到处改路由和前端。
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # 文件和 Shell 的底层能力仍由 Sandbox 服务提供。
        # Manager 只负责把这些能力组织成“当前沙箱”的统一入口。
        self.file_client = SandboxFileClient(
            base_url=settings.sandbox_api_base_url,
            timeout_seconds=settings.sandbox_api_timeout_seconds,
        )
        self.shell_client = SandboxShellClient(
            base_url=settings.sandbox_api_base_url,
            timeout_seconds=settings.sandbox_api_timeout_seconds,
        )

    # ===================== 第1步：获取或创建当前沙箱实例 =====================
    def ensure_current(self) -> SandboxInstance:
        """确认当前沙箱是否可用。

        本章不真正创建 Docker 容器，因为容器由 Docker Compose 管理。
        这里先固定 ensure 的接口形状，后续可以替换成真实创建逻辑。
        """

        if self._is_healthy():
            return self._build_instance("ready", "Sandbox 服务已经可用。")
        return self._build_instance("unavailable", "Sandbox 服务暂时不可用。")

    def get_current(self) -> SandboxInstance:
        """读取当前沙箱状态。

        当前阶段 get 和 ensure 行为一致：都通过健康检查判断 Compose 沙箱是否可用。
        """

        return self.ensure_current()

    # ===================== 第2步：等待沙箱健康 =====================
    def wait_until_ready(
        self,
        retries: int | None = None,
        interval_seconds: float | None = None,
    ) -> SandboxInstance:
        """轮询等待 Sandbox 状态变成 ready。

        这个方法用于容器刚启动、Nginx 刚重启、或者前端点击刷新时。
        """

        max_retries = retries or self.settings.docker_sandbox_wait_retries
        interval = interval_seconds or self.settings.docker_sandbox_wait_interval_seconds

        for _ in range(max_retries):
            if self._is_healthy():
                return self._build_instance("ready", "Sandbox 服务已经通过健康检查。")
            # 使用短暂 sleep 保持实现简单；后续异步任务化时可以改成 async sleep。
            sleep(interval)

        return self._build_instance("unavailable", "等待 Sandbox 健康检查超时。")

    # ===================== 第3步：释放当前沙箱引用 =====================
    def release_current(self) -> SandboxInstance:
        """释放当前沙箱引用，但不停止 Compose 容器。

        当前 sandbox 是共享开发容器。如果这里真的 docker stop，会影响后续章节验证。
        """

        return self._build_instance(
            "released",
            "当前阶段沙箱由 Docker Compose 管理，主 API 只释放引用，不停止容器。",
        )

    # ===================== 第4步：代理文件和 Shell 能力 =====================
    def read_file(self, path: str) -> dict:
        """通过当前沙箱读取文件。

        路径安全仍由 Sandbox 文件 API 负责，Manager 不重复实现安全规则。
        """

        return self.file_client.read_file(path)

    def write_file(self, path: str, content: str, create_parent: bool) -> dict:
        """通过当前沙箱写入文件。"""

        return self.file_client.write_file(path, content, create_parent)

    def run_shell(
        self,
        command: str,
        cwd: str,
        timeout_seconds: float | None,
    ) -> dict:
        """在当前沙箱中执行 Shell 命令，并等待一段时间返回输出。"""

        started = self.shell_client.execute(command=command, cwd=cwd)
        return self.shell_client.wait(
            session_id=str(started["id"]),
            timeout_seconds=timeout_seconds or self.settings.sandbox_shell_wait_timeout_seconds,
        )

    # ===================== 第5步：健康检查辅助方法 =====================
    def _is_healthy(self) -> bool:
        """调用 Sandbox /status 判断服务是否可用。"""

        try:
            # 健康检查访问的是 Docker 网络内的 sandbox 服务，禁用环境代理更稳。
            with httpx.Client(
                timeout=self.settings.sandbox_api_timeout_seconds,
                trust_env=False,
            ) as client:
                response = client.get(f"{self.settings.sandbox_api_base_url}/status")
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            # 网络失败或响应不是 JSON，都说明当前沙箱不可用。
            return False

        return response.status_code == 200 and payload.get("code") == 200

    def _build_instance(self, status: str, message: str) -> SandboxInstance:
        """把配置和健康检查结果组合成统一的沙箱实例对象。"""

        return SandboxInstance(
            id=self.settings.docker_sandbox_id,
            name=self.settings.docker_sandbox_name,
            base_url=self.settings.sandbox_api_base_url,
            status=status,
            message=message,
        )
