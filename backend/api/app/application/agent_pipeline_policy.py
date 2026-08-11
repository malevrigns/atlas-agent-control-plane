_STRONG_KEYWORDS = (
    "沙箱",
    "sandbox",
    "Sandbox",
    "搜索",
    "检索一下",
    "新闻",
    "资讯",
    "浏览器",
    "网页",
    "网站",
    "截图",
    "爬取",
    "抓取",
    "写入文件",
    "保存到",
    "保存为",
    "存到",
    "导出到",
    "读取文件",
    "创建文件",
    "生成文件",
    "终端",
    "命令行",
    "shell",
    "Shell",
    "MCP",
    "mcp",
    "A2A",
    "a2a",
    "多 Agent",
    "多Agent",
    "远程 Agent",
    "远程智能体",
)

_ACTION_VERBS = ("执行", "运行", "跑一下", "跑个")
_ACTION_OBJECTS = (
    "任务",
    "脚本",
    "命令",
    "代码",
    "程序",
    "测试",
    "pytest",
    "文件",
)


def needs_agent_pipeline(content: str) -> bool:
    if "http://" in content or "https://" in content:
        return True
    if any(keyword in content for keyword in _STRONG_KEYWORDS):
        return True
    has_action = any(verb in content for verb in _ACTION_VERBS)
    has_target = any(target in content for target in _ACTION_OBJECTS)
    return has_action and has_target
