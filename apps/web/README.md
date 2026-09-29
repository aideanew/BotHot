# apps/web — BotHot 前端 Web 应用

> **状态**：目录骨架已建，代码尚未迁入。当前前端代码仍在 `frontend/` 目录运行。
>
> 迁移计划详见 [docs/03_solution/project-structure-design.md](../../docs/03_solution/project-structure-design.md)

## 目录结构

```
apps/web/
├── src/
│   ├── app/               # Next.js App Router（路由页面层）
│   ├── features/          # 业务功能域（10 个域）
│   │   ├── auth/          # 认证
│   │   ├── knowledge/     # 知识库
│   │   ├── subscription/  # 订阅
│   │   ├── ingest/        # 入库任务
│   │   ├── chat/          # 问答
│   │   ├── engine/        # 引擎管理
│   │   ├── bot/           # Bot 渠道
│   │   ├── hot/           # 热点/日报
│   │   ├── admin/         # 管理后台
│   │   └── onboarding/    # 引导
│   ├── components/        # 纯 UI 组件（零业务逻辑）
│   ├── data-access/       # 数据访问层（HTTP 客户端）
│   ├── lib/               # 全局通用能力
│   └── constants/         # 常量
├── public/
├── tests/
├── e2e/
├── package.json
├── next.config.mjs
├── tailwind.config.ts
└── Dockerfile
```

## 依赖方向

```
✅ pages → features → components/ui → lib/utils（单向）
❌ features/A → features/B/internal/
❌ components/ui → features/（UI 组件依赖业务逻辑）
❌ utils/ → features/（工具函数依赖业务域）
```

## 功能域内部结构

每个 feature 目录包含：

```
features/<domain>/
├── components/    # 该域的 React 组件
├── hooks/         # 该域的自定义 Hooks
├── api/           # 该域的 API 调用
└── index.ts       # 公开导出（其他域只能通过 index.ts 访问）
```
