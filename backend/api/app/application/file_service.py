import csv
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from uuid import UUID

from pypdf import PdfReader

from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.core.exceptions import AppException
from app.domain.files.entities import FileObject, SessionFile
from app.domain.files.storage import FileStorage, StoredFile
from app.infrastructure.storage.factory import build_file_storage

TEXT_PREVIEW_TYPES = {
    "application/json",
    "application/xml",
    "application/yaml",
    "text/csv",
}

CODE_EXTENSIONS = {
    ".css": "css",
    ".html": "html",
    ".js": "javascript",
    ".jsx": "jsx",
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
}


@dataclass(slots=True)
class FileReference:
    label: str
    excerpt: str
    start_line: int | None = None
    end_line: int | None = None


@dataclass(slots=True)
class FilePreview:
    file: FileObject
    content: str
    file_type: str
    language: str | None
    line_count: int
    parse_status: str
    parse_message: str
    references: list[FileReference]
    summary: str
    truncated: bool


class FileService:
    def __init__(self, uow: UnitOfWork, storage: FileStorage | None = None) -> None:
        self.uow = uow
        self.storage = storage or build_file_storage()

    async def save_upload(
        self,
        original_name: str,
        content_type: str | None,
        content: bytes,
    ) -> FileObject:
        clean_name = self._clean_filename(original_name)
        if not clean_name:
            raise AppException(
                message="file name is required",
                code=400,
                status_code=400,
            )
        if not content:
            raise AppException(
                message="file content is required",
                code=400,
                status_code=400,
            )
        if len(content) > settings.max_upload_size:
            raise AppException(
                message="file is too large",
                code=413,
                status_code=413,
            )

        stored_file = self._write_upload_file(
            clean_name=clean_name,
            content=content,
        )

        try:
            file_object = await self.uow.files.add(
                original_name=clean_name,
                stored_name=stored_file.stored_name,
                content_type=content_type or "application/octet-stream",
                size=len(content),
                storage_path=stored_file.storage_path,
            )
            await self.uow.commit()
        except Exception:
            # 元数据写入失败时清理已落盘文件，避免出现没有数据库记录的孤立文件。
            self.storage.delete(stored_file.storage_path)
            await self.uow.rollback()
            raise
        return file_object

    async def save_session_upload(
        self,
        session_id: UUID,
        original_name: str,
        content_type: str | None,
        content: bytes,
    ) -> SessionFile:
        session = await self.uow.sessions.get(session_id)
        if session is None:
            raise AppException(
                message="session not found",
                code=404,
                status_code=404,
            )

        clean_name = self._clean_filename(original_name)
        stored_file = self._write_upload_file(
            clean_name=clean_name,
            content=content,
        )

        try:
            file_object = await self.uow.files.add(
                original_name=clean_name,
                stored_name=stored_file.stored_name,
                content_type=content_type or "application/octet-stream",
                size=len(content),
                storage_path=stored_file.storage_path,
            )
            session_file = await self.uow.session_files.add(
                session_id=session_id,
                file_id=file_object.id,
            )
            await self.uow.sessions.touch(session_id)
            await self.uow.commit()
        except Exception:
            # 会话归属写入失败时也要清理文件，避免页面永远找不到这份上传内容。
            self.storage.delete(stored_file.storage_path)
            await self.uow.rollback()
            raise
        return session_file

    async def list_session_files(self, session_id: UUID) -> list[SessionFile]:
        session = await self.uow.sessions.get(session_id)
        if session is None:
            raise AppException(
                message="session not found",
                code=404,
                status_code=404,
            )
        return await self.uow.session_files.list_by_session(session_id)

    async def delete_session_file(self, session_id: UUID, session_file_id: UUID) -> None:
        # ===================== 第1步：确认会话和附件归属 =====================
        # 删除接口不允许跨会话操作：session_file 必须确实属于路径里的会话。
        session = await self.uow.sessions.get(session_id)
        if session is None:
            raise AppException(
                message="session not found",
                code=404,
                status_code=404,
            )
        session_file = await self.uow.session_files.get(session_file_id)
        if session_file is None or session_file.session_id != session_id:
            raise AppException(
                message="file not found",
                code=404,
                status_code=404,
            )

        # ===================== 第2步：先删数据库记录，再清理磁盘内容 =====================
        # 归属关系和文件元数据在同一事务里删除；提交成功后再删磁盘文件，
        # 避免磁盘删除失败导致接口反复报错而记录已消失。
        await self.uow.session_files.delete(session_file)
        await self.uow.files.delete(session_file.file)
        await self.uow.commit()
        self.storage.delete(session_file.file.storage_path)

    async def get_file(self, file_id: UUID) -> FileObject:
        file_object = await self.uow.files.get(file_id)
        if file_object is None:
            raise AppException(
                message="file not found",
                code=404,
                status_code=404,
            )
        return file_object

    async def get_download_path(self, file_id: UUID) -> tuple[FileObject, Path]:
        file_object = await self.get_file(file_id)
        if not self.storage.exists(file_object.storage_path):
            raise AppException(
                message="file content not found",
                code=404,
                status_code=404,
            )
        path = self.storage.get_local_path(file_object.storage_path)
        return file_object, path

    async def preview_file(self, file_id: UUID) -> FilePreview:
        # ===================== 第1步：读取文件元数据和本地路径 =====================
        # 预览接口不会直接相信前端传来的文件名，而是先通过数据库记录找到存储路径。
        file_object, path = await self.get_download_path(file_id)

        # ===================== 第2步：识别文件类型 =====================
        # 后续解析策略取决于文件类型：PDF 走 pypdf，CSV/Markdown/代码走文本解析。
        file_type = self._detect_file_type(file_object)

        if file_type == "pdf":
            return self._preview_pdf(file_object, path)

        if not self._is_text_preview_supported(file_object):
            return FilePreview(
                file=file_object,
                content="",
                file_type=file_type,
                language=None,
                line_count=0,
                parse_status="unsupported",
                parse_message="当前文件类型暂不支持文本解析，可以先下载原文件查看。",
                references=[],
                summary="该文件暂不支持在线解析。",
                truncated=False,
            )

        # ===================== 第3步：读取可控大小的文本内容 =====================
        # 预览只读取有限字节，避免把大文件一次性塞进接口响应。
        preview_bytes = self.storage.read_bytes(
            file_object.storage_path,
            max_size=settings.max_file_preview_size + 1,
        )
        truncated = len(preview_bytes) > settings.max_file_preview_size
        preview_bytes = preview_bytes[: settings.max_file_preview_size]
        content = preview_bytes.decode("utf-8", errors="replace")

        # ===================== 第4步：生成摘要、引用片段和最终响应对象 =====================
        return self._build_text_preview(
            file_object=file_object,
            content=content,
            file_type=file_type,
            truncated=truncated,
        )

    def _preview_pdf(self, file_object: FileObject, path: Path) -> FilePreview:
        """抽取 PDF 文本并生成摘要。

        这里只做课程项目需要的轻量解析：读取前几页文本，生成摘要和引用片段。
        复杂版式、扫描件 OCR、表格识别会在真实生产项目中交给专门文档解析服务。
        """

        try:
            reader = PdfReader(str(path))
            page_texts: list[str] = []
            for index, page in enumerate(reader.pages[:8], start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    page_texts.append(f"[第 {index} 页]\n{text}")
        except Exception as exc:
            raise AppException(
                message=f"pdf preview failed: {exc}",
                code=415,
                status_code=415,
                suggestion="请确认 PDF 不是损坏文件；扫描件 PDF 需要 OCR 服务才能解析。",
            ) from exc

        content = "\n\n".join(page_texts)
        truncated = len(reader.pages) > 8 or len(content.encode("utf-8")) > settings.max_file_preview_size
        content = content[: settings.max_file_preview_size]
        if not content.strip():
            return FilePreview(
                file=file_object,
                content="",
                file_type="pdf",
                language=None,
                line_count=0,
                parse_status="empty",
                parse_message="PDF 未抽取到文本，可能是扫描件或图片型 PDF。",
                references=[],
                summary="PDF 未抽取到可用文本。",
                truncated=False,
            )
        return self._build_text_preview(
            file_object=file_object,
            content=content,
            file_type="pdf",
            truncated=truncated,
        )

    def _build_text_preview(
        self,
        *,
        file_object: FileObject,
        content: str,
        file_type: str,
        truncated: bool,
    ) -> FilePreview:
        # 1. 按行拆分内容。引用片段需要行号，前端也会展示文件大致行数。
        lines = content.splitlines()

        # 2. 从文本里提取适合引用的片段，例如 Markdown 标题、代码符号、CSV 表头。
        references = self._build_references(lines, file_type)

        # 3. 汇总成统一的 FilePreview。路由层只负责把它转换成 Pydantic 响应。
        return FilePreview(
            file=file_object,
            content=content,
            file_type=file_type,
            language=self._detect_language(file_object, file_type),
            line_count=len(lines),
            parse_status="parsed",
            parse_message=(
                "文件已解析，预览内容已裁剪。"
                if truncated
                else "文件已解析，可以用于 Agent 上下文和最终回答引用。"
            ),
            references=references,
            summary=self._build_summary(file_object, content, file_type, references),
            truncated=truncated,
        )

    def _build_summary(
        self,
        file_object: FileObject,
        content: str,
        file_type: str,
        references: list[FileReference],
    ) -> str:
        # 这里的摘要不是 LLM 总结，而是低成本结构摘要。
        # 它的目标是让前端和 Agent 先知道“这个文件大概是什么”，再决定是否深入读取。
        if file_type == "csv":
            return self._summarize_csv(file_object, content)
        if file_type == "code":
            return self._summarize_code(file_object, content)
        if file_type == "markdown":
            headings = [
                line.strip("# ").strip()
                for line in content.splitlines()
                if line.lstrip().startswith("#")
            ][:5]
            if headings:
                return f"Markdown 文档包含 {len(headings)} 个主要标题：{'、'.join(headings)}。"
        if references:
            return f"已提取 {len(references)} 个可引用片段，适合在最终回答中引用。"
        return f"{file_object.original_name} 已解析为 {file_type} 文本。"

    @staticmethod
    def _summarize_csv(file_object: FileObject, content: str) -> str:
        reader = csv.reader(StringIO(content))
        rows = list(reader)
        if not rows:
            return f"{file_object.original_name} 是空 CSV 文件。"
        headers = rows[0]
        data_rows = max(len(rows) - 1, 0)
        return (
            f"CSV 文件包含 {len(headers)} 列、约 {data_rows} 行数据。"
            f"主要字段：{'、'.join(headers[:8])}。"
        )

    @staticmethod
    def _summarize_code(file_object: FileObject, content: str) -> str:
        lines = content.splitlines()
        symbols = [
            line.strip()
            for line in lines
            if line.strip().startswith(("def ", "class ", "function ", "export function", "const "))
        ][:6]
        if symbols:
            return f"代码文件包含 {len(lines)} 行，主要符号包括：{'、'.join(symbols)}。"
        return f"代码文件包含 {len(lines)} 行，可用于结构分析和问题定位。"

    @staticmethod
    def _build_references(lines: list[str], file_type: str) -> list[FileReference]:
        references: list[FileReference] = []

        # CSV 的第一行通常是表头，最适合作为用户理解数据结构的引用。
        if file_type == "csv" and lines:
            references.append(
                FileReference(
                    label="表头",
                    excerpt=lines[0][:500],
                    start_line=1,
                    end_line=1,
                )
            )
        for index, line in enumerate(lines, start=1):
            clean = line.strip()
            if not clean:
                continue

            # Markdown 标题天然适合作为文档目录和引用锚点。
            if file_type == "markdown" and clean.startswith("#"):
                references.append(
                    FileReference(
                        label=clean.strip("# ").strip() or f"第 {index} 行标题",
                        excerpt=clean,
                        start_line=index,
                        end_line=index,
                    )
                )
            # 代码文件优先引用函数、类和导出符号，方便用户定位业务逻辑。
            elif file_type == "code" and clean.startswith(
                ("def ", "class ", "function ", "export function", "const ")
            ):
                references.append(
                    FileReference(
                        label=f"代码符号：{clean[:60]}",
                        excerpt=clean,
                        start_line=index,
                        end_line=index,
                    )
                )
            # 普通文本没有结构化标记时，提取较长的自然段作为引用证据。
            elif len(clean) >= 40 and len(references) < 4:
                references.append(
                    FileReference(
                        label=f"片段 {len(references) + 1}",
                        excerpt=clean[:500],
                        start_line=index,
                        end_line=index,
                    )
                )
            if len(references) >= 6:
                break
        return references

    @staticmethod
    def _detect_file_type(file_object: FileObject) -> str:
        suffix = Path(file_object.original_name).suffix.lower()
        content_type = file_object.content_type.split(";")[0].lower()
        if content_type == "application/pdf" or suffix == ".pdf":
            return "pdf"
        if content_type == "text/csv" or suffix == ".csv":
            return "csv"
        if suffix in {".md", ".markdown"}:
            return "markdown"
        if suffix in CODE_EXTENSIONS:
            return "code"
        if content_type.startswith("text/") or suffix in {".txt", ".json", ".yaml", ".yml"}:
            return "text"
        return "binary"

    @staticmethod
    def _detect_language(file_object: FileObject, file_type: str) -> str | None:
        if file_type == "code":
            return CODE_EXTENSIONS.get(Path(file_object.original_name).suffix.lower())
        if file_type in {"markdown", "csv", "pdf", "text"}:
            return file_type
        return None

    @staticmethod
    def _clean_filename(filename: str) -> str:
        # 只保留文件名本身，避免用户传入 ../ 这类路径片段。
        return Path(filename).name.strip()

    def _write_upload_file(self, clean_name: str, content: bytes) -> StoredFile:
        if not clean_name:
            raise AppException(
                message="file name is required",
                code=400,
                status_code=400,
            )
        if not content:
            raise AppException(
                message="file content is required",
                code=400,
                status_code=400,
            )
        if len(content) > settings.max_upload_size:
            raise AppException(
                message="file is too large",
                code=413,
                status_code=413,
            )

        return self.storage.save(clean_name, content)

    @staticmethod
    def _is_text_preview_supported(file_object: FileObject) -> bool:
        content_type = file_object.content_type.split(";")[0].lower()
        if content_type.startswith("text/") or content_type in TEXT_PREVIEW_TYPES:
            return True
        return Path(file_object.original_name).suffix.lower() in {
            ".csv",
            ".json",
            ".markdown",
            ".md",
            ".py",
            ".txt",
            ".ts",
            ".tsx",
            ".yaml",
            ".yml",
        }
