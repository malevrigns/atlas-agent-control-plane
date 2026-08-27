# RAG 知识库与 Skill 注册中心

本文说明 AtlasAgent 中两类"可治理注入物"的数据模型、生命周期与接口。配套教程为
[第五十章](../tutorial/chapters/50-RAG%20检索增强生成与知识库.md)、
[第五十一章](../tutorial/chapters/51-Skill%20注册中心与上下文注入.md)。

## 四类注入物的边界

Agent 上下文里可能出现四类外部内容，它们的存储与治理路径必须分开。

| 注入物 | 回答什么 | 谁产生 | 治理重点 |
| --- | --- | --- | --- |
| Tool | 我能做什么 | 开发者写代码 | 权限、风险、幂等、审计 |
| Memory | 我以前知道什么 | Agent 执行中产生 | 写入门禁、有效期、supersede |
| RAG | 资料里怎么说 | 团队批量摄取文档 | 索引一致性、引用可追溯 |
| Skill | 这类任务该怎么做 | 团队人工沉淀 | 版本冻结、发布审批、启停 |

渲染进入提示词时的顺序是**先技能、再记忆、最后对话历史**：操作指引应该在模型读到具体内容之前建立行为框架。

## RAG 数据模型

```text
knowledge_bases          租户与配置边界（embedding 模型与切分参数在建库时冻结）
  └─ knowledge_documents 原文 + 摄取状态 + 内容指纹（同库 sha256 唯一）
       └─ knowledge_chunks  检索正文的事实源，带 char_start / char_end
            └─ 向量           由 VectorStore 独立管理，只存 embedding + 回链 id
```

三条不变量：

1. **embedding 配置冻结在知识库上。** 换模型必须建新库重灌——不同维度的向量不在同一空间。
2. **向量库只存回链，正文永远以 `knowledge_chunks` 为准。** 两份正文早晚漂移。
3. **检索只命中 `status = ready` 的文档。** 摄取中或失败的内容绝不进入模型上下文。

### 文档状态机

```text
pending → processing → ready
                    ↘ failed（error 字段记录原因，可 reingest 重建）
```

摄取管线中任何一步失败都会 rollback 并把文档标记为 `failed`，不会留下半成品索引。

### 向量后端

`VectorStore` 是协议，所有实现把相似度统一归一化到 `[0, 1]`（越大越相似），因此
`RAG_MIN_SCORE` 阈值可以跨后端复用。

| 后端 | 配置 | 适用场景 |
| --- | --- | --- |
| pgvector（默认） | `RAG_VECTOR_BACKEND=pgvector` | 与业务同库，复用现有备份与迁移体系 |
| Qdrant | `RAG_VECTOR_BACKEND=qdrant` + `docker compose --profile qdrant up -d` | 向量独立扩缩容，过滤能力更强 |

pgvector 实现会在运行时探测扩展是否可用：可用时使用原生 `vector` 列与 HNSW 索引，
不可用时 embedding 列为 JSONB，检索退回应用层余弦计算（正确性一致，性能降级）。
迁移脚本据此在建表时选择列类型，因此**任何 PostgreSQL 实例都能完成迁移**。

### Embedding

配置在 `backend/api/config/llm.yaml` 的 `embedding` 节点，指向 `providers` 中任一
OpenAI 兼容服务。密钥缺失时自动降级为确定性本地哈希向量（`local_hash`），保证离线可运行——
该实现没有语义理解能力，仅供教学与联调，不要用于生产。

### 检索评分

```text
final_score = vector_score * 0.7 + lexical_score * 0.3
```

词法分用中英文混合分词计算查询与 chunk 的加权重叠，用于缓解纯向量召回对精确技术名词的"高分幻觉"。
命中结果带编号引用 `[1] 文档标题 · chunk#3`，与 `context_text` 中的编号一一对应，
chunk 的 `char_start`/`char_end` 可回溯到原文字符位置。

每次检索写入一条 `retrieval_traces`（与记忆检索共用同一张表），记录检索计划、候选与最终选中项。

### 检索重排与置信度
查询管线在混合评分之后还有两级增强，均可独立开关：

1. **查询改写与 RRF 融合。** `RAG_QUERY_EXPAND_ENABLED` 开启后，检索会先对查询做改写（LLM 改写，失败时降级为规则改写），产生 2-3 个变体后逐查询检索，
   用倒数排名融合（RRF）合并候选。融合信号记在 chunk 的 `fusion_score`（归一化到 0-1；单查询检索时为 1）。
