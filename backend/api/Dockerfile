FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_DEFAULT_TIMEOUT=60
ARG PYTHON_PACKAGE_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
ENV UV_DEFAULT_INDEX=${PYTHON_PACKAGE_INDEX}
ENV PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

# 不再从 GHCR 多阶段拷贝 uv，避免 ghcr.io 元数据请求超时导致镜像构建失败。
# 这里从 Python 包源安装同版本 uv；必要时可以通过 --build-arg PYTHON_PACKAGE_INDEX 切换镜像源。
RUN python -m pip install --no-cache-dir --index-url "${PYTHON_PACKAGE_INDEX}" uv==0.11.15

COPY pyproject.toml uv.lock README.md ./
# uv.lock 中会记录 PyPI 文件直链；在部分网络环境下这些直链容易超时。
# 这里先从锁文件导出纯版本清单，再通过指定 Python 包源安装，确保依赖下载真正走镜像源。
RUN uv venv .venv \
    && uv export --format requirements.txt --no-dev --no-hashes --no-emit-project --frozen -o requirements.txt \
    && uv pip install --python .venv/bin/python --default-index "${PYTHON_PACKAGE_INDEX}" -r requirements.txt \
    && rm requirements.txt

COPY app ./app
COPY config ./config
COPY scripts ./scripts
COPY alembic.ini ./
COPY migrations ./migrations
RUN chmod +x ./scripts/start.sh

EXPOSE 8000

CMD ["./scripts/start.sh"]
