"""查询改写与多查询扩展（Query Rewriting / Multi-Query）。

检索质量的第一道放大器：用户的原始问句往往与文档的表述"字面不同、
语义相同"，单一查询会漏召回。这里做两件事：

1. ``expand_query``：把原始查询改写成 2-3 个变体（同义改写、上位词
   扩展、子问题分解）。LLM 可用时由 LLM 生成；不可用或生成失败时
   降级为确定性规则改写（去停用词、同义词表替换、中英扩展），
   保证没有外部依赖时管线依然能工作。
2. ``reciprocal_rank_fuse``：多查询各自召回一个有序候选列表，
   用 RRF（Reciprocal Rank Fusion，k 默认 60）融合成单一排序，
   避免"某个变体召回很偏"时主导最终结果。
"""

import json
import re
from typing import Any, Protocol

from app.domain.llm.entities import LLMChatResult, LLMMessage
from app.domain.rag.entities import ExpandedQuery

# ===================== 第1步：LLM 的最小结构契约 =====================
class LLMChatProvider(Protocol):
    """领域层对 LLM 服务的结构化契约（与 LLMService.chat 同构）。

    依赖倒置：领域模块不直接 import 应用层 LLMService，
    只依赖这个最小协议，应用层的 LLMService 天然满足它。
    """

    async def chat(
        self,
        messages: list[LLMMessage],
        *args: Any,
        **kwargs: Any,
    ) -> LLMChatResult:
        raise NotImplementedError


# ===================== 第2步：中英文混合分词（与词法信号共用） =====================
_LATIN_TERM_PATTERN = re.compile(r"[a-z0-9_]+")
_CJK_BLOCK_PATTERN = re.compile(r"[一-鿿]+")


def tokenize_mixed_text(text: str) -> set[str]:
    """中英文混合分词：英文按词、中文按 2/3/4 字滑窗切分。

    与记忆检索、词法重叠评分共用同一套分词口径，
    保证"查询侧"与"文档侧"比较的是同一种 token。
    """

    normalized = text.lower()
    terms = set(_LATIN_TERM_PATTERN.findall(normalized))
    for block in _CJK_BLOCK_PATTERN.findall(normalized):
        for size in (2, 3, 4):
            if len(block) < size:
                continue
            terms.update(block[index : index + size] for index in range(len(block) - size + 1))
    return terms


# ===================== 第3步：规则改写（无 LLM 时的确定性降级） =====================
# 无检索意义的功能词：规则改写模式下从查询中剔除，突出主题词。
_STOPWORDS: frozenset[str] = frozenset(
    {
        # 中文功能词（作为子串从中文词块中剔除）
        "的", "了", "和", "与", "或", "在", "是", "吗", "呢", "啊", "吧", "么",
        "怎么", "怎样", "如何", "什么", "哪些", "哪个", "这个", "那个", "一下",
        "我们", "你们", "它们", "我的", "你的",
        # 英文功能词（按整词剔除）
        "the", "a", "an", "is", "are", "was", "were", "do", "does", "did",
        "how", "what", "which", "who", "whom", "why", "when", "where",
        "can", "could", "should", "would", "will", "to", "of", "in", "on",
        "for", "and", "or", "it", "its", "this", "that", "please", "help",
    }
)

# 同义词组：组内第一个词是规范形，规则改写用组内最后一个词替换规范形，
# 制造一个"用另一套词面表达"的变体，扩大字面召回面。
_SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("错误", "报错", "故障", "异常"),
    ("数据库", "db", "database"),
    ("缓存", "cache", "缓存机制"),
    ("接口", "api", "接口文档"),
    ("部署", "deploy", "deployment"),
    ("迁移", "migration", "migrate"),
    ("回滚", "rollback", "回退"),
    ("日志", "log", "logs"),
    ("超时", "timeout", "超时时间"),
    ("配置", "config", "configuration"),
    ("文档", "docs", "documentation"),
    ("权限", "permission", "授权"),
    ("登录", "login", "登陆"),
    ("性能", "performance", "性能优化"),
)

