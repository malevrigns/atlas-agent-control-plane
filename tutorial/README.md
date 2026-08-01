# AtlasAgent · 智能体开发实战教程
![智能体开发实战教程封面](assets/agent-tutorial-cover.png)
## 写在前面
​        项目的开始源于工作和学习的需要。有时候我在想，当今世界从 OpenClaw、Hermes、Claude Code、Codex 等 Agent 横空出世之后，强工具调用的 Agent 已经展现出极其强大的通用能力。它们会读代码，会调用命令，会搜索资料，会写页面，也会在某种程度上替人拆解问题。似乎人类在通往 AGI 的道路上确实迈出了一大步。
​        笔者第一次部署 OpenClaw 时，它带给我的体验是前所未有的。但问题也随之而来：这些通用 Agent 已经这么强大了，我们还有没有必要从零开发一个新的智能体？这个问题困扰了笔者很久。后来笔者慢慢有了答案：做自己领域的垂类 Agent，和使用通用 Agent，并不冲突。通用 Agent 像一把通用刀，而垂类 Agent 更像一台已经按业务流程装配好的机器。前者解决广泛问题，后者解决稳定场景。
​        也正因如此，才有了这次实践记录。笔者很少写文档，不过这次还是想把开发过程中的问题、架构取舍和一些不成熟的技术思考记录下来。纵使这个时代资料多如繁星，我也希望自己的思考能在这个时代留下痕迹。
​        项目开始之前，笔者先简要说一下技术栈。笔者素来推崇前沿技术，当然这多少有点激进，因为前沿技术在生态完备性和工程成熟度上总会有所欠缺。笔者喜欢 Rust 给人的安全感，也喜欢 Go 天然高并发的通畅。可惜这次实践并不以炫技为目的，而是要把一个完整的 AI Agent 工作台从零搭出来，所以笔者会更看重工程闭环：后端、前端、数据库、消息流、沙箱、工具、部署，都要能跑起来。
​        本项目可以概括为一个全栈 AI Agent 工作台。它不是一个只接 LLM 接口的聊天壳，也不是一个提示词页面，而是一个能围绕任务进行规划、执行、调用工具、观察结果、形成最终回答的系统。它包含 FastAPI、SQLAlchemy、Alembic、PostgreSQL、Redis、Next.js、Electron、Textual、Nginx、Docker Compose、Sandbox、Playwright、VNC、MCP、A2A、多 Agent 编排、类型化长期记忆、Checkpoint DAG 以及可审计 Tool Runtime。
​        言归正传，下面进入真正的项目初始化。本文后续统一把项目称为 AtlasAgent，名字不重要，重要的是我们要亲手把它从一堆目录变成一个能执行任务的 Agent 产品。
![全栈多 Agent 架构图](assets/agent-workbench-architecture.png)

## 如何使用本教程

​        本教程共 74 章（第 0 章到第七十三章），建议按顺序阅读。每一章的结构基本一致：

- **本章目标**：读完这一章你能做到什么。
- **为什么需要这一章**：设计动机、架构取舍与常见坑。
- **实现步骤**：分步给出后端 / 前端 / 配置的完整可运行代码。
- **本章小结 / 验收**：如何确认这一章确实跑通。

​        只要跟着 74 章走完，你就能从一个空目录，亲手搭出一个能规划任务、调用工具、观察结果并生成带证据最终回答的全栈 AI Agent 工作台，并学会把它升级为可恢复、可追溯、可审计的 Control Plane。

### 配套源码

​        教程每一章都对应一份可运行的源码快照，位于同级的配套源码仓库 `atlas-agents-source/`：

```text
atlas-agent/
├── atlas-agent-tutorial/                     # 本教程
├── atlas-agents-source/
│   └── chapters/
│       ├── atlas-agents-01/                  # 第一章完成后的项目状态
│       ├── atlas-agents-02/                  # 第二章完成后的项目状态
│       ├── ...
│       └── atlas-agents-67/                  # 最终完整项目
└── atlas-agent-standalone/                   # 去课程化的独立产品发行物
```

​        快照是“累积式”的：`atlas-agents-NN` 就是完成到第 NN 章时的完整项目。推荐的学习方式：

1. 先读本章正文，理解“要做什么、为什么这么做”；
2. 跟着代码自己敲一遍；
3. 卡住时，对照同名快照 `atlas-agents-NN` 检查差异。

### 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 API | FastAPI · SQLAlchemy · Alembic · PostgreSQL · Redis |
| 客户端 | Next.js Web · Electron 桌面端 · Textual TUI |
| 沙箱 | FastAPI · Playwright · Xvfb + noVNC 远程桌面 |
| Agent 能力 | 规划 / ReAct · 类型化记忆 · Checkpoint DAG · 可审计 Tool Runtime · MCP / A2A |
| 部署 | Nginx 网关 · Docker Compose · 私有化交付 |

