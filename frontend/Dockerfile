# BotHot frontend 容器化（A 所有，不触碰 C 的代码文件）
# 说明：next.config.mjs 未启用 output:'standalone'（属 C 变更单），故采用单阶段 + pnpm start
# 网络：依赖安装走 npmmirror；构建期代理由 compose build.args 注入（宿主 10808 经 host.docker.internal）
# 基础镜像可注入：默认走 docker.io；网络受限时由 compose build.args 换成镜像源
# （同 backend/Dockerfile 的实证口径，例 docker.m.daocloud.io/library/node:24-alpine）
# 3.4 版本锚统一：Node 基线 = .nvmrc(24.21.0)，Dockerfile FROM 对齐 node:24-alpine。
ARG BASE_IMAGE=node:24-alpine
FROM ${BASE_IMAGE}

ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG http_proxy=""
ARG https_proxy=""
ARG NO_PROXY="*"
ARG no_proxy="*"

ENV TZ=Asia/Shanghai \
    NODE_ENV=production

# BACKEND_ORIGIN 必须在构建期注入：Next 生产模式在 build 时烘焙 rewrites 的
# process.env，运行时 env 对已构建产物不生效（runtime env 只影响 dev 模式）
ARG BACKEND_ORIGIN=http://backend:8000
ENV BACKEND_ORIGIN=${BACKEND_ORIGIN}
# A-T7 联调窗口（2026-09-09）：关闭 mock，走真实 backend。NEXT_PUBLIC_* 为构建期内联变量，必须 build-arg 烘焙
ARG NEXT_PUBLIC_API_MOCK=false
ENV NEXT_PUBLIC_API_MOCK=${NEXT_PUBLIC_API_MOCK}

WORKDIR /app

# C 于 2026-09-09 迁移至 pnpm（pnpm-lock.yaml），构建配置同步为 corepack/pnpm。
# 3.4 pnpm 版本锚单一源 = packageManager 字段（frontend/package.json）。corepack 按
# 其自动解析，Dockerfile 不再硬编码 pnpm 版本（与 CI「Resolve pnpm version from
# packageManager」同源）。先 COPY package.json 再 enable，使 corepack 能读到声明版本。
# --frozen-lockfile：锁文件即事实源；devDependencies 默认安装（typescript 缺失会破坏 @/* 别名）
COPY package.json pnpm-lock.yaml ./
RUN corepack enable
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    npm_config_registry=https://registry.npmmirror.com

RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm run build

EXPOSE 3000

CMD ["pnpm", "start"]