# 中英对照表：查询只出现一种语言时，把另一种语言的主题词补上，
# 让"向量空间里中文章节和英文章节都能被命中"。
_BILINGUAL_GLOSSARY: dict[str, str] = {
    "数据库": "database",
    "缓存": "cache",
    "超时": "timeout",
    "部署": "deployment",
    "迁移": "migration",
    "回滚": "rollback",
    "日志": "log",
    "接口": "api",
    "配置": "configuration",
    "向量": "vector",
    "检索": "retrieval",
    "嵌入": "embedding",
    "权限": "permission",
    "登录": "login",
    "密码": "password",
    "备份": "backup",
    "分词": "tokenization",
    "相似度": "similarity",
}


def _strip_stopwords(query: str) -> str:
    """剔除停用词：中文按子串剔除，英文按整词剔除。"""

    tokens: list[str] = []
    # 按"英文词 / 中文块 / 其他"的顺序扫描，中文块内部做子串剔除。
    for match in re.finditer(r"[a-z0-9_]+|[一-鿿]+|\s+|[^a-z0-9_\s一-鿿]", query.lower()):
        token = match.group(0)
        if _CJK_BLOCK_PATTERN.fullmatch(token):
            cleaned = token
            for stopword in sorted(_STOPWORDS, key=len, reverse=True):
                if not _CJK_BLOCK_PATTERN.fullmatch(stopword):
                    continue
                cleaned = cleaned.replace(stopword, "")
            tokens.append(cleaned)
        elif token in _STOPWORDS:
            continue
        else:
            tokens.append(token)
    return " ".join("".join(tokens).split())


def _replace_synonyms(query: str) -> str:
    """同义词替换：把同义词组的规范形替换为组内最后一个同义词。"""

    lowered = query.lower()
    replaced = query
    for group in _SYNONYM_GROUPS:
        canonical, target = group[0], group[-1]
        if canonical == target:
            continue
        if canonical in lowered:
            replaced = _replace_term(replaced, canonical, target)
    return replaced.strip()


def _replace_term(text: str, term: str, replacement: str) -> str:
    """大小写不敏感替换第一个出现的词，保留原词的其它部分。"""

    match = re.search(re.escape(term), text, flags=re.IGNORECASE)
    if match is None:
        return text
    return text[: match.start()] + replacement + text[match.end() :]


def _bilingual_expand(query: str) -> str:
    """中英扩展：把查询里出现的中文主题词对应的英文追加到句尾（去重）。"""

    lowered = query.lower()
    additions: list[str] = []
    for zh_term, en_term in _BILINGUAL_GLOSSARY.items():
        if zh_term in lowered and en_term not in lowered and en_term not in additions:
            additions.append(en_term)
    if not additions:
        return query.strip()
    return f"{query.strip()} {' '.join(additions)}"


def rule_expand(query: str, max_variants: int = 3) -> list[str]:
    """规则改写：生成确定性的查询变体（无 LLM 依赖）。

    依次尝试三种策略并去重：
    1. 去停用词：突出主题词；
    2. 同义词替换：换一套词面表达；
    3. 中英扩展：补上另一种语言的主题词。
    与原始查询相同、或相互重复的候选会被丢弃，最多返回 ``max_variants`` 个。
    """

    clean = " ".join(query.split())
    if not clean or max_variants <= 0:
        return []

    candidates: list[str] = []
    for strategy in (_strip_stopwords, _replace_synonyms, _bilingual_expand):
        variant = strategy(clean)
        if (
            variant
            and variant.lower() != clean.lower()
            and variant.lower() not in {item.lower() for item in candidates}
        ):
            candidates.append(variant)
    return candidates[:max_variants]


