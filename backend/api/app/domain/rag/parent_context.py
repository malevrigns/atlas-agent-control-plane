"""父文档检索：从命中的子块拼回更大的父块上下文（small-to-big）。

检索命中的是细粒度子块（向量召回更精确），但生成答案需要更大的
上下文窗口（语义更完整）。本模块负责"命中子块 → 父块内容"的换算，
三条路径按优先级回退：

1. ``metadata["parent_text"]``：两级切分管线（split_with_parents）
   入库时已把父块全文记在子块 metadata 里，直接取用，零额外查询；
2. 兄弟子块拼接：子块带 ``parent_seq`` 但 metadata 里没有父块文本
   （如旧数据补录），把同文档同父块的全部子块按 seq 排序拼接；
3. 邻块扩展：传统单级切分的旧文档（无 parent_seq），按 seq 向
   前后各扩展 N 个相邻 chunk，模拟"更大的阅读窗口"。

扩展结果与子块原文相同时返回原文（避免无谓放大上下文预算）。
"""

from app.domain.rag.entities import KnowledgeChunk

# metadata 中存放父块全文的键（两级切分管线写入）。
PARENT_TEXT_KEY = "parent_text"


def expand_to_parent_context(
    chunk: KnowledgeChunk,
    document_chunks: dict[int, KnowledgeChunk],
    *,
    neighbor_count: int = 1,
) -> str:
    """返回命中子块对应的父上下文。

    :param chunk: 检索命中的子块（向量存储回链的对象）。
    :param document_chunks: 该子块所属文档的全部 chunk，
        键为 seq，值为本体；用于兄弟拼接与邻块扩展两条回退路径。
    :param neighbor_count: 第 3 条路径向前后各扩展的相邻 chunk 数。
    :returns: 父块内容（或扩展窗口内容）；无法扩展时返回子块原文。
    """

    # 路径1：入库时已冻结的父块全文（最快，零歧义）。
    parent_text = chunk.metadata.get(PARENT_TEXT_KEY)
    if isinstance(parent_text, str) and parent_text.strip():
        return parent_text if parent_text != chunk.content else chunk.content

    # 路径2：同父块兄弟子块按 seq 拼接（子块只索引不存父块时的兜底）。
    if chunk.parent_seq is not None:
        siblings = sorted(
            (
                item
                for item in document_chunks.values()
                if item.parent_seq == chunk.parent_seq
            ),
            key=lambda item: item.seq,
        )
        joined = "\n".join(item.content for item in siblings if item.content.strip())
        if joined and joined != chunk.content:
            return joined

    # 路径3：旧文档邻块扩展，[seq-N, seq+N] 窗口按 seq 拼接。
    if neighbor_count > 0:
        window = [
            document_chunks[seq]
            for seq in range(chunk.seq - neighbor_count, chunk.seq + neighbor_count + 1)
            if seq in document_chunks
        ]
        window.sort(key=lambda item: item.seq)
        joined = "\n".join(item.content for item in window if item.content.strip())
        if joined and joined != chunk.content:
            return joined

    return chunk.content