### 环境准备

- Docker 与 Docker Compose（一键起全套基础设施）
- Node.js 20+ 与 pnpm（前端）
- Python 3.11+ 与 uv（后端 / 沙箱）
- 一个 OpenAI 兼容的大模型 API Key（默认接入 DeepSeek，可在 `api/config/llm.yaml` 中改成任意 OpenAI 兼容服务）

### 快速跑通最终项目

```bash
cd ../atlas-agents-source/chapters/atlas-agents-67
cp .env.example .env          # 在 .env 里填入 LLM_API_KEY
BUILD=true ./scripts/start.sh # 首次构建并启动 nginx / ui / api / sandbox / postgres / redis
# 之后再启动只需 ./scripts/start.sh
```

> 网关默认只绑定 `127.0.0.1`。本项目不含鉴权层，详见发行物 README 的「安全模型」。

​        启动后统一入口在 `http://localhost:8088`，可以先做几个健康检查：

```bash
curl http://localhost:8088/api/status
curl http://localhost:8088/api/status/database
```

​        停止服务：

```bash
./scripts/stop.sh                    # 保留数据卷
CLEAN_VOLUMES=true ./scripts/stop.sh # 连同数据库、Redis、上传文件一起清理
```


## 目录

- [第 0 章. 项目缘起](chapters/00-项目缘起.md)
- [第一章. 项目伊始](chapters/01-项目伊始.md)
- [第二章. Docker Compose 基础设施奠基](chapters/02-Docker%20Compose%20基础设施奠基.md)
- [第三章. 后端 API 最小服务初成](chapters/03-后端%20API%20最小服务初成.md)
- [第四章. 后端通用模块备料](chapters/04-后端通用模块备料.md)
- [第五章. 前端 UI 最小服务初成](chapters/05-前端%20UI%20最小服务初成.md)
- [第六章. Nginx 网关贯通](chapters/06-Nginx%20网关贯通.md)
- [第七章. 数据库、迁移与会话模型立制](chapters/07-数据库、迁移与会话模型立制.md)
- [第八章. 会话开立与左侧列表](chapters/08-会话开立与左侧列表.md)
- [第九章. 对话输入与消息事件](chapters/09-对话输入与消息事件.md)
- [第十章. SSE 事件如流](chapters/10-SSE%20事件如流.md)
- [第十一章. 会话状态与任务收放](chapters/11-会话状态与任务收放.md)
- [第十二章. 文件上传与本地存储](chapters/12-文件上传与本地存储.md)
- [第十三章. 会话文件与预览开卷](chapters/13-会话文件与预览开卷.md)
- [第十四章. 文件存储拓界](chapters/14-文件存储拓界.md)
- [第十五章. 应用配置与 LLM 客户端就位](chapters/15-应用配置与%20LLM%20客户端就位.md)
- [第十六章. Agent 思维模型立论](chapters/16-Agent%20思维模型立论.md)
- [第十七章. Agent Memory 与工具协议](chapters/17-Agent%20Memory%20与工具协议.md)
- [第十八章. PlannerAgent 任务运筹](chapters/18-PlannerAgent%20任务运筹.md)
- [第十九章. ReActAgent 循步而行](chapters/19-ReActAgent%20循步而行.md)
- [第二十章. AgentTaskRunner 与 Redis Stream 任务流转](chapters/20-AgentTaskRunner%20与%20Redis%20Stream%20任务流转.md)
- [第二十一章. 上下文工程](chapters/21-上下文工程.md)
- [第二十二章. Sandbox 服务骨架初成](chapters/22-Sandbox%20服务骨架初成.md)
- [第二十三章. Sandbox 文件 API 与 FileTool 成形](chapters/23-Sandbox%20文件%20API%20与%20FileTool%20成形.md)
- [第二十四章. Sandbox Shell 与 ShellTool 成形](chapters/24-Sandbox%20Shell%20与%20ShellTool%20成形.md)
- [第二十五章. DockerSandbox 契合](chapters/25-DockerSandbox%20契合.md)
- [第二十六章. Playwright 与 CDP 奠基](chapters/26-Playwright%20与%20CDP%20奠基.md)
- [第二十七章. BrowserTool 浏览器工具成形](chapters/27-BrowserTool%20浏览器工具成形.md)
- [第二十八章. VNC 远程桌面临场](chapters/28-VNC%20远程桌面临场.md)
- [第二十九章. 工具预览面板落成](chapters/29-工具预览面板落成.md)
- [第三十章. SearchTool 搜索能力成形](chapters/30-SearchTool%20搜索能力成形.md)
- [第三十一章. MCP 协议初识](chapters/31-MCP%20协议初识.md)
- [第三十二章. MCP 工具入列](chapters/32-MCP%20工具入列.md)
- [第三十三章. 后端分层框架再造](chapters/33-后端分层框架再造.md)
- [第三十四章. A2A 协议初识](chapters/34-A2A%20协议初识.md)
- [第三十五章. A2A 工具入列](chapters/35-A2A%20工具入列.md)
- [第三十六章. 多 Agent 协作统筹](chapters/36-多%20Agent%20协作统筹.md)
- [第三十七章. 设置面板落成](chapters/37-设置面板落成.md)
- [第三十八章. AI 对话工作台再造](chapters/38-AI%20对话工作台再造.md)
- [第三十九章. 发送即执行与详情抽屉开阖](chapters/39-发送即执行与详情抽屉开阖.md)
- [第四十章. 长期记忆系统立档](chapters/40-长期记忆系统立档.md)
- [第四十一章. 记忆调阅与上下文注入](chapters/41-记忆调阅与上下文注入.md)
- [第四十二章. Agent Runner 归一](chapters/42-Agent%20Runner%20归一.md)
- [第四十三章. 模型工具选择策略精进](chapters/43-模型工具选择策略精进.md)
- [第四十四章. 复杂任务状态、重试与复原](chapters/44-复杂任务状态、重试与复原.md)
- [第四十五章. Agent Harness 量度与回放](chapters/45-Agent%20Harness%20量度与回放.md)
- [第四十六章. 生产构建、一键即起与 Nginx](chapters/46-生产构建、一键即起与%20Nginx.md)
- [第四十七章. 测试、调试与可观测性](chapters/47-测试、调试与可观测性.md)
- [第四十八章. 安全加固与沙箱划界](chapters/48-安全加固与沙箱划界.md)
- [第四十九章. 成熟 Agent 产品体验点验](chapters/49-成熟%20Agent%20产品体验点验.md)
- [第五十章. 前端产品化交互与视觉细琢](chapters/50-前端产品化交互与视觉细琢.md)
- [第五十一章. 前端组件体系与设计规范合辙](chapters/51-前端组件体系与设计规范合辙.md)
- [第五十二章. 流式执行体验与步骤动画](chapters/52-流式执行体验与步骤动画.md)
- [第五十三章. 工具预览、浏览器 VNC 与文件工作区细琢](chapters/53-工具预览、浏览器%20VNC%20与文件工作区细琢.md)
- [第五十四章. 响应式、可访问性与视觉终校](chapters/54-响应式、可访问性与视觉终校.md)
- [第五十五章. 对话叙事流与 Markdown 代码陈列](chapters/55-对话叙事流与%20Markdown%20代码陈列.md)
- [第五十六章. 任务计划折叠条与执行流动效](chapters/56-任务计划折叠条与执行流动效.md)
- [第五十七章. 右侧工具详情与浏览器观察](chapters/57-右侧工具详情与浏览器观察.md)
- [第五十八章. 搜索工具稳定性精进](chapters/58-搜索工具稳定性精进.md)
- [第五十九章. 任务发送到自动执行成环](chapters/59-任务发送到自动执行成环.md)
- [第六十章. 对话执行流与步骤卡片显影](chapters/60-对话执行流与步骤卡片显影.md)
- [第六十一章. 右侧详情抽屉与工具内容渲染](chapters/61-右侧详情抽屉与工具内容渲染.md)
- [第六十二章. 配置中心与最终集成点验](chapters/62-配置中心与最终集成点验.md)
- [第六十三章. 后端异常整饬与任务错误体验](chapters/63-后端异常整饬与任务错误体验.md)
- [第六十四章. 文件解析、摘要、引用与预览精进](chapters/64-文件解析、摘要、引用与预览精进.md)
- [第六十五章. 最终回答质量与引用体系](chapters/65-最终回答质量与引用体系.md)
- [第六十六章. 最终 UI 微调与交付清单点验](chapters/66-最终%20UI%20微调与交付清单点验.md)
- [第六十七章. Docker 私有化部署与内网交付](chapters/67-Docker%20私有化部署与内网交付.md)
- [第六十八章. 项目简历落笔](chapters/68-项目简历落笔.md)
- [第六十九章. Memory Control Plane 与 Checkpoint DAG](chapters/69-Memory%20Control%20Plane%20与%20Checkpoint%20DAG.md)
- [第七十章. Tool Runtime 权限、幂等与审计](chapters/70-Tool%20Runtime%20权限、幂等与审计.md)
- [第七十一章. Electron 多主题桌面客户端](chapters/71-Electron%20多主题桌面客户端.md)
- [第七十二章. 键盘优先 TUI 客户端](chapters/72-键盘优先%20TUI%20客户端.md)
- [第七十三章. 迁移、测试与交付验收](chapters/73-迁移、测试与交付验收.md)
