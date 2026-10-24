# STEP-50 门面版本声明 ↔ 实值一致性门（STACK-001）

> 基线 main@9028b89｜状态：🔶 第 1 轮已交付（2026-10-25，读数在 EVD-V21-50/）｜版本 V0.21.0

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手（Agent-Guard） |
| 2 切片 | SL-SEC-PROOF |
| 3 来源 | REQ-C-001；backlog `STACK-001`（`docs/04_engineering/backlog.md:235-243`） |
| 4 目标 | 文档里"带文件:行号锚的版本引用"与被引文件该行实值不一致 ⇒ CI 红 |
| 5 输入 | `scripts/check_docs_consistency.py`（已在 CI 步 "Docs reference consistency gate"，`ci.yml:172`）；引用样本：`AGENTS.md:84`、`docs/02_requirements/constraints/REQ-C-001-tech-stack.md:19,29`、`product-requirements.md:93,116` |
| 6 输出 | 改 `scripts/check_docs_consistency.py`：新增 `verify_stack_citations()`——扫 `AGENTS.md` 与 `docs/02_requirements/**/*.md`，抽取形如"反引号包住的 `"键": "值"`"且同一行/紧邻带 `apps/web/package.json:N` 或 `apps/api/pyproject.toml:N` 锚的引用，断言被引文件第 N 行**逐字包含**该 `"键": "值"`（pyproject 用 `键 = "值"` 形，同理）；行内含 HTML 注释 `<!-- stack-history -->` 的整行跳过（用于叙述历史值）；`--self-test` 增两条负例（值不符、行号不符）；改 `REQ-C-001-tech-stack.md:29` 的历史叙述行加 `<!-- stack-history -->`；backlog STACK-001 改 ✅ |
| 7 验收 | ① 先红：在旧脚本上把 AGENTS.md:84 的 next 版本临时写错一位，现脚本 rc=0（证明旧门抓不到）；新脚本同改动 rc=1 ② 现仓库新脚本 rc=0 ③ `--self-test` 通过且负例数 +2 ④ `requires-python` 的"更宽"关系不判漂移（脚本不比对 `requires-python`）⑤ 三绿 |
| 8 命令 | `python scripts/check_docs_consistency.py && python scripts/check_docs_consistency.py --self-test` |
| 9 证据 | `EVD-V21-50/s50_readings.md` |
| 10 允许修改 | 第 6 格所列 |
| 11 禁止修改 | `.github/workflows/**`（脚本已在 CI 里，无需动）、`package.json`、`pyproject.toml` |
| 12 依赖 | 无（文件与 48、49 不相交） |
| 13 档位 | sonnet |
| 14 升级条件 | 现仓库新脚本 rc=1（文档已漂移）⇒ 先把漂移列表入证，按被引实值修文档（只改引用文字），修文档条数 >5 ⇒ 停交回 |
| 15 规模 | 小，≈0.4 人日 |
| 16 熔断 | 同判据 2 次 FAIL ⇒ 停 |

## 三级任务
1. [x] **S50.1 先红**：旧脚本对"写错一位"无反应（rc=0）入证
2. [x] **S50.2 门实现**
   1. [ ] S50.2.1 抽取器 + 逐字比对 + history 标记跳过
   2. [ ] S50.2.2 self-test 两条负例
3. [x] **S50.3 现仓库对账**：新脚本 rc=0；历史行打标
4. [x] **S50.4** backlog 回填 + 三绿 + 07 记录
