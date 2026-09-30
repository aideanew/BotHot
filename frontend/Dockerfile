# BotHot frontend 容器化（W6 A.4：多阶段 + 非 root(uid1000=node) + HEALTHCHECK）
# 说明：next.config.mjs 未启用 output:'standalone'（属 C 变更单），故 runtime 携 node_modules + .next
# 网络：依赖安装走 npmmirror；构建期代理由 compose build.args 注入（宿主 10808 经 host.docker.internal）
# 基础镜像可注入：默认走 docker.io；网络受限时由 compose build.args 换成镜像源
#   （同 backend/Dockerfile 的实证口径，例 docker.m.daocloud.io/library/node:24-alpine）
# 3.4 版本锚统一：Node 基线 = .nvmrc(24.21.0)，Dockerfile FROM 对齐 node:24-alpine。
#   注意 BASE_IMAGE 若被 compose args 覆盖，默认值必须同为 node:24（2026-09-30 实测 compose
#   曾用 node:20-alpine 悄悄覆盖本锚点，已修；guard-versions 已扩围盯住 compose 侧）。
#
# 构建上下文 = **仓库根**（compose: context: .. + dockerfile: frontend/Dockerfile）。
# 原因：前端 tsconfig paths 把 @bothot/contracts 解析到 ../packages/contracts/src，
# next build 的期类型检查需要它；旧的 context: ../frontend 镜像内取不到 → build 必炸。
ARG BASE_IMAGE=node:24-alpine

# ---------------- builder：装依赖 + 构建产物 ----------------
FROM ${BASE_IMAGE} AS builder

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

# pnpm 版本锚单一源 = packageManager 字段（frontend/package.json）。corepack 按其自动解析，
# Dockerfile 不硬编码 pnpm 版本。先 COPY package.json 再 enable，使 corepack 读到声明版本。
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN corepack enable
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    npm_config_registry=https://registry.npmmirror.com

RUN pnpm install --frozen-lockfile

# 契约源码放 /packages：/app(tsconfig) 的 ../packages 即 /packages
COPY packages /packages

COPY frontend/. .
RUN pnpm run build

# ---------------- runner：只带运行所需，非 root ----------------
FROM ${BASE_IMAGE} AS runner

ENV TZ=Asia/Shanghai \
    NODE_ENV=production

WORKDIR /app

# node 官方镜像自带 uid/gid=1000 的 `node` 用户；产物 --chown 给它，`next start`
# 若需写 .next/cache 也不会因 root 属主而失败（frontend 不强制 read_only）。
COPY --from=builder --chown=node:node /app/node_modules ./node_modules
COPY --from=builder --chown=node:node /app/.next ./.next
COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder --chown=node:node /app/package.json ./package.json
COPY --from=builder --chown=node:node /app/next.config.mjs ./next.config.mjs

# runtime 也要 corepack 解析出的 pnpm 才能 `pnpm start`
RUN corepack enable

USER node

EXPOSE 3000

# alpine busybox 自带 wget：探 SPA 首页返 2xx 即存活
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:3000/ || exit 1

CMD ["pnpm", "start"]
