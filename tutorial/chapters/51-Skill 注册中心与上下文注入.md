# 第五十一章. Skill 注册中心与上下文注入

## 51.1 本章目标

上一章解决了"Agent 怎么读团队的资料"。这一章解决另一个问题：**Agent 怎么按团队的规矩做事**。

这两件事经常被混淆。资料回答"是什么"（我们的部署流程文档里写了哪些步骤），规矩回答"怎么做"（这次发布，你应该先跑测试、再核对迁移、最后确认回滚脚本）。前者是知识，后者是**可复用的操作指引**——在 Claude、Cursor 这类产品里通常叫 Skill。

没有 Skill 的 Agent，每次面对同类任务都在从零发挥：这次记得检查迁移，下次忘了；这次输出格式是 Markdown 表格，下次变成一段散文。团队积累的经验没有沉淀载体。

完成本章后，你将能够：

- 区分 Skill、Tool、Memory、RAG 四种"注入物"的职责，不把它们做成一锅粥；
- 设计 draft → published → deprecated → archived 的技能生命周期，并说清为什么 published 必须冻结；
- 用 semver 做版本演进，让每一次 Agent 行为都能回溯到当时生效的技能定义；
- 实现启用/停用与注入的分离控制；
- 写一个可解释的技能选择器：按相关度打分、双预算裁剪、渲染成提示词片段；
- 把技能上下文接进第十五章的上下文工程管线，并保证它失败时不拖垮会话。

本章新增代码：

```text
backend/api/app/domain/skills/                  领域层：实体、生命周期、仓库协议
backend/api/app/infrastructure/database/models/skill.py
backend/api/app/infrastructure/repositories/skill_repository.py
backend/api/app/application/skill_service.py    应用层：治理 + 选择 + 渲染
backend/api/app/presentation/http/routes/skills.py
```

## 51.2 四种注入物的分工

Agent 的上下文里现在可能出现四类外部内容。它们的边界必须清楚，否则会互相污染。

| 注入物 | 回答什么 | 谁产生 | 治理重点 |
| --- | --- | --- | --- |
| **Tool** | "我能做什么" | 开发者写代码 | 权限、风险、幂等、审计（第 46 章） |
| **Memory** | "我以前知道什么" | Agent 执行中产生 | 写入门禁、有效期、supersede（第 45 章） |
| **RAG** | "资料里怎么说" | 团队批量摄取文档 | 索引一致性、引用可追溯（第 50 章） |
| **Skill** | "这类任务该怎么做" | 团队人工沉淀 | 版本冻结、发布审批、启停（本章） |

最容易犯的错误是**把 Skill 做成 Tool**。区别在于：Tool 是可执行的代码，Runtime 负责执行它；Skill 是给模型看的文字指引，模型读完自己决定怎么行动。一个"部署前检查"的 Skill 不会自己跑测试，它会告诉模型"你应该调用 shell 工具跑测试"。

第二容易犯的错误是**把 Skill 做成 Memory**。Memory 是 Agent 自动抽取的，可信度参差不齐，所以需要 Write Gate。Skill 是人写的、经过评审的，它的治理重点不是"可不可信"，而是"这个版本什么时候生效、谁批准的、改了之后旧行为还能不能复现"。

## 51.3 复活第 45 章预留的表

第四十五章的 Control Plane 迁移里已经建过一张 `skills` 表，但当时只是占位，没有任何代码使用它：

```python
op.create_table(
    "skills",
    sa.Column("id", UUID, primary_key=True),
    sa.Column("skill_key", sa.String(128), nullable=False),
    sa.Column("version", sa.String(32), nullable=False),
    sa.Column("description", sa.Text(), nullable=False),
    sa.Column("definition", JSONB, nullable=False),
    sa.Column("risk_level", sa.String(16), nullable=False),
    sa.Column("status", sa.String(32), nullable=False, server_default="candidate"),
    sa.Column("test_record", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("created_at", ...),
    sa.Column("published_at", ...),
    sa.UniqueConstraint("skill_key", "version", name="uq_skill_version"),
)
```

本章不重建这张表，而是**在原表上增量演进**。这是生产环境处理"预留表"的正确姿势——已经上线的表结构，即使没人用，也可能有历史数据或外部依赖（比如 `skill_executions` 的外键）。

