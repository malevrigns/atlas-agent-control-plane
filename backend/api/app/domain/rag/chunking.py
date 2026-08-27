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


# ===================== 第5步：父文档两级切分（small-to-big） =====================


@dataclass(slots=True)
class ParentChunkGroup:
    """一个父块及其从父块内部切出的子块（父文档检索的结构单元）。

    向量存储只索引子块；命中子块后按 ``parent_seq`` 拼回父块内容，
    让模型拿到比命中子块更大的上下文窗口（small-to-big）。
    """

    parent_seq: int
    parent: TextSpan
    children: list[TextSpan]


def split_with_parents(
    text: str,
    *,
    parent_size: int = 2000,
    child_size: int = 500,
    child_overlap: int = 80,
) -> list[ParentChunkGroup]:
    """两级切分：先切父块，再从每个父块内部切出子块。

    第1级（父块）：沿用“段落优先 + 句子回退 + 装箱”策略，
    把全文切成不超过 ``parent_size`` 的语义完整大段，作为上下文窗口；
    第2级（子块）：在每个父块内部按 ``child_size`` 窗口切细粒度检索单元，
    相邻子块保留 ``child_overlap`` 个字符的重叠。子块的字符区间
    始终落在所属父块内，保证“拼回父块”时不越界。

    与单级 ``split_text`` 的区别：单级切分没有上下文窗口，
    命中即返回子块本身；两级切分命中子块后返回父块全文。
    """

    if parent_size <= 0 or child_size <= 0:
        raise ValueError("parent_size and child_size must be positive")
    if parent_size < child_size:
        raise ValueError("parent_size must be >= child_size")
    if child_overlap < 0 or child_overlap >= child_size:
        raise ValueError("child_overlap must be in [0, child_size)")

    normalized = text.replace("\r\n", "\n")
    if not normalized.strip():
        return []

    # 第1级：段落优先切父块（不加重叠，父块之间天然不重叠）。
    paragraphs = _split_paragraphs(normalized)
    pieces: list[TextSpan] = []
    for paragraph in paragraphs:
        if len(paragraph.content) <= parent_size:
            pieces.append(paragraph)
        else:
            pieces.extend(_split_long_span(paragraph, parent_size))
    parent_spans = _pack_spans(pieces, normalized, parent_size)

    # 第2级：每个父块内部切子块，parent_seq 从 0 递增。
    groups: list[ParentChunkGroup] = []
    for index, parent in enumerate(parent_spans):
        children = _split_children(parent, child_size, child_overlap)
        if children:
            groups.append(
                ParentChunkGroup(parent_seq=index, parent=parent, children=children)
            )
    # 重新编号：保证 parent_seq 连续，与“被跳过的空父块”解耦。
    for sequence, group in enumerate(groups):
        group.parent_seq = sequence
    return groups


def _split_children(parent: TextSpan, child_size: int, child_overlap: int) -> list[TextSpan]:
    """在父块内部按窗口切子块，重叠只向前借父块自身的内容。

    切分点优先吸附到句子边界（不超过目标窗口，且不小于窗口一半），
    避免把句子拦腰截断；仍超长的极端情况按窗口硬切保底。
    子块的字符区间是相对原文的绝对坐标（父块偏移 + 父块内偏移）。
    """

    content = parent.content
    total = len(content)
    if total <= child_size:
        return [
            TextSpan(
                content=content, char_start=parent.char_start, char_end=parent.char_end
            )
        ]

    children: list[TextSpan] = []
    start = 0
    while start < total:
        end = min(start + child_size, total)
        if end < total:
            end = _snap_to_sentence_boundary(content, start, end)
        if end <= start:  # 防御：切分点回缩过头时保底前进一步
            end = min(start + 1, total)
        piece = content[start:end]
        if piece.strip():
            children.append(
                TextSpan(
                    content=piece,
                    char_start=parent.char_start + start,
                    char_end=parent.char_start + end,
                )
            )
        if end >= total:
            break
        start = max(end - child_overlap, start + 1)
    return children


_SENTENCE_END_PATTERN = re.compile(r"[。！？!?；;.]\s*")


def _snap_to_sentence_boundary(text: str, start: int, end: int) -> int:
    """把窗口终点吸附到不晚于 ``end`` 的最近句子边界。

    只允许向前提（缩小窗口），且前提后不得小于窗口长度的一半，
    避免出现过小的碎片子块；找不到合适边界时保持 ``end`` 不变。
    """

    floor = start + (end - start) // 2
    best = -1
    for match in _SENTENCE_END_PATTERN.finditer(text, start + 1, end):
        if match.end() >= floor:
            best = match.end()
        else:
            break
    return best if best > start else end
