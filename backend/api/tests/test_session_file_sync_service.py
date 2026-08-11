import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.application.session_file_sync_service import SessionFileSyncService


class FakeSessionFiles:
    def __init__(self, files) -> None:
        self.files = files

    async def list_by_session(self, session_id):
        return self.files


class FakeStorage:
    def __init__(self, content_by_path) -> None:
        self.content_by_path = content_by_path
        self.reads = []

    def read_bytes(self, path, max_size):
        self.reads.append((path, max_size))
        return self.content_by_path[path]


class FakeSandboxFiles:
    def __init__(self) -> None:
        self.writes = []

    def write_file(self, **kwargs) -> None:
        self.writes.append(kwargs)


def session_file(name: str, content_type: str, storage_path: str):
    return SimpleNamespace(
        file=SimpleNamespace(
            original_name=name,
            content_type=content_type,
            storage_path=storage_path,
        )
    )


class SessionFileSyncServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_sync_preserves_existing_text_attachment_paths(self) -> None:
        files = [
            session_file("Page.tsx", "text/plain", "text-path"),
            session_file("image.png", "image/png", "image-path"),
        ]
        storage = FakeStorage({"text-path": b"export default Page;"})
        sandbox = FakeSandboxFiles()
        uow = SimpleNamespace(session_files=FakeSessionFiles(files))
        service = SessionFileSyncService(
            uow,
            storage=storage,
            sandbox_files=sandbox,
            max_file_size=4096,
        )

        await service.sync(uuid4())

        self.assertEqual(storage.reads, [("text-path", 4096)])
        self.assertEqual(
            {write["path"] for write in sandbox.writes},
            {"Page.tsx", "attachments/Page.tsx"},
        )
        self.assertTrue(all(write["create_parent"] for write in sandbox.writes))
        self.assertTrue(
            all(write["content"] == "export default Page;" for write in sandbox.writes)
        )


if __name__ == "__main__":
    unittest.main()
