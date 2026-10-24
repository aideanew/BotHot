# STEP-51 需求判词与文档纠真（X-1～X-5）

> 基线 main@9028b89｜状态：⬜ 待执行助手｜版本 V0.21.0

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手（Agent-Doc） |
| 2 切片 | SL-TRUTH（需求表说的 = 代码与证据说的） |
| 3 来源 | `01-事实基线与进度.md` §5 X-1～X-5；D-V21-05；P-78 |
| 4 目标 | 需求实现度判词与 roadmap、AGENTS 端口表全部有当前证据支撑 |
| 5 输入 | `docs/04_engineering/roadmap.md:14,44`；`docs/02_requirements/product-requirements.md`（§二、§三、§四表）；`non-functional/REQ-NF-001-performance.md`；`features/REQ-F-004-article-ingest.md`、`REQ-F-005-rag-chat.md`；`constraints/REQ-C-002-port-allocation.md`；`AGENTS.md` 端口表；`docker/compose*.yml`；`PERF-baseline-v1.md`；`apps/web/tests/ask-sse.spec.ts`、`r061-sse-ask.spec.ts` |
| 6 输出 | 只改上列文档 |
| 7 验收（逐条机器可判或可复读） | ① X-1：roadmap 站内通知行写"前端订阅侧已实现"并引 `notifications.ts` 与 `NotificationBell.tsx` 的现读行号 ② X-2：roadmap 当前阶段改为 v1.1.x 维护期，引 tag 与 CHANGELOG ③ X-3：REQ-NF-001 子文件与总表判词改"已实现（首测基线，2026-10-24）"，四个数字引 `PERF-baseline-v1.md`，局限照抄（首 Token 为录制回放）④ X-4：AGENTS.md 与 REQ-C-002 端口表拆"本栈发布 / 外部提供"两段，外部段的端口取自 `docker/compose.yml` 注释现读值；`test_r19_ports.py` 仍绿 ⑤ X-5：REQ-F-004 按 04 §4.3 的判据锚逐条列具名用例并跑一遍（`pytest -q <这些用例>` 读数入证），全过 ⇒ 判"已实现"，有不过 ⇒ 判"部分"并登记 P 号 ⑥ REQ-F-005：跑 `pnpm exec vitest run tests/ask-sse.spec.ts tests/r061-sse-ask.spec.ts`，读数挂到判词（组件层流式已证；真后端端到端仍未测，判词写"部分：组件层已证"）⑦ `check_docs_consistency.py` rc=0（含 STEP-50 新门）⑧ 三绿 |
| 8 命令 | `python scripts/check_docs_consistency.py`；`cd apps/api && pytest -q tests/test_r19_ports.py`；⑤⑥中的用例命令 |
| 9 证据 | `EVD-V21-51/s51_readings.md` |
| 10 允许修改 | 第 5 格所列文档（不含 compose 与任何代码） |
| 11 禁止修改 | 代码、compose、端口值、`docs/任务规划V0.12.0/contracts/**` |
| 12 依赖 | STEP-50（⑦要用新门）｜ Blocks：STEP-53 的 CHANGELOG |
| 13 档位 | haiku 起步；⑤⑥判词由 sonnet（涉及判断） |
| 14 升级条件 | 判据锚的用例跑红 ⇒ 登记 P 号、判"部分"，不修代码 |
| 15 规模 | 中，≈0.6 人日 |
| 16 熔断 | 同判据 2 次 FAIL ⇒ 停 |

## 三级任务
1. [ ] **S51.1 roadmap**（X-1、X-2）
2. [ ] **S51.2 REQ-NF-001**（X-3）
3. [ ] **S51.3 端口表**（X-4，D-V21-05）
4. [ ] **S51.4 REQ-F-004 判词**（X-5）
5. [ ] **S51.5 REQ-F-005 判词**
6. [ ] **S51.6** 门禁 + 三绿 + 07 记录