```python
op.add_column("skills", sa.Column("name", sa.String(160), nullable=False, server_default=""))
op.add_column("skills", sa.Column("instructions", sa.Text(), nullable=False, server_default=""))
op.add_column("skills", sa.Column("tags", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
op.add_column("skills", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
op.add_column("skills", sa.Column("created_by", sa.String(128), nullable=False, server_default="system"))
op.add_column("skills", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
op.add_column("skills", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
# 第 45 章的默认状态 candidate 并入新的 draft 生命周期。
op.execute("UPDATE skills SET status = 'draft' WHERE status = 'candidate'")
op.alter_column("skills", "status", server_default="draft")
op.create_index("ix_skills_key_status", "skills", ["skill_key", "status", "enabled"])
```

三个细节值得注意：

**所有新增列都有 server_default。** 表里可能已经有行，不给默认值的 NOT NULL 列会让迁移直接失败。

**状态值做数据迁移，而不是兼容两套枚举。** `UPDATE skills SET status = 'draft' WHERE status = 'candidate'` 一次性归一。代码层面再兜一次底，防止迁移前的连接读到老值：

```python
raw_status = self.status if self.status in set(SkillStatus) else SkillStatus.draft.value
```

**新增列不叫 `content` 而叫 `instructions`。** 命名要说清用途：这段文字是**要注入模型上下文的操作指引**，不是随便什么内容。

`enabled` 默认 `false` 也是刻意的：新建的技能不会意外影响线上 Agent 行为，必须显式启用。

## 51.4 生命周期：为什么 published 必须冻结

```python
class SkillStatus(StrEnum):
    draft = "draft"           # 可以随意修改，不会注入
    published = "published"   # 内容冻结，允许启用并注入
    deprecated = "deprecated" # 保留审计，不再注入
    archived = "archived"     # 彻底下线，仅供追溯
```

核心规则只有一条：**published 版本不可原地修改。要改内容必须开新版本。**

```python
async def update_skill(self, skill_id: UUID, **kwargs) -> Skill:
    skill = await self._require_skill(skill_id)
    # 生产纪律：published 内容冻结。要改内容必须开新版本。
    if skill.status is not SkillStatus.draft:
        raise AppException(
            message="only draft skills can be edited; create a new version instead",
            code=409,
            status_code=409,
        )
```

为什么这么严格？设想一个真实场景：上周三 Agent 执行了一次生产发布，出了问题。你去复盘，发现它跳过了迁移检查。你打开 `deploy-check` 技能一看——里面明明写着"必须核对迁移"。

问题是，上周三的时候写着吗？如果技能可以原地修改，你**永远无法回答这个问题**。审计日志里记的是 `skill_key=deploy-check`，但那个 key 指向的内容已经变了。

冻结之后，审计记录里的 `deploy-check@1.2.0` 是一个不可变的引用。想知道当时发生了什么，直接查那个版本的 `instructions` 就行。这和 Docker 镜像 tag 不能覆盖、npm 包版本不能重发是同一个道理。

其余的状态迁移约束：

```python
async def publish_skill(self, skill_id: UUID) -> Skill:
    skill = await self._require_skill(skill_id)
    if skill.status is SkillStatus.published:
        return skill                      # 幂等：重复发布不报错
    if skill.status is not SkillStatus.draft:
        raise AppException(message=f"cannot publish a {skill.status.value} skill", code=409, ...)
    if not skill.instructions.strip():
        raise AppException(message="cannot publish a skill without instructions", code=422, ...)
```

空指引不许发布——一个没有内容的技能被启用后，只会白白占用上下文预算。

## 51.5 启用与发布是两个开关

`status` 和 `enabled` 是两个正交的维度，很多人会想合并成一个字段，这是错的。

- `status=published` 表示**这个版本的内容已经定稿**；
- `enabled=true` 表示**现在要不要用它**。

分开的价值在运维时体现得最明显：线上出问题，怀疑是某个技能的指引把模型带偏了。你需要**立刻停用它**，但不能删、也不能改状态——事后还要复盘。这时 `enabled=false` 是唯一正确的操作：一秒生效，内容和历史完整保留。

```python
async def set_enabled(self, skill_id: UUID, *, enabled: bool) -> Skill:
    skill = await self._require_skill(skill_id)
    if enabled and skill.status is not SkillStatus.published:
        raise AppException(message="only published skills can be enabled", code=409, ...)
    ...
```

注入判定同时看三个条件，写在领域实体上而不是散落在查询里：

