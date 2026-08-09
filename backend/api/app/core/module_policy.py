import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

from app.core.config import settings


DEFAULT_MODULES = {
    "llm": True,
    "search": True,
    "mcp": True,
    "a2a": True,
    "multi_agent": True,
    "sandbox": True,
    "rag": True,
}

TOOL_MODULES = {
    "web_search": "search",
    "mcp_call": "mcp",
    "a2a_call": "a2a",
    "multi_agent_collaborate": "multi_agent",
    "knowledge_search": "rag",
}


def module_for_tool(tool_name: str) -> str | None:
    if tool_name.startswith(("shell_", "file_", "browser_")):
        return "sandbox"
    return TOOL_MODULES.get(tool_name)


def module_enabled(module_key: str) -> bool:
    return bool(load_module_policy().get(module_key, True))


def load_module_policy() -> dict[str, bool]:
    path = Path(settings.module_config_path)
    payload: dict = {}
    if path.is_file():
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    configured = dict(payload.get("modules") or {})
    return {
        key: bool(configured.get(key, default))
        for key, default in DEFAULT_MODULES.items()
    }


def set_module_enabled(module_key: str, enabled: bool) -> None:
    if module_key not in DEFAULT_MODULES:
        raise KeyError(module_key)
    policy = load_module_policy()
    policy[module_key] = enabled
    path = Path(settings.module_config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        yaml.safe_dump({"modules": policy}, handle, allow_unicode=True, sort_keys=False)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    temporary.replace(path)
