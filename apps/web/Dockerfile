# BotHot frontend 容器化（W6 A.4：多阶段 + 非 root(uid1000=node) + HEALTHCHECK）
# 说明：next.config.mjs 未启用 output:'standalone'（属 C 变更单），故 runtime 携 node_modules + .next
# 网络：依赖安装走 npmmirror；构建期代理由 compose build.args 注入（宿主 10808 经 host.docker.internal）
# 基础镜像可注入：默认走 docker.io；网络受限时由 compose build.args 换成镜像源
#   （同 apps/api/Dockerfile 的实证口径，例 docker.m.daocloud.io/library/node:24-alpine）
# 3.4 版本锚统一：Node 基线 = .nvmrc(24.21.0)，Dockerfile FROM 对齐 node:24-alpine。
#   注意 BASE_IMAGE 若被 compose args 覆盖，默认值必须同为 node:24（2026-09-30 实测 compose
#   曾用 node:20-alpine 悄悄覆盖本锚点，已修；guard-versions 已扩围盯住 compose 侧）。
#
# 构建上下文 = **仓库根**（compose: context: .. + dockerfile: apps/web/Dockerfile）。
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

# pnpm 版本锚单一源 = packageManager 字段（apps/web/package.json）。corepack 按其自动解析，
# Dockerfile 不硬编码 pnpm 版本。先 COPY package.json 再 enable，使 corepack 读到声明版本。
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
RUN corepack enable
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    npm_config_registry=https://registry.npmmirror.com

# 2026-10-08 实证修复：builder ENV 的 NODE_ENV=production 会让 pnpm install 跳装
# 全部 devDependencies（typescript 缺失 → Next 无法应用 tsconfig paths → `@/*` 解析
# 全炸，webpack 错误归并后表象为个别页 Module not found）。--prod=false 显式装全量；
# build 后 prune --prod 收刀，runner COPY 的 node_modules 仍保持纯生产依赖。
RUN pnpm install --frozen-lockfile --prod=false

# 契约源码放 /packages：/app(tsconfig) 的 ../packages 即 /packages
COPY packages /packages

COPY apps/web/. .
RUN pnpm run build

# 产物定型：剥除 devDependencies（typescript/vitest 等），runner 层保最小依赖面
RUN pnpm prune --prod

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

# 健康探针（A-T024 配套 3.2，2026-10-09）：用 node -e 替代 busybox wget。
# 根因：Next.js 15 `next start` 绑定 :::3000（IPv6 wildcard），Alpine busybox wget
# 对 127.0.0.1 做纯 IPv4 connect 在此网络配置下被拒；Node.js http.get 能正确处理双栈。
# /api/health 是前端本地零依赖路由（app/api/health/route.ts），不级联后端/数据库。
HEALTHCHECK --interval=30s --timeout=8s --start-period=45s --retries=3 \
    CMD node -e "require('http').get('http://127.0.0.1:3000/api/health',r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"

CMD ["pnpm", "start"]
