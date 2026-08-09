# 第五十章. RAG 检索增强生成与知识库

## 50.1 本章目标

到第四十九章为止，AtlasAgent 已经有了会话、工具、沙箱、类型化长期记忆和 Checkpoint。但它仍然缺少一项在真实业务里几乎必备的能力：**让 Agent 读团队自己的资料**。

模型权重里没有你们公司的部署手册、没有上个季度的故障复盘、没有内部 API 的字段含义。把这些内容一次性塞进 prompt 不现实——上下文窗口有限、成本高、而且大部分内容与当前问题无关。工业界的标准解法是 RAG（Retrieval-Augmented Generation，检索增强生成）：**先检索，再生成**。

完成本章后，你将能够：

- 说清 RAG 与长期记忆（Memory）的职责分工，不把两者混为一谈；
- 设计知识库 / 文档 / chunk / 向量四层数据模型，并知道各自的事实源边界；
- 实现一个段落优先、句子回退、带重叠的文档切分器，并解释每个参数的取舍；
- 抽象 `EmbeddingProvider` 与 `VectorStore` 两个接口，让向量后端可替换；
- 用 pgvector 与 Qdrant 两种后端实现同一套协议，并理解各自的适用场景；
- 写出一条**失败可观测**的摄取管线：任何一步出错都标记 failed，绝不留下半成品索引；
- 写出一条**带引用**的检索管线：向量召回 + 词法重排 + 预算裁剪 + 编号引用；
- 把检索能力注册为 Agent 工具 `knowledge_search`，并让 ToolRuntime 支持异步 handler。

本章新增代码集中在：

```text
backend/api/app/domain/rag/                    领域层：实体、切分、两个协议
backend/api/app/infrastructure/rag/            基础设施：embedding 与向量存储实现
backend/api/app/infrastructure/repositories/rag_repository.py
backend/api/app/application/rag_service.py     应用层：摄取与检索管线
backend/api/app/presentation/http/routes/rag.py
backend/api/app/infrastructure/agent_tools/rag.py
backend/api/migrations/versions/202608090001_rag_knowledge_and_skill_registry.py
```

## 50.2 RAG 和长期记忆是两件事

第二十七章和第四十五章做的 Memory，和本章的 RAG，都在"往上下文里塞外部信息"，但它们的性质完全不同。把它们混在一张表里是新手最常犯的架构错误。

| 维度 | 长期记忆 Memory | 知识库 RAG |
| --- | --- | --- |
| 数据来源 | Agent 执行过程中**自己产生**的经验、结论、用户偏好 | 团队**已有**的文档、手册、规范、历史工单 |
| 写入方式 | 由 Write Gate 审核后写入，有 candidate / verified 生命周期 | 由人或流程批量摄取，只有摄取成功与否 |
| 单条粒度 | 一条结构化事实（subject-predicate-value） | 一段原文切片（chunk），保留上下文语境 |
| 是否可变 | 会被 supersede、过期、失效 | 文档更新时整体重建索引 |
| 检索目标 | "我以前知道什么" | "资料里怎么说" |
| 失效风险 | 记忆过期后仍被注入 → 决策错误 | 索引漂移（文档改了索引没改）→ 引用错误 |

一句话总结：**Memory 是 Agent 的经验，RAG 是团队的资料。** 经验需要治理生命周期，资料需要治理索引一致性。

两者在检索层可以共用一套"预算 + 可解释评分 + 审计"的语言——本章的检索 trace 就复用了第四十五章的 `retrieval_traces` 表——但存储与写入路径必须分开。

## 50.3 RAG 的四个典型失败模式

在写代码之前，先明确我们要防的是什么。几乎所有"RAG 效果不好"的抱怨都能归到这四类：

**失败一：切分把答案切断了。** 文档里"回滚步骤"这一节被切成两个 chunk，前半段讲"先停服务"，后半段讲"再执行 downgrade"。检索命中前半段，模型只回答了一半。**对策：chunk 之间保留重叠。**

**失败二：向量召回的"高分幻觉"。** 纯语义向量对"数据库迁移"和"数据仓库同步"这类字面不同、语义相近的内容给了高分，但用户问的是精确的技术名词。**对策：向量分数 + 词法重叠混合重排。**

**失败三：引用不可追溯。** 模型说"根据文档，应该先备份"，但没人知道这句话来自哪份文档的哪一段，也没法验证。**对策：每个 chunk 带编号引用，回链 document_id 与 chunk 序号。**

