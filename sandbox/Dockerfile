FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_DEFAULT_TIMEOUT=60
ENV APT_OPTS="-o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 -o Acquire::ForceIPv4=true"
ARG APT_MIRROR=http://mirrors.aliyun.com/debian
ARG APT_SECURITY_MIRROR=http://mirrors.aliyun.com/debian-security
ARG PYTHON_PACKAGE_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
ENV UV_DEFAULT_INDEX=${PYTHON_PACKAGE_INDEX}
ENV PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

# 不再从 GHCR 多阶段拷贝 uv，避免国内网络下 ghcr.io 元数据请求超时。
# 这里从 Python 包源安装同版本 uv；如果网络慢，可以通过 --build-arg PYTHON_PACKAGE_INDEX 切换镜像源。
RUN python -m pip install --no-cache-dir --index-url "${PYTHON_PACKAGE_INDEX}" uv==0.11.15

RUN sed -i "s|http://deb.debian.org/debian-security|${APT_SECURITY_MIRROR}|g; s|http://deb.debian.org/debian|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get ${APT_OPTS} update \
    && apt-get ${APT_OPTS} install -y --no-install-recommends \
        bash \
        fluxbox \
        websockify \
        x11vnc \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
# uv.lock 中会记录 PyPI 文件直链；在部分网络环境下这些直链容易超时。
# 这里先从锁文件导出纯版本清单，再通过指定 Python 包源安装，确保依赖下载真正走镜像源。
RUN uv venv .venv \
    && uv export --format requirements.txt --no-dev --no-hashes --no-emit-project --frozen -o requirements.txt \
    && uv pip install --python .venv/bin/python --default-index "${PYTHON_PACKAGE_INDEX}" -r requirements.txt \
    && rm requirements.txt

# Playwright 需要浏览器二进制和系统依赖。
# 第 28 章接入 VNC 后，Chromium 可以运行在 Xvfb 虚拟显示器中。
RUN playwright install --with-deps chromium

COPY app ./app
COPY scripts ./scripts
RUN chmod +x ./scripts/start.sh

EXPOSE 8100
EXPOSE 5900
EXPOSE 6080

CMD ["./scripts/start.sh"]
