# STEP-75：`backend` job 稳定性收口（P-159 派生）

## 1. 归属

- 所属切片：**P-A″**（验收通道恢复）
- 来源需求：`04` §1 M-2；台账 **P-159**（`5002410` 的确定性红，`df210b3` 已修）
- 来源方案：**D-V25-03**（含通道约束）、`01` F-4/F-5
- 执行者：执行助手

## 2. 目标

给出「`backend` 是否稳定绿」的**单一结论**，且 `e2e-real` 不再因 `needs` 连坐被 `skipped`。

结论只允许三种取值，且必须各自带读数：

| 取值 | 判据 |
|---|---|
| **绿** | 连续 3 次 push 的 `backend` conclusion 均 `success` |
| **已定位并修** | 失败用例原文名 + 根因 + 修复提交 + 修复后 3 连绿 |
| **仍未定位但已隔离** | 失败用例原文名 + 3 条假设的证伪读数 + 隔离手段 + 剩下的读数缺口 |

**不允许**的第四种：「rerun 转绿了，所以好了」。

## 3. 输入

- CI 读数（规划方快照时点，`5002410`）：
  - `40673181463`（`5002410`）`backend` **failure**
  - `40671439614`（`a8f756b`）`backend` **failure**
  - `40668413325`（`3c4138d`）`backend` **success**
- 已知失败用例（**F-4 实测，非猜测**）：`tests/test_collection_contract.py::test_decision_log_tables_are_well_formed`，
  在 `40673181463`（ubuntu `backend`）与 `40673181460`（CI-Windows）**同名**出现
- 根因：`docs/03_solution/decisions/decision-log.md:183` 原为空行（表格终止符），`7c15264` 把 D-V24-01～12 接在其后 ⇒ 表被劈成两张
- 已落地修复：**`df210b3`**（2 文件 +1/−1，只删该空行并登 P-159）
- 相关代码：`.github/workflows/ci.yml`（`backend` job 与 `:546` 的 `needs: [backend, frontend]`）
- 契约约束（本卡确立）：**`e2e-real` 的读数只在 `backend=success` 时存在**（D-V25-03 第二句）
- 前置任务：无（`df210b3` 已提交）

## 4. 输出

- 修改：**默认不改任何文件**。仅在 S75.3 判定为「本仓测试缺陷」时，允许改 `apps/api/tests/**`（除 `test_ux_states_contract.py`）或 `apps/api/pyproject.toml` 的 pytest 配置
- 新增：`docs/06_validation/evidence/EVD-V25-75/`
  - `s75_readings.md`（三次 push 的 conclusion 表 + 单一结论）
  - `s75_failure_name.txt`（失败用例原文名，逐字）
  - `s75_hypotheses.md`（H1/H2/H3 逐条证伪）
  - `s75_e2e_real_status.txt`（`e2e-real` 的 job status 与 steps 数）

## 5. Execution Steps

> 执行记录（V0.25.0 批 1，2026-10-28）：S75.1 的读法有一处偏离卡面假设——`df210b3` 与 `fe46206` 同批推送，**没有自己的 CI run**（`GET /commits/df210b3/check-runs` 为空），故首读落在含该修复字节的第一个提交 `fe46206`（`backend`=success），按 S75.1 的 `success ⇒ 跳 S75.4` 分支走「已定位并修」，S75.2/S75.3 未进入（三条假设各自的读数缺口见 `EVD-V25-75/s75_hypotheses.md`）。三连绿 = `fe46206` / `a1ef93a` / `299b220`；`e2e-real` 在第三次 push 上 `completed/success`（20 步全绿）。S75.7 等本提交自己的 @ci。
>
1. [x] **S75.1** 读 `df210b3` 的 `backend` 结论（推送后第一次）。
   - `success` ⇒ 跳到 S75.4（本卡的「已定位并修」路径，F-4 的根因已在手）。
   - `failure` ⇒ **先取失败用例原文名**，落 `s75_failure_name.txt`。取法见 §7 第 2 条（run 级 `/logs` zip，**job 级日志 403**）。
   - **不许**在这一步直接 rerun——rerun 不改字节，对确定性红无效（D-V25-03 备选甲已否）。
2. [ ] **S75.2** 若仍红，按三条假设**逐条证伪**（每条都要有读数，不许写「看起来不像」）——**条件未成立**（S75.1 走 `success` 分支，未进入；三条假设各自的读数缺口见 `EVD-V25-75/s75_hypotheses.md`）：

   | 假设 | 内容 | 判据 | 若成立怎么修 |
   |---|---|---|---|
   | **H1** | skip 门阈值：跳过量波动 | `skip 门禁` 输出的 `total_skipped` / `baseline` / `pg_unreachable` 三值 | 只抬该 job 的 baseline 常量到**实测值**，不加余量（D-V10-11） |
   | **H2** | 覆盖率边界：`88.9x%` 邻域抖动 | `Total coverage:` 与模块门的 `✅/❌` | 只调该模块阈值或补该用例，**不放宽全局 gate**（P-104 同族） |
   | **H3** | 时间或网络依赖：TZ、外部域名 | 失败用例名里是否含时间/网络语义；红是否只在 ubuntu 或只在 Windows | 只修该用例的时钟/网络隔离，不加 retry |