```python
def is_injectable(self) -> bool:
    """只有已发布且启用的技能才能进入 Agent 上下文。"""
    return (
        self.enabled
        and self.deleted_at is None
        and self.status is SkillStatus.published
    )
```

删除也做了保护：已启用的已发布技能不能直接删，必须先停用。这避免了"手滑删掉线上正在用的技能"。

```python
if skill.status is SkillStatus.published and skill.enabled:
    raise AppException(message="disable the skill before deleting it", code=409, ...)
```

而且删除是软删除——`deleted_at` 打标，行还在，审计链不断。

## 51.6 版本演进

新版本 = 复制当前内容 + 递增 semver + 状态回到 draft：

```python
async def create_new_version(self, skill_id: UUID, *, version: str | None = None, created_by: str = "operator") -> Skill:
    source = await self._require_skill(skill_id)
    next_version = version or self._bump_patch(source.version)
    self._validate_version(next_version)
    if not self._is_newer(next_version, source.version):
        raise AppException(
            message=f"new version {next_version} must be greater than {source.version}",
            code=400, status_code=400,
        )
    existing = await self.uow.skills.get_by_key_version(source.skill_key, next_version)
    if existing is not None:
        raise AppException(message=f"skill {source.skill_key}@{next_version} already exists", code=409, ...)
    draft = await self.uow.skills.add(
        skill_key=source.skill_key,
        version=next_version,
        name=source.name,
        description=source.description,
        instructions=source.instructions,
        definition=dict(source.definition),
        risk_level=source.risk_level.value,
        tags=list(source.tags),
        created_by=created_by,
    )
```

版本号严格 semver，用正则校验：

```python
_SEMVER_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
```

版本必须递增。`_is_newer` 按元组比较，避免字符串比较把 `1.10.0` 判成小于 `1.9.0`：

```python
@staticmethod
def _is_newer(candidate: str, current: str) -> bool:
    left = tuple(int(part) for part in candidate.split("."))
    right = tuple(int(part) for part in current.split("."))
    return left > right
```

skill_key 也有格式约束，因为它会出现在审计记录和提示词里，需要稳定可读：

```python
_SKILL_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
```

一个典型的演进流程：

```text
deploy-check@1.0.0  published, enabled   ← 线上生效中
deploy-check@1.0.1  draft                ← 正在改，不影响线上
        ↓ publish + enable
deploy-check@1.0.1  published, enabled   ← 新版本生效
deploy-check@1.0.0  published, enabled   ← 注意：老版本还开着！
```

最后一步要小心：发布新版本**不会自动停用老版本**。这是刻意的（自动停用会让灰度和回滚变得不可控），但意味着运维需要手动关掉旧版，否则两个版本会同时注入。管理面板在版本历史里用绿色对勾标出所有启用中的版本，就是为了让这种状态一眼可见。

## 51.7 可解释的技能选择

不是所有技能都注入。一次任务只该看到相关的那几条，否则上下文预算会被无关指引吃光。

选择逻辑与第四十一章的记忆检索一脉相承：词法相关度 + 双预算。

```python
async def build_skill_context(self, *, query: str) -> SkillContext:
    clean_query = " ".join(query.split())
    candidates = await self.uow.skills.list_injectable(limit=100)
    query_terms = self._tokenize(clean_query)

    ranked: list[SkillContextItem] = []
    for skill in candidates:
        skill_text = " ".join([skill.name, skill.description, " ".join(skill.tags)])
        skill_terms = self._tokenize(skill_text + " " + skill.instructions[:400])
        matched = sorted(query_terms & skill_terms, key=lambda term: (-len(term), term))[:8]
        matched_weight = sum(max(len(term), 1) for term in matched)
        query_weight = min(sum(max(len(term), 1) for term in query_terms) or 1, 40)
        score = min(matched_weight / query_weight, 1.0)
        if score < settings.context_skill_min_score:
            continue
        ranked.append(SkillContextItem(..., relevance_score=round(score, 4), matched_terms=matched))
    ranked.sort(key=lambda item: item.relevance_score, reverse=True)
```

几个设计取舍：

**为什么只匹配 instructions 的前 400 字？** 指引正文可能很长，全文参与匹配会让"内容多"的技能天然占优。前 400 字通常包含适用场景描述，这是判断相关性最有信息量的部分。名称、描述、标签则全量参与——它们本来就是为检索而写的。

