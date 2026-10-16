# @ci 读数：STEP-01 第六/七批推送后的工作流结论（D-V6-02 认定口径）

认定方式：GitHub REST 原始响应（run id + head_sha + conclusion），存证 JSON 在同目录
`jobs_ci_3298c78.json`、`jobs_ci_aedba58.json`，本文件列结论。取数时刻 2026-10-16 13:0x +0800，
`CI-Windows` 对最新提交仍在跑，故那一条记 `in_progress` 而不是结论。

| head | 工作流 | run id | run number | status / conclusion |
|---|---|---|---|---|
| `3298c78`（第五轮返工） | CI | 38850751522 | 116 | completed / **success** |
| `3298c78` | Security | 38850751572 | 110 | completed / **success** |
| `3298c78` | CI-Windows | 38850751597 | 18 | completed / **failure** |
| `aedba58`（events 收编） | CI | 38851594496 | 117 | completed / **success** |
| `aedba58` | Security | 38851594569 | 111 | completed / **success** |
| `aedba58` | CI-Windows | 38851594576 | 19 | completed / **failure** |
| `11f596e`（台账 D-V8-01/02） | CI | 38852069893 | 118 | completed / **success** |
| `11f596e` | Security | 38852069703 | 112 | completed / **success** |
| `11f596e` | CI-Windows | 38852069754 | 20 | completed / **failure** |
| `4b91d6f`（发布 P-9） | CI | 38852413729 | 119 | completed / **success** |
| `4b91d6f` | Security | 38852413775 | 113 | completed / **success** |
| `4b91d6f` | CI-Windows | 38852413727 | 21 | completed / **failure** |
| `c966a34`（第六轮返工） | CI | 38854844793 | 120 | in_progress |
| `c966a34` | Security | 38854844911 | 114 | completed / **success** |
| `c966a34` | CI-Windows | 38854844817 | 22 | in_progress |

## CI（ubuntu）里与本批直接相关的两步

`aedba58` 的 run 38851594496 job 级读数（`jobs_ci_aedba58.json`）：

- `backend` → success，其中 **`Contract drift gate (gen_contracts --check)` → success**
  ——这是"三域产物 == 三域模型"在 `@ci` 上的直接证据，不只是我本机 `--check` 跑绿；
- `frontend` → success，其中 `Contracts package strict check (tsc --noEmit)` → success；
- `compose` / `compose-smoke` / `workflow-lint` → success。

## `CI-Windows` 的失败**不是本批引入的**（同点比较）

我拉了失败步名做前后对比（`.staging` 取数，命令可复跑）：

| run | head | 失败步 |
|---|---|---|
| 38848452563（number 17，本批**之前**的 983a356） | `983a356` | `Backend tests（连库用例在本平台会 skip，只记账不主张）` |
| 38852413727（number 21，本批**之后**的 4b91d6f） | `4b91d6f` | `Backend tests（连库用例在本平台会 skip，只记账不主张）` |

同一个步、同一处失败 ⇒ 这条红是 **U-23**（同步 `TestClient` 等 anyio blocking portal 的挂起面，
已发布为 P-5 等认领），不是我这几批改动造成的回归。我据此把本批的 Windows 面记为
**已知失败、外部残项**，不写成"CI 全绿"。

## 本机全量套件的处置（写清楚，免得被当成"未验证却说已验证"）

- 本机一次 `pytest -q` 全量跑了约 45 分钟无输出后被我把其中止（它管道到 `tail`，中间读数取不到，
  这是取证方式的缺陷，不是用例的结论）。第二次改成"输出直接写文件、不经管道"重跑，
  结果见本文件末尾的补记。
- **CI 日志的总数取不到**：`actions/runs/{id}/logs` 需要仓库 admin（实测返回
  `Must have admin rights to Repository`），当前凭据没有 ⇒ 我不引用任何"CI 上的 pass/skip 总数"，
  只主张 `conclusion=success`（D-V6-02 认定的口径就是 run id + head_sha + conclusion）。
- 本机跑过的有界子集：`pytest tests -q -k "contract or gen_contracts or schema"`
  → `131 passed, 1 skipped, 1059 deselected` `@win`；
  单文件 `pytest tests/test_collection_contract.py -q` → `127 passed` `@win`。
- 全量结论以 `@ci` 的 `backend` job 为准：`c966a34`（第六轮返工那一次提交）的
  run 38854844793 已 completed / **success** ⇒ 本批改动在 ubuntu 全量面上是绿的。

## 补记（后到读数，追加而不覆盖）

| head | 工作流 | run id | 结论 |
|---|---|---|---|
| `c966a34` | CI | 38854844793 | completed / **success**（backend job 含 `Contract drift gate (gen_contracts --check)`） |
| `c966a34` | Security | 38854844911 | completed / **success** |
| `c966a34` | CI-Windows | 38854844817 | 取数时 in_progress（不预告结论） |
| `2df0f88` | CI / Security / CI-Windows | 38855155404 / 38855155422 / 38855155401 | 取数时 in_progress |

