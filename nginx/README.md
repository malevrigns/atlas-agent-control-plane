# Nginx 网关

这里放置 AtlasAgent 的 Nginx 网关配置。

当前章节已经加入：

- 前端页面代理
- `/api` 后端接口代理
- `/api` 流式响应代理缓冲关闭
- `/sandbox-api` 沙箱 API 代理
- `/sandbox-vnc` noVNC 远程桌面代理
- `/uploads` 上传文件静态访问预留
- SSE 和 WebSocket 长连接超时配置

## 访问入口

使用 Docker Compose 启动后，通过 Nginx 访问：

```text
http://localhost:8088
```

API 状态接口：

```text
http://localhost:8088/api/status
```

## 当前代理规则

```text
/      -> ui:3000
/api   -> api:8000
/api/* -> api:8000
/sandbox-api   -> sandbox:8100/api
/sandbox-api/* -> sandbox:8100/api/*
/sandbox-vnc/* -> sandbox:6080/*
/uploads/*     -> api_uploads volume
```

`ui` 和 `api` 是 Docker Compose 里的服务名。Nginx 容器和它们在同一个 Docker 网络中，所以可以通过服务名访问。

`/api` 和 `/sandbox-api` 都关闭了代理缓冲，避免 SSE 流式事件被 Nginx 攒成一大块再返回。

`/sandbox-vnc` 使用 WebSocket 升级请求头，供 noVNC 远程桌面连接使用。
