---
id: PLAN-V0.4.0
title: BotHot 采集域剩余任务规划 V0.4.0
baseline: main@b45777a（2026-10-12 22:27 +08:00）
previous: docs/任务规划V0.3.0（基线 4afaedd）
planned_at: 2026-10-13（Asia/Shanghai）
status: 规划产物；未写入仓库；未改任何业务代码
---

# BotHot 采集域剩余任务规划 V0.4.0

## 1. 一页结论
1. **上一步（STEP-00R + STEP-02 S2.1.1–S2.1.3）功能上是对的**：连库全量从 1 failed 变为 **1037 passed / 0 failed**，有代理和无代理两种环境下 1042 条用例的结论逐条一致；`parse_wechat_url` 覆盖率 100%。
2. **但 CI 连续红了 13 次**（Security 同样 13 次），没有人处理。这条本轮**重新实测**过而不是抄旧账：
   `curl -x http://127.0.0.1:10808 https://api.github.com/repos/aideanew/BotHot/actions/runs?per_page=60`，
   筛 `name=CI && event=push` 从 HEAD 往回数到第一个非 failure，得 **13 连红**，区间
   `5c8552b`（2026-10-12T11:23:30Z）→ `d80eeaf`（2026-10-13T04:43:13Z），前一条 `86269a2` 是 success。
   本包初稿写的「10 次」是**当时**的数（其后又推了 3 次），起红的 sha 没有记错；这里把口径与复测命令一起留下，
   是为了让「红了几次」这种话以后可以直接重跑而不是靠回忆。
   - CI 红是因为 ruff 报了 3×I001 + 1×E501，都在本轮新增的测试文件里；
   - Security 红是因为 gitleaks 命中证明脚本里的 5 处假 DSN `x:y@`；
   - 根因是本地门禁 g24 对这两类规则假绿，执行机又没有真实的 ruff/gitleaks。
   - 修法已在临时克隆里验证过：ruff 和 gitleaks 都回绿，相关测试 49 passed。整理为**新增的 STEP-00C**，排在所有工作之前。
   - **一条必须写明的连带风险**（本轮取自 `d80eeaf` 那次跑的 job 明细）：CI 里只有 `backend` job 的
     `Lint (ruff)` 这一步是 failure，其后 **7 步全是 skipped** ——mypy、连库 pytest、e2e 已经 13 次推送没执行过了。
     所以 ruff 回绿不等于 CI 回绿；STEP-00C 的 S0C.4 就是为这一步预留的（先修 lint，再看真红在哪）。
     `compose` / `compose-smoke` / `frontend` / `workflow-lint` 四个 job 目前都是 success。
3. **采集 P0 在 b45777a 全部仍然复现**（四个探针）。P-3 在 S2.1.3 之后**机制变了，症状没变**：碰撞从源层下移到资产层，只有 S2.2 的规范键能关闭。所以 D-V2-01 仍是 M1 关键路径上唯一的人工卡点。
4. 剩余 86 个原子任务，约 15 人日；到 M1 约 7.5 人日。（本轮 +1：S0C.2.4，落库切分实测出来的收尾刀，不单列工时。）

## 2. 目录
| 文件 | 内容 |
|---|---|
| `01-事实基线与上一步复核.md` | 快照、区间 10 个提交、F-25…F-36、上一步的对与错 |
| `02-需求基线复核.md` | V0.3.0 全文 + §7 增补（M-09、K-07、U-09/U-10） |
| `03-契约冻结包与数据模型.md` | V0.3.0 全文 + §9 增补（Identity 解析层已落地、D-13、键约束） |
| `04-剩余任务大纲体系.md` | 执行账、切片、DAG、并行判定、所有权、预算、指标、风险、裁决、完成定义、四级大纲 |
| `05-自检与局限.md` | §12 自检、落盘清单与**落库切分（§2.1）**、局限、启动顺序 |
| `steps/STEP-00C-…` | **新增**：CI 回绿与门禁对齐 |
| `steps/STEP-00R、STEP-02` | 头部新增“V0.4.0 复核结论”（优先于原文） |
| `steps/STEP-07` | 审计增 `'s'` 旧源项 |
| `steps/其余` | 同 V0.3.0 |
| `contracts/` | 契约冻结稿（未改） |
| `evidence/b45777a/` | 本轮全部实跑输出 + 模拟修复 patch |

## 3. 执行账（STEP 级）
| STEP | 状态 | 剩余原子任务 | 下一动作 |
|---|---|---|---|
| **00C** CI 回绿 | ⬜ 新 | 10 | **最先做**；S0C.1/2.1/3 不等拍板，只有 S0C.2.2 等 D-12 |
| 00R 测试基线 | 🟡 H-1/H-2/H-4 本轮实跑闭合 | 3 | docker 人工项；D-11 两项 |
| 01 契约冻结 | ⬜ | 7 | ADR-0011 草案先行 |
| 02 文章身份 | 🟡 3/12 | 9 | S2.1.4 去 LIKE 可立即做 |
| 03–12 | ⬜ | 57 | 按 DAG |

