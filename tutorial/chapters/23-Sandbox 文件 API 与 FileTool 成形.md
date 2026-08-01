# 第二十三章. Sandbox 文件 API 与 FileTool 成形

## 23.1 本章目标
​        学完本章后，你将能够：
​        这一章要把第 22 章搭好的 Sandbox 骨架变成真正能工作的执行环境。文件能力是 Agent 工具链里的第一块地基，因为后续无论是写代码、保存搜索结果、下载产物，还是把浏览器截图交给模型分析，最终都会落到文件系统里。
​        学完本章后，你应该能解释为什么文件工具必须运行在沙箱工作目录内，也能在 Sandbox 服务中实现列表、读取、写入、替换、删除、上传和下载接口。更重要的是，你要理解路径归一化为什么必须放在服务端完成，`../` 这类路径穿越为什么不能交给模型或前端自觉避免。最后，我们会在主 API 中封装 `SandboxFileClient`，把沙箱文件能力注册成 Agent 可调用的 FileTool，并通过 `/sandbox-api/files` 和 `/api/agent-core/tools` 验证完整链路。

## 23.2 最终效果
​        本章结束后，Sandbox 服务会新增一组文件接口：

```Plain
GET    /api/files
GET    /api/files/read
POST   /api/files/write
POST   /api/files/replace
DELETE /api/files
POST   /api/files/upload
GET    /api/files/download
```

​        通过 Nginx 访问时，路径会变成：

```Plain
GET    /sandbox-api/files
GET    /sandbox-api/files/read
POST   /sandbox-api/files/write
POST   /sandbox-api/files/replace
DELETE /sandbox-api/files
POST   /sandbox-api/files/upload
GET    /sandbox-api/files/download
```

​        主 API 会新增 Sandbox 文件客户端，并把这些能力注册成工具：

```Plain
file_list
file_read
file_write
file_replace
file_delete
```

​        本章完成后，请求链路会变成：

```Plain
Agent / 主 API
  |
  |  SandboxFileClient
  v
Sandbox 文件 API
  |
  |  安全路径校验
  v
/workspace
```

## 23.3 本章要解决的问题
​        第 22 章已经把 Sandbox 服务独立出来，并通过 `/sandbox-api/status` 确认沙箱服务可以访问。
​        但此时沙箱还不能真正做事。Agent 要执行任务，最基础的能力之一就是操作文件。例如：

```Plain
读取需求文档
生成代码文件
替换配置内容
保存执行结果
下载产物文件
```

​        这些文件操作不能直接发生在主 API 容器里。主 API 负责业务和调度，沙箱负责执行和隔离。
​        所以本章先给 Sandbox 加文件 API，再让主 API 通过 FileTool 调用它。

## 23.4 本章技术方案
​        本章采用“Sandbox 提供文件 API，主 API 只通过客户端调用”的方案。
​        可选方案有三种：
​        一种做法是让主 API 直接读写宿主机文件，这样最快，但也最危险，因为业务服务和执行环境没有边界。另一种做法是让主 API 挂载并直接读写沙箱数据卷，这比直接碰宿主机好一些，却仍然把文件路径、目录结构和执行环境细节泄露给了主 API。第三种做法是让 Sandbox 服务提供文件 API，主 API 只通过 HTTP 客户端调用它。
​        本项目选择第三种。这样主 API 不需要知道沙箱容器里的真实路径，也不需要直接操作 `/workspace` 数据卷。所有文件读写都集中在 Sandbox 服务里，路径安全校验、大小限制、上传保存和下载响应都可以在同一层完成。后续如果引入多沙箱、多任务隔离或远程沙箱，主 API 也只需要把请求发给不同的 Sandbox 地址，而不用重写工具协议。
​        本章会先在 Sandbox 中定义文件请求和响应模型，再实现 `SandboxFileService` 和 `/api/files` 路由，同时给读取、写入、上传加入大小限制。主 API 侧会增加 `SandboxFileClient`，并把文件能力注册成 `file_list`、`file_read`、`file_write`、`file_replace` 和 `file_delete`。Shell 命令执行、多沙箱实例管理、文件权限系统、二进制文件预览，以及 Planner/ReAct 对 FileTool 的真实自动调用策略，都留到后续章节逐步补上。

## 23.5 新增和修改的文件

```Plain
.env.example
README.md
api/README.md
docker-compose.yml
sandbox/README.md
docs/course/chapters/23-file-tool.md
sandbox/pyproject.toml
sandbox/uv.lock
sandbox/app/core/config.py
sandbox/app/schemas/files.py
sandbox/app/services/file_service.py
sandbox/app/api/routes/files.py
sandbox/app/api/router.py
api/app/core/config.py
api/app/infrastructure/sandbox/__init__.py
api/app/infrastructure/sandbox/file_client.py
api/app/infrastructure/agent_tools/sandbox_file.py
api/app/infrastructure/agent_tools/builtin.py
```

## 23.6 实施步骤
### 23.6.1 为 Sandbox 加入文件上传依赖
​        打开 `sandbox/pyproject.toml`，在 `dependencies` 中加入：

```TOML
"python-multipart>=0.0.30",
```

​        完整依赖部分如下：

```TOML
dependencies = [
  "fastapi>=0.115,<1.0",
  "pydantic-settings>=2.7,<3.0",
  "python-multipart>=0.0.30",
  "uvicorn[standard]>=0.34,<1.0",
]
```

​        然后在 `sandbox` 目录执行：

```Bash
uv lock
```

#### 23.6.1.1 这一步的作用
​        FastAPI 接收普通 JSON 请求时不需要额外依赖。
​        但上传文件使用的是 `multipart/form-data` 格式。FastAPI 解析这种格式时需要 `python-multipart`。
​        本章的 `/api/files/upload` 会使用：

```Python
upload: UploadFile = File(...)
```

​        如果没有安装 `python-multipart`，应用启动或请求上传接口时会报错。

### 23.6.2 补充 Sandbox 文件配置
​        打开 `sandbox/app/core/config.py`，把文件限制配置加到 `workspace_dir` 后面：

