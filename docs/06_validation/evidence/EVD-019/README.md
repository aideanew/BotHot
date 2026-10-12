> 卡片：[TASK-019](../../05_execution/tasks/TASK-019.md) ｜ 采集时间：2026-10-12 ｜ 锚：`HEAD=60e5723`（**本轮改动尚未提交**）
> 状态图例： locally-proven=本机已实测 ｜ ⚪ ci-only=本机物理上不可证（无 docker / 无 .venv / 无二进制 / 禁止起服务）

## 🟡 locally-proven

| 命令 | 实测 |
|---|---|
| `python scripts/check_docs_consistency.py` | **rc=0** |
| 陈旧"待迁移/未落地"字样复扫（卡片第二条） | **rc=1（空）** |
| X-02…X-12 逐条现文核对 | 已改：`conventions.md:117/147/157/187/197/200/87`、`product-requirements.md:56`、`roadmap.md:118-142`、`AGENTS.md:64/69` |

## 本轮被复核推翻后自纠的两处

1. `project-map.md:73-74` 我曾写"07_release 有 `rotate-keys-plan.md` 与 `release-checklist.md`"——
   `find docs/07_release -type f` 实证只有 `key-rotation-sop.md` + 两个 `.gitkeep` ⇒ **修 X-15 的动作造出了 X-17**。
   已改为实测口径并降格 🟡（元缺陷 = 大纲 G-18：验收命令不覆盖自己新写的那段）。
2. 引用锚 `X-06` 曾在 `conventions.md` 内自 `:160` 漂到 **`:187`**、`AGENTS.md` 自 `:70` 漂到 **`:69`**；
   现按现文核对。

## ⚪ 不在本卡范围但同域未收口

- X-13 仍活：`CHANGELOG.md:29`「公共引流位保持可见」与 `:33-34`「middleware…裁定不实施」互斥
  （且 `:335-338` 自述承认）⇒ 属 S2/ADR-0009 链，需 D-01；
- X-15 的目标 > 验收（`current-plan.md:115` 把 X-15 指派给本卡，验收只列 X-01…X-12）⇒ 大纲 G-10。