2. **重排与置信度。** `RAG_RERANK_ENABLED` 开启时，对候选做二次相关分评估（`RAG_RERANK_USE_LLM` 决定是否调用 LLM），结果记在 `rerank_score`；
   最终 `final_score` 按 `RAG_WEIGHT_RERANK` 权重与原始分混合。每条命中另附 `confidence`（0-1）：相关分 × 文档新鲜度 × 来源类型加权的综合评估。

以上分数均为可选字段，旧版检索结果不携带时返回 `null`。查询响应的 `retrieval_metadata` 记录检索过程元数据
（耗时、候选数、使用的查询变体、重排开关与权重），与 `retrieval_traces` 使用同一套审计语言，供前端展示与运维排查。
### RAG 接口

```http
GET    /api/rag/knowledge-bases                    列出知识库
POST   /api/rag/knowledge-bases                    创建知识库
GET    /api/rag/knowledge-bases/{id}               详情
PATCH  /api/rag/knowledge-bases/{id}               更新名称与描述
DELETE /api/rag/knowledge-bases/{id}               删除（连同 chunk 与向量）
GET    /api/rag/knowledge-bases/{id}/documents     列出文档（可按状态过滤）
POST   /api/rag/knowledge-bases/{id}/documents     摄取文档
POST   /api/rag/knowledge-bases/{id}/query         检索
POST   /api/rag/documents/{id}/reingest            重建单文档索引
DELETE /api/rag/documents/{id}                     删除文档
GET    /api/rag/health                             向量后端与 embedding 运行状态
```

### Agent 工具

`knowledge_search` 注册在内置工具表里，风险等级 low，无需额外权限，超时 20 秒。
它是项目中第一个异步 handler——ToolRuntime 会直接 `await` 协程函数，
不再经过线程池，避免在工作线程中再开事件循环。

模块开关：`rag`（`runtime-config/modules.yaml`），关闭后 `knowledge_search` 调用会被 Runtime 拒绝。

### 对话自动召回

`knowledge_search` 要求模型自己知道知识库 ID，普通问答很难触发。
因此直答路径（`AgentRunnerService._load_rag_context`）在每次回答前会自动召回一次：
遍历全部非空知识库、逐库检索、跨库按 `final_score` 排序，
过 `CHAT_RAG_MIN_SCORE` 阈值后取前 `CHAT_RAG_TOP_K` 条注入 system 上下文。

注入片段带编号、文档标题、所属知识库与相关度，并要求模型
"优先依据片段作答、句末标注（来源：《文档标题》）、片段无关则忽略、不得编造"。
本轮命中的文档标题会写进 `task_done` 事件的 `rag_sources` 字段，供客户端展示引用来源。

三个设计约束：

- 自动召回使用**独立数据库会话**，不与当前请求事务纠缠；
- `record_trace=False`，自动召回不写入检索审计，避免污染人工检索记录；
- 整段捕获异常并静默降级——无知识库、向量服务异常或测试环境无数据库时，
  问答退回纯模型回答，绝不因为检索失败而中断对话。

把 `CHAT_RAG_TOP_K` 设为 `0` 即可整体关闭自动召回，只保留工具式检索。

> 检索命中提示：混合检索里的词法通道按字面匹配，机构或产品的**简称、别名、缩写
> 要显式写进文档正文**（例如"星海人工智能研究院（内部也常简称星智院）"），
> 否则用户用简称提问时召回分会明显偏低。

## Skill 数据模型

`skills` 表由第 45 章预留、第 51 章激活。核心字段：

```text
skill_key + version   联合唯一，semver 版本
name / description    展示与检索用
instructions          注入模型上下文的操作指引正文
risk_level            复用 ToolRiskLevel 四级
status                draft / published / deprecated / archived
enabled               与 status 正交的运行开关
tags                  参与相关度匹配
test_record           评测结果
```

### 生命周期

```text
draft ──publish──> published ──deprecate──> deprecated
  ↑                    │
  └──create_version────┘
```

三条规则：

1. **published 内容冻结。** 编辑已发布技能返回 409，要改内容必须派生新版本。这样审计记录里的
   `deploy-check@1.2.0` 才是一个不可变引用，事后能复现"当时 Agent 看到的指引"。