```Python
    # ----- 沙箱工作目录：后续文件、Shell、浏览器下载都限制在这里 -----
    workspace_dir: str = "workspace"
    max_file_read_bytes: int = 64 * 1024
    max_file_write_bytes: int = 512 * 1024
    max_upload_size: int = 10 * 1024 * 1024
```

#### 23.6.2.1 字段含义
​        `workspace_dir` 是文件 API 的根边界。本地运行时，它默认指向 `sandbox/workspace`，方便不用 Docker 也能调试；Docker Compose 运行时，它会被环境变量覆盖成容器里的 `/workspace`，也就是第 22 章挂载出来的沙箱工作目录。
​        另外三个配置都是为了限制工具调用的资源消耗。`max_file_read_bytes` 控制一次读取最多返回多少字节，避免大文件直接进入 Agent 上下文；`max_file_write_bytes` 控制文本写入大小，防止错误工具调用写出异常大文件；`max_upload_size` 控制上传文件大小，避免沙箱数据卷被意外填满。这里的限制不是为了让功能变弱，而是为了让后续自动化执行有明确边界。

#### 23.6.2.2 代码讲解
​        文件工具一定要有限制。
​        没有读取限制时，一个 Agent 可能把大文件一次性读进上下文，导致响应变慢，甚至后续 LLM 调用超出上下文预算。
​        没有写入和上传限制时，错误的工具调用可能把沙箱数据卷写满。
​        本章先用简单的字节数限制。后续如果要支持更复杂的文件策略，可以继续扩展成按任务、按用户、按沙箱实例的配额。

### 23.6.3 定义文件 API 的请求和响应模型
​        创建 `sandbox/app/schemas/files.py`：

```Python
from pydantic import BaseModel, Field


class FileEntryResponse(BaseModel):
    name: str  # 展示文件名，前端列表直接使用。
    path: str  # 相对 workspace 的路径，后续读取、下载、删除都用它。
    type: str  # file 或 directory，前端据此决定是否可以继续进入目录。
    size: int  # 文件字节数，目录固定返回 0。
    modified_at: float  # 文件最后修改时间戳，方便后续排序或展示。


class FileListResponse(BaseModel):
    current_path: str  # 当前正在浏览的目录路径。
    items: list[FileEntryResponse]  # 当前目录下的文件和子目录。


class FileReadResponse(BaseModel):
    path: str  # 被读取的文件路径。
    content: str  # 读取到的文本内容。
    size: int  # 文件真实字节数，不受截断影响。
    truncated: bool  # 是否因为超过读取上限被截断。


class FileWriteRequest(BaseModel):
    path: str = Field(min_length=1)
    content: str
    create_parent: bool = True  # 父目录不存在时是否自动创建。


class FileWriteResponse(BaseModel):
    path: str  # 写入成功的文件路径。
    size: int  # 写入后的文件字节数。


class FileReplaceRequest(BaseModel):
    path: str = Field(min_length=1)
    old_text: str = Field(min_length=1)
    new_text: str


class FileReplaceResponse(BaseModel):
    path: str  # 完成替换的文件路径。
    replacements: int  # 实际替换次数，0 表示没有命中 old_text。
    content: str  # 替换后的完整文本，便于调用方立即查看结果。


class FileDeleteResponse(BaseModel):
    path: str  # 被删除的文件或目录路径。
    deleted: bool  # 删除成功时固定为 true。


class FileUploadResponse(BaseModel):
    path: str  # 上传后保存在 workspace 内的路径。
    original_name: str  # 用户上传时的原始文件名。
    size: int  # 上传文件大小。
```

#### 23.6.3.1 这段代码在流程中的位置
​        这些模型位于 Sandbox 服务的接口边界。
​        浏览器、主 API 或 FileTool 调用 Sandbox 文件接口时，请求和响应都会经过这些模型。

#### 23.6.3.2 输入和输出
​        写入文件时，输入是：

```JSON
{
  "path": "notes/hello.txt",
  "content": "hello sandbox",
  "create_parent": true
}
```

​        读取文件时，输出是：

```JSON
{
  "path": "notes/hello.txt",
  "content": "hello sandbox",
  "size": 13,
  "truncated": false
}
```

#### 23.6.3.3 为什么这样设计
​        文件列表、文件内容、写入结果、替换结果、删除结果分别使用不同响应模型，是为了让调用方知道每个接口到底返回什么。
​        `path` 使用相对路径，而不是绝对路径。调用方只知道 `notes/hello.txt`，不知道真实路径是 `sandbox/workspace/notes/hello.txt` 还是容器里的 `/workspace/notes/hello.txt`。这样可以减少沙箱实现细节暴露。
​        `truncated` 很重要。它告诉调用方内容是否被截断。后续 Agent 看到 `truncated=true` 时，可以选择分段读取，而不是误以为已经拿到完整文件。

#### 23.6.3.4 常见误区
​        不要把容器真实路径返回给前端或主 API。
​        如果返回 `/workspace/notes/hello.txt`，后续多沙箱实例、不同工作目录、远程沙箱都会变得更难迁移。

### 23.6.4 实现 Sandbox 文件服务
​        创建 `sandbox/app/services/file_service.py`：

