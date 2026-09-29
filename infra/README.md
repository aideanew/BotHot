# infra/ — 基础设施即代码

> **状态**：目录骨架已建。当前 Docker Compose 配置仍在 `docker/`，待迁移到此目录。

## 目录结构

```
infra/
└── docker/
    ├── compose.yml          # Docker Compose 编排
    ├── compose.prod.yml     # 生产配置（未来）
    └── .env.example         # 环境变量模板
```

## 迁移策略

从 `docker/` 迁入 `infra/docker/`，更新根目录 `docker-compose.yml` 软链接指向 `infra/docker/compose.yml`。
