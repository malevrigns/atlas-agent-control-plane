"""检索结果重排（Reranking）与引用置信度。

两阶段检索的经典收口：粗排（向量召回 + RRF 融合）保证召回率，
重排保证精排质量。这里提供两条可切换的重排路径：

1. LLM Listwise 重排：把候选段落整组交给 LLM，让它对每个候选打
   0-10 相关分。整组比较（listwise）比逐对比较（pairwise）调用
   次数恒定，且 LLM 能看到候选间的相对差异。
2. 增强词法信号（无 LLM 时的降级路径）：TF-IDF 加权 + 短语匹配
   加分 + 位置衰减，纯函数、确定性，离线环境可用。

引用置信度（confidence）把"分数有多高"升级成"这条引用有多可信"：
相关分、文档新鲜度、来源类型三者加权，供答案溯源展示与审计。
"""

import json
import math
import re
from dataclasses import replace
from datetime import UTC, datetime

from app.domain.llm.entities import LLMMessage
from app.domain.rag.entities import (
    KnowledgeSourceType,
    RetrievedChunk,
)
from app.domain.rag.query_processing import (
    LLMChatProvider,
    tokenize_mixed_text,
)

# 单条候选喂给 LLM 的正文截断长度：够判断相关性，又不爆 token。
_CANDIDATE_SNIPPET_CHARS = 300
# 重排 LLM 的提示词模板（listwise：整组候选一次打分）。
_LLM_RERANK_PROMPT = (
    "你是搜索重排助手。根据用户查询，评估每个候选段落与查询的相关性，"
    "给出 0-10 的整数评分（10 表示完全相关，0 表示完全不相关）。\n"
    "只输出 JSON 对象数组，元素形如 {\"index\": <段落序号>, \"score\": <评分>}，不要任何解释。\n"
    "用户查询：{query}\n\n候选段落：\n{candidates}"
)


# ===================== 第1步：LLM Listwise 重排 =====================
async def _llm_listwise_scores(
    query: str, chunks: list[RetrievedChunk], llm: LLMChatProvider
) -> list[float]:
    """让 LLM 对整组候选打分，返回与 ``chunks`` 等长的 0-1 分数列表。

    输出不可解析或没有任何有效评分时抛出异常，由 ``rerank_chunks``
    降级到词法重排——重排是增强项，失败不得阻塞主检索链路。
    """

    lines = [
        f"{index}. {item.content[:_CANDIDATE_SNIPPET_CHARS]}"
        for index, item in enumerate(chunks)
    ]
    prompt = _LLM_RERANK_PROMPT.format(query=query, candidates="\n".join(lines))
    result = await llm.chat([LLMMessage(role="user", content=prompt)])
    return _parse_scores(result.content, len(chunks))


def _parse_scores(content: str, expected: int) -> list[float]:
    """解析 LLM 评分输出：[{"index": 0, "score": 9}, ...] → 0-1 列表。

    容错代码围栏与多余文字；缺失的候选按 0 分处理。
    """

    text = content.strip()
    match = re.search(r"\[[\s\S]*\]", text)
    if match is None:
        raise ValueError("llm rerank output has no json array")
    payload = json.loads(match.group(0))
    if not isinstance(payload, list):
        raise ValueError("llm rerank output is not a list")

    scores = [0.0] * expected
    parsed = 0
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        index = entry.get("index", entry.get("id"))
        raw_score = entry.get("score")
        if not isinstance(index, int) or not isinstance(raw_score, (int, float)):
            continue
        if index < 0 or index >= expected:
            continue
        scores[index] = max(0.0, min(float(raw_score), 10.0)) / 10.0
        parsed += 1
    if parsed == 0:
        raise ValueError("llm rerank output produced no usable scores")
    return scores


# ===================== 第2步：增强词法重排（无 LLM 降级） =====================
def _term_occurrences(term: str, text: str) -> int:
    """统计 term 在 text 中的出现次数（英文按整词，中文按子串）。"""

    if re.fullmatch(r"[a-z0-9_]+", term):
        return len(re.findall(rf"\b{re.escape(term)}\b", text))
    return text.count(term)


def _phrase_bonus(query: str, chunk_content: str) -> float:
    """短语匹配加分：查询词在正文中成簇（相邻出现）时给分。

    取查询分词后出现在正文中的词，计算这些词的
    首现位置跨度与词总长之比：跨度越紧凑越像"原句被正文命中"，
    得分越高（1.0 / 0.6 / 0.3 三档）。词数 < 2 不给分。
    """

    lowered = chunk_content.lower()
    terms_in_text = [term for term in tokenize_mixed_text(query) if term in lowered]
    if len(terms_in_text) < 2:
        return 0.0
    # 每个词的首现位置；跨度 = 最远两词首现位置的距离。
    first_positions = [lowered.find(term) for term in terms_in_text]
    span = max(first_positions) - min(first_positions) + 1
    total_chars = sum(len(term) for term in terms_in_text)
    # 紧凑度：词本身总长占跨度的比例（1.0 表示词几乎紧挨着出现）。
    density = total_chars / span if span > 0 else 0.0
    if density >= 0.7:
        return 1.0
    if density >= 0.4:
        return 0.6
    if density >= 0.15:
        return 0.3
    return 0.0


