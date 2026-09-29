---
id: ADR-0005
type: decision
title: 多渠道推送 Provider 适配器模式
status: accepted
date: 2026-09-29
---

# ADR-0005：多渠道推送 Provider 适配器模式

## 背景
推送渠道多样（飞书/钉钉/企微/ClawBot/Webhook/站内），且未来可能增加。

## 决策
PushProvider 接口 + 注册表，每种渠道一个 Provider 实现。channel 字段存为 String(32) 而非 enum。

## 理由
- 新增渠道只需新增 Provider 文件 + 注册，零数据库迁移
- String(32) 比 enum 更灵活，不受 ORM 枚举约束
- Provider 可独立测试

## 影响
- 渠道类型校验在应用层而非数据库层
- PushProvider 实现未完成时返回 delivered=False（诚实回执，不伪造）
