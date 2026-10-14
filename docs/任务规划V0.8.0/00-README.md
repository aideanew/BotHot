# BotHot 剩余任务规划 V0.8.0（基线 main@61358c3）

> 规划日期：2026-10-14｜仓库：https://github.com/aideanew/BotHot（main）｜项目名：AideanBotHot｜用户访问端口段：3200-3300
> 上一版：V0.7.0（基线 13acacc，已入库）。**规划方本轮未修改任何业务代码、测试、配置或契约源**，只写 `docs/任务规划V0.8.0/**`。

## 0. 一句话结论

**上一轮执行把 V0.7.0 的两张 M0 卡落了地（STEP-R0 短链缓存修复、STEP-16 告警默认开启），但主干仍是「双红」：CI 红在一条测试自身的断言写法（`str(stmt.compile())` 不展开绑定参数，断言却找字面值 `source_id = 'src-1'`——测试缺陷，不是产品缺陷）；Security 红在 gitleaks 8 处凭据形命中，其中 2 处是上一轮自己新增的（含 V0.7.0 规划文档 `06-入库与双端一致.md:46`）。**
**所以 V0.8.0 的立场是：先把门禁修回能说真话的状态（STEP-00C/00S，约 0.5 人日），再让 R0/16 拿到「真库全量 0 failed + CI 双绿」的读数才算 Done；其后核心价值集中在管理端 UI（14a/14b/15，由规划方亲自执行，待 D-V3-00 批准）与引擎能力面收敛（13），其余中低难卡发布给执行 Agent。**

## 1. 本版相对 V0.7.0 的变化（每条附证据，证据件在 `evidence/61358c3/`）

| # | 变化 | 证据 |
|---|---|---|
| 1 | 基线 13acacc → **61358c3**；其间 12 个提交，`apps/api/app` 仅改 3 文件（kb.py、alerting.py、system.py） | `static.txt` §HEAD / §app diff |
| 2 | **STEP-R0 状态：已实现、未验收**（kb.py 改为 external_id 精确回查；缺 PG 真库全量读数） | `static.txt`；`pytest_local_noPG.txt`（421 skip 均为 PG 不可达） |
| 3 | **STEP-16 状态：已实现、未验收**（compose/.env.example 默认 `ALERTING_ENABLED=true`，宽限 600s，冷却 1800s） | `static.txt` §alerting defaults |
| 4 | **CI 唯一失败定位到测试缺陷**：`tests/test_asset_fragment_guard.py:38` 用 `str(stmt.compile())`，`:142-144` 却断言字面值；CI 与本地同一条红 | `ci_security_61358c3.txt`；`pytest_local_noPG.txt` |
| 5 | **Security 唯一阻断项 = gitleaks 8 处**（pip-audit / pnpm-audit OK，Trivy 仅 MEDIUM 告警 mako 1.4.1→1.4.2）；仓内无 `.gitleaksignore` | `ci_security_61358c3.txt`；`gitleaks_summary.txt` |
| 6 | 上一版「证明脚本只降不升」指标被破：evidence `.py` 全量 8,383 → **9,519** 行 | `static.txt` §evidence py lines |
| 7 | 管理端 6 组端点前端消费者仍为 **0**；引擎 `NotImplementedError` 仍 16+1 处 | `static.txt` |
| 8 | 前端依赖已就绪（`apps/web/node_modules` 存在，pnpm 9.15.9 / Node 22），**上一轮「装不装依赖」的问题已失效**；UI 卡唯一剩余阻塞是 D-V3-00 批准 | 事实基线 F-08 |
| 9 | 新增 **STEP-00S**（Security 回绿，从 00C 拆出，所有权不同：`.gitleaksignore` + 文档打码 vs 测试文件） | 04 §1 |
| 10 | 新增规划自律门 **G-PLAN**：任何规划文档入库前必须 gitleaks 零新增（本版已自测） | 06 §2 |

## 2. 阅读顺序

| 文件 | 内容 |
|---|---|
| `01-事实基线与进度.md` | 快照、F-01…F-20 读数、已完成/已实现未验收/未开始三态、NOT_MEASURED |
| `02-需求拆解与辩证分析.md` | 需求 R-1…R-10 分级、辩证统一的四对矛盾、根因链、全方位设计（前端/后端/数据/交互/性能/配置/知识库/资源） |
| `03-裁决与契约.md` | 裁决表（BLOCKING/NON_BLOCKING）、六类机器契约状态与本版增量 |
| `04-剩余可执行大纲体系.md` | 27 STEP 总表、执行归属（规划方/执行 Agent）、DAG、所有权矩阵、档位成本、指标、里程碑、完成定义 |
| `05-风险自检与局限.md` | 风险、自检逐条、局限 |
| `06-入库与双端一致.md` | 落盘清单、入库前门、推送与双端一致自证 |
| `steps/STEP-*.md` | 每步一卡，16 字段，三级任务编号 `Sx.y.z` |
| `evidence/61358c3/` | 本会话机器读数（已对凭据形打码） |

## 3. 立即可做（按序）

1. **执行 Agent，今天**：STEP-00C（改测试 1 行 + 补断言）与 STEP-00S（打码 HEAD 中 2 处新命中 + `.gitleaksignore` 登记 6 处历史指纹 + mako 升级），两卡文件不重叠，可并行，合计约 0.5 人日。
2. **执行 Agent，紧随**：STEP-RV（R0/16 真库验收）——在有 PG/Redis 的机器跑全量，要求 `0 failed` 且 skip ≤ `SKIP_BASELINE=6`。
3. **用户裁决**：签 D-V3-00（UI 由规划方执行），签后规划方立即开 STEP-15 → 14b。
