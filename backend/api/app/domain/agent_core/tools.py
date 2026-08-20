from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from inspect import iscoroutinefunction, signature
from typing import Any, cast, get_type_hints

from app.core.exceptions import AppException


class ToolRiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ToolInvocationStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    timed_out = "timed_out"
    denied = "denied"
    approval_required = "approval_required"
    deduplicated = "deduplicated"


# ===================== 第1步：定义工具参数的描述结构 =====================
@dataclass(slots=True)
class ToolParameter:
    """工具参数 schema。

    name 是参数名，type 是参数类型，description 用来给模型或前端解释参数含义。
    """

    name: str
    type: str
    description: str
    required: bool = True


# ===================== 第2步：定义工具描述结构 =====================
@dataclass(slots=True)
class ToolDefinition:
    """一个可以被 Agent 调用的工具。"""

    name: str
    description: str
    parameters: list[ToolParameter]
    version: str = "1.0.0"
    risk_level: ToolRiskLevel = ToolRiskLevel.low
    required_permissions: tuple[str, ...] = ()
    idempotent: bool = True
    timeout_seconds: float = 30.0
    output_mode: str = "inline_or_artifact"


# ===================== 第3步：定义工具执行结果 =====================
@dataclass(slots=True)
class ToolCallResult:
    """工具调用后的统一结果。"""

    tool_name: str
    arguments: dict[str, Any]
    output: str
    invocation_id: str | None = None
    status: ToolInvocationStatus = ToolInvocationStatus.succeeded
    risk_level: ToolRiskLevel = ToolRiskLevel.low
    duration_ms: int | None = None
    artifact_id: str | None = None
    output_truncated: bool = False
    audit: dict[str, Any] | None = None


# ===================== 第4步：封装真实 Python 函数和工具 schema =====================
@dataclass(slots=True)
class AgentTool:
    """工具对象。

    definition 给前端和模型看，handler 是后端真正执行的 Python 函数。

    handler 允许是同步函数，也允许是协程函数（例如需要访问数据库和
    向量存储的知识库检索）。ToolRuntime 会分别处理这两种情况：
    同步 handler 丢进线程池，异步 handler 直接 await。
    """

    definition: ToolDefinition
    handler: Callable[..., str] | Callable[..., Awaitable[str]]

    @property
    def is_async(self) -> bool:
        """handler 是否为协程函数。"""

        return iscoroutinefunction(self.handler)

    def call(self, arguments: dict[str, Any]) -> ToolCallResult:
        """同步执行工具函数，并包装成统一结果。

        这是不经过控制面的直接调用路径，只保留给同步 handler。
        异步 handler 必须通过 ToolRuntime.execute() 执行，否则会绕过
        权限、幂等、超时与审计。
        """

        if self.is_async:
            raise AppException(
                message=(
                    f"tool {self.definition.name} has an async handler; "
                    "execute it through ToolRuntime.execute()"
                ),
                code=500,
                status_code=500,
            )
        checked_arguments = self._validate_arguments(arguments)
        handler = cast(Callable[..., str], self.handler)
        output = handler(**checked_arguments)
        return ToolCallResult(
            tool_name=self.definition.name,
            arguments=checked_arguments,
            output=output,
        )

    def _validate_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """根据工具参数 schema 做最小校验。

        本章先检查必填参数是否存在。更严格的类型校验会在后续工具章节逐步增强。
        """

        checked: dict[str, Any] = {}
        declared_names = {parameter.name for parameter in self.definition.parameters}
        unexpected = sorted(set(arguments) - declared_names)
        if unexpected:
            raise AppException(
                message=f"unexpected tool arguments: {', '.join(unexpected)}",
                code=400,
                status_code=400,
            )
        for parameter in self.definition.parameters:
            value = arguments.get(parameter.name)
            if parameter.required and value in (None, ""):
                raise AppException(
                    message=f"tool argument is required: {parameter.name}",
                    code=400,
                    status_code=400,
                )
            if value is not None:
                value = self._coerce_value(parameter, value)
            checked[parameter.name] = value
        return checked

    @staticmethod
    def _coerce_value(parameter: ToolParameter, value: Any) -> Any:
        try:
            if parameter.type == "integer":
                return int(value)
            if parameter.type == "number":
                return float(value)
            if parameter.type == "boolean":
                if isinstance(value, str):
                    normalized = value.strip().lower()
                    if normalized in {"true", "1", "yes"}:
                        return True
                    if normalized in {"false", "0", "no"}:
                        return False
                    raise ValueError
                return bool(value)
            if parameter.type == "string" and not isinstance(value, str):
                return str(value)
        except (TypeError, ValueError) as exc:
            raise AppException(
                message=f"invalid tool argument type: {parameter.name} must be {parameter.type}",
                code=400,
                status_code=400,
            ) from exc
        return value


