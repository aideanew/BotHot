---
id: ADR-0001
type: decision
title: RAG 引擎选型：LangBot
status: accepted
date: 2026-09-29
---

# ADR-0001：RAG 引擎选型

## 背景
BotHot 需要知识问答能力，可选方案：自建 RAG、LangBot、外部 API。

## 决策
LangBot 作为知识引擎，知识空间 1:1 映射 LangBot KB。

## 理由
- LangBot 已有成熟的 RAG 能力，避免重复造轮子
- 1:1 映射降低同步复杂度
- 已有 Docker 镜像，部署成本低

## 影响
- 知识空间创建时需同步创建 LangBot KB
- 引擎切换需通过 EnginePort 抽象（见 ADR-0004）
