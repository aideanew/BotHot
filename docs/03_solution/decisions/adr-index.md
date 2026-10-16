---
id: ADR-INDEX
type: decision-index
title: 架构决策记录索引
status: active
owner: architecture
created: 2026-09-29
updated: 2026-10-15
---

# 架构决策记录（ADR）索引

| ADR | 标题 | 状态 | 日期 |
|---|---|---|---|
| [ADR-0001](adr-0001-rag-engine-selection.md) | RAG 引擎选型：LangBot | accepted | 2026-09-29 |
| [ADR-0002](adr-0002-message-topology-and-llm-billing.md) | 消息拓扑与 LLM 计费路径 | accepted | 2026-09-29 |
| [ADR-0003](adr-0003-session-and-space-resolution.md) | 会话与知识空间解析规则 | accepted | 2026-09-29 |
| [ADR-0004](adr-0004-pluggable-engine-architecture.md) | 知识库引擎可插拔架构 | accepted | 2026-09-29 |
| [ADR-0005](adr-0005-push-provider-adapter-pattern.md) | 多渠道推送 Provider 适配器模式 | accepted | 2026-09-29 |
| [ADR-0006](adr-0006-monorepo-apps-structure.md) | Monorepo apps/ 目录架构 | proposed | 2026-09-29 |
| [ADR-0007](adr-0007-job-queue-postgres-skip-locked.md) | Job 队列用 PostgreSQL FOR UPDATE SKIP LOCKED | accepted | 2026-09-29 |
| [ADR-0008](adr-0008-contract-single-source.md) | 契约唯一源 = 后端 Python 代码，TypeScript 契约一律生成 | proposed | 2026-10-12 |
| [ADR-0009](adr-0009-guest-access-policy.md) | 访客（未登录）访问策略 | proposed | 2026-10-12 |
| [ADR-0010](adr-0010-externalize-connection-strings.md) | 编排中的数据库/缓存连接串一律来自环境变量 | proposed | 2026-10-12 |
| [ADR-0011](adr-0011-canonical-article-key.md) | 文章规范键格式（D-V2-01） | accepted | 2026-10-15 |
| [ADR-0012](adr-0012-manifest-asset-alignment.md) | 清单↔资产键对齐与清单状态机（D-V2-02 / D-V3-01） | accepted | 2026-10-16 |

## 归位记录（STEP-01 S1.1.0 · 2026-10-15）

ADR-0008 / 0009 / 0010 曾**只躺在** `docs/任务规划V0.1.0/03_solution/decisions/` 快照里，
不在本目录、本索引的**表格里也只有断链占位** ⇒ 任何"依据 ADR-0008"的规划（含决策台账 D-09）
当时都拿不到可解析的活链接。**订正一处我最初的过话**：快照自带的 `adr-index.md` 并非"完全没登记"，
它正文里有这三份的章节（`:61`、`:66`、`:70`，含 `proposed` 与日期），只是它的**表格**只列到 0007
——缺的是"能被链接解析到"，不是"没人写过"。本节由 STEP-01 的 **S1.1.0** 关闭：

- 三份文件 `git mv` 到本目录，历史保留：`git log --follow` 现为两级
  （`8820e4c` 本次归位 ← `3bb61c3` 2026-10-12 的 V0.1.0 全量入库）。**注意**最早那一级是
  批量导入提交，所以"可追到 2026-10-12"指的是**进入本仓库**的时间，不是单文件的创作提交；
- 快照目录留一份指针说明 `adr-relocated-2026-10-15.md`，**不改写**任何历史结论；
- **status 仍是 `proposed`**：归位只解决"可发现性"，不等于裁决通过。ADR-0009 的标题本身就写着
  "待裁决 D-01"，把它顺手改成 accepted 会伪造一次批准 ⇒ 明确不动；