**失败四：索引漂移。** 文档摄取到一半失败，chunk 写了一半，向量没写完。之后检索命中这些孤儿 chunk，返回残缺内容。**对策：摄取管线要么全成功标记 ready，要么回滚并标记 failed；检索只查 ready 文档。**

后面每一节的设计，都是在回应这四条中的某一条。

## 50.4 四层数据模型

```text
KnowledgeBase   知识库：租户与配置边界（embedding 模型、切分参数被冻结在这一层）
  └─ KnowledgeDocument   文档：原文 + 摄取状态 + 内容指纹
       └─ KnowledgeChunk  切片：检索正文的事实源（有字符区间，可回溯原文）
            └─ Vector      向量：只存 embedding + 回链 id，不存正文
```

四层的关键设计决策有三个。

**决策一：embedding 配置冻结在知识库上，不是全局配置。**

```python
class KnowledgeBaseModel(Base):
    __tablename__ = "knowledge_bases"
    embedding_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=800)
    chunk_overlap: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
```

为什么？因为**换 embedding 模型必须重建索引**。1024 维的 bge-m3 向量和 1536 维的 text-embedding-3-small 向量不在同一个空间里，混用会得到毫无意义的相似度。把配置冻结在建库时刻，一个知识库内部永远维度一致；要换模型就建新库重灌，老库继续可用。这是生产上最省事的做法。

**决策二：向量存储不出现在 ORM 模型里。**

`KnowledgeChunkModel` 里没有 embedding 列。向量由 `VectorStore` 层独立管理：pgvector 后端写 `knowledge_chunk_embeddings` 表（原生 SQL），Qdrant 后端写外部 collection。这样 ORM 对向量后端零感知，切后端不用改模型。

**决策三：向量库只存回链，正文永远以 chunk 表为准。**

```python
@dataclass(slots=True)
class VectorRecord:
    chunk_id: UUID
    document_id: UUID
    knowledge_base_id: UUID
    embedding: list[float]
    metadata: dict[str, object] = field(default_factory=dict)
```

如果正文同时存在数据库和向量库两份，早晚会漂移。检索时先从向量库拿 `chunk_id` 列表，再回数据库读正文——多一次查询，换来永不漂移。

文档表上还有一条同库唯一约束：

```python
sa.UniqueConstraint("knowledge_base_id", "content_sha256", name="uq_knowledge_document_sha")
```

内容指纹去重，防止同一份文档被反复摄取导致检索结果被同一内容刷屏。

## 50.5 切分器：段落优先，句子回退，固定重叠

切分是 RAG 质量的第一道闸门。chunk 太大，召回不精确、上下文预算容易爆；chunk 太小，语义被切碎、引用不完整。

`backend/api/app/domain/rag/chunking.py` 实现了四步策略。它是纯函数、无外部依赖，因此可以完全单元测试。

**第一步：按空行切段落。** 段落是作者自己划定的语义单元，优先尊重它。

```python
def _split_paragraphs(text: str) -> list[TextSpan]:
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
```

注意 `TextSpan` 保留了 `char_start` 与 `char_end`。这不是可有可无的元数据——有了字符区间，任何一个 chunk 都能精确回溯到原文位置，这是引用可验证的基础。测试里专门有一条断言守住这个不变量：

```python
def test_char_ranges_point_back_to_source(self) -> None:
    text = "第一段内容。\n\n第二段内容，比第一段稍微长一点。"
    for span in split_text(text, chunk_size=12, chunk_overlap=0):
        self.assertEqual(text[span.char_start : span.char_end], span.content)
```

**第二步：超长段落按句子回退切分。** 一段写了三千字的技术说明，必须再切。中英文句末标点一起处理：

```python
_SENTENCE_PATTERN = re.compile(r"(?<=[。！？!?；;.])\s*")
```

**第三步：极端情况硬切。** 压缩日志、base64、没有任何标点的长串，句子切分也无能为力，按固定窗口硬切保底。这条路径平时不会走到，但少了它，一份异常文件就能让整个摄取挂掉。

**第四步：装箱与重叠。** 先把连续的小切片合并到接近 `chunk_size`（减少碎片），再给相邻 chunk 附加重叠：

```python
def _apply_overlap(spans, text, chunk_overlap):
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
```

重叠只向前看一个 chunk，索引体积的增长因此是线性可控的（约 `overlap / chunk_size`，默认 120/800 = 15%）。这就是对**失败模式一**的回应：答案横跨切分边界时，至少有一个 chunk 完整包含它。