def _lexical_rerank_scores(query: str, chunks: list[RetrievedChunk]) -> list[float]:
    """增强词法重排：TF-IDF 加权 + 短语加分 + 位置衰减。

    - TF-IDF：idf = ln(1 + N/df)，缓解"常见词刷分"；
    - 短语加分：查询词对成簇出现在正文中时额外加分；
    - 位置衰减：输入顺序（粗排名次）靠前的候选乘更大的衰减系数，
      让粗排已有的名次信息不浪费。
    """

    candidate_texts = [item.content.lower() for item in chunks]
    candidate_terms = [tokenize_mixed_text(item.content) for item in chunks]
    document_count = len(chunks)
    query_terms = tokenize_mixed_text(query)

    # 文档频率：该词出现在多少候选正文里。
    doc_freq: dict[str, int] = {}
    for terms in candidate_terms:
        for term in query_terms & terms:
            doc_freq[term] = doc_freq.get(term, 0) + 1

    raw_scores: list[float] = []
    for text, terms in zip(candidate_texts, candidate_terms, strict=True):
        raw = 0.0
        for term in query_terms & terms:
            idf = math.log(1.0 + document_count / doc_freq.get(term, 1))
            raw += _term_occurrences(term, text) * idf
        raw_scores.append(raw)

    max_raw = max(raw_scores) if raw_scores else 0.0
    scores: list[float] = []
    for position, raw in enumerate(raw_scores):
        tfidf_norm = raw / max_raw if max_raw > 0 else 0.0
        phrase = _phrase_bonus(query, candidate_texts[position])
        decay = 1.0 / (1.0 + 0.1 * position)
        scores.append(round(max(0.0, min(0.7 * tfidf_norm + 0.3 * phrase, 1.0)) * decay, 4))
    return scores


# ===================== 第3步：重排入口 =====================
async def rerank_chunks(
    query: str,
    chunks: list[RetrievedChunk],
    llm: LLMChatProvider | None = None,
    *,
    top_n: int = 10,
    use_llm: bool = True,
) -> list[RetrievedChunk]:
    """对粗排候选重排，返回写入 ``rerank_score`` 的新列表（不改动原对象）。

    - ``use_llm`` 为 True 且 ``llm`` 可用时走 LLM listwise 打分；
      LLM 调用异常或输出不可解析时自动降级词法重排；
    - 只对前 ``top_n`` 个候选计算重排分（重排成本随 top_n 线性），
      其余候选 ``rerank_score`` 保持 None，由融合公式按旧权重兜底；
    - 返回顺序：参与重排的候选按重排分降序，未参与者保持原相对顺序。
    """

    if not chunks:
        return []

    head = chunks[:top_n]
    tail = chunks[top_n:]

    if use_llm and llm is not None:
        try:
            scores = await _llm_listwise_scores(query, head, llm)
        except Exception:
            scores = _lexical_rerank_scores(query, head)
    else:
        scores = _lexical_rerank_scores(query, head)

    ranked_head = sorted(
        zip(head, scores), key=lambda pair: pair[1], reverse=True
    )
    result: list[RetrievedChunk] = []
    for item, score in ranked_head:
        # dataclass(slots=True) 没有 __dict__，用 dataclasses.replace 生成带重排分的新对象。
        updated = replace(item, rerank_score=score)
        result.append(updated)
    result.extend(tail)
    return result


# ===================== 第4步：引用置信度 =====================
# 来源类型可信度权重：人工沉淀的内容 > 会话沉淀 > 外部网页。
SOURCE_CONFIDENCE_WEIGHT: dict[KnowledgeSourceType, float] = {
    KnowledgeSourceType.manual: 1.0,
    KnowledgeSourceType.upload: 1.0,
    KnowledgeSourceType.session: 0.95,
    KnowledgeSourceType.image: 0.9,
    KnowledgeSourceType.url: 0.85,
}


def confidence_score(
    final_score: float,
    *,
    source_type: KnowledgeSourceType,
    updated_at: datetime | None,
    freshness_half_life_days: float = 180.0,
    now: datetime | None = None,
) -> float:
    """引用置信度：0.6 相关分 + 0.25 文档新鲜度 + 0.15 来源类型权重。

    新鲜度按半衰期指数衰减：``0.5 ** (age_days / half_life)``，
    刚更新的文档得 1.0，过半个衰期后得 0.5；无时间戳的文档按
    0.8 的中性值处理。结果裁剪到 [0, 1] 并保留 4 位小数。
    """

    reference = now or datetime.now(UTC)
    freshness = 0.8
    if updated_at is not None:
        stamped = updated_at
        if stamped.tzinfo is None:
            stamped = stamped.replace(tzinfo=UTC)
        age_days = max((reference - stamped).total_seconds() / 86400.0, 0.0)
        if freshness_half_life_days > 0:
            freshness = 0.5 ** (age_days / freshness_half_life_days)
        else:
            freshness = 1.0

    weight = SOURCE_CONFIDENCE_WEIGHT.get(source_type, 0.9)
    confidence = 0.6 * max(0.0, min(final_score, 1.0)) + 0.25 * freshness + 0.15 * weight
    return round(max(0.0, min(confidence, 1.0)), 4)