2. **发布与启用分离。** `status=published` 表示内容定稿，`enabled=true` 表示现在要用它。
   线上出问题时 `enabled=false` 可以一秒止血，同时保留完整历史。
3. **注入需要同时满足** `enabled` + `status=published` + 未删除。

派生新版本会复制内容、递增 patch 版本、状态回到 draft。**发布新版本不会自动停用旧版本**——
灰度和回滚需要这个自由度，但意味着运维要手动关闭旧版，否则两个版本会同时注入。

删除是软删除，且已启用的已发布技能必须先停用才能删除。

### 上下文注入

按词法相关度打分，双预算裁剪（默认 `CONTEXT_SKILL_LIMIT=3`、`CONTEXT_SKILL_MAX_CHARS=2000`）。
匹配范围是名称、描述、标签全量 + instructions 前 400 字——指引正文全文参与会让"内容多"的技能天然占优。

选择结果可解释：每条命中带 `relevance_score` 与 `matched_terms`。
`GET /api/skills/context?query=...` 可以在不跑真实任务的前提下预览注入结果，
返回里的 `rendered` 字段就是模型会看到的原始文本。

技能注入失败不会阻塞会话上下文构建——它是增强项，异常时降级为不注入。

### Skill 接口

```http
GET    /api/skills                          列表（status / enabled_only / search）
GET    /api/skills/context?query=...        注入命中调试
GET    /api/skills/{skill_id}               详情
GET    /api/skills/{skill_key}/versions     某个 key 的全部版本
POST   /api/skills                          创建草稿
PATCH  /api/skills/{skill_id}               编辑草稿（published 返回 409）
POST   /api/skills/{skill_id}/versions      派生下一个草稿版本
POST   /api/skills/{skill_id}/publish       发布
POST   /api/skills/{skill_id}/enabled       启用 / 停用
POST   /api/skills/{skill_id}/deprecate     废弃（同时自动停用）
POST   /api/skills/{skill_id}/test-record   记录评测结果
DELETE /api/skills/{skill_id}               软删除
```

## 配置速查

```bash
# 向量后端与 embedding
RAG_VECTOR_BACKEND=pgvector        # pgvector | qdrant
RAG_EMBEDDING_PROVIDER=auto        # auto | local_hash
RAG_EMBEDDING_DIM=256              # 仅本地哈希实现使用
EMBEDDING_API_KEY=                 # 留空则降级为本地向量

# 切分与检索预算
RAG_CHUNK_SIZE=800
RAG_CHUNK_OVERLAP=120
RAG_TOP_K=5
RAG_CANDIDATE_LIMIT=24
RAG_MIN_SCORE=0.15
RAG_MAX_CONTEXT_CHARS=3600
RAG_MAX_DOCUMENT_CHARS=200000

# Qdrant（仅 RAG_VECTOR_BACKEND=qdrant 时使用）
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=
QDRANT_TIMEOUT_SECONDS=10

# 技能注入预算
CONTEXT_SKILL_LIMIT=3
CONTEXT_SKILL_MAX_CHARS=2000
CONTEXT_SKILL_MIN_SCORE=0.1

# 对话自动召回（直答路径）
CHAT_RAG_TOP_K=4                   # 设为 0 关闭自动召回
CHAT_RAG_MIN_SCORE=0.42            # 底噪约 0.35，阈值必须明显高于它
CHAT_RAG_CONTEXT_CHARS=6000
```

三种典型部署组合：

| 场景 | 组合 |
| --- | --- |
| 教学 / 离线演示 | `pgvector` + `local_hash`，零外部依赖 |
| 内网生产（推荐） | `pgvector` + OpenAI 兼容 embedding |
| 大规模检索 | `qdrant` + OpenAI 兼容 embedding |

## 桌面端管理

Electron 客户端左侧导航提供「技能」与「知识库」两个管理视图：

- **技能**：列表与搜索、草稿编辑、发布、启停、版本历史（标出所有启用中的版本）、注入命中调试；
- **知识库**：建库、文档摄取与状态（含失败原因）、重建索引、检索验证台（分别显示综合/向量/词法三个分数）。

详见 [客户端指南](CLIENTS.md) 与[第五十二章](../tutorial/chapters/52-桌面客户端重构与管理工作台.md)。