参数怎么选？经验值：

- 中文技术文档：`chunk_size=800`、`chunk_overlap=120`（约 1-2 个自然段）；
- 代码或 API 文档：可以调大到 1200，因为代码块不宜切断；
- FAQ 或短问答：调小到 300-400，一问一答就是一个 chunk。

默认值放在 `settings.rag_chunk_size` / `rag_chunk_overlap`，建库时可以逐库覆盖。

## 50.6 Embedding 抽象与离线降级

向量化服务与聊天模型解耦：聊天可以走 DeepSeek，向量化走任何 OpenAI 兼容的 `/embeddings` 端点。协议只有三个方法：

```python
class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str
    dim: int

    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...
```

`OpenAICompatibleEmbeddingClient` 有两个容易被忽略的实现细节。

**细节一：必须按 index 还原顺序。** OpenAI 兼容协议不保证 `data` 数组的顺序与输入一致，但每一项带 `index`。如果直接按数组顺序取，会把 A 段的向量安到 B 段头上——这种 bug 极难发现，因为检索仍然"能跑"，只是结果莫名其妙。

```python
ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
```

测试里专门构造了一个乱序返回的 MockTransport 来守这条：

```python
def handler(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    # 故意乱序返回，客户端必须按 index 还原。
    data = [
        {"index": position, "embedding": [float(position), 1.0]}
        for position in reversed(range(len(payload["input"])))
    ]
    return httpx.Response(200, json={"data": data})
```

**细节二：分批。** 大部分服务商对单次请求的条数和总 token 有上限，默认 `batch_size=16`，一份大文档会自动拆成多次请求。

**离线降级。** 教学环境不应该因为没有 API Key 就跑不起来。`HashingEmbeddingProvider` 把中英文 n-gram 哈希散列到固定维度并做 L2 归一化：

```python
def _embed(self, text: str) -> list[float]:
    vector = [0.0] * self.dim
    for term in self._terms(text):
        digest = hashlib.sha256(term.encode("utf-8")).digest()
        slot = int.from_bytes(digest[:4], "big") % self.dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[slot] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    return vector if norm == 0 else [value / norm for value in vector]
```

它**没有语义理解能力**，请不要在生产里用。但它满足三个性质：同一文本向量稳定、共享 n-gram 的文本相似度更高、整条链路零外部依赖。这让你可以先把摄取和检索管线跑通、把测试写完，再接真实模型。

工厂函数按优先级选择实现：

```python
def build_embedding_provider():
    if settings.rag_embedding_provider == "local_hash":
        return HashingEmbeddingProvider(dim=settings.rag_embedding_dim)
    config = load_llm_config()
    embedding_config = config.embedding
    if embedding_config is not None:
        provider = config.providers.get(embedding_config.provider)
        if provider is not None:
            api_key = os.environ.get(provider.api_key_env or "", "")
            if api_key:
                return OpenAICompatibleEmbeddingClient(...)
    return HashingEmbeddingProvider(dim=settings.rag_embedding_dim)
```

密钥缺失 → 自动降级，而不是启动失败。这是"教学项目可运行"与"生产项目可配置"之间的平衡点。

对应的 `config/llm.yaml` 新增了 embedding 节点：

```yaml
providers:
  embedding_compatible:
    base_url: https://api.siliconflow.cn/v1
    api_key_env: EMBEDDING_API_KEY
    timeout_seconds: 30

embedding:
  provider: embedding_compatible
  model: BAAI/bge-m3
  dim: 1024
  batch_size: 16
```

`dim` 填 0 表示由首次真实响应自动学习维度，省得为每个模型查文档。

## 50.7 VectorStore 抽象

这是本章最值得强调的架构决策。应用层只依赖协议：

```python
class VectorStore(Protocol):
    backend_name: str

    async def ensure_ready(self, *, knowledge_base_id: UUID, embedding_dim: int) -> None: ...
    async def upsert(self, records: list[VectorRecord]) -> int: ...
    async def query(self, *, knowledge_base_id: UUID, embedding: list[float], top_k: int) -> list[VectorMatch]: ...
    async def delete_document(self, *, knowledge_base_id: UUID, document_id: UUID) -> int: ...
    async def delete_knowledge_base(self, *, knowledge_base_id: UUID) -> int: ...
    async def health(self) -> dict[str, object]: ...
```

抽象带来三个实际收益：

