---
id: ADR-0004
type: decision
title: 知识库引擎可插拔架构
status: accepted
date: 2026-09-29
---

# ADR-0004：知识库引擎可插拔架构

## 背景
知识引擎可能需要切换（LangBot → 自建 → 其他），不能硬编码绑定。

## 决策
EnginePort 抽象接口 + 注册表，支持 builtin/langbot/aidean/redfox 四种后端。

## 理由
- 避免锁定单一引擎
- 新引擎接入只需实现 EnginePort 接口
- 空间级引擎配置，不同空间可用不同引擎

## 影响
- 引擎密钥管理需独立于引擎实现
- 引擎切换不影响已有知识空间数据
