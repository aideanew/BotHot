---
id: ADR-0006
type: decision
title: Monorepo apps/ 目录架构
status: proposed
date: 2026-09-29
---

# ADR-0006：Monorepo apps/ 目录架构

## 背景
当前 backend/ + frontend/ 扁平结构缺少业务域边界，跨域依赖混乱，共享契约无处放置。

## 决策
从 `backend/ + frontend/` 迁移到 `apps/api/ + apps/web/` 规范化结构，按业务域组织模块。

## 理由
- 业务域边界清晰（9 后端域 + 10 前端域）
- 依赖方向可控（interfaces → application → domain ← infrastructure）
- 共享契约可提取到 packages/contracts/
- 数据库迁移和基础设施配置独立管理

## 状态
proposed — 设计文档已完成（project-structure-design.md），实施分阶段推进。

## 影响
- 迁移期间旧结构和新结构并存
- 需逐域迁移，每域迁移后跑测试验证
- 完全迁移后删除旧目录
