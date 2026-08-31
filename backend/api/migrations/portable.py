"""迁移脚本共用的可移植类型与默认值。

迁移里原本直接写 ``postgresql.JSONB`` / ``postgresql.UUID`` 和
``sa.text("'{}'::jsonb")``，这些在 SQLite 上会直接失败。这里提供一组
等价物：PostgreSQL 上生成的 DDL 与改造前完全一致，其他方言退化为
JSON / CHAR(36)。

迁移只需把顶部的两个别名指过来，正文一行都不用改。
"""

import sqlalchemy as sa
from alembic import op

from app.infrastructure.database.types import JsonValue, UuidValue

#: 与 ``postgresql.JSONB(astext_type=sa.Text())`` 等价，但跨方言可用。
JSONB = JsonValue

#: 与 ``postgresql.UUID(as_uuid=True)`` 等价，但跨方言可用。
UUID = UuidValue


def json_server_default(literal: str) -> sa.TextClause:
    """JSON 列的 server_default。

    PostgreSQL 上渲染成 ``'{}'::jsonb``（与历史迁移一致，已有库不会产生
    多余的 diff）；其他方言只写字面量。
    """

    from app.infrastructure.database.types import json_default

    return json_default(literal)


def timestamp_column(name: str, **kwargs) -> sa.Column:
    """带时区的时间戳列。SQLite 上退化为不带时区的 DATETIME。"""

    return sa.Column(name, sa.DateTime(timezone=True), **kwargs)


#: 手写 DDL 里用到的类型关键字，按方言给出等价写法。
#: PostgreSQL 一列不改，保证已有部署生成的 SQL 与改造前逐字节一致。
_RAW_TYPES: dict[str, dict[str, str]] = {
    "postgresql": {
        "uuid": "UUID",
        "json": "JSONB",
        "timestamptz": "TIMESTAMPTZ",
        "now": "now()",
    },
    "sqlite": {
        "uuid": "CHAR(36)",
        "json": "JSON",
        "timestamptz": "DATETIME",
        "now": "CURRENT_TIMESTAMP",
    },
}


def raw_types() -> dict[str, str]:
    """当前方言下手写 DDL 该用的类型关键字。

    少数迁移用 ``op.execute`` 写原生 DDL（pgvector 的 ``vector`` 列没法用
    SQLAlchemy 类型表达）。那些字符串里的 ``UUID`` / ``JSONB`` /
    ``TIMESTAMPTZ`` 同样不可移植，这里按方言替换，而不是把它们统一降级
    成最小公分母——那会让 PostgreSQL 丢掉时区语义。

    未知方言按 SQLite 一档处理：都是标准 SQL 关键字，比直接抛错更有用。
    """

    name = op.get_context().dialect.name
    return _RAW_TYPES.get(name, _RAW_TYPES["sqlite"])
