from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ----- 基础服务信息：用于 /api/status 和接口文档 -----
    sandbox_app_name: str = "AtlasAgent Sandbox"
    sandbox_env: str = "development"
    sandbox_version: str = "0.1.0"
    sandbox_api_prefix: str = "/api"
    sandbox_auth_enabled: bool = False
    atlas_api_key: SecretStr = SecretStr("")
    log_level: str = "INFO"

    # ----- 沙箱工作目录：后续文件、Shell、浏览器下载都限制在这里 -----
    workspace_dir: str = "workspace"
    max_file_read_bytes: int = 64 * 1024
    max_file_write_bytes: int = 512 * 1024
    max_upload_size: int = 10 * 1024 * 1024
    shell_output_limit: int = 64 * 1024
    shell_default_timeout_seconds: float = 10.0

    # ----- Browser / CDP：本章先用 Playwright 启动一个 headless Chromium -----
    browser_enabled: bool = True
    browser_headless: bool = True
    browser_viewport_width: int = 1280
    browser_viewport_height: int = 720
    browser_default_timeout_ms: int = 15_000
    browser_screenshot_full_page: bool = True

    # ----- VNC / noVNC：把沙箱中的浏览器画面暴露成可嵌入的远程桌面 -----
    vnc_enabled: bool = True
    vnc_display: str = ":99"
    vnc_port: int = 5900
    vnc_web_port: int = 6080
    vnc_iframe_path: str = ""

    # ----- Supervisor：本章先固定接口形状，后续再接真实进程管理 -----
    supervisor_enabled: bool = False
    supervisor_services: list[str] = ["sandbox-api"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    # 配置对象只创建一次，避免每次请求都重新解析环境变量。
    return Settings()


settings = get_settings()