1. **按部署形态选后端。** 内网单机交付用 pgvector（少一个组件要运维），大规模场景用 Qdrant（检索与过滤能力更强）。业务代码一行不改。
2. **单元测试不需要外部服务。** 测试里注入一个内存实现就能跑完整的摄取-检索闭环。
3. **迁移路径清晰。** 从 pgvector 迁到 Qdrant，只需要重灌一次索引，不动业务。

协议里还有一个约定值得注意：**所有实现的 `score` 统一归一化到 [0, 1]，越大越相似。** pgvector 的 `<=>` 返回余弦距离，Qdrant 的 Cosine 返回 [-1, 1] 相似度，两者都要在实现内部映射到同一区间。否则上层的阈值 `rag_min_score` 就没法跨后端复用。

`cosine_similarity` 作为纯 Python 兜底也放在领域层：

```python
def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = sum(a * a for a in left) ** 0.5
    norm_right = sum(b * b for b in right) ** 0.5
    if norm_left == 0 or norm_right == 0:
        return 0.0
    # 余弦取值 [-1, 1]，线性映射到 [0, 1] 便于统一比较与展示。
    return (dot / (norm_left * norm_right) + 1) / 2
```

## 50.8 pgvector 实现：原生索引与优雅降级

默认后端。向量与业务数据同库，复用既有的备份、迁移与运维体系。

`docker-compose.yml` 里把 postgres 镜像换成官方 pgvector 镜像（数据目录与 `postgres:16` 兼容，已有部署可以原地升级）：

```yaml
postgres:
  image: pgvector/pgvector:pg16
```

但我们不能假设所有人的 PostgreSQL 都装了 pgvector——有人用云托管数据库，有人用现成实例。所以迁移脚本会**在运行时探测扩展是否可用**：

```python
def _pgvector_available() -> bool:
    bind = op.get_bind()
    if bind is None or getattr(bind, "engine", None) is None:
        return False  # 离线生成 SQL 时按不可用处理
    try:
        row = bind.execute(
            sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
        ).fetchone()
    except Exception:
        return False
    return row is not None
```

可用时建 `vector` 列，不可用时建 `JSONB` 列。表结构其余部分完全一致，因此上层代码只需要判断一次列类型：

```python
async def _is_native(self) -> bool:
    if self._native is not None:
        return self._native
    result = await self.db_session.execute(
        text("""
            SELECT udt_name FROM information_schema.columns
            WHERE table_name = 'knowledge_chunk_embeddings'
              AND column_name = 'embedding'
        """)
    )
    row = result.fetchone()
    self._native = bool(row and row[0] == "vector")
    return self._native
```

原生模式下用 `<=>` 余弦距离算子，让 PostgreSQL 走 ANN 索引：

```sql
SELECT chunk_id, document_id,
       1 - (embedding::vector(1024) <=> CAST(:query AS vector(1024))) AS cosine
FROM knowledge_chunk_embeddings
WHERE knowledge_base_id = :knowledge_base_id
  AND embedding_dim = :dim
ORDER BY embedding::vector(1024) <=> CAST(:query AS vector(1024))
LIMIT :top_k
```

降级模式下把该知识库的向量全部读出来，在应用层算余弦。**正确性完全一致，性能随数据量线性下降。** 这个取舍是刻意的：宁可慢，不可错，也不能因为环境不满足就完全不能用。

HNSW 索引的建立放在 `ensure_ready` 而不是迁移里，原因是列类型是无维度修饰的 `vector`（要容纳不同知识库的不同维度），无法在建表时直接建 ANN 索引。首次写入某个维度时按需补建：

```python
async def ensure_ready(self, *, knowledge_base_id: UUID, embedding_dim: int) -> None:
    if not await self._is_native():
        return
    index_name = f"ix_kce_hnsw_{embedding_dim}"
    await self.db_session.execute(
        text(f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON knowledge_chunk_embeddings
            USING hnsw ((embedding::vector({int(embedding_dim)})) vector_cosine_ops)
            WHERE embedding_dim = {int(embedding_dim)}
        """)
    )
```

部分索引（`WHERE embedding_dim = N`）让不同维度的知识库各走各的索引，互不干扰。

## 50.9 Qdrant 实现：可选的独立向量库

适合向量规模超出单库承载、或需要独立扩缩容的场景。实现走 REST API，不引入 `qdrant-client` 依赖——少一个依赖，少一次版本冲突。

每个知识库对应一个独立 collection，天然实现租户隔离：

