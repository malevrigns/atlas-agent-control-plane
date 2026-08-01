# Sandbox 沙箱服务

这里将实现 AtlasAgent 的独立沙箱服务。

当前章节已经加入：

- FastAPI 沙箱接口
- pydantic-settings 配置读取
- 统一响应结构
- 统一异常处理
- `/api/status` 状态检查接口
- `/api/supervisor/services` Supervisor 状态接口
- `/api/files` 文件列表接口
- `/api/files/read` 文件读取接口
- `/api/files/write` 文件写入接口
- `/api/files/replace` 文本替换接口
- `/api/files/upload` 文件上传接口
- `/api/files/download` 文件下载接口
- `/api/shell/sessions` Shell 会话启动和列表接口
- `/api/shell/sessions/{session_id}` Shell 会话详情接口
- `/api/shell/sessions/{session_id}/wait` Shell 等待接口
- `/api/shell/sessions/{session_id}/write` Shell 输入写入接口
- `/api/shell/sessions/{session_id}/terminate` Shell 终止接口
- `/api/browser/status` 浏览器运行状态接口
- `/api/browser/session` 浏览器会话启动和关闭接口
- `/api/browser/page/navigate` 页面导航接口
- `/api/browser/page` 当前页面信息接口
- `/api/browser/page/screenshot` 页面截图接口
- `/api/vnc/status` VNC/noVNC 状态接口
- Sandbox Dockerfile
- Docker Compose 中的 `sandbox` 服务配置
- Nginx `/sandbox-api` 网关转发
- Nginx `/sandbox-vnc` noVNC 远程桌面转发

## 本地运行

```bash
cd sandbox
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8100
```

访问：

```text
http://localhost:8100/api/status
http://localhost:8100/api/supervisor/services
http://localhost:8100/api/files
http://localhost:8100/api/shell/sessions
http://localhost:8100/api/browser/status
http://localhost:8100/api/vnc/status
```

## Docker Compose 运行

在项目根目录执行：

```bash
docker compose up -d sandbox nginx
```

通过 Nginx 访问：

```text
http://localhost:8088/sandbox-api/status
http://localhost:8088/sandbox-api/supervisor/services
http://localhost:8088/sandbox-api/files
http://localhost:8088/sandbox-api/shell/sessions
http://localhost:8088/sandbox-api/browser/status
http://localhost:8088/sandbox-api/vnc/status
http://localhost:8088/sandbox-vnc/vnc.html
```

## 后续章节会逐步加入：

- 更完整的浏览器元素识别、点击、输入和滚动工具
- 统一工具预览面板
