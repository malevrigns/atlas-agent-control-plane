import uuid
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.a2a_config import A2aAgentConfig, load_a2a_config
from app.core.exceptions import AppException
from app.domain.a2a.entities import (
    A2aAgentCard,
    A2aCapability,
    A2aMessagePart,
    A2aRemoteAgentInfo,
    A2aTaskResult,
    A2aTaskStep,
)


class A2aTransportClient(ABC):
    """A2A 传输层客户端基类。

    上层应用服务只关心“列出 Agent Card”和“发送任务消息”。
    具体是内置 demo、HTTP 远程服务，还是后续更完整的 A2A SDK，
    都封装在 transport client 中。
    """

    def __init__(self, agent_key: str, config: A2aAgentConfig) -> None:
        self.agent_key = agent_key
        self.config = config

    @abstractmethod
    def get_agent_card(self) -> A2aAgentCard:
        """读取远程 Agent Card。"""

    @abstractmethod
    def send_message(self, message: str) -> A2aTaskResult:
        """向远程 Agent 发送一条任务消息。"""


class DemoA2aTransportClient(A2aTransportClient):
    """内置 A2A 演示客户端。

    它模拟真实远程 Agent 的 Agent Card 和 message/send 响应，
    不需要额外启动服务，适合课程稳定验证完整工具事件链路。
    """

    def get_agent_card(self) -> A2aAgentCard:
        # 1. demo transport 不发网络请求，直接把配置转换成 Agent Card。
        #    这样本地环境不用启动远程服务，也能跑通 Host 读取 Agent Card 的流程。
        return _agent_card_from_config(self.config)

    def send_message(self, message: str) -> A2aTaskResult:
        # 1. 清理用户任务文本。远程 Agent 不应该收到空消息。
        clean_message = message.strip()
        if not clean_message:
            raise AppException(
                message="A2A message is required",
                code=400,
                status_code=400,
            )

        # 2. 为本次远程调用生成一个模拟 task_id。
        #    真实 A2A 服务通常会返回自己的任务 ID，本章用 uuid 模拟。
        task_id = f"a2a-task-{uuid.uuid4()}"

        # 3. 组装统一的 A2aTaskResult。
        #    ReAct 工具和 HTTP API 都依赖这个结构，所以这里不直接返回 dict。
        return A2aTaskResult(
            agent_key=self.agent_key,
            remote_agent=self.config.name,
            task_id=task_id,
            status="completed",
            input_message=[A2aMessagePart(kind="text", text=clean_message)],
            output_message=[
                A2aMessagePart(
                    kind="text",
                    text=(
                        f"{self.config.name} 已完成远程协作："
                        f"围绕“{clean_message}”整理了摘要、关键点和下一步建议。"
                    ),
                )
            ],
            steps=[
                A2aTaskStep(
                    index=1,
                    action="agent_card/read",
                    detail=f"读取远程 Agent Card：{self.config.name}。",
                ),
                A2aTaskStep(
                    index=2,
                    action="message/send",
                    detail="Host Agent 把用户任务包装成 A2A message 并发送。",
                ),
                A2aTaskStep(
                    index=3,
                    action="task/completed",
                    detail="远程 Agent 返回 completed 状态和输出消息。",
                ),
            ],
        )


