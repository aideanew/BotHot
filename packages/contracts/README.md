# packages/contracts — 前后端共享契约

> **状态**：目录骨架已建，契约尚未提取。

## 用途

存放前后端共享的 TypeScript 类型定义，确保 API Request/Response 类型一致。

前端 `apps/web/` 和后端（通过 codegen 生成的 OpenAPI types）共同引用此包。

## 目录结构

```
packages/contracts/
├── src/
│   ├── identity/       # 认证契约
│   ├── knowledge/      # 知识库契约
│   ├── subscription/   # 订阅契约
│   ├── ingest/         # 入库契约
│   ├── chat/           # 问答契约
│   ├── engine/         # 引擎契约
│   ├── bot/            # 推送契约
│   ├── hot/            # 热点契约
│   ├── common/         # 通用类型（分页、响应格式、错误）
│   └── index.ts        # 统一导出
└── package.json
```
