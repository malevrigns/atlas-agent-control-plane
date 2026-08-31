"""迁移链的可执行断言。

仓库里曾经出现过两个迁移脚本共用同一个 revision ID 的情况：``alembic``
在加载 versions 目录时就直接报错，``alembic upgrade head`` 一行也跑不了。
测试全绿、应用也能起（测试用 ``create_all`` 建表），但任何一次真实部署
都会失败——这正是最贵的一类 bug：只有新用户会踩到。

所以这里把三件事钉成 CI 约束：

1. revision ID 唯一、且只有一个 head（迁移链不允许分叉）；
2. 整条链能在 SQLite 上从零跑到 head（跨方言可移植性）；
3. 跑完的表结构与 ORM 模型一致（迁移与模型不许漂移）。

第 2、3 条必须在子进程里做：``app.core.config.settings`` 与 engine 都是
模块级单例，导入后再改 ``DATABASE_URL`` 已经来不及。
"""

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent.parent

SCRIPT = textwrap.dedent(
    """
    import json, os, sys
    from pathlib import Path

    workdir = Path(sys.argv[1])
    db_path = workdir / "migrated.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["LOG_LEVEL"] = "CRITICAL"

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    config = Config(str(Path.cwd() / "alembic.ini"))
    command.upgrade(config, "head")

    import app.infrastructure.database.models  # noqa: F401
    from app.infrastructure.database.base import Base

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    db_tables = set(inspector.get_table_names()) - {"alembic_version"}
    orm_tables = set(Base.metadata.tables)

    missing_columns = {}
    for name in sorted(orm_tables & db_tables):
        db_columns = {column["name"] for column in inspector.get_columns(name)}
        orm_columns = {column.name for column in Base.metadata.tables[name].columns}
        gap = sorted(orm_columns - db_columns)
        if gap:
            missing_columns[name] = gap
    engine.dispose()

    print("REPORT:" + json.dumps({
        "missing_tables": sorted(orm_tables - db_tables),
        "missing_columns": missing_columns,
        "table_count": len(db_tables),
    }))
    """
)


class MigrationChainTests(unittest.TestCase):
    """不连数据库也能查的静态约束。"""

    def _script_directory(self):
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        return ScriptDirectory.from_config(Config(str(API_ROOT / "alembic.ini")))

    def test_revision_ids_are_unique(self) -> None:
        """重复的 revision ID 会让 alembic 拒绝加载整个 versions 目录。"""

        version_files = sorted((API_ROOT / "migrations" / "versions").glob("*.py"))
        self.assertGreater(len(version_files), 0, "没有找到迁移脚本，路径可能变了")

        seen: dict[str, str] = {}
        duplicates: list[str] = []
        for path in version_files:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("revision: str = "):
                    revision = line.split("=", 1)[1].strip().strip('"')
                    if revision in seen:
                        duplicates.append(f"{revision}: {seen[revision]} 与 {path.name}")
                    seen[revision] = path.name
                    break
        self.assertEqual(duplicates, [], "revision ID 必须唯一")

    def test_chain_has_exactly_one_head(self) -> None:
        """多个 head 意味着 upgrade head 无法确定目标，部署会直接失败。"""

        heads = self._script_directory().get_heads()
        self.assertEqual(len(heads), 1, f"迁移链分叉了：{heads}")

    def test_every_revision_is_reachable_from_base(self) -> None:
        """每个脚本都必须挂在链上，孤立脚本永远不会被执行。"""

        script_directory = self._script_directory()
        head = script_directory.get_heads()[0]
        walked = {rev.revision for rev in script_directory.walk_revisions("base", head)}
        known = {rev.revision for rev in script_directory.walk_revisions()}
        self.assertEqual(known - walked, set(), "存在没有接入迁移链的脚本")


class MigrationOnSqliteTests(unittest.TestCase):
    """真实跑一遍迁移——这是唯一能证明新用户装得起来的方式。"""

    def test_upgrade_head_on_sqlite_matches_orm_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [sys.executable, "-c", SCRIPT, tmp],
                cwd=API_ROOT,
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(
                completed.returncode,
                0,
                f"SQLite 迁移失败：\n{completed.stdout}\n{completed.stderr}",
            )
            line = next(
                (l for l in completed.stdout.splitlines() if l.startswith("REPORT:")),
                None,
            )
            self.assertIsNotNone(line, f"没拿到报告：\n{completed.stdout}")
            report = json.loads(line.removeprefix("REPORT:"))

        self.assertEqual(report["missing_tables"], [], "迁移没有建出模型声明的表")
        self.assertEqual(report["missing_columns"], {}, "迁移建出的列与模型不一致")
        self.assertGreater(report["table_count"], 10)