# ===================== 第4步：LLM 改写（优先路径） =====================
_LLM_EXPAND_PROMPT = (
    "你是搜索查询改写助手。请基于用户的原始查询，为向量检索生成 {max_variants} 个改写查询变体，要求：\n"
    "1. 第 1 个：同义改写，用不同的词表达相同的意思；\n"
    "2. 第 2 个：上位词扩展，把具体概念泛化成更通用的表述；\n"
    "3. 第 3 个：子问题分解，把复合问题拆成其中一个关键子问题。\n"
    "每个变体不超过 30 字，不要解释，只输出一个 JSON 字符串数组，例如：[\"...\", \"...\"]。\n"
    "原始查询：{query}"
)


async def _llm_rewrite(
    query: str, llm: LLMChatProvider, max_variants: int
) -> list[str]:
    """调用 LLM 生成查询变体；输出不可解析时抛出异常由调用方降级。"""

    prompt = _LLM_EXPAND_PROMPT.format(max_variants=max_variants, query=query)
    result = await llm.chat([LLMMessage(role="user", content=prompt)])
    return _parse_string_list(result.content, query, max_variants)


def _parse_string_list(content: str, original: str, max_variants: int) -> list[str]:
    """从 LLM 输出中解析字符串数组，容错代码围栏与多余解释文字。

    解析失败或没有任何有效变体时抛出 ValueError，
    由 ``expand_query`` 统一降级到规则改写。
    """

    text = content.strip()
    match = re.search(r"\[[\s\S]*\]", text)
    if match is None:
        raise ValueError("llm output has no json array")
    payload = json.loads(match.group(0))
    if not isinstance(payload, list):
        raise ValueError("llm output is not a list")

    variants: list[str] = []
    for item in payload:
        if not isinstance(item, str):
            continue
        cleaned = " ".join(item.split())
        if not cleaned or cleaned.lower() == original.lower():
            continue
        if cleaned.lower() in {variant.lower() for variant in variants}:
            continue
        variants.append(cleaned[:120])
        if len(variants) >= max_variants:
            break
    if not variants:
        raise ValueError("llm output produced no usable variants")
    return variants


async def expand_query(
    query: str,
    llm: LLMChatProvider | None = None,
    *,
    max_variants: int = 3,
) -> ExpandedQuery:
    """查询改写入口：LLM 多查询优先，失败自动降级规则改写。

    - ``llm`` 为 None 时直接走规则改写（离线/无密钥部署的默认路径）；
    - LLM 调用异常、输出不可解析、变体全被过滤时，同样静默降级，
      查询改写是增强项，任何失败都不得阻塞主检索链路。
    """

    clean = " ".join(query.split())
    if not clean:
        return ExpandedQuery(original=clean)
    if llm is not None:
        try:
            variants = await _llm_rewrite(clean, llm, max_variants)
            return ExpandedQuery(original=clean, variants=variants, method="llm")
        except Exception:
            # 降级是设计内行为：不打日志告警，避免污染检索主链路。
            pass
    return ExpandedQuery(
        original=clean, variants=rule_expand(clean, max_variants), method="rule"
    )


# ===================== 第5步：RRF 多列表融合 =====================
def reciprocal_rank_fuse(
    ranked_lists: list[list[Any]], *, k: int = 60
) -> list[tuple[Any, float]]:
    """Reciprocal Rank Fusion：把多个有序候选列表融合为单一排序。

    每个候选的得分 ``score(id) = Σ 1 / (k + rank_i)``，rank 从 1 计，
    只出现在部分列表里的候选按"缺席列表得 0 分"处理。k 越大，
    名次差异被平滑得越多（推荐 60，Cormack 2009 的取值）。

    返回按得分降序的 (id, score) 列表；同分时保持先出现者在前，
    保证确定性。空列表输入返回空列表。
    """

    scores: dict[Any, float] = {}
    first_seen: dict[Any, int] = {}
    for position, ranked in enumerate(ranked_lists):
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(chunk_id, position)
    fused = sorted(
        scores, key=lambda chunk_id: (-scores[chunk_id], first_seen[chunk_id])
    )
    return [(chunk_id, round(scores[chunk_id], 6)) for chunk_id in fused]
