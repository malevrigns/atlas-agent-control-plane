from dataclasses import dataclass


@dataclass(slots=True)
class A2aRole:
    """A2A 协议中的一个角色。

    第 34 章先用领域对象解释协议概念，不直接调用远程 Agent。
    name 是角色名称，responsibility 描述它负责什么，
    system_mapping 帮助读者理解它在当前项目中会落到哪里。
    """

    name: str
    responsibility: str
    system_mapping: str


@dataclass(slots=True)
class A2aCapability:
    """远程 Agent 对外声明的一项能力。"""

    name: str
    description: str
    example: str


@dataclass(slots=True)
class A2aAgentCard:
    """A2A Agent Card 的最小领域模型。

    Agent Card 类似远程 Agent 的名片。Host 在真正发送任务前，
    会先读取它来判断这个 Agent 是谁、能做什么、应该怎么调用。
    """

    name: str
    description: str
    url: str
    version: str
    capabilities: list[A2aCapability]
    default_input_modes: list[str]
    default_output_modes: list[str]


@dataclass(slots=True)
class A2aMessagePart:
    """A2A message 中的一段内容。

    A2A 的消息可以包含多种 part。第 34 章先使用 text，
    后续接文件、artifact 或更复杂内容时再扩展。
    """

    kind: str
    text: str


@dataclass(slots=True)
class A2aTaskStep:
    """模拟一次 A2A 调用中的可观察步骤。"""

    index: int
    action: str
    detail: str


@dataclass(slots=True)
class A2aMessageDemo:
    """第 34 章模拟 message/send 的返回结果。"""

    remote_agent: str
    task_id: str
    status: str
    input_message: list[A2aMessagePart]
    output_message: list[A2aMessagePart]
    steps: list[A2aTaskStep]


@dataclass(slots=True)
class A2aRemoteAgentInfo:
    """配置文件中的一个远程 Agent。

    第 35 章开始，A2A 不再只是概念演示，而是可以注册成工具。
    这个对象用于 API 列表、前端状态面板和工具选择排查。
    """

    key: str
    enabled: bool
    transport: str
    name: str
    description: str
    url: str
    version: str
    capabilities: list[A2aCapability]


@dataclass(slots=True)
class A2aTaskResult:
    """一次远程 Agent 调用的统一结果。

    task_id 是远程任务 ID，status 是远程任务状态，input_message 和
    output_message 记录输入输出，steps 用来解释 Host 调用远程 Agent 的过程。
    """

    agent_key: str
    remote_agent: str
    task_id: str
    status: str
    input_message: list[A2aMessagePart]
    output_message: list[A2aMessagePart]
    steps: list[A2aTaskStep]
