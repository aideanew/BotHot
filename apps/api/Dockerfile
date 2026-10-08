# BotHot backend 容器（W6 A.4：多阶段 + 非 root uid1000 + HEALTHCHECK）
# 基础镜像可注入：默认走 docker.io；网络受限时由 compose build.args 换成镜像源。
#   实证（2026-09-23）：本机 Docker Desktop 无 HTTPS 代理，docker.io 不可达，
#   `BASE_IMAGE=docker.m.daocloud.io/library/python:3.12-slim` 可用。
ARG BASE_IMAGE=python:3.12-slim

# ---------------- builder：装依赖与打包 app 到隔离层 ----------------
FROM ${BASE_IMAGE} AS builder

# M0 实证要点 #1：Docker Desktop 会把宿主死代理（127.0.0.1:10809）注入构建环境，
# compose build.args 显式传空覆盖；依赖安装走 PIP_INDEX_URL 国内镜像直连
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG http_proxy=""
ARG https_proxy=""
ARG NO_PROXY="*"
ARG no_proxy="*"

ENV PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    HTTP_PROXY= \
    HTTPS_PROXY= \
    http_proxy= \
    https_proxy= \
    NO_PROXY='*' \
    no_proxy='*'

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
# 先装依赖 + 把 app 打成包（setuptools include=app*）进 site-packages
RUN pip install --no-cache-dir .

# ---------------- runtime：只带运行所需，最小面 ----------------
FROM ${BASE_IMAGE} AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 非 root：固定 uid/gid=1000（compose 侧 read_only 根 + tmpfs 已就绪，禁字节码免写 pyc）
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --no-create-home app

WORKDIR /app

# 从 builder 搬已安装的依赖 + 入口脚本（两阶段同 BASE_IMAGE，site-packages 路径一致）
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
# migrate 服务复用同一镜像跑 `alembic upgrade head`，需迁移脚本与配置在场
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./alembic.ini

USER app

EXPOSE 3300

# 存活探针打 /live（无依赖、进程在跑即 200），与功能探活 /health 分层
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:3300/api/v1/system/live', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3300"]
