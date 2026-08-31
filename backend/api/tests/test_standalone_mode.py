"""零依赖模式的端到端验证：SQLite + 进程内队列，不连 Postgres / Redis。

这是「可插拔」最有说服力的一条测试：同一个 FastAPI 应用、同一批模型、
同一套路由，只把两个适配器换掉就能跑起来。如果哪天有人在模型里写死
JSONB、或在 service 里直连 Redis，这个测试会第一个失败。

注意它必须在子进程里跑：``app.core.config.settings`` 与数据库 engine 都是
模块级单例，导入后再改环境变量已经来不及。用子进程可以拿到干净的
进程状态，也顺便证明了「换后端只靠环境变量」这件事成立。
"""

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = textwrap.dedent(
    """
    import asyncio, json, os, sys
    from pathlib import Path
    from uuid import UUID

    workdir = Path(sys.argv[1])
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{workdir / 'atlas.db'}"
    os.environ["AGENT_TASK_BACKEND"] = "local"
    os.environ["AGENT_TASK_LOCAL_PATH"] = str(workdir / "queue.db")
    os.environ["RAG_VECTOR_BACKEND"] = "auto"
    os.environ["RAG_EMBEDDING_PROVIDER"] = "local_hash"
    os.environ["API_AUTH_ENABLED"] = "false"
    os.environ["MEMORY_DECAY_ENABLED"] = "false"
    os.environ["LOG_LEVEL"] = "CRITICAL"

    from httpx import ASGITransport, AsyncClient

    import app.infrastructure.database.models  # noqa: F401
    from app.infrastructure.database.base import Base
    from app.infrastructure.database.session import AsyncSessionLocal, engine
    from app.main import create_app

    async def main():
        report = {}
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        report["schema"] = "ok"

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            async with app.router.lifespan_context(app):
                queue = app.state.task_queue
                report["queue_backend"] = queue.backend_name
                report["queue_health"] = await queue.health()

                created = await client.post("/api/sessions", json={"title": "standalone"})
                report["create_session"] = created.status_code
                session_id = created.json()["data"]["id"]

                task = await queue.enqueue_execute_plan(UUID(session_id))
                fetched = await client.get(f"/api/sessions/tasks/{task.id}")
                report["task_status"] = fetched.json()["data"]["status"]

                kb = await client.post(
                    "/api/rag/knowledge-bases",
                    json={"name": "kb", "description": ""},
                )
                kb_id = kb.json()["data"]["id"]
                await client.post(
                    f"/api/rag/knowledge-bases/{kb_id}/documents",
                    json={
                        "title": "note",
                        "content": "AtlasAgent runs on SQLite without Redis.",
                    },
                )
                hit = await client.post(
                    f"/api/rag/knowledge-bases/{kb_id}/query",
                    json={"query": "AtlasAgent SQLite Redis", "top_k": 3, "min_score": 0.0},
                )
                report["rag_chunks"] = len(hit.json()["data"]["chunks"])

                health = await client.get("/api/rag/health")
                report["vector_store"] = health.json()["data"]["vector_store"]

        await engine.dispose()
        print("REPORT:" + json.dumps(report))

    asyncio.run(main())
    """
)


class StandaloneModeTests(unittest.TestCase):
    def test_full_stack_runs_without_postgres_or_redis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "run_standalone.py"
            script.write_text(SCRIPT, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(script), tmp],
                capture_output=True,
                text=True,
                timeout=180,
                cwd=str(Path(__file__).resolve().parent.parent),
            )

        self.assertEqual(
            completed.returncode,
            0,
            f"standalone boot failed:\nSTDOUT{completed.stdout}\nSTDERR{completed.stderr}",
        )
        line = next(
            (l for l in completed.stdout.splitlines() if l.startswith("REPORT:")),
            None,
        )
        self.assertIsNotNone(line, completed.stdout)
        assert line is not None
        report = json.loads(line.removeprefix("REPORT:"))

        # 建表成功即证明列类型是方言中立的。
        self.assertEqual(report["schema"], "ok")
        # 队列换成了进程内实现，且如实上报不支持多进程。
        self.assertEqual(report["queue_backend"], "local")
        self.assertFalse(report["queue_health"]["multi_process"])
        self.assertTrue(report["queue_health"]["durable"])
        # 业务路由照常工作。
        self.assertEqual(report["create_session"], 200)
        self.assertEqual(report["task_status"], "queued")
        # RAG 全链路（切块→embedding→写入→召回）在 SQLite 上完整可用。
        self.assertEqual(report["rag_chunks"], 1)
        # auto 解析到可移植实现，并如实上报是全表精确扫描。
        self.assertEqual(report["vector_store"]["backend"], "sql")
        self.assertEqual(report["vector_store"]["mode"], "exact_scan")


if __name__ == "__main__":
    unittest.main()
