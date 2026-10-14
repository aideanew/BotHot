# BotHot 剩余任务规划 V0.6.0（基线 main@a9b194d）

> 规划日期：2026-10-14 10:33–11:10 CST｜仓库：github.com/aideanew/BotHot｜规划方没有改仓库任何文件（修复只在临时 worktree 里模拟）。
> 上一版：V0.5.0（基线 65f508b，已于 d028075 以“第 1 批”入库到 `docs/任务规划V0.5.0/`）。

## 0. 一句话结论

**上一步做成了 S2.1.4/S2.1.5（078dc30）：P-4 关闭，片段守卫上线。但同一个提交删掉的 LIKE 兜底还负责“无参短链找回页面 biz 源”，main 上现在有 1 个真实回归（全量 1044 passed / 1 failed）。CI 的 pytest 已经 22 次没跑，所以没人看到。**
V0.6.0 把“修回归 + CI 回绿”合成 M0 的同一个 PR（补丁已在 a9b194d 实测：1045/5/0、ruff 0、gitleaks 0），然后按 V0.5.0 的主线继续：规范键（P-3）→ 行契约（P-1）→ 清单对齐（P-2）→ 告警 → E2E。

## 1. 本版相对 V0.5.0 的变化

| # | 变化 | 理由（证据） |
|---|---|---|
| 1 | **新增 STEP-R0 短链缓存回归修复**（M0 最高优先，7 个原子任务） | 01 F-55/F-56：test_be02_engine_routing.py:301 在 a9b194d 红、在 65f508b 绿 |
| 2 | STEP-02 改为“文章身份规范键-P3”：S2.1.4/S2.1.5 移出剩余表；P-3 的冒名走的是 biz 锚 + 等值 `"s"`，锚定层补丁修不了，只有换键能修 | 02 §2.0/§2.1；probes_a9b194d.txt |
| 3 | STEP-00C 合并补丁重做：ruff 错 4 → 5（新增 test_asset_fragment_guard.py:104 E501），与 R0 同 PR；新增 S0C.6 pre-commit 防漂移 | ruff_a9b194d.txt；F-63 |
| 4 | STEP-00G 冻结基线 4,670 → 6,801 行；新增 S0G.5“证明台不能替代真实测试” | F-53；078dc30 反例 |
| 5 | 完成定义加一条：假会话/AST 证明台 PASS 不算 Done | 04 §4.9 |
| 6 | 基线表加 a9b194d 一列：B-4 已达标（P-4 关闭），B-5 退步（0 → 1 failed），B-7 15 → 22 | 04 §4.7 |
| 7 | gitleaks 取指纹必须带 `--log-opts=origin/main`（否则会混进未合并分支的 798f263×3） | gitleaks_a9b194d.txt |

## 2. 规模

- **17 个 STEP，剩余 116 个三级原子任务**（👤 12 个），约 19.25 人日（不含生产窗口与外部等待）。
- 累计已完成并移出剩余表：13 个（STEP-00R 8、STEP-02 S2.1.1–S2.1.5）。
- **M0（R0 + 00C + 00G）约 1 人日；M1 关键路径约 7.25 人日、工作量约 10 人日。**

## 3. 阅读顺序

| 文件 | 内容 |
|---|---|
| `01-事实基线与上一步复核.md` | a9b194d 实测读数；上一步做了什么/没做什么；回归二分；对 V0.5.0 结论的复核 |
| `02-需求拆解与根因穿透.md` | 本次需求拆解；§2.0 回归根因；P-3/P-2/P-1 的调用链；测试为什么没抓住；取舍 |
| `03-裁决默认值与契约.md` | 11 个待裁决项的默认值与生效规则（仍 0 项已签）；ADR-0011 键格式；对齐契约；行契约 |
| `04-剩余可执行大纲体系.md` | 编号规则、STEP 总表、完整三~四级大纲、DAG、并行矩阵、所有权、基线指标、里程碑、完成定义、日历 |
| `05-风险自检与局限.md` | 风险、未决、规划自检、局限 |
| `steps/STEP-*.md` | 17 张任务书，一步一卡（STEP-R0 排在最前面执行） |
| `contracts/` | 采集域契约冻结稿（未改字段） |
| `evidence/a9b194d/` | 本版全部机器读数 + 两份模拟补丁 |

## 4. 立即可做的三件事（不需要任何新裁决）

1. 在 a9b194d 上 `git apply evidence/a9b194d/STEP-R0+00C_combined_simulated_a9b194d.patch`，本地跑 `ruff check app tests`、全量 pytest（必须 0 failed）、`gitleaks detect`，然后推送，拿到 CI + Security 双绿的 run id（STEP-R0 + STEP-00C）。
2. 建 `docs/03_solution/decisions/decision-log.md`，按 03 §1 登记 11 项默认值，开始 24 小时计时（STEP-00G）。
3. D-V2-01 生效后开 STEP-01 → STEP-02 S2.2（规范键，关闭 P-3）。

> ⚠ 两份 `.patch` 文件本身含有被删除的占位 DSN 行，**不要提交进仓库**（与 V0.5.0 第 2 批同口径），只用来 `git apply`。

## 5. 复现基线读数的命令（沙箱 aarch64，PG16@5547）

```bash
export AIDEANBOT_TEST_PG_DSN=postgresql+psycopg://postgres@127.0.0.1:5547/bothot_test
export DATABASE_URL=$AIDEANBOT_TEST_PG_DSN
cd apps/api && .venv/bin/python -m alembic upgrade head
.venv/bin/python -m pytest tests/ -q -rs --cov=app --junitxml=junit.xml   # a9b194d：1 failed / 1044 passed / 5 skipped / 79%
.venv/bin/python -m pytest tests/test_be02_engine_routing.py -q -k short_link_second   # 回归哨兵
.venv/bin/ruff check app tests                                             # 5 errors（3×I001 + 2×E501）
cd ../.. && gitleaks git --log-opts=origin/main --config .gitleaks.toml .  # main 历史 6 条
```
