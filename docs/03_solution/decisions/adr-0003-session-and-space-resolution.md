---
id: ADR-0003
type: decision
title: 会话与知识空间解析规则
status: accepted
date: 2026-09-29
---

# ADR-0003：会话与知识空间解析规则

## 背景
用户提问可能涉及多个知识空间，需要确定 RAG 检索的目标空间。

## 决策
通过 intent 检测 + resolver 解析目标空间。

## 理由
- 用户不总是显式指定空间
- 意图检测可自动路由到最相关空间
- 支持多空间联合检索（未来扩展）

## 影响
- 需要意图检测服务（intent_detector）
- 需要空间解析服务（space_resolver）
- 会话上下文需记录解析结果