**为什么不用向量？** 技能总量通常在几十到几百条，词法匹配足够，而且**可解释**：`matched_terms` 直接告诉运维"这条技能是因为命中了『部署』『发布』才被选中的"。管理面板的命中调试功能就靠它。如果你的技能库增长到上千条，可以复用第五十章的 embedding 基础设施升级成混合检索，`SkillContext` 结构不用变。

**双预算裁剪：**

```python
for item in ranked:
    if len(included) >= settings.context_skill_limit:
        break
    remaining = settings.context_skill_max_chars - used_chars
    if remaining <= 0:
        break
    if len(item.instructions) > remaining:
        if remaining <= 12:
            break
        item.instructions = item.instructions[: remaining - 9] + "...[已裁剪]"
    included.append(item)
    used_chars += len(item.instructions)
```

默认 `context_skill_limit=3`、`context_skill_max_chars=2000`。技能指引比记忆条目长得多，条数必须压得更狠。

渲染成提示词片段：

```python
@staticmethod
def render_skill_context(context: SkillContext) -> str:
    if not context.items:
        return ""
    lines = [
        (
            f"- [{item.skill_key}@{item.version}] {item.name}"
            f"（风险 {item.risk_level}，相关度 {item.relevance_score:.2f}）：\n"
            f"  {item.instructions}"
        )
        for item in context.items
    ]
    return "可用技能（按团队沉淀的最佳实践执行）：\n" + "\n".join(lines)
```

**版本号写进提示词**是有意为之。模型的输出里如果提到"按 deploy-check 的要求"，我们能从同一次会话的上下文里确认它当时看到的是哪个版本。

## 51.8 接入上下文工程管线

第十五章的 `ContextEngineeringService.build_snapshot` 已经在构造记忆检索查询，技能选择直接复用同一份查询文本：

```python
# 4.5 用同一份检索查询挑选可注入的已发布技能。
#     技能来自注册中心（published + enabled），失败时不阻塞会话上下文。
skill_context = None
try:
    from app.application.skill_service import SkillService

    skill_context = await SkillService(self.uow).build_skill_context(query=memory_query)
except Exception:  # noqa: BLE001 - 技能注入是增强项，不能拖垮上下文构建
    skill_context = None
```

这里的 try/except 不是偷懒。上下文构建在会话主链路上，**任何一个增强功能都不应该让整个会话打不开**。技能表查询失败、迁移还没跑、数据异常——这些情况下会话应该照常工作，只是少了技能注入。

渲染时技能段落排在最前面：

```python
sections: list[str] = []

if snapshot.skill_context is not None and snapshot.skill_context.items:
    rendered_skills = SkillService.render_skill_context(snapshot.skill_context)
    if rendered_skills:
        sections.append(rendered_skills)

if snapshot.memory_context.items:
    ...
```

顺序有讲究：**先规矩，再事实，最后对话历史**。操作指引应该在模型读到具体内容之前就建立行为框架。

最终 Agent 看到的提示词大致长这样：

```text
可用技能（按团队沉淀的最佳实践执行）：
- [deploy-check@1.0.0] 部署前检查（风险 low，相关度 0.42）：
  1. 运行完整测试套件，确认无失败用例
  2. 核对本次发布包含的数据库迁移，确认 downgrade 脚本存在
  3. 确认回滚触发条件已写入发布记录

长期记忆：
- [project_fact] 生产环境使用蓝绿部署 (重要度 4，相关度 0.38)

最近消息：
- user: 帮我准备今晚的生产发布
```

## 51.9 HTTP 接口一览

```http
GET    /api/skills                         列表（支持 status / enabled_only / search）
GET    /api/skills/context?query=...       注入命中调试（预览会注入哪些技能）
GET    /api/skills/{skill_id}              详情
GET    /api/skills/{skill_key}/versions    某个 key 的全部版本
POST   /api/skills                         创建草稿
PATCH  /api/skills/{skill_id}              编辑草稿（published 会 409）
POST   /api/skills/{skill_id}/versions     从当前版本派生下一个草稿
POST   /api/skills/{skill_id}/publish      发布（内容从此冻结）
POST   /api/skills/{skill_id}/enabled      启用 / 停用
POST   /api/skills/{skill_id}/deprecate    废弃（同时自动停用）
POST   /api/skills/{skill_id}/test-record  记录评测结果
DELETE /api/skills/{skill_id}              软删除
```

`/context` 这个接口值得单独说。它让运维可以在不跑一次真实任务的前提下，回答"这个任务会注入哪些技能"：