class HttpA2aTransportClient(A2aTransportClient):
    """最小 HTTP A2A 客户端。

    本章先约定远程服务暴露两个 HTTP 接口：
    GET /agent-card 和 POST /message/send。
    后续如果接入更完整 A2A 协议，可以继续替换这里的传输细节。
    """

    def get_agent_card(self) -> A2aAgentCard:
        # 1. 向远程 Agent 读取 Agent Card。
        #    本章约定真实 HTTP Agent 暴露 GET /agent-card。
        payload = self._request("GET", "/agent-card")

        # 2. 把远程响应里的 capabilities 转成领域对象。
        #    如果远程字段缺失，使用空字符串兜底，避免前端渲染崩掉。
        capabilities = [
            A2aCapability(
                name=str(item.get("name") or ""),
                description=str(item.get("description") or ""),
                example=str(item.get("example") or item.get("description") or ""),
            )
            for item in payload.get("capabilities", [])
            if isinstance(item, dict)
        ]

        # 3. 返回统一 Agent Card。
        #    远程没返回的基础字段，使用配置文件中的值补齐。
        return A2aAgentCard(
            name=str(payload.get("name") or self.config.name),
            description=str(payload.get("description") or self.config.description),
            url=str(payload.get("url") or self.config.url),
            version=str(payload.get("version") or self.config.version),
            capabilities=capabilities,
            default_input_modes=list(payload.get("default_input_modes") or ["text"]),
            default_output_modes=list(payload.get("default_output_modes") or ["text"]),
        )

    def send_message(self, message: str) -> A2aTaskResult:
        # 1. 调用远程 Agent 的 message/send。
        #    本章先约定请求体只有 message，后续可扩展 artifacts、metadata 等字段。
        payload = self._request("POST", "/message/send", json={"message": message})

        # 2. 解析远程输入输出消息。
        #    远程服务可能不返回 input_message，所以 fallback 使用本次发送的 message。
        input_message = _message_parts_from_payload(payload.get("input_message"), message)
        output_message = _message_parts_from_payload(payload.get("output_message"), "")

        # 3. 解析远程执行步骤。
        #    steps 会进入前端工具预览，帮助用户看到远程 Agent 做过哪些动作。
        steps = [
            A2aTaskStep(
                index=int(item.get("index") or index),
                action=str(item.get("action") or "remote_step"),
                detail=str(item.get("detail") or ""),
            )
            for index, item in enumerate(payload.get("steps", []), start=1)
            if isinstance(item, dict)
        ]

        # 4. 包装成统一任务结果。
        #    即使真实远程 Agent 字段不完整，主 API 也尽量返回稳定结构。
        return A2aTaskResult(
            agent_key=self.agent_key,
            remote_agent=str(payload.get("remote_agent") or self.config.name),
            task_id=str(payload.get("task_id") or f"a2a-task-{uuid.uuid4()}"),
            status=str(payload.get("status") or "completed"),
            input_message=input_message,
            output_message=output_message,
            steps=steps,
        )

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # 1. 根据配置里的 base url 拼出远程接口地址。
        url = f"{self.config.url.rstrip('/')}{path}"
        try:
            # 2. 发送 HTTP 请求，并使用配置里的 timeout 避免调用长期卡住。
            response = httpx.request(
                method,
                url,
                json=json,
                timeout=self.config.timeout_seconds,
            )
            # 3. 非 2xx 响应直接抛出，统一转成 AppException 给上层。
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppException(
                message=f"A2A HTTP request failed: {exc}",
                code=502,
                status_code=502,
            ) from exc

        # 4. 兼容两种响应格式：
        #    - 直接返回业务 JSON
        #    - 返回统一 ApiResponse，其中业务数据在 data 字段里
        payload = response.json()
        if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], dict):
            return payload["data"]
        return payload if isinstance(payload, dict) else {}