```Python
from pathlib import Path
from shutil import rmtree

from fastapi import UploadFile

from app.core.config import Settings
from app.core.exceptions import SandboxException
from app.schemas.files import (
    FileDeleteResponse,
    FileEntryResponse,
    FileListResponse,
    FileReadResponse,
    FileReplaceResponse,
    FileUploadResponse,
    FileWriteResponse,
)


class SandboxFileService:
    """把所有文件操作限制在 workspace 目录内。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.workspace = Path(settings.workspace_dir).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    # ===================== 第1步：浏览目录 =====================
    def list_files(self, path: str = ".") -> FileListResponse:
        target = self._resolve_path(path)
        if not target.exists():
            raise SandboxException(message="path not found", code=404, status_code=404)
        if not target.is_dir():
            raise SandboxException(message="path is not a directory")

        items = [self._to_entry(child) for child in sorted(target.iterdir())]
        return FileListResponse(current_path=self._to_relative_path(target), items=items)

    # ===================== 第2步：读取文本文件 =====================
    def read_file(self, path: str) -> FileReadResponse:
        target = self._resolve_existing_file(path)
        raw_content = target.read_bytes()
        truncated = len(raw_content) > self.settings.max_file_read_bytes
        preview = raw_content[: self.settings.max_file_read_bytes]
        content = preview.decode("utf-8", errors="replace")
        return FileReadResponse(
            path=self._to_relative_path(target),
            content=content,
            size=len(raw_content),
            truncated=truncated,
        )

    # ===================== 第3步：写入文本文件 =====================
    def write_file(
        self,
        path: str,
        content: str,
        create_parent: bool,
    ) -> FileWriteResponse:
        encoded = content.encode("utf-8")
        if len(encoded) > self.settings.max_file_write_bytes:
            raise SandboxException(message="file content is too large", code=413, status_code=413)

        target = self._resolve_path(path)
        if target.exists() and target.is_dir():
            raise SandboxException(message="path is a directory")
        if create_parent:
            target.parent.mkdir(parents=True, exist_ok=True)
        elif not target.parent.exists():
            raise SandboxException(message="parent directory not found", code=404, status_code=404)

        target.write_bytes(encoded)
        return FileWriteResponse(path=self._to_relative_path(target), size=len(encoded))

    # ===================== 第4步：替换文本内容 =====================
    def replace_text(
        self,
        path: str,
        old_text: str,
        new_text: str,
    ) -> FileReplaceResponse:
        current = self.read_file(path)
        replacements = current.content.count(old_text)
        next_content = current.content.replace(old_text, new_text)
        self.write_file(path=path, content=next_content, create_parent=False)
        return FileReplaceResponse(
            path=current.path,
            replacements=replacements,
            content=next_content,
        )

    # ===================== 第5步：删除文件或目录 =====================
    def delete_path(self, path: str) -> FileDeleteResponse:
        target = self._resolve_path(path)
        if target == self.workspace:
            raise SandboxException(message="workspace root cannot be deleted")
        if not target.exists():
            raise SandboxException(message="path not found", code=404, status_code=404)
        if target.is_dir():
            rmtree(target)
        else:
            target.unlink()
        return FileDeleteResponse(path=path, deleted=True)

    # ===================== 第6步：保存上传文件 =====================
    async def save_upload(
        self,
        directory: str,
        upload: UploadFile,
    ) -> FileUploadResponse:
        filename = Path(upload.filename or "").name
        if not filename:
            raise SandboxException(message="filename is required")

        target_dir = self._resolve_path(directory)
        target_dir.mkdir(parents=True, exist_ok=True)
        if not target_dir.is_dir():
            raise SandboxException(message="upload target is not a directory")

        content = await upload.read()
        if len(content) > self.settings.max_upload_size:
            raise SandboxException(message="upload file is too large", code=413, status_code=413)

        target = self._resolve_path(str(Path(directory) / filename))
        target.write_bytes(content)
        return FileUploadResponse(
            path=self._to_relative_path(target),
            original_name=filename,
            size=len(content),
        )

    # ===================== 第7步：获取下载路径 =====================
    def get_download_path(self, path: str) -> Path:
        return self._resolve_existing_file(path)

    # ===================== 第8步：路径安全校验 =====================
    def _resolve_path(self, path: str) -> Path:
        clean_path = path.strip() or "."
        if Path(clean_path).is_absolute():
            raise SandboxException(message="absolute path is not allowed")

        target = (self.workspace / clean_path).resolve()
        if target != self.workspace and self.workspace not in target.parents:
            raise SandboxException(message="path escapes workspace")
        return target

    def _resolve_existing_file(self, path: str) -> Path:
        target = self._resolve_path(path)
        if not target.exists():
            raise SandboxException(message="file not found", code=404, status_code=404)
        if not target.is_file():
            raise SandboxException(message="path is not a file")
        return target

    def _to_entry(self, path: Path) -> FileEntryResponse:
        stat = path.stat()
        return FileEntryResponse(
            name=path.name,
            path=self._to_relative_path(path),
            type="directory" if path.is_dir() else "file",
            size=0 if path.is_dir() else stat.st_size,
            modified_at=stat.st_mtime,
        )

    def _to_relative_path(self, path: Path) -> str:
        relative = path.resolve().relative_to(self.workspace)
        return "." if str(relative) == "." else relative.as_posix()
```

#### 23.6.4.1 这段代码在流程中的位置
​        `SandboxFileService` 是 Sandbox 文件 API 的核心业务层。
​        路由只负责接收 HTTP 请求，真正的路径检查、读写文件、大小限制和返回模型都放在这里。

#### 23.6.4.2 输入和输出
​        输入来自 HTTP 接口：

```Plain
path=notes/hello.txt
content=hello sandbox
```

​        输出是 Pydantic 响应模型，例如：

```Plain
FileWriteResponse(path="notes/hello.txt", size=13)
```

#### 23.6.4.3 调用链路
​        写文件的调用链路是：

```Plain
POST /api/files/write
  |
  v
files.py 路由函数
  |
  v
SandboxFileService.write_file()
  |
  v
_resolve_path()
  |
  v
/workspace/notes/hello.txt
```

#### 23.6.4.4 关键代码逐段解释
​        `__init__()` 中先把 `workspace_dir` 转成真实路径：

```Python
self.workspace = Path(settings.workspace_dir).resolve()
```

​        这里必须使用 `resolve()`。因为后续要判断用户路径是否逃出 workspace，比较的必须是真实路径。
​        `_resolve_path()` 是本章最重要的安全函数：

```Python
target = (self.workspace / clean_path).resolve()
if target != self.workspace and self.workspace not in target.parents:
    raise SandboxException(message="path escapes workspace")
```

​        如果用户传入 `../secret.txt`，拼接后看起来还在 workspace 下面，但 `resolve()` 会把 `..` 折叠掉。折叠后的真实路径如果不在 workspace 内，就直接拒绝。
​        读取文件时使用：

```Python
preview = raw_content[: self.settings.max_file_read_bytes]
content = preview.decode("utf-8", errors="replace")
```