```python
@staticmethod
def collection_name(knowledge_base_id: UUID) -> str:
    return f"atlas_kb_{str(knowledge_base_id).replace('-', '')}"
```

`ensure_ready` 是幂等的：先 GET 探测，不存在才 PUT 创建。

```python
async def ensure_ready(self, *, knowledge_base_id, embedding_dim) -> None:
    name = self.collection_name(knowledge_base_id)
    existing = await self._request("GET", f"/collections/{name}", allow_missing=True)
    if existing.get("result"):
        return
    await self._request(
        "PUT",
        f"/collections/{name}",
        json_body={"vectors": {"size": embedding_dim, "distance": "Cosine"}},
    )
```

构造函数接受一个可选的 `transport`，测试里注入 `httpx.MockTransport` 就能在不启动 Qdrant 的情况下验证整套 REST 编排。这是给基础设施类写测试的通用技巧：**把 I/O 的最后一跳做成可注入的**。

docker-compose 里用 profile 控制，默认不启动：

```yaml
qdrant:
  image: qdrant/qdrant:v1.15.1
  profiles:
    - qdrant
```

启用方式：

```bash
docker compose --profile qdrant up -d
# 然后在 .env 里设置
RAG_VECTOR_BACKEND=qdrant
QDRANT_URL=http://qdrant:6333
```

## 50.10 摄取管线：让失败可观测

摄取是"写"路径，最容易留下不一致状态。`RagService.ingest_document` 的完整流程：

```text
1. 校验知识库存在、标题与正文非空、长度不超限
2. 计算 content_sha256，同库去重（重复 → 409）
3. 落库文档，状态 pending
4. 标记 processing
5. 按知识库冻结的配置切分
6. 批量向量化
7. ensure_ready（建索引 / 建 collection）
8. 写 chunk 表
9. 写向量存储
10. 标记 ready + 刷新知识库统计
```

第 4 步到第 10 步整体包在 try/except 里，任何异常都走同一条失败路径：

```python
except Exception as exc:
    await self.uow.rollback()
    message = exc.message if isinstance(exc, AppException) else f"{type(exc).__name__}: {exc}"
    failed = await self.uow.knowledge_documents.set_status(
        document.id,
        status=KnowledgeDocumentStatus.failed,
        chunk_count=0,
        error=message[:2000],
    )
    await self.uow.commit()
    return failed or document
```

三个要点：

**先 rollback，再写失败状态。** 顺序反了的话，失败状态会被 rollback 一起回滚掉，文档永远卡在 processing。

**错误信息落库。** `error` 字段保存到文档行上，运维在管理面板直接能看到"为什么这份文档没进索引"，不用翻日志。

**返回终态而不是抛异常。** 摄取失败是业务结果，不是系统错误。调用方拿到 `status=failed` 的文档对象，可以决定重试还是放弃。

对应的测试注入一个必定爆炸的向量存储：

```python
def test_failed_ingestion_marks_document_failed(self) -> None:
    class ExplodingStore(InMemoryVectorStore):
        async def upsert(self, records) -> int:
            raise RuntimeError("vector backend down")
    ...
    document = await service.ingest_document(knowledge_base.id, title="doc", content="任何内容")
    self.assertIs(document.status, KnowledgeDocumentStatus.failed)
    self.assertIn("vector backend down", document.error)
```

重建入口 `reingest_document` 先清旧索引再走同一条管线，让失败文档和内容更新共用一套逻辑：

```python
async def reingest_document(self, document_id: UUID) -> KnowledgeDocument:
    document = await self._require_document(document_id)
    knowledge_base = await self.get_knowledge_base(document.knowledge_base_id)
    await self.vector_store.delete_document(
        knowledge_base_id=document.knowledge_base_id, document_id=document.id
    )
    await self.uow.knowledge_chunks.delete_by_document(document.id)
    await self.uow.commit()
    return await self._process_document(knowledge_base, document)
```

删除路径同理，**先删向量再删事实源**：向量库删除失败时整体回滚，不会留下孤儿索引。

## 50.11 检索管线：混合重排、预算、引用

检索是"读"路径，要解决失败模式二、三、四。

**第一步：查询向量化 + 向量召回。** 注意召回数量 `max(limit, rag_candidate_limit)` 大于最终返回的 `top_k`——多召回一些，给重排留出空间。只召回 5 条再重排 5 条，重排就没有意义了。

```python
query_embedding = await self.embedding.embed_query(clean_query)
matches = await self.vector_store.query(
    knowledge_base_id=knowledge_base_id,
    embedding=query_embedding,
    top_k=max(limit, settings.rag_candidate_limit),
)
```