- 机检读数：活目录 `ls adr-*.md | grep -v index | wc -l` **8 → 11**；本索引内三份文件的
  活链接行（Markdown 链接目标以本目录文件名开头，无 `../../` 前缀）**0 → 各 1**。
  （卡面 S1.1.0.3 的反证写的是 `grep -c 'ADR-0008' …`。**准确说法**：这条在卡片自己的基线
  `a9b194d`（2026-10-14）上读数是 **0**、当时是好判据；它在 `6764ebe`（2026-10-15，V0.11.0
  第二增量加"断链登记"表）之后才烂掉——归位前读数为 2，用它验收必然假绿。
  所以这是**判据腐化**，与 S1.1.0.1 期望值 10→11 同源（都是"卡面写死读数、目录后来变了"），
  不是判据当初写错。执行期我把它说成"当场就是坏的"，措辞偏重，已在此更正。）
- 因此本节的**验收锚换成"表格里链接目标是否指向本目录文件"**（描述式，见上一条读数 0 → 各 1）。
  踩过的坑记在这里：我最初把新锚的**字面形式**直接写进说明文字，结果那段说明自己被 grep 计数、
  读数变成 2 ⇒ "测量锚不能与被测文本同处一节"，这条与 00S 那次"把敏感形抄进禁止敏感形的文档"
  是同一类错误，只是后果从"门禁红"降级成"读数失真"。
- 卡面 S1.1.0.1 的期望值 **10** 也已过期：它写于 ADR-0011 尚不存在的年代（7+3=10），现实现算为
  **11**（8+3，`adr-0011` 已于 2026-10-15 落档并 `accepted`）。按"判据不可满足 ⇒ 上报规划方"的纪律，
  本卡由规划方自己执行，故在此重算并留痕，不改判据字面。

- **2026-10-16 追加**：S1.1.2 落 `ADR-0012`（status accepted，因为 D-V2-02/D-V3-01 已在台账签入，本 ADR 只是把已签裁决写成可实现形状）⇒ 活目录文件数 11 → **12**，索引表也补一行。上面那句"现实现算为 11"保留为当时读数，不改。

仍过期、但**故意不改**的两处（改了就是重写历史）：`docs/任务规划V0.3.0/01-事实基线与上一步复核.md:54`
的 F-18 仍写快照路径；决策台账 `decision-log.md:45`（D-09） rationale 里仍写"现 stranded 于…、
归位见 STEP-01 S1.1.0"。台账纪律是"只追加、不改历史行"，归位完成后由下一次台账维护统一标注。

---

## ADR-0001：RAG 引擎选型

**决策**：LangBot 作为知识引擎，知识空间 1:1 映射。
**理由**：LangBot 已有成熟的 RAG 能力，避免重复造轮子；1:1 映射降低同步复杂度。

## ADR-0002：消息拓扑与 LLM 计费路径

**决策**：LLM 流式响应直连 SiliconFlow，不经 LangBot 转发。
**理由**：LangBot 转发会增加延迟和计费复杂度；直连降低延迟，计费透明。

## ADR-0003：会话与知识空间解析规则

**决策**：通过 intent + resolver 解析目标空间。
**理由**：用户提问可能涉及多空间，需要意图检测和空间解析。

## ADR-0004：知识库引擎可插拔架构

**决策**：EnginePort 抽象 + 注册表，支持 builtin/langbot/aidean/redfox 四种后端。
**理由**：避免锁定单一引擎，新引擎接入只需实现 EnginePort 接口。

## ADR-0005：多渠道推送 Provider 适配器模式

**决策**：PushProvider 接口 + 注册表，每种渠道一个 Provider 实现。
**理由**：channel 字段存为 String(32) 而非 enum，新增渠道零数据库迁移。

## ADR-0006：Monorepo apps/ 目录架构

**决策**：从 `backend/ + frontend/` 迁移到 `apps/api/ + apps/web/` 规范化结构。
**状态**：proposed — 设计文档已完成，实施分阶段推进。
**理由**：业务域边界清晰，依赖方向可控，共享契约可提取。

## ADR-0007：Job 队列用 PostgreSQL FOR UPDATE SKIP LOCKED

**决策**：不引入 Redis 队列，Job 队列在 PostgreSQL 中用 FOR UPDATE SKIP LOCKED 实现。
**理由**：减少组件依赖；PostgreSQL 已有事务保障，SKIP LOCKED 适合多 Worker 并发拉取。
