# BotHot 剩余任务规划 V0.5.0（基线 main@65f508b）

> 规划日期：2026-10-13 14:10–14:40 CST｜仓库：github.com/aideanew/BotHot｜规划方未改仓库任何文件。
> 上一版：V0.4.0（基线 b45777a，已于 9a0a20a 以“第 1 批”入库到 `docs/任务规划V0.4.0/`）。

## 0. 一句话结论

**b45777a → 65f508b 的 8 个提交，业务代码 0 行、测试代码 0 行、CI 配置 0 行变化；新增约 3,650 行证明脚本/证据文本和约 4,900 行规划文档。四个采集 P0 在 65f508b 原样复现，CI 与 Security 已连续 15 次失败，后端测试在 CI 上已 15 次没有运行。**
V0.5.0 不再新增“复核层”，而是把剩余工作改造成**可以直接开工、由测试判定完成**的执行序列，并用“默认裁决 + 复审熔断”解开卡住主线的两个流程瓶颈。

## 1. 本版相对 V0.4.0 的变化

| # | 变化 | 理由（证据） |
|---|---|---|
| 1 | STEP-00C 修复包**已在 65f508b 上实测回绿**（ruff 0 错、gitleaks git 模式 0 命中、证明脚本 24/0），可原样 `git apply`；**该 patch 本身按第 2 批口径暂不入库**（见 05 §5） | `gitleaks_65f508b.txt` [C]（patch 只在工作树，路径见 §3 表末行） |
| 2 | gitleaks 历史命中从 5 条更正为 **6 条**（de78125 新增 `out_evidence_check.txt:137`） | `gitleaks_65f508b.txt` [A] |
| 3 | 新增 **STEP-00G 执行治理**：默认裁决生效机制、复审 ≤2 轮熔断、证明脚本冻结、AGENTS.md 不实陈述先打标 | 01 §3：S2.1.3 已到第 10 轮复审；7/11 个待裁决项无人拍板 |
| 4 | 新增 **STEP-00T 证明判据 pytest 化**：BD-1…16、NR-14/15/17 迁入 `apps/api/tests`，脚本归档不删除 | 01 §2.3：4,670 行证明脚本不在 CI 回归网内 |
| 5 | STEP-00C 增 **S0C.3 CI 下游首跑预演**：ruff 修好后 mypy/alembic/契约/文档/pytest+skip 门禁 7 步将 15 次以来首次运行；本地 CI 等价链已全过，但 skip=6 恰等于 `SKIP_BASELINE=6`，零余量 | `gates_65f508b.txt`、`junit_65f508b.xml`（skipped=6） |
| 6 | 关键路径重排：M1 = 00C → 00G → {01 ∥ 02.1 ∥ 00T} → 02.2 → {03 ∥ 04 前半} → 04 → 05 → 06 | 04 §4.3 |
| 7 | 每张 STEP 卡统一为：目标与可证伪验收 / 证据链 / 执行逻辑穿透 / 原子任务（三~四级）/ 测试设计 / 停止与回滚 / 交付证据 | 便于独立验证者只看卡判 PASS/FAIL |

## 2. 规模

- **16 个 STEP，剩余 109 个三级原子任务**（其中 👤 人工/裁决 11 个），按 04 §4.6 估算约 19 人日工作量（不含生产窗口与外部等待）。
- 已完成并移出剩余表：STEP-00R 的 8 个、STEP-02 的 S2.1.1–S2.1.3（共 11 个，口径同 V0.4.0）。
- **M0（门禁回绿 + 治理）约 0.75 人日；M1（核心采集正确性 + 测试闭环）关键路径约 7 人日、工作量约 10 人日**。

## 3. 阅读顺序

| 文件 | 内容 |
|---|---|
| `01-事实基线与上一步复核.md` | 65f508b 实测读数；上一步做了什么/没做什么；对用户“历史任务评价”的逐条核验（同意/更正） |
| `02-需求拆解与根因穿透.md` | 本次需求拆解；四个 P0 的调用链穿透；流程失衡的根因；辩证取舍 |
| `03-裁决默认值与契约.md` | 11 个待裁决项的默认值与生效规则；ADR-0011 键格式规格；清单↔资产对齐契约；行契约 |
| `04-剩余可执行大纲体系.md` | 编号规则、STEP 总表、完整三~四级大纲、DAG、并行矩阵、所有权、里程碑、完成定义、成本 |
| `05-风险自检与局限.md` | 风险/未决、规划自检表、本版局限、入库切分（第 1/2 批口径） |
| `06-执行记录.md` | 本会话的执行日志：一个提交一行、双端一致的复现方法、交接口与环境事实 |
| `steps/STEP-*.md` | 16 张任务书，一步一卡 |
| `contracts/` | 采集域契约冻结稿（沿用 V0.4.0，未改字段） |
| `evidence/65f508b/` | 本版全部机器读数（pytest/junit/探针/门禁/ruff/gitleaks/CI 运行/入库前敏感形召回器）；`STEP-00C_simulated_65f508b.patch` 与 `ci_runs_65f508b.txt` 同目录，但前者**第 1 批不入库**，理由与第 2 批条件见 `05` §5 |

## 4. 立即可做的三件事（不需要任何新裁决）

1. 落地 STEP-00C：把 `gitleaks_65f508b.txt` [C] 描述的那组改动（ruff 4 处 + 两文件的 `x:y@` 占位化
   + `.gitleaksignore` 逐指纹）做成一个提交并推送，拿到 CI/Security 双绿 run id。
   规划方留的那份 `STEP-00C_simulated_65f508b.patch` 在第 1 批里**没有入库**（它自带会被 Security
   门禁检出的邻接形，见 `05` §5），所以执行方按 [C] 重做即可——真做完之后，那个提交的 diff
   就是第 2 批要存档的东西。
2. 执行 S2.1.4：删除 `kb.py:354-361` 的 `Source.url.like(f"%{article_key}%")` 兜底，关闭 P-4 的 500 路径（不依赖 D-V2-01）。
3. 签署或默认生效 D-V2-01（建议 A：`b:/s:/h:` 前缀），解锁 STEP-02.2 → 03 → 04 主线。

## 5. 复现基线读数的命令（沙箱 aarch64，PG16@5547）

```bash
export AIDEANBOT_TEST_PG_DSN=postgresql+psycopg://postgres@127.0.0.1:5547/bothot_test
export DATABASE_URL=$AIDEANBOT_TEST_PG_DSN
cd apps/api && .venv/bin/python -m alembic upgrade head
.venv/bin/python -m pytest -q --cov=app --junitxml=junit.xml      # 1036 passed / 6 skipped / 0 failed / 79%
.venv/bin/ruff check app tests                                    # 4 errors（3×I001 + 1×E501）
cd ../.. && gitleaks detect --source . --config .gitleaks.toml    # main 历史 6 条
```
