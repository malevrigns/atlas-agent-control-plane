import shutil
import subprocess

from app.core.config import settings
from app.schemas.supervisor import SupervisorServiceResponse, SupervisorStatusResponse


class SupervisorService:
    """读取沙箱容器内的进程管理状态。

    第 22 章先把接口形状固定下来。
    如果容器里暂时没有 supervisorctl，就返回配置中的服务占位状态。
    """

    def list_services(self) -> SupervisorStatusResponse:
        # ===================== 第1步：Supervisor 未启用时返回占位状态 =====================
        if not settings.supervisor_enabled:
            return SupervisorStatusResponse(
                enabled=False,
                services=[
                    SupervisorServiceResponse(
                        name=name,
                        status="not_configured",
                        description="Supervisor will be enabled in later sandbox chapters.",
                    )
                    for name in settings.supervisor_services
                ],
            )

        # ===================== 第2步：启用了配置，但镜像里还没安装 supervisorctl =====================
        supervisorctl = shutil.which("supervisorctl")
        if supervisorctl is None:
            return SupervisorStatusResponse(
                enabled=True,
                services=[
                    SupervisorServiceResponse(
                        name=name,
                        status="unavailable",
                        description="supervisorctl is not installed in this image.",
                    )
                    for name in settings.supervisor_services
                ],
            )

        # ===================== 第3步：真实读取 supervisorctl status 输出 =====================
        completed = subprocess.run(
            [supervisorctl, "status"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
        services = [
            self._parse_status_line(line)
            for line in completed.stdout.splitlines()
            if line.strip()
        ]
        return SupervisorStatusResponse(enabled=True, services=services)

    @staticmethod
    def _parse_status_line(line: str) -> SupervisorServiceResponse:
        # supervisorctl 的一行输出通常是：进程名 状态 描述。
        parts = line.split(maxsplit=2)
        name = parts[0] if parts else "unknown"
        status = parts[1] if len(parts) > 1 else "unknown"
        description = parts[2] if len(parts) > 2 else ""
        return SupervisorServiceResponse(
            name=name,
            status=status.lower(),
            description=description,
        )