​        这样即使文件很大，也只返回允许的前半部分。`errors="replace"` 可以避免非 UTF-8 字节导致接口直接崩掉。
​        写入文件时先把内容编码成字节，再比较大小：

```Python
encoded = content.encode("utf-8")
```

​        不要用 `len(content)` 判断大小。中文字符在 UTF-8 中可能占多个字节，文件大小应该按字节计算。

#### 23.6.4.5 为什么这样设计
​        文件 API 的核心不是“能读写文件”，而是“只能读写允许的文件”。
​        Agent 后续会自动调用工具。工具参数可能来自模型输出，模型输出不能直接信任。所以文件路径必须在服务端做安全校验。
​        本章把安全校验放在 `SandboxFileService`，而不是放在每个路由函数里。这样未来 ShellTool、BrowserTool 如果也需要处理文件路径，可以复用同样的设计思路。

#### 23.6.4.6 小白最容易困惑的点
​        `Path(filename).name` 不是为了好看，而是为了去掉上传文件名里的路径。
​        如果浏览器或客户端上传的文件名是 `../../a.txt`，`Path(...).name` 会取出 `a.txt`。真正保存前仍然会经过 `_resolve_path()`，形成双重保护。

### 23.6.5 创建 Sandbox 文件路由
​        创建 `sandbox/app/api/routes/files.py`：

```Python
from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
from app.schemas.common import ApiResponse
from app.schemas.files import (
    FileDeleteResponse,
    FileListResponse,
    FileReadResponse,
    FileReplaceRequest,
    FileReplaceResponse,
    FileUploadResponse,
    FileWriteRequest,
    FileWriteResponse,
)
from app.services.file_service import SandboxFileService

router = APIRouter(prefix="/files", tags=["files"])


def build_file_service() -> SandboxFileService:
    # 文件服务只依赖配置，后续如果接入权限或审计，可以从这里统一扩展。
    return SandboxFileService(settings=settings)


@router.get("", response_model=ApiResponse[FileListResponse])
async def list_files(
    path: str = Query(default="."),
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileListResponse]:
    # 列表接口只允许浏览 workspace 里的相对路径。
    return ApiResponse(data=service.list_files(path))


@router.get("/read", response_model=ApiResponse[FileReadResponse])
async def read_file(
    path: str = Query(min_length=1),
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileReadResponse]:
    return ApiResponse(data=service.read_file(path))


@router.post("/write", response_model=ApiResponse[FileWriteResponse])
async def write_file(
    payload: FileWriteRequest,
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileWriteResponse]:
    return ApiResponse(
        data=service.write_file(
            path=payload.path,
            content=payload.content,
            create_parent=payload.create_parent,
        )
    )


@router.post("/replace", response_model=ApiResponse[FileReplaceResponse])
async def replace_text(
    payload: FileReplaceRequest,
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileReplaceResponse]:
    return ApiResponse(
        data=service.replace_text(
            path=payload.path,
            old_text=payload.old_text,
            new_text=payload.new_text,
        )
    )


@router.delete("", response_model=ApiResponse[FileDeleteResponse])
async def delete_path(
    path: str = Query(min_length=1),
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileDeleteResponse]:
    return ApiResponse(data=service.delete_path(path))


@router.post("/upload", response_model=ApiResponse[FileUploadResponse])
async def upload_file(
    path: str = Query(default="."),
    upload: UploadFile = File(...),
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileUploadResponse]:
    return ApiResponse(data=await service.save_upload(path, upload))


@router.get("/download")
async def download_file(
    path: str = Query(min_length=1),
    service: SandboxFileService = Depends(build_file_service),
) -> FileResponse:
    target = service.get_download_path(path)
    return FileResponse(path=target, filename=target.name)
```

#### 23.6.5.1 这段代码在流程中的位置
​        这是 Sandbox 文件模块的 HTTP 入口。
​        它把请求参数转换成 `SandboxFileService` 的方法调用，再把结果包成统一响应。

#### 23.6.5.2 接口输入和返回
​        写入文件：

```Bash
curl -X POST http://localhost:8100/api/files/write \
  -H "Content-Type: application/json" \
  -d '{"path":"notes/hello.txt","content":"hello sandbox"}'
```

​        读取文件：

```Bash
curl "http://localhost:8100/api/files/read?path=notes/hello.txt"
```

​        上传文件：

```Bash
curl -F "upload=@README.md" "http://localhost:8100/api/files/upload?path=uploads"
```

#### 23.6.5.3 为什么这样设计
​        下载接口没有使用 `ApiResponse`，而是直接返回 `FileResponse`。
​        原因是下载文件本身就是二进制响应。如果把文件内容塞进 JSON，浏览器就不能自然地把它当作附件下载。
​        其余接口都返回 `ApiResponse`，保持和主 API 一致的错误处理风格。

#### 23.6.5.4 常见误区
​        `GET /files` 和 `DELETE /files` 使用同一个路径，但 HTTP 方法不同，所以它们不会冲突。
​        读取接口用 `/files/read`，下载接口用 `/files/download`。读取返回文本内容，下载返回文件流。两者服务的场景不同。

### 23.6.6 注册 Sandbox 文件路由
​        打开 `sandbox/app/api/router.py`，改成：

```Python
from fastapi import APIRouter

from app.api.routes import files, status, supervisor

api_router = APIRouter()
api_router.include_router(files.router)
api_router.include_router(status.router)
api_router.include_router(supervisor.router)
```

#### 23.6.6.1 代码讲解
​        第 22 章只注册了 `status` 和 `supervisor`。
​        本章新增 `files.router` 后，Sandbox 应用才会真正暴露：

```Plain
/api/files
/api/files/read
/api/files/write
```

​        如果忘记注册路由，请求会返回 404。

### 23.6.7 更新 Docker Compose 环境变量
​        打开 `.env.example`，在 Sandbox 配置区域加入：

```Plain
SANDBOX_MAX_FILE_READ_BYTES=65536
SANDBOX_MAX_FILE_WRITE_BYTES=524288
SANDBOX_MAX_UPLOAD_SIZE=10485760
```