```bash
curl -H "X-Atlas-API-Key: ${ATLAS_KEY}" \
  "http://localhost:8088/api/skills/context?query=准备一次生产部署发布"
```

返回里既有结构化的命中项（含 `relevance_score` 和 `matched_terms`），也有 `rendered` 字段——就是模型会看到的原始文本。调试提示词时这比翻日志高效得多。

一次完整的技能生命周期演练：

```bash
ATLAS_KEY="$(sed -n 's/^ATLAS_API_KEY=//p' .env)"
BASE=http://localhost:8088/api/skills

# 1. 创建草稿
SKILL=$(curl -s -X POST $BASE \
  -H "X-Atlas-API-Key: ${ATLAS_KEY}" -H "Content-Type: application/json" \
  -d '{
    "skill_key":"deploy-check",
    "name":"部署前检查",
    "description":"生产发布前的标准检查动作",
    "instructions":"1. 运行完整测试套件\n2. 核对数据库迁移与 downgrade 脚本\n3. 确认回滚触发条件",
    "tags":["部署","发布"]
  }' | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["id"])')

# 2. 发布并启用
curl -s -X POST $BASE/$SKILL/publish -H "X-Atlas-API-Key: ${ATLAS_KEY}"
curl -s -X POST $BASE/$SKILL/enabled -H "X-Atlas-API-Key: ${ATLAS_KEY}" \
  -H "Content-Type: application/json" -d '{"enabled":true}'

# 3. 验证注入
curl -s -H "X-Atlas-API-Key: ${ATLAS_KEY}" \
  "$BASE/context?query=准备今晚的生产发布"

# 4. 尝试原地修改（预期 409）
curl -s -X PATCH $BASE/$SKILL -H "X-Atlas-API-Key: ${ATLAS_KEY}" \
  -H "Content-Type: application/json" -d '{"instructions":"改一改"}'

# 5. 正确做法：派生新版本
curl -s -X POST $BASE/$SKILL/versions -H "X-Atlas-API-Key: ${ATLAS_KEY}"
```

## 51.10 本章验收

```bash
cd backend/api
uv run python -m unittest tests.test_skill_service
```

重点检查：

- 非法 skill_key 与非 semver 版本被拒绝；
- published 技能原地编辑返回 409；
- 未发布的技能不能启用；
- 派生新版本自动 bump patch、复制内容、状态回到 draft，且不允许降版本；
- 废弃后自动停用，且不再出现在注入结果里；
- 相关技能按分数排序、无关查询返回空、渲染文本包含 `skill_key@version`；
- 启用中的已发布技能不能直接删除，停用后可以软删除。

## 51.11 常见坑

**坑一：把 Skill 当 prompt 模板用。** 有人把整段系统提示词塞进一个技能，然后所有任务都注入它。这样做失去了"按相关度选择"的意义，而且预算会被一条撑满。技能应该是**窄而具体**的：一条技能解决一类任务。

**坑二：发布新版本后忘记停用旧版本。** 两个版本同时注入，模型收到两份可能矛盾的指引。上线检查清单里应该有这一条。

**坑三：instructions 写成描述性文字。** "本技能用于部署检查" 这种句子对模型没有任何行动指导价值。指引应该是**祈使句 + 可验证步骤**："运行 `pytest -q`，确认退出码为 0"。

**坑四：把敏感信息写进 instructions。** 技能内容会原样进入模型上下文。生产密钥、内部地址、客户名单都不该出现在这里。

**坑五：忘记技能选择失败要降级。** 上下文构建是主链路，任何增强功能挂掉都不能让会话打不开。

## 51.12 本章小结

Skill 注册中心表面上是一个 CRUD，实质上是一套**行为治理机制**。它回答的是"上周三 Agent 为什么那样做"这类审计问题，而不只是"怎么让模型多知道点东西"。

三条规矩支撑整个设计：

1. **published 冻结**——让每一次行为都能回溯到确定的指引版本；
2. **发布与启用分离**——让线上问题能一秒止血，同时保留完整历史；
3. **相关度选择 + 双预算**——让注入既有效又不失控。

到这里，后端的四类注入物（Tool / Memory / RAG / Skill）都有了各自的治理面。

---

[← 第五十章. RAG 检索增强生成与知识库](50-RAG%20检索增强生成与知识库.md) · [返回目录](../README.md) · [第五十三章. 直答路由与推理流直播 →](53-直答路由与推理流直播.md)