**第二步：回读正文，过滤非 ready 文档。**

```python
if document.status is not KnowledgeDocumentStatus.ready:
    continue
```

这一行直接回应失败模式四。摄取中或摄取失败的内容，绝不给模型。测试专门守住它：

```python
def test_query_ignores_documents_that_are_not_ready(self) -> None:
    ...
    await uow.knowledge_documents.set_status(document.id, status=KnowledgeDocumentStatus.failed)
    result = await service.query(knowledge_base.id, query="唯一内容片段")
    self.assertEqual(result.chunks, [])
```

**第三步：词法重叠混合重排。** 这是对失败模式二的回应：

```python
chunk_terms = self._tokenize(chunk.content)
matched = sorted(query_terms & chunk_terms, key=lambda term: (-len(term), term))[:12]
matched_weight = sum(max(len(term), 1) for term in matched)
query_weight = min(sum(max(len(term), 1) for term in query_terms) or 1, 40)
lexical_score = min(matched_weight / query_weight, 1.0)
final_score = round(match.score * 0.7 + lexical_score * 0.3, 4)
```

分词沿用第四十一章记忆检索的中英文混合策略：英文按单词，中文按 2-4 字 n-gram。`query_weight` 上限 40 是一个经验修正——中文 n-gram 会产生大量片段，不封顶的话 `FastAPI`、`PostgreSQL` 这类精确技术名词会被稀释掉。

权重 0.7 / 0.3 的含义：**以语义为主，用字面命中做修正。** 如果你的场景里精确术语很重要（如法律、医药、内部代号），可以调到 0.5 / 0.5。

**第四步：双预算裁剪 + 编号引用。** 条数预算 `top_k` 和字符预算 `rag_max_context_chars` 同时生效：

```python
for item in ranked:
    if len(included) >= limit:
        break
    remaining = settings.rag_max_context_chars - used_chars
    if remaining <= 0:
        break
    content = item.content
    if len(content) > remaining:
        if remaining <= 12:
            break
        content = content[: remaining - 9] + "...[已裁剪]"
    item.content = content
    item.citation = f"[{len(included) + 1}] {item.document_title} · chunk#{item.seq}"
    included.append(item)
    used_chars += len(content)
```

引用编号 `[1]`、`[2]` 与拼装出的 `context_text` 一一对应：

```python
context_lines = [
    f"[{index + 1}] （{item.document_title}）{item.content}"
    for index, item in enumerate(included)
]
```

模型在回答里写 `[1]`，用户点开就能看到对应的文档标题与 chunk 序号，chunk 又有 `char_start`/`char_end` 能定位到原文。这就是失败模式三的完整解法——**引用链一路可追溯到字符位置**。

**第五步：写审计 trace。** 复用第四十五章的 `retrieval_traces` 表，与记忆检索共用一条审计链路：

```python
await self.uow.control_plane.record_retrieval_trace({
    "project_id": knowledge_base.project_id,
    "query": result.query,
    "plan": {
        "channels": ["vector", "lexical"],
        "backend": self.vector_store.backend_name,
        "embedding": {"provider": ..., "model": ...},
        "weights": {"vector": 0.7, "lexical": 0.3},
        "knowledge_base_id": str(knowledge_base_id),
    },
    "candidates": [...],
    "selected_memory_ids": [str(item.chunk_id) for item in included],
    "token_budget": settings.rag_max_context_chars // 4,
})
```

事后排查"为什么模型答错了"，能直接看到当时召回了哪些候选、各自什么分数、最终选了哪几条。

## 50.12 接入 Agent：knowledge_search 工具与异步 handler

检索能力必须能被 Agent 主动调用，而不只是人在界面上查。注册为工具：

```python
registry.register(
    AgentTool(
        definition=ToolDefinition(
            name="knowledge_search",
            description=(
                "在指定知识库中检索与问题相关的内容片段，"
                "返回带引用编号和评分的证据，用于回答业务与领域问题。"
            ),
            risk_level=ToolRiskLevel.low,
            required_permissions=(),
            idempotent=True,
            timeout_seconds=20.0,
            parameters=[...],
        ),
        handler=_run_knowledge_search,
    )
)
```

这里遇到一个真实的工程问题：**`_run_knowledge_search` 是异步的，但第四十六章的 ToolRuntime 只支持同步 handler**（它把 handler 丢进 `asyncio.to_thread`）。检索需要访问 PostgreSQL 和向量存储，都是 async I/O，在工作线程里再开一个事件循环是反模式。

