# 第四十三章. Docker 私有化部署与内网交付

`BUILD=true ./scripts/start.sh` 构建 api-ts、sandbox-ts、web，前面挂 Nginx。网关绑回环。数据在 `api_data`、`api_uploads`、`sandbox_workspace` 卷里。Key 由脚本生成，打印在终端，不写进浏览器存储。

![箱子已经封好，口子只留一个](../assets/ch43-deploy.jpg)

Windows 用 `start.ps1`。停服务 `./scripts/stop.sh`，连数据一起清加 `CLEAN_VOLUMES=true`。内网交付把 8088 放在他们的反向代理后面，自己上 TLS。不要把 Compose 的 80 直接暴露到公网。

健康检查失败时不要强行起 Nginx。入口活着、后面全 502，比起不来更糟。

---

[← 第四十二章. 最终 UI 微调与交付清单](42-最终%20UI%20微调与交付清单.md) · [返回目录](../README.md) · [第四十四章. 项目简历落笔 →](44-项目简历落笔.md)
