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