3. [ ] **S75.3** 若命中 H1/H2/H3 且可修：只改**该用例**或**该阈值**，然后回到 S75.1——**条件未成立**（未进入 S75.2）。
4. [x] **S75.4** 取「连续 3 次 push 的 `backend` conclusion」：`df210b3` 与随后两次含本版改动的提交。
5. [x] **S75.5** 取 `e2e-real` 的 job `status`/`conclusion`：必须 **≠ `skipped`**（`failure` 也可接受——那是 74/60 的读数面，不是本卡的判据）。
6. [x] **S75.6** 写 `s75_readings.md`：结论 + 三次读数表 + 缺口（若 `e2e-real` 仍 skipped ⇒ 结论只能写「`backend` 绿，通道未验证」）。
7. [x] 提交（卡面勾选 + 证据同提交），推送，读 `@ci` 确认本轮改动没引入新红。

## 6. 验收标准

- [ ] `backend` 连续 3 次 `success`（三次都要贴 run id + conclusion）
- [ ] `e2e-real` 的 `conclusion` **≠ `skipped`**（`completed`/`failure` 都算通过本卡判据）
- [ ] 若走过 S75.2：证据含失败用例**原文名**（逐字），不含「pytest 失败」这类概称
- [ ] 若走了 rerun：必须写明「rerun 是兜底，且 rerun 前后字节相同」（附 `git diff` 为空）
- [ ] 未改 `.github/workflows/ci.yml` 的 `needs` / `continue-on-error`（`git diff` 该两行为空）
- [ ] 未动 `apps/api/tests/test_ux_states_contract.py`

## 7. 验证命令

```bash
# 1) 三次 conclusion（无 gh，REST；token 只在进程内用，不回显）
cd /d/Code/AideanBotHot && python -X utf8 "$TEMP/s59/dump_fail_5002410.py" <full-40-char-sha>

# 2) 失败用例原文名（run 级 logs zip；job 级 /actions/jobs/{id}/logs 需管理员 ⇒ 403）
#    现成脚本：$TEMP/s59/read_ci_5002410.py（按 sha 取 run → 下载 logs zip → grep FAILED）

# 3) 直达复现（本机，需 PG@5547；无库则用 -k 只跑该用例的纯文件部分）
cd apps/api && ../.venv/Scripts/python.exe -X utf8 -m pytest tests/test_collection_contract.py -q
```

## 8. 证据路径

`docs/06_validation/evidence/EVD-V25-75/`

## 9. 允许修改

- `apps/api/tests/**`（**显式排除** `apps/api/tests/test_ux_states_contract.py`——它归 STEP-68）
- `apps/api/pyproject.toml` 的 **pytest 配置节**（`addopts` / 覆盖率相关阈值项）
- `docs/06_validation/evidence/EVD-V25-75/**`

## 10. 禁止修改

- `.github/workflows/ci.yml` 的任何行（尤其 `needs` 与 `continue-on-error`，D-V23-20）
- `apps/api/tests/test_ux_states_contract.py`（STEP-68 独占）
- `packages/contracts/**`、`docs/任务规划V0.12.0/contracts/**`
- `apps/api/app/**`（业务代码）——本卡只收「测试与阈值」，不改产品行为
- 不得给 CI 加 retry / `--reruns` 来「消红」
- 不得用 `-k "not <失败用例>"` 或 `deselect` 把失败用例摘掉

## 11. 依赖与阻塞

- Depends on：无（`df210b3` 已在本地，未推送）
- Blocks：**STEP-60**（`e2e-real` 被 `needs` 连坐 ⇒ 60 拿不到读数）
- 阻塞条件：若定位到的失败用例是 `test_ux_states_contract.py` ⇒ **停下**，改串行于 STEP-68 之后（避免抢文件）
- 阻塞条件：取不到 job 日志且 run 级 zip 也取不到 ⇒ 结论写「仍未定位但已隔离」+ 缺口，不要写「修好了」

## 12. 建议执行档位

**sonnet**（D-V25-06）。理由：读 + 定位 + 单点修；取日志是工具问题（已解），不是推理问题。

## 13. 升级条件

- 两次 rerun 结论互相矛盾（一次绿一次红）且日志无共同失败点 ⇒ 升级 **opus** 做并发/资源类根因分析
- 失败用例名指向 `apps/api/app/**` 的缺陷（不是测试自身） ⇒ 升级并交回规划方开新卡（本卡禁止改业务代码）

## 14. 预估规模

中，**≈0.5 人日**，其中大部分是等 CI（每次 push 的 `backend` 约 6 分钟，3 次 ≈ 20 分钟串行）。

## 15. 熔断

同一判据 2 轮未过 ⇒ 停手，登 P 号交回（D-14）。

## 16. 交接物

`EVD-V25-75/` 要能让一周后的人只看三件事就判断本卡是否真交付：
① 三次 run id + `backend` conclusion；② 若有失败，失败用例**原文名**与根因；③ `e2e-real` 的 `conclusion` 不再是 `skipped`。
