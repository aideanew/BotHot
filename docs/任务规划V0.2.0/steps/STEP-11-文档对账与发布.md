---
id: STEP-11
title: 文档对账与发布
priority: P2
depends: 全部 STEP（按实际完成范围对账）
estimate: 0.5 人日
---

# STEP-11 文档对账与发布

## 目标
让文档只陈述代码里真实成立的事；把 V0.1.0 的元治理缺口收拢为一条 backlog，不再分散悬挂；形成可审计的发布证据。

## 依据
- AGENTS.md "文章来源：4 平台已接入""详情兜底协调器按成本排序"与 02 §D-03/§D-08 矛盾。
- `docs/RSS订阅渠道.md` 预置外链源与 D-07 矛盾。
- `product-requirements.md` REQ-F-004/006 验收条款未覆盖长链与对齐语义。
- V0.1.0 G-6/7/10/11/13/16/18/23/24 九项均为"文档/门禁自身可信度"问题（`remaining-outline.md` R.11/R.12）。

## 允许修改
`AGENTS.md`、`README.md`、`CHANGELOG.md`、`docs/02_requirements/product-requirements.md`、`docs/RSS订阅渠道.md`、`docs/04_engineering/{backlog,conventions}.md`、`docs/06_validation/evidence/EVD-V2-*/**`
## 禁止修改
任何代码与测试。

## 原子任务

| 编号 | 类型 | 动作 | 验收命令 |
|---|---|---|---|
| S11.1.1 | 📄 | AGENTS.md "文章来源"段按 STEP-03/04/06 实际完成情况改写，每句附 `file:symbol` 证据；未完成项写"未接线/未验证" | `python scripts/check_docs_consistency.py` rc=0 |
| S11.1.2 | 📄 | REQ-F-004 增验收："同号两篇不同长链分别入库"（锚 `test_kb_longlink_ingest.py`）；REQ-F-006 增"Job 终态后不重复入列"（锚 `test_manifest_asset_alignment.py`） | `grep -c "test_kb_longlink_ingest\|test_manifest_asset_alignment" docs/02_requirements/product-requirements.md` = 2 |
| S11.1.3 | 📄 | `conventions.md` 增"测试必须设置 AIDEANBOT_TEST_PG_DSN，`scripts/test-env.sh` 用法"；运维说明"启用付费渠道必须同时配置日预算" | grep 命中 |
| S11.2.1 | 📄 | backlog 新增"文档门禁 v2"一条，列 G-6/7/10/11/13/16/18/23/24 指针，标"不阻塞 V0.2.0" | grep 命中 |
| S11.3.1 | ✅ | EVD-V2-00…08 汇总表（每份：命令、结果、提交 sha） | 文件存在 |
| S11.3.2 | 📄 | CHANGELOG `[v1.1.0]`：采集正确性修复（D-01/01b/02/03/04）+ 新能力；tag 由人执行 | grep 命中 |

## 完成定义
`check_docs_consistency.py` 与 CI 全绿；AGENTS.md 中采集相关陈述逐句可在代码中找到对应符号。
