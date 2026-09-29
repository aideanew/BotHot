# database/ — 数据库生命周期资产

> **状态**：目录骨架已建。当前 Alembic 迁移仍在 `backend/alembic/`，待迁移到此目录。

## 目录结构

```
database/
├── migrations/
│   ├── env.py              # Alembic 环境
│   └── versions/           # 迁移版本脚本
├── seeds/                  # 种子数据
└── alembic.ini             # Alembic 配置
```

## 迁移策略

从 `backend/alembic/` 整体迁入 `database/migrations/`，更新 `alembic.ini` 中的路径引用。
