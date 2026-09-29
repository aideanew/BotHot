---
id: ADR-0002
type: decision
title: 消息拓扑与 LLM 计费路径
status: accepted
date: 2026-09-29
---

# ADR-0002：消息拓扑与 LLM 计费路径

## 背景
RAG 问答需要 LLM 推理。LangBot 可转发 LLM 请求，也可后端直连 LLM 服务。

## 决策
LLM 流式响应直连 SiliconFlow，不经 LangBot 转发。

## 理由
- LangBot 转发增加延迟和计费复杂度
- 直连降低延迟（SSE 首 Token < 3s）
- 计费透明，用户余额实时查询主平台

## 影响
- 后端需维护 SiliconFlow API 客户端
- 余额/等级从不持久化，实时查询主平台（SSO 身份锚点 = users.sub）