​        打开 `docker-compose.yml`，在 `sandbox.environment` 中加入：

```YAML
      MAX_FILE_READ_BYTES: ${SANDBOX_MAX_FILE_READ_BYTES:-65536}
      MAX_FILE_WRITE_BYTES: ${SANDBOX_MAX_FILE_WRITE_BYTES:-524288}
      MAX_UPLOAD_SIZE: ${SANDBOX_MAX_UPLOAD_SIZE:-10485760}
```

#### 23.6.7.1 代码讲解
​        `.env.example` 面向使用者。
​        `docker-compose.yml` 面向容器运行时。
​        这里变量名看起来有一层转换：

```Plain
SANDBOX_MAX_FILE_READ_BYTES -> MAX_FILE_READ_BYTES
```

​        左边是项目根目录 `.env` 中的名字，带 `SANDBOX_` 前缀，避免和主 API 的文件配置混淆。
​        右边是 Sandbox 容器内读取的名字，对应 `Settings.max_file_read_bytes`。

### 23.6.8 在主 API 中增加 Sandbox 配置
​        打开 `api/app/core/config.py`，在文件配置后加入：

```Python
    sandbox_api_base_url: str = "http://localhost:8100/api"
    sandbox_api_timeout_seconds: float = 10.0
```

​        同时在 `.env.example` 的 API 配置区域加入：

```Plain
SANDBOX_API_BASE_URL=http://sandbox:8100/api
SANDBOX_API_TIMEOUT_SECONDS=10
```

​        在 `docker-compose.yml` 的 `api.environment` 中加入：

```YAML
      SANDBOX_API_BASE_URL: ${SANDBOX_API_BASE_URL:-http://sandbox:8100/api}
      SANDBOX_API_TIMEOUT_SECONDS: ${SANDBOX_API_TIMEOUT_SECONDS:-10}
```

#### 23.6.8.1 字段含义
​        `sandbox_api_base_url` 是主 API 访问 Sandbox API 的基础地址。直接在本机运行时，它可以是 `http://localhost:8100/api`；放进 Docker Compose 后，它必须变成 `http://sandbox:8100/api`，因为容器里的 `localhost` 指向的是当前容器自己，不是另一个服务。
​        `sandbox_api_timeout_seconds` 则控制主 API 等待 Sandbox 响应的最长时间。文件读写通常不应该无限等待，如果 Sandbox 不可用、网络不通或接口卡住，主 API 应该尽快把错误暴露出来，让 Agent 事件流和前端都能看到真实失败原因。

#### 23.6.8.2 代码讲解
​        本地直接运行主 API 时，默认地址是：

```Plain
http://localhost:8100/api
```

​        Docker Compose 中运行主 API 时，地址是：

```Plain
http://sandbox:8100/api
```

​        因为容器里不能用 `localhost` 访问另一个容器。`sandbox` 是 Docker Compose 服务名。

### 23.6.9 实现主 API 的 Sandbox 文件客户端
​        创建 `api/app/infrastructure/sandbox/__init__.py`：

```Python
"""Sandbox API clients used by the main API service."""
```

​        创建 `api/app/infrastructure/sandbox/file_client.py`：

```Python
from typing import Any

import httpx

from app.core.exceptions import AppException


class SandboxFileClient:
    """主 API 访问 Sandbox 文件接口的同步客户端。"""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
    ) -> None:
        # base_url 指向 Sandbox 服务地址，例如 http://sandbox:8100/api。
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    # ===================== 第1步：封装文件列表 =====================
    def list_files(self, path: str = ".") -> dict[str, Any]:
        return self._request("GET", "/files", params={"path": path})

    # ===================== 第2步：封装文件读取 =====================
    def read_file(self, path: str) -> dict[str, Any]:
        return self._request("GET", "/files/read", params={"path": path})

    # ===================== 第3步：封装文件写入 =====================
    def write_file(
        self,
        path: str,
        content: str,
        create_parent: bool = True,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/files/write",
            json={
                "path": path,
                "content": content,
                "create_parent": create_parent,
            },
        )

    # ===================== 第4步：封装文本替换 =====================
    def replace_text(
        self,
        path: str,
        old_text: str,
        new_text: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/files/replace",
            json={
                "path": path,
                "old_text": old_text,
                "new_text": new_text,
            },
        )

    # ===================== 第5步：封装文件删除 =====================
    def delete_path(self, path: str) -> dict[str, Any]:
        return self._request("DELETE", "/files", params={"path": path})

    # ===================== 第6步：统一处理 Sandbox 响应 =====================
    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.request(method, url, **kwargs)
        except httpx.HTTPError as error:
            raise AppException(
                message=f"sandbox request failed: {error}",
                code=502,
                status_code=502,
            ) from error

        try:
            payload = response.json()
        except ValueError as error:
            raise AppException(
                message="sandbox returned non-json response",
                code=502,
                status_code=502,
            ) from error

        if response.status_code >= 400 or payload.get("code") != 200:
            raise AppException(
                message=str(payload.get("message") or "sandbox request failed"),
                code=int(payload.get("code") or response.status_code),
                status_code=response.status_code,
            )

        data = payload.get("data")
        if not isinstance(data, dict):
            raise AppException(
                message="sandbox returned invalid data",
                code=502,
                status_code=502,
            )
        return data
```

#### 23.6.9.1 这段代码在流程中的位置
​        `SandboxFileClient` 位于主 API 的基础设施层。
​        它不处理业务决策，只负责把主 API 的工具调用转换成 Sandbox HTTP 请求。

#### 23.6.9.2 调用链路
​        读取文件时链路是：

```Plain
FileTool
  |
  v
SandboxFileClient.read_file()
  |
  v
GET http://sandbox:8100/api/files/read?path=...
  |
  v
SandboxFileService.read_file()
```

#### 23.6.9.3 关键代码逐段解释
​        `base_url.rstrip("/")` 是为了避免拼接路径时出现双斜杠：

```Plain
http://sandbox:8100/api//files
```

