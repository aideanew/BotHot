# EVD-V25-75 读数：`backend` 稳定性收口（P-159 派生）

> 卡面：`docs/任务规划V0.25.0/steps/STEP-75-backend非确定性.md`
> 结论只有三种取值，本卡取**第二种「已定位并修」**，理由见 §2。

## 1. 三次 push 的读数（`backend` 与 `e2e-real` 同表）

| # | head | CI run | `backend` | `e2e-real` job | `E2E` 步 | 备注 |
|---|---|---|---|---|---|---|
| 1 | `fe46206` | `40689977731` | **success** | failure | failure（⑥ strict mode） | 含 `df210b3` 的修复字节；P-159 的修在此首次生效 |
| 2 | `a1ef93a` | `40691241415` | **success** | failure | failure（同一 ⑥） | STEP-71（`stop_all` 收严） |
| 3 | `299b220` | `40692846396` | **success** | **success** | **success**（⑥ ✓ 476ms / ⑦ ✓ 403ms） | STEP-74（⑥ 定位器收窄） |

这三个 head 是**连续三次 push 的推送头**：`5002410..fe46206` → `fe46206..a1ef93a` → `a1ef93a..299b220`。
口径说明（避免把「连续」说过头）：git 历史里 `fe46206` 与 `a1ef93a` 之间还有 `ff6e9c9`（V0.25.0 §5 的双端一致文档批，纯文档），
它与 `a1ef93a` 在同一次 push 里推送，**没有自己的 run**（`GET /commits/ff6e9c9/check-runs` 返回空列表）；
同理 `df210b3` 与 `fe46206` 同批推送、也无自己的 run。⇒ 本表的三行是「每次 push 的推送头」的读数，不是「每个提交各一跑」。

## 2. 单一结论：**已定位并修**

| 判据（卡面 §2 的第二种取值） | 本版读数 |
|---|---|
| 失败用例原文名 | `tests/test_collection_contract.py::test_decision_log_tables_are_well_formed`（逐字见 `s75_failure_name.txt`） |
| 根因 | `docs/03_solution/decisions/decision-log.md:183` 的表格终止空行被 `7c15264` 追加 D-V24-01…12 时留在原地 ⇒ 表被劈成两张、其后 12 条裁决脱离表格 |
| 修复提交 | `df210b3`（2 文件 +1/−1：只删该空行 + 登 P-159） |
| 修复后 3 连绿 | `fe46206` / `a1ef93a` / `299b220` 的 `backend` 均 `success`（§1 表） |

**不是第三种「仍未定位但已隔离」**：失败用例名、根因、修复提交、修复后读数四样齐全，且本机纯函数复算能把同一句报错按原行号复现（`s75_hypotheses.md` §「为什么 flaky 被否证」）。

## 3. `e2e-real` 通道（S75.5）

原文见 `s75_e2e_real_status.txt`：`job=e2e-real status=completed conclusion=success`，`steps=20` 全部 success。
判据只要求 **≠ `skipped`**，实际拿到 `success`；`Stop stack` 仍 success，且日志逐字 `stopped backend pid=4084` / `stopped frontend pid=4432`。

⇒ 卡面 §5.6 的「若 `e2e-real` 仍 skipped ⇒ 结论只能写『`backend` 绿，通道未验证』」**未触发**：通道已验证。

## 4. 读数缺口（如实记，不影响结论）

| 缺口 | 事实 | 影响 |
|---|---|---|
| `df210b3` 没有自己的 CI run | 它与 `fe46206` 由同一次 push 推送；`GET /commits/df210b3/check-runs` 返回**空列表**。卡面 S75.1 假设「`df210b3` 会被单独推送、可单独读」 | 首读落在**含该修复字节的第一个提交** `fe46206`，读数等价；不改变结论，但卡面那句假设需要更正 |
| CI-Windows 的同名失败未重新下载复核 | 本卡只读了 ubuntu 侧 `40673181463`；Windows 侧 `40673181460` 的「同名同败」引自 P-159 登记行 | 影响「双平台确定性」这一辅证强度，不影响修与不修 |
| `df210b3` 那一跑的 `skip 门禁` 无运行时读数 | pytest 步失败后 job 直接终止，门那一步没执行 | H1 的读数不可得，已在 `s75_hypotheses.md` 写明 |
| 第三次绿同时带 STEP-74 的改动 | `299b220` = 74 的提交 | 三次绿里第三次并非「纯文档/无改动」样本；三次之间产品侧的变化只有 `apps/web/e2e/admin.spec.ts` 一行（e2e 断言），另有一处 `scripts/e2e/run_real_backend.sh`（STEP-71 的停机分支顺序，改后 CI 日志仍是 `stopped backend pid=3814` / `stopped frontend pid=4119`）；`apps/api/app/**` 零改动 ⇒ 三连绿不是靠改后端换来的 |

## 5. 本卡的禁止面核对

- 未改 `.github/workflows/ci.yml`（`git diff 5002410..299b220 -- .github` 为空）
- 未动 `apps/api/tests/test_ux_states_contract.py`
- 未加 retry / `--reruns`，未用 `-k "not …"` 摘用例
- 未改 `apps/api/app/**`