# ===================== 第5步：提供一个工具注册表 =====================
class ToolRegistry:
    """保存所有可用工具，并按名称查找工具。"""

    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        """注册工具。工具名不能重复。"""

        if tool.definition.name in self._tools:
            raise AppException(
                message=f"tool already exists: {tool.definition.name}",
                code=500,
                status_code=500,
            )
        self._tools[tool.definition.name] = tool

    def list_tools(self) -> list[ToolDefinition]:
        """返回全部工具 schema。"""

        return [tool.definition for tool in self._tools.values()]

    def get(self, name: str) -> AgentTool:
        """按名称获取工具，不存在时返回清晰错误。"""

        tool = self._tools.get(name)
        if tool is None:
            raise AppException(
                message=f"tool not found: {name}",
                code=404,
                status_code=404,
            )
        return tool


# ===================== 第6步：用装饰器把普通函数变成 AgentTool =====================
def agent_tool(
    name: str,
    description: str,
    parameter_descriptions: dict[str, str],
    *,
    version: str = "1.0.0",
    risk_level: ToolRiskLevel = ToolRiskLevel.low,
    required_permissions: tuple[str, ...] = (),
    idempotent: bool = True,
    timeout_seconds: float = 30.0,
) -> Callable[[Callable[..., str] | Callable[..., Awaitable[str]]], AgentTool]:
    """工具装饰器。

    使用方式：

    @agent_tool(...)
    def summarize_text(text: str) -> str:
        ...

    装饰器会读取函数签名，生成 ToolDefinition。
    """

    def decorator(func: Callable[..., str] | Callable[..., Awaitable[str]]) -> AgentTool:
        parameters = _build_parameters(func, parameter_descriptions)
        return AgentTool(
            definition=ToolDefinition(
                name=name,
                description=description,
                parameters=parameters,
                version=version,
                risk_level=risk_level,
                required_permissions=required_permissions,
                idempotent=idempotent,
                timeout_seconds=timeout_seconds,
            ),
            handler=func,
        )

    return decorator


def _build_parameters(
    func: Callable[..., Any],
    parameter_descriptions: dict[str, str],
) -> list[ToolParameter]:
    """从函数签名中提取工具参数。"""

    func_signature = signature(func)
    type_hints = get_type_hints(func)
    parameters: list[ToolParameter] = []
    for parameter_name, parameter in func_signature.parameters.items():
        annotation = type_hints.get(parameter_name, str)
        parameters.append(
            ToolParameter(
                name=parameter_name,
                type=_to_schema_type(annotation),
                description=parameter_descriptions.get(parameter_name, ""),
                required=parameter.default is parameter.empty,
            )
        )
    return parameters


def _to_schema_type(annotation: Any) -> str:
    """把 Python 类型转换成前端更容易展示的 schema 类型。"""

    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if annotation is bool:
        return "boolean"
    return "string"


def to_openai_tool_schema(tool: ToolDefinition) -> dict[str, Any]:
    """把单个工具定义转成 OpenAI 兼容的 function calling schema。"""

    properties = {
        parameter.name: {"type": parameter.type, "description": parameter.description}
        for parameter in tool.parameters
    }
    required = [parameter.name for parameter in tool.parameters if parameter.required]
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def to_openai_tool_schemas(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """把工具定义列表转成 OpenAI 兼容的 function calling schema 列表。"""

    return [to_openai_tool_schema(tool) for tool in tools]