​        `_request()` 统一处理所有 Sandbox 响应。这样每个文件方法不用重复写异常处理。
​        如果 Sandbox 不可用，`httpx.HTTPError` 会被转换成主 API 的 `AppException`，前端会拿到统一错误响应。
​        如果 Sandbox 返回非 JSON，说明请求可能打到了错误服务，或者 Nginx 返回了 HTML 错误页。这种情况也统一转成 502。

#### 23.6.9.4 为什么这样设计
​        FileTool 不直接依赖 `httpx`。
​        FileTool 依赖的是 `SandboxFileClient`。这样工具代码只关心“读文件、写文件”，不关心 HTTP 方法、路径、超时和响应格式。

### 23.6.10 实现 Sandbox FileTool
​        创建 `api/app/infrastructure/agent_tools/sandbox_file.py`：

```Python
from app.core.config import settings
from app.domain.agent_core.tools import (
    AgentTool,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
)
from app.infrastructure.sandbox.file_client import SandboxFileClient


def build_sandbox_file_client() -> SandboxFileClient:
    """根据主 API 配置创建 Sandbox 文件客户端。"""

    return SandboxFileClient(
        base_url=settings.sandbox_api_base_url,
        timeout_seconds=settings.sandbox_api_timeout_seconds,
    )


def register_sandbox_file_tools(
    registry: ToolRegistry,
    client: SandboxFileClient | None = None,
) -> None:
    """把 Sandbox 文件能力注册成 Agent 可调用工具。"""

    file_client = client or build_sandbox_file_client()

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="file_list",
                description="列出 Sandbox 工作目录中的文件和子目录。",
                parameters=[
                    ToolParameter(
                        name="path",
                        type="string",
                        description="要浏览的相对路径，默认是 workspace 根目录。",
                        required=False,
                    )
                ],
            ),
            handler=lambda path=".": _format_file_list(file_client.list_files(path or ".")),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="file_read",
                description="读取 Sandbox 工作目录中的文本文件。",
                parameters=[
                    ToolParameter(
                        name="path",
                        type="string",
                        description="要读取的文件相对路径。",
                    )
                ],
            ),
            handler=lambda path: _format_file_content(file_client.read_file(path)),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="file_write",
                description="向 Sandbox 工作目录写入文本文件。",
                parameters=[
                    ToolParameter(
                        name="path",
                        type="string",
                        description="要写入的文件相对路径。",
                    ),
                    ToolParameter(
                        name="content",
                        type="string",
                        description="要写入文件的文本内容。",
                    ),
                ],
            ),
            handler=lambda path, content: _format_write_result(
                file_client.write_file(path=path, content=content)
            ),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="file_replace",
                description="替换 Sandbox 文本文件中的指定内容。",
                parameters=[
                    ToolParameter(
                        name="path",
                        type="string",
                        description="要修改的文件相对路径。",
                    ),
                    ToolParameter(
                        name="old_text",
                        type="string",
                        description="需要被替换的原文本。",
                    ),
                    ToolParameter(
                        name="new_text",
                        type="string",
                        description="替换后的新文本。",
                    ),
                ],
            ),
            handler=lambda path, old_text, new_text: _format_replace_result(
                file_client.replace_text(
                    path=path,
                    old_text=old_text,
                    new_text=new_text,
                )
            ),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="file_delete",
                description="删除 Sandbox 工作目录中的文件或目录。",
                parameters=[
                    ToolParameter(
                        name="path",
                        type="string",
                        description="要删除的文件或目录相对路径。",
                    )
                ],
            ),
            handler=lambda path: _format_delete_result(file_client.delete_path(path)),
        )
    )


def _format_file_list(data: dict) -> str:
    items = data.get("items", [])
    if not items:
        return f"{data.get('current_path', '.')} 目录为空。"

    lines = [f"当前目录：{data.get('current_path', '.')}"]
    for item in items:
        marker = "目录" if item.get("type") == "directory" else "文件"
        lines.append(
            f"- [{marker}] {item.get('path')} ({item.get('size', 0)} bytes)"
        )
    return "\n".join(lines)


def _format_file_content(data: dict) -> str:
    suffix = "\n\n内容已截断。" if data.get("truncated") else ""
    return f"文件：{data.get('path')}\n大小：{data.get('size')} bytes\n\n{data.get('content', '')}{suffix}"


def _format_write_result(data: dict) -> str:
    return f"文件已写入：{data.get('path')}，大小 {data.get('size')} bytes。"


def _format_replace_result(data: dict) -> str:
    return (
        f"文件已替换：{data.get('path')}，"
        f"替换次数 {data.get('replacements')}。\n\n{data.get('content', '')}"
    )


def _format_delete_result(data: dict) -> str:
    if data.get("deleted"):
        return f"路径已删除：{data.get('path')}"
    return f"路径未删除：{data.get('path')}"
```

#### 23.6.10.1 这段代码在流程中的位置
​        这是主 API 的工具注册代码。
​        它把 Sandbox 文件 API 包装成 Agent 能理解的工具 schema。

#### 23.6.10.2 输入和输出
​        模型或前端看到的工具是：

```Plain
file_write(path, content)
file_read(path)
file_replace(path, old_text, new_text)
```

​        工具返回给 Agent 的是字符串，例如：

```Plain
文件已写入：notes/hello.txt，大小 13 bytes。
```

#### 23.6.10.3 调用链路
​        调用 `file_write` 时：

```Plain
AgentTool.call()
  |
  v
handler=lambda path, content: ...
  |
  v
SandboxFileClient.write_file()
  |
  v
Sandbox /api/files/write
```

#### 23.6.10.4 为什么这样设计
​        工具返回 `str`，是为了和第 17 章的工具协议保持一致。
​        当前 `AgentTool` 的 handler 类型是：

```Python
Callable[..., str]
```

​        所以本章把 Sandbox 返回的结构化数据格式化成文本。后续如果工具协议升级为结构化输出，可以把 `ToolCallResult.output` 扩展为 `dict` 或新增 `metadata` 字段。

#### 23.6.10.5 小白最容易困惑的点
​        这里没有用 `@agent_tool` 装饰器，是因为 FileTool 需要持有 `SandboxFileClient`。
​        装饰器适合简单纯函数工具，比如 `summarize_text()`。
​        FileTool 需要访问外部服务，所以用 `AgentTool(...)` 手动创建更清晰。