## 4. 待你拍板（按紧急度）
| ID | 问题 | 建议 | 卡住什么 |
|---|---|---|---|
| **D-12** | 历史 5 处假 DSN 怎么豁免 | A：`.gitleaksignore` 逐指纹（最窄） | 只卡 S0C.2.2 一个原子任务 + Security 回绿；**CI 回绿不依赖它**（本轮实测收窄，见 §7） |
| **D-V2-01** | 文章键格式 | A：带 `b:/s:/h:` 前缀 | M1 关键路径（S2.2、03.3.3、04） |
| D-14 | 复审轮次上限 / 执行机补 venv | ≤2 轮；补 venv | 交付节奏 |
| D-13 | 非微信域名是否走微信解析 | 不改解析，ADR 里按 host 分支 | ADR-0011 |
| D-V2-02 | 清单对齐 | article_key 列 + manifest_id + 状态机 | STEP-04 |
| D-09 | 契约唯一源 | Pydantic → 生成 | STEP-01.3 |
| D-11 | 授权改 ci.yml | 授权（仅注释 + stdlib job） | 00R 两项、06.3 |
| D-V2-03…06 | RSS 外链 / 路由降级 / 兜底预算 / 生产回填 | 见 04 §4.8 | M2 |

## 5. 第一刀
STEP-00C → （双绿后并行）STEP-00R 残项 ∥ STEP-01 ∥ STEP-02.1.4/2.1.5 → D-V2-01 拍板 → STEP-02.2/2.3 ∥ STEP-03 → STEP-04 → STEP-05 ∥ STEP-11 → STEP-06（M1）。

## 6. 复现本包结论
下面四条命令**都要 uv/依赖/PG**，即都要在沙箱档跑（本机 win32 连 pytest 的收集都过不了，见 §7）；
每条后面的「沙箱实测」是当时的读数出处，不是保证你在同样的机器上。
```bash
git checkout b45777a
cd apps/api && uv run ruff check app tests            # 期望 4 errors（CI 红因）｜沙箱实测 ruff_0.12.12_b45777a.txt
gitleaks detect --source . --config .gitleaks.toml --log-opts=main --redact   # 期望 5 leaks｜沙箱实测 gitleaks_main_b45777a.txt
AIDEANBOT_TEST_PG_DSN=postgresql+psycopg://bothot:bothot_ci@localhost:5547/bothot_test \
  uv run pytest tests -q -rfs                         # 期望 1037 passed / 5 skipped｜沙箱实测（有代理 56.05s；无代理 1036/6、27.63s）
```

## 7. 两台机器分工（本轮补，因为本包混用了它们）

写「本地实测」四个字时必须同时说清是哪台机器——本包的读数来自两台，混起来读会把「全绿」的门槛读低一档：

| 档 | 机器 | 有什么 | 本包里由它产出的读数 |
|---|---|---|---|
| 沙箱 | aarch64 Linux（`/workspace/work/BotHot`） | uv + 依赖 + PG + gitleaks/ruff 二进制 | b45777a 两次全量（56.05s / 27.63s）、`probes_*`、`junit_*`、`gitleaks_main_b45777a.txt`、`evidence_check_b45777a.txt` |
| win32 执行机 | 本机，Python 3.11.9 | 只有 stdlib + pytest 9.1.1 **壳**（无 sqlalchemy 等 app 依赖） | `ruff` 形状对照（E501 宽度 `e501_calibrate.py`、I001 互斥 `g24_vs_ruff_I001.py`）、`STEP-00C_ruff_tests.patch` 切分与 `git apply --check`、`precommit_gitleaks_scan.txt`、EVD-V2-02 的 A–N 驱动留档 |

本轮把这件事量化了（读数 `evidence/win32_pytest_collect_20261013.txt`）：win32 上跑
`python -m pytest tests --collect-only -q -p no:cacheprovider` **0.73 秒**死在 `tests/conftest.py:33` 的
`ModuleNotFoundError: No module named 'sqlalchemy'`，rc=4，连 `collected N items` 都拿不到。⇒ 两个后果：

1. **「本机全绿」在 win32 上无从证伪**——它不是「测过没问题」，而是「测不了」。这正是 STEP-00R 与 STEP-02
   反复用 stdlib/AST 判据搭证明层的原因，也是本包必须把每条命令标档的原因。
2. **S0C.3.3（执行机补 `uv sync --extra dev`）的优先级要升**：补上之前，S0C.1 的验收
   （`uv run ruff check app tests`）与 S0C.2.1 的验收（`prove_net_isolation.py --self-test`）在 win32 上
   只能靠「形状等价」的替身判据（本轮已备两件：`e501_calibrate.py`、`g24_vs_ruff_I001.py`），
   替身判据覆盖不到 ruff 的其它规则 —— 这一点必须让下一个执行者知道，别把替身当终判。