正确的做法是让 Runtime 同时支持两种 handler：

```python
# 同步 handler 走线程池；异步 handler（如 RAG 检索）直接 await，
# 避免在工作线程里再开事件循环。
if inspect.iscoroutinefunction(tool.handler):
    raw = await asyncio.wait_for(
        tool.handler(**checked_arguments),
        timeout=timeout_seconds,
    )
else:
    raw = await asyncio.wait_for(
        asyncio.to_thread(tool.handler, **checked_arguments),
        timeout=timeout_seconds,
    )
```

风险、权限、幂等、脱敏、审计、超时这些控制面逻辑一行没动——这正是第四十六章把它们收敛到 Runtime 的价值：新增一类 handler，只需要在执行那一步分叉。

配套测试验证异步 handler 的正常路径和超时路径：

```python
def test_async_handler_respects_timeout(self) -> None:
    runtime = build_runtime()
    result = asyncio.run(runtime.execute("async_slow", {"text": "x"}, ToolExecutionContext()))
    self.assertIs(result.status, ToolInvocationStatus.timed_out)
```

工具自己开独立数据库会话，与调用方事务隔离：

```python
async with AsyncSessionLocal() as db_session:
    service = RagService(UnitOfWork(db_session))
    result = await service.query(kb_id, query=str(query), top_k=_normalize_top_k(top_k))
```

失败不抛异常，转成结构化输出——和第二十章 SearchTool 的处理一致。一次检索失败不应该让整个 Agent 任务崩掉：

```python
except AppException as exc:
    return json.dumps({
        "kind": "rag_error",
        "knowledge_base_id": str(knowledge_base_id),
        "query": str(query),
        "message": exc.message,
        "items": [],
    }, ensure_ascii=False)
```

最后在模块开关里登记，让运维能整体停用 RAG：

```python
DEFAULT_MODULES = {..., "rag": True}
TOOL_MODULES = {..., "knowledge_search": "rag"}
```

## 50.13 HTTP 接口一览

```http
GET    /api/rag/knowledge-bases                          列出知识库
POST   /api/rag/knowledge-bases                          创建知识库
GET    /api/rag/knowledge-bases/{id}                     知识库详情
PATCH  /api/rag/knowledge-bases/{id}                     更新名称与描述
DELETE /api/rag/knowledge-bases/{id}                     删除知识库（连同向量）

GET    /api/rag/knowledge-bases/{id}/documents           列出文档（可按状态过滤）
POST   /api/rag/knowledge-bases/{id}/documents           摄取文档
POST   /api/rag/documents/{id}/reingest                  重建单文档索引
DELETE /api/rag/documents/{id}                           删除文档（连同 chunk 与向量）

POST   /api/rag/knowledge-bases/{id}/query               检索
GET    /api/rag/health                                   向量后端与 embedding 运行状态
```

一次完整的手工验证：

```bash
ATLAS_KEY="$(sed -n 's/^ATLAS_API_KEY=//p' .env)"
BASE=http://localhost:8088/api/rag

# 1. 建库
KB=$(curl -s -X POST $BASE/knowledge-bases \
  -H "X-Atlas-API-Key: ${ATLAS_KEY}" -H "Content-Type: application/json" \
  -d '{"name":"工程运维知识库","description":"部署与故障处理"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["id"])')

# 2. 摄取
curl -s -X POST $BASE/knowledge-bases/$KB/documents \
  -H "X-Atlas-API-Key: ${ATLAS_KEY}" -H "Content-Type: application/json" \
  -d '{"title":"数据库运维","content":"数据库迁移使用 Alembic 管理。\n\n回滚需要执行 downgrade 脚本，并先停止写入流量。"}'

# 3. 检索
curl -s -X POST $BASE/knowledge-bases/$KB/query \
  -H "X-Atlas-API-Key: ${ATLAS_KEY}" -H "Content-Type: application/json" \
  -d '{"query":"数据库迁移怎么回滚","top_k":3}'

# 4. 看后端状态
curl -s -H "X-Atlas-API-Key: ${ATLAS_KEY}" $BASE/health
```

检索返回里 `chunks[].citation` 就是模型该引用的编号，`context_text` 可以直接拼进 prompt。

## 50.14 配置与部署

`.env.example` 新增：

