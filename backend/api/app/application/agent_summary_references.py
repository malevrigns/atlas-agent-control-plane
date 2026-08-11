import json
from collections.abc import Mapping


SEARCH_RESULT_LIMIT = 5
REFERENCE_TEXT_LIMIT = 160
SNIPPET_LIMIT = 90
BYTES_PER_KIBIBYTE = 1024


def reference_lines(title: str, tool_name: str, output: str) -> list[str]:
    parsed = parse_json_object(output)
    if parsed and parsed.get("kind") == "search_results":
        items = parsed.get("items")
        return _search_reference_lines(items) if isinstance(items, list) else []
    if tool_name.startswith("file_"):
        return _file_reference_lines(title, output)
    if tool_name.startswith("browser_"):
        return _browser_reference_lines(title, output)
    return []


def artifact_lines(title: str, tool_name: str, output: str) -> list[str]:
    parsed = parse_json_object(output)
    if parsed and parsed.get("kind") == "browser_screenshot":
        return [_screenshot_artifact_line(title, parsed)]
    lines = _path_artifact_lines(title, output)
    if lines or not tool_name.startswith("file_write"):
        return lines
    return [f"- **{title}**：{trim(first_line(output), REFERENCE_TEXT_LIMIT)}"]


def parse_json_object(value: str) -> dict[str, object] | None:
    try:
        loaded = json.loads(value)
    except (TypeError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def match_line(text: str, label: str) -> str:
    prefix = f"{label}："
    for line in text.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    return ""


def first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return "工具已返回结果。"


def trim(value: str, max_length: int) -> str:
    clean = " ".join(value.split())
    return clean if len(clean) <= max_length else f"{clean[:max_length]}..."


def _file_reference_lines(title: str, output: str) -> list[str]:
    lines = [
        line.strip()
        for line in output.splitlines()
        if line.strip()
        and (line.startswith(("文件：", "路径：", "第 ")) or "行" in line)
    ][:4]
    return [f"- **{title}**：{trim(line, REFERENCE_TEXT_LIMIT)}" for line in lines]


def _search_reference_lines(items: list[object]) -> list[str]:
    lines = []
    for item in items[:SEARCH_RESULT_LIMIT]:
        line = _search_reference_line(item)
        if line:
            lines.append(line)
    return lines


def _search_reference_line(item: object) -> str | None:
    if not isinstance(item, Mapping):
        return None
    title = str(item.get("title") or "").strip()
    url = str(item.get("url") or "").strip()
    snippet = str(item.get("snippet") or "").strip()
    if not title or not url:
        return None
    suffix = f"：{trim(snippet, SNIPPET_LIMIT)}" if snippet else ""
    return f"- **{title}**（{url}）{suffix}"


def _browser_reference_lines(title: str, output: str) -> list[str]:
    page_title = match_line(output, "页面标题")
    url = match_line(output, "页面已打开") or match_line(output, "当前地址")
    if not page_title and not url:
        return []
    suffix = f"（{url}）" if url else ""
    return [f"- **{title}**：{page_title or '浏览器页面'}{suffix}"]


def _screenshot_artifact_line(title: str, parsed: Mapping[str, object]) -> str:
    size = int(parsed.get("size") or 0)
    size_text = f"{round(size / BYTES_PER_KIBIBYTE)} KB" if size > 0 else "未知大小"
    return f"- **{title}**：浏览器截图已生成，大小约 {size_text}。"


def _path_artifact_lines(title: str, output: str) -> list[str]:
    lines = []
    for label in ("输出文件", "文件路径", "保存路径", "下载地址"):
        value = match_line(output, label)
        if value:
            lines.append(f"- **{title}**：{label} `{value}`")
    return lines
