# 基础镜像可注入：默认走 docker.io；网络受限时由 compose build.args 换成镜像源。
# 实证（2026-09-23）：本机 Docker Desktop 无 HTTPS 代理，docker.io 不可达，
#   `BASE_IMAGE=docker.m.daocloud.io/library/python:3.12-slim` 可用。
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

# M0 实证要点 #1：Docker Desktop 会把宿主死代理（127.0.0.1:10809）注入构建/运行环境，
# compose build.args 显式传空覆盖；依赖安装走 PIP_INDEX_URL 国内镜像直连
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG http_proxy=""
ARG https_proxy=""
ARG NO_PROXY="*"
ARG no_proxy="*"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    HTTP_PROXY= \
    HTTPS_PROXY= \
    http_proxy= \
    https_proxy= \
    NO_PROXY='*' \
    no_proxy='*'

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY . .

EXPOSE 3300

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3300"]
