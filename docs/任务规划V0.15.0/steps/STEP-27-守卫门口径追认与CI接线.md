# STEP-27 守卫门口径追认与 CI 接线（D-V12-01～07 落地）

- 里程碑：M0 ｜ owner：执行 Agent-Guard ｜ 档位：sonnet（S27.3 安全判据改动需独立复核，复核用 opus）｜ 估算：7 项 × 0.15 = 1.05 人日
- 依赖：无（与 STEP-24/25 文件不相交，可并行）
- D-14：本卡 ≤2 轮，第 3 轮熔断（由本卡自己升级后的 rounds-check 执行）

## 允许修改
`scripts/guards.py`、`scripts/entry.py`、`scripts/check_entry_parity.py`、`Makefile`、`.github/workflows/ci.yml`（只限 backend job 追加门步骤）、`.gitattributes`（只追加一行）、`apps/api/tests/test_guard_rounds.py`、`apps/api/tests/test_secret_shape_gate.py`、`apps/api/tests/test_startup_probe_timeout.py`、`docs/04_engineering/conventions.md`、`docs/任务规划V0.13.0/steps/STEP-00P-*.md`（只追加一行）、`docs/06_validation/evidence/EVD-V15-27/**`、`docs/任务规划V0.15.0/07-执行过程记录.md`（只追加）
## 禁止修改
`apps/api/app/**`、`apps/web/**`、`.gitleaks.toml` 规则语义、`.gitleaksignore`、冻结契约

## L2 / L3 原子任务
| L3 | 内容 | 判据（先红后绿） | 证据 |
|---|---|---|---|
| S27.1 | `guards.py` 支持 `GUARD_BASE`：耦合门、敏感形门、轮次门的范围统一读它，未设退回 `origin/main` | 一次性仓库：`GUARD_BASE=<两提交前>` ⇒ 非空批读数；未设且追平 ⇒ rc=3（行为不变）；坏基线 ⇒ rc=1 并点名 | EVD-V15-27/s27_1.txt |
| S27.2 | `ci.yml` backend job 追加 `rounds-check` 与 `evidence-check`（`GUARD_BASE=${{ github.event.before }}`，PR 用 base sha；首推 `before` 全 0 时退回 `HEAD~1`）；CI 内 rc≠0 一律失败；gitleaks 步在该 job 以 `SKIP(covered by Security)` 记账 | @ci 交付提交上该步 rc=0；构造一个越轮次主题的临时分支 PR ⇒ 该步红（截图/日志入 EVD） | run id |
| S27.3 | D-V12-05：口令赋值形要求引号字面量；`_TOKEN` 后缀词界补抓；钉桩用例改新口径 | 31 条表达式引用不再命中（计数由脚本产生）；引号字面量真形状、`APP_TOKEN="…"` 命中；规则顺序/名称与对账用例一致；五轮变异 5/5 | EVD-V15-27/s27_3.md |
| S27.4 | D-V12-06：`.gitattributes` 追加 `*.docx binary` | @win `gitleaks detect` 输出不再含 `failed to scan`，rc=0；@win 非空批 `make evidence-check` rc=0；@linux 读数不变 | EVD-V15-27/s27_4.txt |
| S27.5 | D-V12-02：轮次门扩判据（中文数字一～二十、`S<卡号>.` 反推、跨卡只计主卡） | 反证：`第三轮`、`S1.3.2 第 3 轮`各红；`STEP-20/22/23` 一条主题只计 20；`background-3` 仍不计 | `test_guard_rounds.py` 新增用例 |
| S27.6 | D-V12-07：`_CHILD` 在 `import app.main` 之前把 `asyncio.run` 换成计时包装（进入起表、返回/抛出停表），自报 `SCHEMA_PROBE_SECONDS`；断言上界 7.0s、下界 3.0s；`PROBE_SECONDS`（整段 import）只报不判；不改 `apps/api/app/**` | 包装未生效（没有自报行）⇒ 红；变异（临时改 `main.py:187-188` 为 20 / 30.0，EVD 记录后逐字节还原）⇒ 红；并发 3 个 pytest 下复跑 ×3 不红（P-38 原失败条件） | EVD-V15-27/s27_6.txt |
| S27.7 | D-V12-04：`conventions.md` 写明“验收读数取非空批并标注批面”；00P 卡面验收①追加一行指向本卡 | docs-consistency rc=0；文本经子审查 | — |

## 完成定义
- 7 项全部有 EVD；`@ci` 三绿且 `head_sha` = 交付提交；CI backend job 新步骤可见且非 SKIP。
- 独立复核：S27.3（安全判据）与 S27.2（CI 门）各一轮，由 opus 子智能体做，结论写入 07。
