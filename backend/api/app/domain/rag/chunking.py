"""文档切分策略。

切分是 RAG 质量的第一道闸门：chunk 太大召回不精确、上下文预算容易爆；
chunk 太小语义被切碎、引用不完整。这里实现"段落优先 + 句子回退 +
固定重叠"的切分器，纯函数、无外部依赖，方便单元测试与教学复现。
"""

import re
from dataclasses import dataclass

_PARAGRAPH_PATTERN = re.compile(r"\n\s*\n+")
_SENTENCE_PATTERN = re.compile(r"(?<=[。！？!?；;.])\s*")


@dataclass(slots=True)
class TextSpan:
    """一个待入库的文本切片，保留原文中的字符区间。"""

    content: str
    char_start: int
    char_end: int

    @property
    def token_estimate(self) -> int:
        """粗略 token 估算：中文按字符、英文按 4 字符一个 token 折算。"""

        chinese = len(re.findall(r"[一-鿿]", self.content))
        other = len(self.content) - chinese
        return chinese + max(other // 4, 0)


# ===================== 第1步：段落优先切分 =====================
def split_text(
    text: str,
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[TextSpan]:
    """把长文本切成带重叠的 chunk 列表。

    切分顺序：
    1. 先按空行切段落，尽量保持语义完整；
    2. 段落装箱：连续段落合并到接近 ``chunk_size``；
    3. 超长段落按句子二次切分，仍超长再硬切；
    4. 相邻 chunk 之间保留 ``chunk_overlap`` 个字符的重叠，
       避免答案恰好横跨切分边界时召回失败。
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be in [0, chunk_size)")

    normalized = text.replace("\r\n", "\n")
    if not normalized.strip():
        return []

    paragraphs = _split_paragraphs(normalized)
    pieces: list[TextSpan] = []
    for paragraph in paragraphs:
        if len(paragraph.content) <= chunk_size:
            pieces.append(paragraph)
        else:
            pieces.extend(_split_long_span(paragraph, chunk_size))

    packed = _pack_spans(pieces, normalized, chunk_size)
    return _apply_overlap(packed, normalized, chunk_overlap)


def _split_paragraphs(text: str) -> list[TextSpan]:
    """按空行拆段，跳过空白段落并保留字符区间。"""

    spans: list[TextSpan] = []
    cursor = 0
    for match in _PARAGRAPH_PATTERN.finditer(text):
        segment = text[cursor : match.start()]
        if segment.strip():
            spans.append(_trimmed_span(text, cursor, match.start()))
        cursor = match.end()
    if text[cursor:].strip():
        spans.append(_trimmed_span(text, cursor, len(text)))
    return spans


def _trimmed_span(text: str, start: int, end: int) -> TextSpan:
    """去掉切片首尾空白，同时修正字符区间。"""

    segment = text[start:end]
    left_trim = len(segment) - len(segment.lstrip())
    right_trim = len(segment) - len(segment.rstrip())
    new_start = start + left_trim
    new_end = end - right_trim
    return TextSpan(content=text[new_start:new_end], char_start=new_start, char_end=new_end)


# ===================== 第2步：超长段落按句子回退切分 =====================
def _split_long_span(span: TextSpan, chunk_size: int) -> list[TextSpan]:
    """段落超过 chunk_size 时先按句子切，仍超长再按固定窗口硬切。"""

    sentences: list[TextSpan] = []
    cursor = span.char_start
    for part in _SENTENCE_PATTERN.split(span.content):
        if not part:
            continue
        start = cursor
        end = start + len(part)
        if part.strip():
            sentences.append(TextSpan(content=part, char_start=start, char_end=end))
        cursor = end

    result: list[TextSpan] = []
    for sentence in sentences or [span]:
        if len(sentence.content) <= chunk_size:
            result.append(sentence)
            continue
        # 极端情况：单句超过 chunk_size（如压缩日志），按窗口硬切保底。
        for offset in range(0, len(sentence.content), chunk_size):
            piece = sentence.content[offset : offset + chunk_size]
            result.append(
                TextSpan(
                    content=piece,
                    char_start=sentence.char_start + offset,
                    char_end=sentence.char_start + offset + len(piece),
                )
            )
    return result


# ===================== 第3步：把小切片装箱到目标大小 =====================
def _pack_spans(spans: list[TextSpan], text: str, chunk_size: int) -> list[TextSpan]:
    """相邻切片合并到不超过 chunk_size，减少碎片化 chunk。"""

    packed: list[TextSpan] = []
    current: TextSpan | None = None
    for span in spans:
        if current is None:
            current = span
            continue
        merged_length = span.char_end - current.char_start
        if merged_length <= chunk_size:
            current = TextSpan(
                content=text[current.char_start : span.char_end],
                char_start=current.char_start,
                char_end=span.char_end,
            )
        else:
            packed.append(current)
            current = span
    if current is not None:
        packed.append(current)
    return packed


# ===================== 第4步：为相邻 chunk 附加重叠前缀 =====================
def _apply_overlap(
    spans: list[TextSpan],
    text: str,
    chunk_overlap: int,
) -> list[TextSpan]:
    """把前一个 chunk 的结尾拼接到当前 chunk 开头。

    重叠只向前看一个 chunk，保证索引体积线性可控。
    """

    if chunk_overlap == 0 or len(spans) <= 1:
        return spans

    overlapped: list[TextSpan] = [spans[0]]
    for span in spans[1:]:
        overlap_start = max(span.char_start - chunk_overlap, 0)
        overlapped.append(
            TextSpan(
                content=text[overlap_start : span.char_end],
                char_start=overlap_start,
                char_end=span.char_end,
            )
        )
    return overlapped