### 23.6.11 把 FileTool 注册进工具列表
​        打开 `api/app/infrastructure/agent_tools/builtin.py`，新增 import：

```Python
from app.infrastructure.agent_tools.sandbox_file import register_sandbox_file_tools
```

​        然后在 `build_builtin_tool_registry()` 中加入：

```Python
    register_sandbox_file_tools(registry)
```

​        修改后函数如下：

```Python
def build_builtin_tool_registry() -> ToolRegistry:
    """注册并返回本章可用的内置工具。"""

    registry = ToolRegistry()
    registry.register(summarize_text)
    registry.register(extract_keywords)
    registry.register(draft_plan)
    register_sandbox_file_tools(registry)
    return registry
```

#### 23.6.11.1 代码讲解
​        第 17 章创建工具注册表时，只有三个教学工具：

```Plain
summarize_text
extract_keywords
draft_plan
```

​        本章加入：

```Plain
file_list
file_read
file_write
file_replace
file_delete
```

​        这意味着访问：

```Plain
GET /api/agent-core/tools
```

​        应该能看到这些文件工具。

## 23.7 关键理解
​        本章最重要的是“路径安全”。
​        文件工具不是简单地把用户传入的路径交给 `open()`。
​        正确流程是：

```Plain
用户传入相对路径
  |
  v
拼到 workspace 下面
  |
  v
resolve() 归一化真实路径
  |
  v
确认真实路径仍然在 workspace 内
  |
  v
允许读写
```

​        这样可以拦住：

```Plain
../.env
/etc/passwd
notes/../../secret.txt
```

​        第二个重点是“主 API 不直接操作文件”。
​        主 API 通过 HTTP 调用 Sandbox：

```Plain
主 API -> Sandbox API -> /workspace
```

​        这个边界会让后续 DockerSandbox、多任务隔离、远程沙箱更容易实现。
​        第三个重点是“工具协议和沙箱协议分层”。
​        Sandbox API 返回结构化 JSON，FileTool 返回给 Agent 的是可读文本。两者不是一层：

```Plain
Sandbox API：给程序调用
FileTool 输出：给 Agent/模型理解
```

## 23.8 技术难点与亮点
​        本章的技术难点首先是路径安全。文件工具不是把用户传进来的字符串直接交给 `open()`，而是必须把相对路径拼到 `workspace` 下，再用 `resolve()` 折叠真实路径，最后确认这个真实路径仍然位于工作目录内部。只要这一步漏掉，`../.env`、`/etc/passwd` 或 `notes/../../secret.txt` 都可能变成越界访问。
​        第二个难点是文件内容并不总是理想文本。读取大文件时需要截断，读取非 UTF-8 字节时不能让接口崩溃，上传文件时还要引入 `python-multipart` 才能解析 `multipart/form-data`。主 API 侧还要注意 Docker Compose 网络里的服务名：容器访问 Sandbox 应该使用 `http://sandbox:8100/api`，而不是本机调试时常见的 `localhost:8100`。
​        本章的亮点，是文件能力从一开始就运行在独立 Sandbox 服务中，而不是和主 API 耦合在一起。Sandbox API 面向程序，返回结构化 JSON；FileTool 面向 Agent，把结构化结果整理成可读文本；工具注册表则让这些能力可以被 `/api/agent-core/tools` 发现。`truncated` 字段也为后续上下文工程和分段读取留下了清楚的信号。

## 23.9 面试考点
​        面试里问到这一章，最容易展开的是“为什么文件工具必须运行在沙箱中”。回答时不要只说“安全”，而要讲清楚主 API 的职责是会话、任务和调度，文件读写属于执行环境，应该被限制在 `workspace` 里，并由 Sandbox 统一做路径校验和大小限制。
​        路径穿越也是一个高频追问点。可以用 `../.env` 举例说明：字符串看起来只是一个相对路径，但经过 `resolve()` 后可能已经跳出了工作目录。正确做法是得到真实路径后，再检查它是否等于 `workspace` 或者位于 `workspace.parents` 关系内。上传接口需要 `python-multipart`，是因为浏览器上传文件使用 `multipart/form-data`，FastAPI 解析这种格式需要额外依赖。
​        主 API 容器不能用 `localhost:8100` 访问 Sandbox，是因为容器里的 `localhost` 指向当前主 API 容器自己。Compose 网络中应该使用服务名 `sandbox`。至于 FileTool 不直接返回原始 JSON，是因为当前工具协议给 Agent 的输出是字符串，程序接口和模型可读输出属于两个层次，不能混在一起。

## 23.10 运行验证
​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

### 23.10.1 检查 Sandbox 依赖锁文件

```Bash
cd sandbox
uv lock --check
```

​        预期看到类似：

```Plain
Resolved ... packages
```

### 23.10.2 检查 Python 编译
​        检查 Sandbox：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents/sandbox
uv run python -m compileall app
```

​        检查主 API：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents/api
uv run python -m compileall app
```

​        预期没有 Python 语法错误。
​        本地直接运行 Sandbox 时，如果没有设置环境变量，文件会写入：

```Plain
sandbox/workspace
```

​        Docker Compose 运行时，`docker-compose.yml` 会把 `SANDBOX_WORKSPACE_DIR` 映射成容器里的：

```Plain
/workspace
```

### 23.10.3 启动服务
​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

​        如果镜像已经构建过，可以执行：

```Bash
docker compose up -d sandbox api nginx
```

​        如果改了依赖或 Dockerfile，需要重新构建：

```Bash
docker compose build sandbox api
docker compose up -d sandbox api nginx
```

​        如果 Nginx 返回旧页面或 404，重启 Nginx：

```Bash
docker compose restart nginx
```

### 23.10.4 验证 Sandbox 文件 API
​        写入文件：

```Bash
curl -X POST http://localhost:8088/sandbox-api/files/write \
  -H "Content-Type: application/json" \
  -d '{"path":"notes/hello.txt","content":"hello sandbox"}'
```

​        预期返回：

