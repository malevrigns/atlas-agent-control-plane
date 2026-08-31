"""架构边界的可执行断言。

「高度解耦」如果只写在文档里，几个月后一定会被一次「先让它跑起来」的
提交悄悄破坏。这些测试把依赖方向变成 CI 里会失败的硬约束：

1. domain 不允许 import infrastructure（依赖只能向内）；
2. application / presentation 不允许 import 具体适配器；
3. 第三方客户端库只能出现在它自己的适配器里；
4. 每个适配器都必须真正实现对应端口的全部方法。
"""

import ast
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "app"


def _imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    return modules


def _python_files(*parts: str) -> list[Path]:
    root = APP_ROOT.joinpath(*parts)
    return sorted(root.rglob("*.py")) if root.exists() else []


class DependencyDirectionTests(unittest.TestCase):
    def test_domain_does_not_import_infrastructure(self) -> None:
        offenders = [
            f"{path.relative_to(APP_ROOT)} -> {module}"
            for path in _python_files("domain")
            for module in _imports_of(path)
            if module.startswith("app.infrastructure")
        ]
        self.assertEqual(offenders, [], "domain 必须只依赖自身与标准库")

    def test_domain_does_not_import_application_or_presentation(self) -> None:
        offenders = [
            f"{path.relative_to(APP_ROOT)} -> {module}"
            for path in _python_files("domain")
            for module in _imports_of(path)
            if module.startswith(("app.application", "app.presentation"))
        ]
        self.assertEqual(offenders, [])

    def test_presentation_does_not_import_concrete_adapters(self) -> None:
        """路由层只能见到端口，不能出现某个具体后端的类名。"""

        forbidden = (
            "app.infrastructure.tasks.redis_queue",
            "app.infrastructure.tasks.local_queue",
            "app.infrastructure.rag.vector_stores.pgvector",
            "app.infrastructure.rag.vector_stores.qdrant",
            "app.infrastructure.rag.vector_stores.sql",
        )
        offenders = [
            f"{path.relative_to(APP_ROOT)} -> {module}"
            for path in _python_files("presentation")
            for module in _imports_of(path)
            if module in forbidden
        ]
        self.assertEqual(offenders, [])

    def test_third_party_clients_are_confined_to_their_adapter(self) -> None:
        """redis 只能出现在 redis 适配器里。

        这一条防的是「在某个 service 里顺手 import redis 加个缓存」——
        那样队列后端就再也换不掉了。
        """

        offenders = [
            str(path.relative_to(APP_ROOT))
            for path in APP_ROOT.rglob("*.py")
            if any(module == "redis" or module.startswith("redis.") for module in _imports_of(path))
            and path.name != "redis_queue.py"
        ]
        self.assertEqual(offenders, [])


class PortImplementationTests(unittest.TestCase):
    """适配器必须覆盖端口的全部方法，缺一个就不算可插拔。"""

    def _assert_implements(self, port: type, adapter: type) -> None:
        required = {
            name
            for name, value in vars(port).items()
            if callable(value) and not name.startswith("_")
        }
        missing = sorted(name for name in required if not hasattr(adapter, name))
        self.assertEqual(missing, [], f"{adapter.__name__} 未实现 {port.__name__} 的: {missing}")
        self.assertTrue(getattr(adapter, "backend_name", ""), "适配器必须声明 backend_name")

    def test_task_queue_adapters_implement_port(self) -> None:
        from app.domain.tasks.queue import AgentTaskQueue
        from app.infrastructure.tasks.local_queue import LocalAgentTaskQueue
        from app.infrastructure.tasks.redis_queue import RedisAgentTaskQueue

        for adapter in (RedisAgentTaskQueue, LocalAgentTaskQueue):
            self._assert_implements(AgentTaskQueue, adapter)

    def test_vector_store_adapters_implement_port(self) -> None:
        from app.domain.rag.vector_store import VectorStore
        from app.infrastructure.rag.vector_stores.pgvector import PgVectorStore
        from app.infrastructure.rag.vector_stores.qdrant import QdrantVectorStore
        from app.infrastructure.rag.vector_stores.sql import SqlVectorStore

        for adapter in (PgVectorStore, QdrantVectorStore, SqlVectorStore):
            self._assert_implements(VectorStore, adapter)

    def test_every_registered_backend_is_distinct(self) -> None:
        """注册表里不能有两个后端共用一个名字（后注册的会静默覆盖前者）。"""

        from app.infrastructure.rag.vector_stores.factory import available_vector_backends
        from app.infrastructure.tasks.factory import available_queue_backends

        for names in (available_queue_backends(), available_vector_backends()):
            self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
