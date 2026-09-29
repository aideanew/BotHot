---
id: ADR-0007
type: decision
title: Job 队列用 PostgreSQL FOR UPDATE SKIP LOCKED
status: accepted
date: 2026-09-29
---

# ADR-0007：Job 队列用 PostgreSQL FOR UPDATE SKIP LOCKED

## 背景
文章入库需要异步 Job 队列。可选：Redis 队列、PostgreSQL 队列、外部 MQ。

## 决策
不引入 Redis 队列，Job 队列在 PostgreSQL 中用 FOR UPDATE SKIP LOCKED 实现。

## 理由
- 减少组件依赖（PostgreSQL 已有）
- 事务保障：Job 状态变更与数据写入在同一事务
- SKIP LOCKED 适合多 Worker 并发拉取，无锁竞争
- 已有成熟实践（GitHub Actions、Solid Queue 均用此模式）

## 影响
- Worker 进程用 `SELECT ... FOR UPDATE SKIP LOCKED` 拉取 Job
- Job 状态机：pending → running → completed/failed
- 心跳机制：Worker 定期更新 process_heartbeats 表
