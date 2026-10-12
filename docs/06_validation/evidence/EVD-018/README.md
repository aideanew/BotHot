> 卡片：[TASK-018](../../05_execution/tasks/TASK-018.md) ｜ 采集时间：2026-10-12 ｜ 锚：`HEAD=60e5723`（**本轮改动尚未提交**）
> 状态图例： locally-proven=本机已实测 ｜ ⚪ ci-only=本机物理上不可证（无 docker / 无 .venv / 无二进制 / 禁止起服务）

## 🟡 locally-proven

| 命令 | 实测 |
|---|---|
| `bash scripts/preflight.sh docs` | **rc=0** |
| 负向判别（伪造根，`### … ✅` 区块内含 1 真 2 假引用） | **rc=1**，报 `ghost.py:999 不存在` 与 `exists.py:99 行号越界（文件共 3 行）` ⇒ 门禁**有鉴别力** |
| 另一负向（backlog 无 ✅ 区块） | **rc=1**，`未找到任何 ✅ 条目的路径引用——禁止静默通过` ⇒ 空解析也红 |
| `grep -n docs_gate scripts/preflight.sh` | `:181` 定义、`:196`/`:201` 两处挂接 |
| `grep -n 'Docs reference consistency gate' .github/workflows/ci.yml` | `:104` step 存在 |

## 本轮修复

`preflight.sh:182` 原为双引号内含反引号的标题 ⇒ `file:line` 被当**命令替换**执行（标题被吞 + 一行
`command not found`）。已去反引号；复跑现打印完整标题且无错误行。

## ⚪ ci-only

- `actionlint`（本机无该二进制）；
- "CI 中该 step 存在且**绿**"属 CI 事实，本机只能证"存在"。

## 已知盲点（另卡，G-6）

`check_docs_consistency.py` 只认 `.py/.ts/.tsx/.mjs` 且只扫 ✅ 区块 ⇒ 指向 `Makefile`/`.yml`/`Dockerfile`/`.toml`
的假 `file:line` 检不出。本 EVD 的负向测试**恰好暴露了这一点**：我的 fixture 用 `.py` 才被抓住。