```bash
RAG_VECTOR_BACKEND=pgvector      # 或 qdrant
RAG_EMBEDDING_PROVIDER=auto      # 或 local_hash（强制离线）
RAG_EMBEDDING_DIM=256            # 仅本地哈希实现使用
RAG_CHUNK_SIZE=800
RAG_CHUNK_OVERLAP=120
RAG_TOP_K=5
RAG_CANDIDATE_LIMIT=24
RAG_MIN_SCORE=0.15
RAG_MAX_CONTEXT_CHARS=3600
RAG_MAX_DOCUMENT_CHARS=200000
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=
EMBEDDING_API_KEY=
```

三种典型部署组合：

| 场景 | 配置 | 说明 |
| --- | --- | --- |
| 教学 / 离线演示 | `pgvector` + `local_hash` | 零外部依赖，`docker compose up` 就能跑通全链路 |
| 内网生产（推荐） | `pgvector` + OpenAI 兼容 embedding | 少一个组件要运维，备份与迁移复用现有体系 |
| 大规模检索 | `qdrant` + OpenAI 兼容 embedding | 向量独立扩缩容，过滤与 payload 能力更强 |

## 50.15 本章验收

```bash
cd backend/api
uv run python -m unittest tests.test_rag_chunking tests.test_rag_embeddings \
    tests.test_rag_service tests.test_qdrant_vector_store tests.test_tool_runtime_async
```

重点检查：

- 切分：空文本返回空、重叠确实回看上一个 chunk、字符区间能还原原文、非法参数抛 `ValueError`；
- Embedding：同文本向量稳定、向量已归一化、相近文本得分高于无关文本、服务商乱序返回能按 index 还原、HTTP 错误转 502；
- 摄取：成功标记 ready 且 chunk 数与向量数一致、重复内容返回 409、向量后端故障时标记 failed 并记录原因；
- 检索：命中带引用编号、`context_text` 含 `[1]`、非 ready 文档被排除、写入了一条 retrieval trace；
- Qdrant：collection 幂等创建、点位 payload 含 document_id、分数映射到 [0,1]、服务端 500 转 502；
- ToolRuntime：异步 handler 被直接 await、异步 handler 的超时正常生效。

迁移链验证：

```bash
uv run alembic upgrade head --sql | head -50   # 离线 SQL 可生成（走 JSONB 降级分支）
```

## 50.16 常见坑

**坑一：换了 embedding 模型忘记重建索引。** 新旧向量维度不同时，pgvector 的 `embedding_dim` 过滤会让老数据直接查不到（表现为"检索突然什么都搜不到"）；维度碰巧相同则更糟——能查到，但结果毫无意义。规矩：**换模型 = 建新库 + 重灌**。

**坑二：chunk_overlap 设得太大。** 有人为了"保险"把 overlap 设成 chunk_size 的一半，结果索引体积翻倍、召回结果里全是内容高度重复的相邻 chunk，实际信息量反而下降。15% 左右是合理起点。

**坑三：把整份 PDF 当一个 chunk。** 有些实现直接一份文档一个向量。文档越长，向量越"平均化"，最后什么都不像。必须切。

**坑四：忘了过滤文档状态。** 检索时不判断 `status is ready`，摄取失败的残留 chunk 就会混进结果。这类 bug 在测试环境很难复现，因为测试数据总是摄取成功的。

**坑五：在 handler 里复用调用方的数据库会话。** 工具执行可能跨越很长时间，复用会话会把调用方的事务拖长，甚至造成锁等待。`knowledge_search` 自己开会话就是为了这个。

## 50.17 本章小结

RAG 的门槛在于"跑通"很容易——切一切、算个向量、查个 top-k，一百行就能出 demo。但生产级 RAG 的难点全在边界上：切分边界、事务边界、租户边界、预算边界、引用边界、失败边界。

本章的每个设计都对应一条边界：

- 知识库冻结 embedding 配置 → 维度边界；
- 向量只存回链 → 事实源边界；
- 摄取失败标记 failed 并记录原因 → 一致性边界；
- 检索只查 ready 文档 → 可信边界；
- 双预算裁剪 + 编号引用 → 上下文与可追溯边界；
- VectorStore 协议 → 部署形态边界。

下一章我们把同样的治理思路用到另一类资产上：**团队沉淀的操作指引**，也就是 Skill 注册中心。

---

[← 第四十九章. 迁移、测试与交付验收](49-迁移、测试与交付验收.md) · [返回目录](../README.md) · [第五十一章. Skill 注册中心与上下文注入 →](51-Skill%20注册中心与上下文注入.md)