```JSON
{"code":200,"message":"success","data":{"path":"notes/hello.txt","size":13}}
```

​        读取文件：

```Bash
curl "http://localhost:8088/sandbox-api/files/read?path=notes/hello.txt"
```

​        预期能看到：

```Plain
hello sandbox
```

​        列出目录：

```Bash
curl "http://localhost:8088/sandbox-api/files?path=notes"
```

​        预期能看到：

```Plain
hello.txt
```

​        替换文本：

```Bash
curl -X POST http://localhost:8088/sandbox-api/files/replace \
  -H "Content-Type: application/json" \
  -d '{"path":"notes/hello.txt","old_text":"sandbox","new_text":"file api"}'
```

​        再次读取：

```Bash
curl "http://localhost:8088/sandbox-api/files/read?path=notes/hello.txt"
```

​        预期能看到：

```Plain
hello file api
```

### 23.10.5 验证路径穿越防护
​        执行：

```Bash
curl "http://localhost:8088/sandbox-api/files/read?path=../README.md"
```

​        预期返回错误，消息类似：

```Plain
path escapes workspace
```

​        这说明 Sandbox 没有允许访问 workspace 外面的文件。

### 23.10.6 验证 FileTool 已注册
​        执行：

```Bash
curl http://localhost:8088/api/agent-core/tools
```

​        预期工具列表里能看到：

```Plain
file_list
file_read
file_write
file_replace
file_delete
```

### 23.10.7 验证 FileTool 调用
​        调用 `file_read`：

```Bash
curl -X POST http://localhost:8088/api/agent-core/demo \
  -H "Content-Type: application/json" \
  -d '{"task":"notes/hello.txt","tool_name":"file_read"}'
```

​        如果文件存在，预期返回的 `tool_result.output` 里能看到文件内容。
​        如果提示 Sandbox 连接失败，先确认：

```Bash
docker compose ps
curl http://localhost:8088/sandbox-api/status
```

## 23.11 常见问题

### 23.11.1 上传接口提示需要 `python-multipart` 怎么办？
​        这个错误说明 FastAPI 已经识别到接口使用了 `UploadFile = File(...)`，但当前环境缺少解析 `multipart/form-data` 的依赖。先确认 `sandbox/pyproject.toml` 中已经加入 `python-multipart`，再进入 `sandbox` 目录执行 `uv lock` 更新锁文件。
​        如果是在 Docker Compose 中验证，还需要重新构建 sandbox 镜像。依赖已经写进源码但镜像没有重建时，容器里仍然是旧环境，请求上传接口还是会报同样的错误。

### 23.11.2 `/sandbox-api/files` 返回 Next.js 404 怎么办？
​        这通常说明请求没有被 Nginx 转发到 Sandbox，而是落到了 UI 服务。最常见原因是 Nginx 没有加载包含 `/sandbox-api` 的新配置，或者容器还在使用旧的 `default.conf`。
​        处理时先执行 `docker compose restart nginx`，再请求 `curl http://localhost:8088/sandbox-api/files`。如果返回的仍然是 Next.js 404，就检查 `nginx/default.conf` 中 `/sandbox-api/` 的 `location` 是否存在，以及 Compose 是否正确挂载了这个配置文件。

### 23.11.3 FileTool 调用时报 `sandbox request failed` 怎么办？
​        这个错误来自主 API 的 `SandboxFileClient`，表示主 API 没有成功请求到 Sandbox。先确认 `SANDBOX_API_BASE_URL` 在 Docker Compose 中是 `http://sandbox:8100/api`，而不是 `http://localhost:8100/api`。
​        然后检查 `atlas-sandbox` 容器是否正在运行，并访问 `http://localhost:8088/sandbox-api/status` 验证网关路径是否可用。如果状态接口正常，但 FileTool 仍失败，再看主 API 容器日志，通常可以看到连接超时、DNS 解析失败或 Sandbox 返回错误响应的具体原因。

### 23.11.4 为什么读取大文件会截断？
​        文件内容后续很可能进入 Agent 上下文。大文件如果一次性读入，不仅会拖慢接口，还可能让后续 LLM 调用超出上下文预算。`MAX_FILE_READ_BYTES` 的作用就是先给文件读取加一个硬边界，让工具返回“可处理的预览”，而不是盲目返回完整内容。
​        `truncated=true` 是一个非常重要的信号。它告诉 Agent 当前内容不是完整文件，如果任务需要继续分析，可以再设计分段读取或其他更细的文件处理策略。

### 23.11.5 为什么不允许绝对路径？
​        沙箱文件 API 只接受相对 `workspace` 的路径。绝对路径会暴露容器内部目录结构，也更容易让调用方绕过工作目录边界。对主 API 和 Agent 来说，只需要知道 `notes/hello.txt` 这样的相对路径，不应该知道它在容器里到底是 `/workspace/notes/hello.txt` 还是本地调试时的 `sandbox/workspace/notes/hello.txt`。
​        这种隐藏真实路径的做法，也为后续多沙箱和远程沙箱留下了空间。只要 API 协议保持相对路径，底层工作目录怎么部署都可以由 Sandbox 自己决定。

## 23.12 本章小结
​        本章完成了 Sandbox 文件能力的第一版。Sandbox 侧新增了文件请求和响应模型，也新增了负责路径安全、读写限制、上传保存和下载路径处理的 `SandboxFileService`。在 HTTP 层，`/api/files` 已经覆盖列表、读取、写入、替换、删除、上传和下载这些基础动作。
​        主 API 侧新增了 `SandboxFileClient`，让业务服务不直接碰沙箱文件系统，而是通过 HTTP 调用 Sandbox。FileTool 又把这些客户端方法包装成 Agent 能理解的工具，并注册进统一工具表。到这一章结束时，Agent 已经具备“通过沙箱读写文件”的基础能力，而且这条能力从一开始就带有路径边界、大小限制和清晰的服务分层。

## 23.13 下一章预告
​        第 24 章会实现 Sandbox Shell API 与 ShellTool，让 Agent 可以在沙箱里执行命令、查看输出、等待进程和终止进程。

## 23.14 代码
​        暂时无法在飞书文档外展示此内容
