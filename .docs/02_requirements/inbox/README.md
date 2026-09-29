# 需求 Inbox — 新需求唯一入口

> 依据：《文档规范-v1.1》§6。任何来源（管理者/用户/开发/AI 会话/运营反馈）的新需求，**必须先落一份 Inbox 文档**，再进入分析流转；不得跳过 Inbox 直接改代码或开方案。

## 1. 文件命名

```text
REQ-INBOX-YYYYMMDD-NNN.md    # 同日多篇顺延 NNN
```

## 2. 文档格式

```markdown
---
id: REQ-INBOX-YYYYMMDD-NNN
type: requirement-inbox
status: new        # new → analyzed → promoted / rejected / parked
source: user | manager | agent | ops
created: YYYY-MM-DD
---

# 原始需求

## 原始描述      ← 提出者原话，不修改原始表述
## 背景          ← 需求出现的场景
## 来源          ← 谁提出的
## 附加上下文    ← 相关链接/截图/关联文档
```

## 3. 流转规则

```text
inbox（原始事实，只读）
  → 分析判定类型
      → 功能需求     02_requirements/（并入需求文档基线或立 REQ-F 单档）
      → 非功能需求   同上（REQ-NF 语义）
      → 约束         同上（REQ-C 语义）
      → 拒绝/挂起    本文件 status 改 rejected/parked，正文不改
  → 需要实现路径分析的，在 03_solution/solutions/ 立 SOL/SPEC
  → 状态同步进 02_requirements/backlog.md
```

## 4. 纪律

- Inbox 条目**不删除**；作废走 status 标注（历史不能被覆盖）。
- Inbox 只保存原始需求事实；分析与方案在目标文档完成，不回写本目录。
- AI 会话代管理者登记时，`source: agent` 并在附加上下文注明会话/日期。