class A2aClientManager:
    """A2A Client 管理器。

    它读取 A2A 配置，按 agent_key 创建对应传输客户端，
    并向应用服务提供统一的 list / card / message 调用方法。
    """

    def __init__(self) -> None:
        # 1. 读取并缓存 A2A 配置。
        #    load_a2a_config 本身带 lru_cache，所以多次创建 manager 不会重复读文件。
        self.config = load_a2a_config()

    # ===================== 第1步：读取远程 Agent 配置列表 =====================
    def list_agents(self) -> list[A2aRemoteAgentInfo]:
        """返回全部配置过的远程 Agent。"""

        # 1. 遍历 YAML 中声明的 agents。
        # 2. 把配置模型转换成领域对象，供 API 和前端状态面板展示。
        return [
            A2aRemoteAgentInfo(
                key=key,
                enabled=agent.enabled,
                transport=agent.transport,
                name=agent.name,
                description=agent.description,
                url=agent.url,
                version=agent.version,
                capabilities=[
                    A2aCapability(
                        name=capability.name,
                        description=capability.description,
                        example=capability.description,
                    )
                    for capability in agent.capabilities
                ],
            )
            for key, agent in self.config.agents.items()
        ]

    # ===================== 第2步：读取 Agent Card =====================
    def get_agent_card(self, agent_key: str | None = None) -> A2aAgentCard:
        """读取指定远程 Agent 的 Agent Card。"""

        # 1. 如果调用方没有传 agent_key，就使用配置中的默认 Agent。
        key = agent_key or self.config.a2a.default_agent

        # 2. 校验 Agent 是否存在且启用，避免调用被禁用的外部服务。
        agent = self._get_enabled_agent(key)

        # 3. 根据 transport 创建 client，并读取 Agent Card。
        return self._build_transport(key, agent).get_agent_card()

    # ===================== 第3步：发送任务消息 =====================
    def send_message(self, agent_key: str | None, message: str) -> A2aTaskResult:
        """向指定远程 Agent 发送一条任务消息。"""

        # 1. 没有指定 agent_key 时使用默认远程 Agent。
        key = agent_key or self.config.a2a.default_agent

        # 2. 先校验配置状态，再创建对应 transport。
        agent = self._get_enabled_agent(key)

        # 3. 真正调用远程 Agent，并返回统一任务结果。
        return self._build_transport(key, agent).send_message(message)

    def _get_enabled_agent(self, agent_key: str) -> A2aAgentConfig:
        # 1. 检查配置中是否存在这个 Agent。
        agent = self.config.agents.get(agent_key)
        if agent is None:
            raise AppException(
                message=f"A2A agent not found: {agent_key}",
                code=404,
                status_code=404,
            )

        # 2. 检查是否启用。禁用的 Agent 不能被工具和 API 调用。
        if not agent.enabled:
            raise AppException(
                message=f"A2A agent is disabled: {agent_key}",
                code=400,
                status_code=400,
            )
        return agent

    def _build_transport(
        self,
        agent_key: str,
        agent: A2aAgentConfig,
    ) -> A2aTransportClient:
        # 1. demo transport 走内置模拟器，适合课程稳定验证。
        if agent.transport == "demo":
            return DemoA2aTransportClient(agent_key, agent)

        # 2. http transport 走真实远程 Agent 服务。
        if agent.transport == "http":
            return HttpA2aTransportClient(agent_key, agent)

        # 3. 配置里出现未知 transport 时返回明确错误。
        raise AppException(
            message=f"unsupported A2A transport: {agent.transport}",
            code=500,
            status_code=500,
        )


def build_a2a_client_manager() -> A2aClientManager:
    return A2aClientManager()


def _agent_card_from_config(config: A2aAgentConfig) -> A2aAgentCard:
    return A2aAgentCard(
        name=config.name,
        description=config.description,
        url=config.url,
        version=config.version,
        capabilities=[
            A2aCapability(
                name=capability.name,
                description=capability.description,
                example=capability.description,
            )
            for capability in config.capabilities
        ],
        default_input_modes=["text"],
        default_output_modes=["text"],
    )


def _message_parts_from_payload(value: object, fallback: str) -> list[A2aMessagePart]:
    if not isinstance(value, list):
        return [A2aMessagePart(kind="text", text=fallback)] if fallback else []
    parts: list[A2aMessagePart] = []
    for item in value:
        if isinstance(item, dict):
            parts.append(
                A2aMessagePart(
                    kind=str(item.get("kind") or item.get("type") or "text"),
                    text=str(item.get("text") or ""),
                )
            )
    return parts
