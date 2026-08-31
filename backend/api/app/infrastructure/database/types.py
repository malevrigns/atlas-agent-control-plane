"""跨方言的列类型。

这个项目的事实源是 PostgreSQL：JSONB、原生 UUID、带时区的时间戳。
但「想先试一下」的人不该被要求先装一套 Postgres。所以这里把三个真正
不可移植的类型收敛成三个别名，模型层只引用别名，不再直接引用
postgresql 方言：

- ``JsonValue``    PostgreSQL 上仍是 JSONB，SQLite 上退化为 JSON 文本；
- ``UuidValue``    PostgreSQL 上仍是原生 uuid，SQLite 上存 CHAR 并双向转换；
- ``UtcDateTime``  两端都保证读出来是带 UTC 时区的 datetime。

前两个用 ``with_variant`` 实现：PostgreSQL 侧生成的 DDL 与改造前逐字节
一致，已有部署不需要任何迁移。第三个必须用 TypeDecorator——SQLite 没有
时区概念，读出来是 naive datetime，一旦和 ``datetime.now(UTC)`` 相减就会
抛 TypeError，记忆衰减、TTL 判定、Checkpoint 时序全都会踩到。
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import CHAR, JSON, DateTime, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ColumnElement


class _SqliteUuid(TypeDecorator):
    """在 SQLite 上用 36 位字符串承载 UUID，读写两侧自动转换。

    只在 SQLite 分支生效；PostgreSQL 走原生 uuid，不经过这里。
    """

    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None or isinstance(value, UUID):
            return value
        return UUID(str(value))


class UtcDateTime(TypeDecorator):
    """始终返回带 UTC 时区的 datetime。

    PostgreSQL 的 timestamptz 自带时区，原样透传；SQLite 存的是 naive
    值，读出时补上 UTC。写入时把带时区的值统一换算到 UTC，避免同一列
    里混进不同基准的时间。
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or dialect.name != "sqlite":
            return value
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None or not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


#: JSON 文档列。PostgreSQL 上是 JSONB，其他方言退化为 JSON。
JsonValue = JSONB().with_variant(JSON(), "sqlite")

#: 主键与外键用的 UUID 列。PostgreSQL 上是原生 uuid。
UuidValue = PgUUID(as_uuid=True).with_variant(_SqliteUuid(), "sqlite")


class json_default(ColumnElement):
    """JSON 列的 server_default。

    ``server_default`` 不支持 ``with_variant``，而 ``'{}'::jsonb`` 这种写法
    只有 PostgreSQL 认。这里按方言分别渲染：PostgreSQL 保留原来的显式
    转换，其他方言只写字面量。
    """

    inherit_cache = True

    def __init__(self, literal: str) -> None:
        self.literal = literal


@compiles(json_default)
def _render_json_default(element, compiler, **kw) -> str:
    return f"'{element.literal}'"


@compiles(json_default, "postgresql")
def _render_json_default_postgresql(element, compiler, **kw) -> str:
    return f"'{element.literal}'::jsonb"
