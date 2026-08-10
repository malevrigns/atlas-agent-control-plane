"""把会话附件转换成可注入模型上下文的文本节选。

直答路径不经过 Sandbox 工具，模型能否“读文件”取决于这里：
- 文本类附件直接解码；
- PDF 用 pypdf 抽取文本层；
- 其他二进制格式明确告知不支持，避免模型凭文件名编造内容。
所有输出都受字符预算约束，超出部分截断并标注。
"""

from io import BytesIO
from pathlib import Path

_TEXT_CONTENT_TYPES = {
    "application/json",
    "application/xml",
    "application/yaml",
    "application/x-yaml",
    "application/javascript",
}

_TEXT_SUFFIXES = {
    ".css",
    ".csv",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

# PDF 抽取的页数上限：防止超大 PDF 拖慢回答；预算通常先耗尽。
_PDF_MAX_PAGES = 80


def is_text_attachment(content_type: str, filename: str) -> bool:
    clean_type = (content_type or "").split(";")[0].strip().lower()
    if clean_type.startswith("text/") or clean_type in _TEXT_CONTENT_TYPES:
        return True
    return Path(filename).suffix.lower() in _TEXT_SUFFIXES


def is_pdf_attachment(content_type: str, filename: str) -> bool:
    clean_type = (content_type or "").split(";")[0].strip().lower()
    return clean_type == "application/pdf" or Path(filename).suffix.lower() == ".pdf"


def build_attachment_excerpt(
    *,
    filename: str,
    content_type: str,
    data: bytes,
    char_budget: int,
) -> str | None:
    """返回附件的文本节选；不支持的格式返回 None。"""

    if char_budget <= 0:
        return None
    if is_pdf_attachment(content_type, filename):
        return _extract_pdf_text(data, char_budget)
    if is_text_attachment(content_type, filename):
        text = data.decode("utf-8", errors="replace").strip()
        if not text:
            return None
        return _truncate(text, char_budget)
    return None


def _extract_pdf_text(data: bytes, char_budget: int) -> str | None:
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        parts: list[str] = []
        total = 0
        for index, page in enumerate(reader.pages):
            if index >= _PDF_MAX_PAGES or total >= char_budget:
                break
            page_text = (page.extract_text() or "").strip()
            if not page_text:
                continue
            parts.append(page_text)
            total += len(page_text)
        text = "\n\n".join(parts).strip()
        if not text:
            return "（该 PDF 没有可提取的文本层，可能是扫描件或图片型 PDF。）"
        return _truncate(text, char_budget)
    except Exception:
        # 加密、损坏或非标准 PDF：给出确定性的失败说明。
        return "（PDF 解析失败，无法提取文本内容。）"


def _truncate(text: str, char_budget: int) -> str:
    if len(text) <= char_budget:
        return text
    return f"{text[:char_budget]}\n……（内容过长已截断，以上为节选）"
