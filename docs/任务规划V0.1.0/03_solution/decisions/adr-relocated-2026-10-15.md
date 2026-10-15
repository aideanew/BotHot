---
id: ADR-RELOCATED-2026-10-15
type: pointer-note
title: 本目录三份 ADR 已归位到活目录（历史说明，非决策）
status: informational
owner: architecture
created: 2026-10-15
updated: 2026-10-15
---

# 本目录的 ADR-0008 / 0009 / 0010 已迁出

**这是一份指针说明，不是一份 ADR，也不改变任何结论。**

V0.1.0 规划会话当时把这三份决策稿写在了本快照目录下，但没有进本目录自带的 `adr-index.md`
（那份索引同样只列到 ADR-0007），也没有进活目录 ⇒ 从 V0.2.0 起，"依据 ADR-0008"这类引用
连续五个版本都是**不可验证引用**（`check_docs_consistency` 只校验 backlog 的路径与行号，
不校验 ADR 是否存在，所以它不会自己变红）。

2026-10-15 由 `docs/任务规划V0.12.0/steps/STEP-01-采集域契约冻结与契约收编.md` 的 **S1.1.0**
用 `git mv` 归位（历史保留，`git log --follow` 可追到 2026-10-12 的原提交）：

| 原路径（本目录） | 现路径（活目录） | status |
|---|---|---|
| `adr-0008-contract-single-source.md` | `docs/03_solution/decisions/adr-0008-contract-single-source.md` | proposed |
| `adr-0009-guest-access-policy.md` | `docs/03_solution/decisions/adr-0009-guest-access-policy.md` | proposed |
| `adr-0010-externalize-connection-strings.md` | `docs/03_solution/decisions/adr-0010-externalize-connection-strings.md` | proposed |

**归位 ≠ 通过**：三份的 `status` 原样保持 `proposed`。ADR-0009 的标题本身写着"待裁决 D-01"，
把它顺手改成 accepted 会伪造一次批准。

引用它们的下游若还指向本快照路径，那是**当时的真实读数**，按"不改写历史结论"的纪律保留原文
（已知两处：`docs/任务规划V0.3.0/01-事实基线与上一步复核.md:54` 的 F-18、
`docs/03_solution/decisions/decision-log.md:45` 的 D-09 rationale）。
