# EVD-V21-50 门面版本声明 ↔ 实值一致性门（执行助手）

平台 @win，开工 head `ccc14d0`（STEP-49 收口批），时间 2026-10-25（Asia/Shanghai）。

## S50.1 先红（旧脚本盲区证明）

把 `AGENTS.md:84` 的 next 版本临时写错一位（`^15.5.28` → `^15.5.29`），跑**旧**
`check_docs_consistency.py` ⇒ **rc=0**（`[ok] 文档一致性检查通过`）——旧门没有在看这一格。
读数记录在 `s50_1_old_blind.txt`。变异保持未还原的状态下跑新门 ⇒ **rc=1**，点名
`AGENTS.md:84 声明 '"next": "^15.5.29"' 与 apps/web/package.json:27 实值不符`；还原后 rc=0。

## S50.2 门实现（`scripts/check_docs_consistency.py` 新增段）

- `stack_citation_problems(corpus, read_line)` 纯函数：扫行内反引号包住的
  `"键": "值"`（package.json 形）/ `键 = "值"`（pyproject 形）与 `被引文件:行号` 锚
  （`apps/web/package.json` / `apps/api/pyproject.toml` 两类），断言被引行**逐字包含**该键值对。
  token 化按最靠前优先（`:N` 裸锚出现在下一键值对之前时先更新行号——AGENTS:84 的 `、:28` 写法，
  首版顺序写反被变异读数抓出后修正）。
- `<!-- stack-history -->` 整行跳过（REQ-C-001:28 历史叙述行已打标）。
- `requires-python` **显式不比对**（卡面验收④：它声明的是"允许更宽"区间，与 CI 钉的精确版是两套口径）。
- `--self-test` 追加负例 ⑧ 值写错一位、⑨ 行号指错、⑩ history 行跳过（卡面要求 +2，交付 +3）。

## S50.3 现仓库对账

新门在现仓库：**4 行含键值引用、0 失配、rc=0**——文档无漂移，无需修引用（卡面升级条件不触发）。
覆盖面：AGENTS.md:84（next/react）、REQ-C-001:19（next/react）、:20（node engines）＝5 处键值引用
+ REQ-C-001:18（requires-python，按验收④跳过）。

## 本机复跑（@win）

`python scripts/check_docs_consistency.py` rc=0；`--self-test` rc=0（10 发极性全 OK）；
`ruff check ../../scripts` All checks passed；`mypy ../../scripts` Success: 12 files（scripts 面自
STEP-34 起在 CI lint/type 门内）。后端全量（清库后，P-120 规避口径）：
**2384 passed / 6 skipped / 1 failed**——唯一 failed 是 `test_workflow_gate_wiring` 的
lint-backend 实跑断言，抓到的恰是本卡门函数里两处 UP031 风格错（percent 格式，我的嵌入脚本产物；
**STEP-34 扩的门咬了 STEP-50 的手，门在工作**）。改为 f-string（其中一次替换碰掉一个引号致
SyntaxError，当场修复）后：`entry.py lint-backend`/`typecheck-backend` 双 rc=0、wiring 4 passed、
docs 门 rc=0、self-test rc=0。风格修复不改判据行为（self-test 10 发极性全过）。

## backlog

`STACK-001` 段头 ⬜ → ✅（证据路径写入）。

## @ci（推送后回填）

_（占位）_
