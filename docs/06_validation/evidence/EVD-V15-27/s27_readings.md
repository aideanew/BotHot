# STEP-27 读数汇总（S27.1–S27.7，第 1 轮）

- 卡：`docs/任务规划V0.15.0/steps/STEP-27-守卫门口径追认与CI接线.md`
- 批面：`8135f1a..HEAD`（交付提交）+ 索引面 25 个路径（提交前跑门时）
- 机器：@win32 / Python 3.12.10（`apps/api/.venv`）/ ruff 0.12.12 / mypy / gitleaks 8.21.2
- 未测项（沙箱无 PostgreSQL、无 docker）：`alembic upgrade head`、迁移往返、连库 pytest。
  这些步在 CI 上有 PG service，本机读数一律记 **未测**，不用任何拼接读数冒充。

## 一、逐项读数

| L3 | 结论 | 关键读数 | 证据 |
|---|---|---|---|
| S27.1 | ✅ 已确认 | `GUARD_BASE=两提交前` rc=0 / 未设且追平 rc=3 / 坏基线 rc=1 并点名 ⇒ 3/3 与期望一致 | `s27_1.txt` + `s27_1_probe.py` |
| S27.2 | ✅ 已确认（CI 读数待 @ci 回填） | YAML 解析通过；backend 13 步，末步即新增门；checkout `fetch-depth: 0`；两条门不短路、rc≠0（含 3）即失败 | `s27_2.txt` |
| S27.3 | ✅ 已确认（一处卡面数字待裁决） | 先红 41 failed/106 passed；绿 146 passed（两门用例）；源码面 52→36、全仓 70→54、少报 26、新增 10、含值位字面量的行少报 0；变异 5/5 全红且还原逐字节一致 | `s27_3.md`/`s27_red.txt`/`s27_3.txt`/`s27_3_mutation.txt` |
| S27.4 | ✅ 已确认 | A/B 同提交同克隆：修复前 `failed to scan`、2.72s"完成"却 rc=0；修复后 270 commits scanned / failed=0 / rc=0 | `s27_4.txt` |
| S27.5 | ✅ 已确认 | 五条反证全对：`第三轮` 红(00T)、`S1.3.2 第 3 轮` 红(01)、跨卡只计主卡 20、`background-3` 不计、`@ci` 记录不计 | `s27_5.txt` + `s27_5_rounds.py` |
| S27.6 | ✅ 已确认 | 绿态 1 passed 8.37s；变异（超时 20/30.0）⇒ 20.02s > 7.0s 红；去包装 ⇒ `SCHEMA_PROBE_SECONDS none` 红；并发 ×3 不红 | `s27_6.txt`/`s27_6_mutation.txt`/`s27_6_no_wrapper.txt` |
| S27.7 | ✅ 已确认 | docs-consistency 23 引用 / 0 缺失 / rc=0；§9.2 写入批面口径；00P 卡面追加一行指向本卡 | `s27_7.txt` |

## 二、本地 CI 等价步骤

| 步骤 | 命令 | 读数 |
|---|---|---|
| ruff | `ruff check app tests` | All checks passed，rc=0 |
| mypy | `mypy app` | 112 文件无问题，rc=0 |
| 契约漂移 | `gen_contracts.py --check` | 10 个产物幂等一致，rc=0 |
| 文档一致性 | `check_docs_consistency.py` | 23 引用 / 0 缺失，rc=0 |
| 守卫 ports/structure/versions | `guards.py guard-*` | 三条 rc=0 |
| 敏感形门（非空批） | `evidence-check --base 8135f1a` | 待检 25 路径、HIGH 0、证据 5 条复跑全过、ruff/gitleaks 两步 rc=0 ⇒ **rc=0** |
| gitleaks | `detect --source . --config .gitleaks.toml` | 270 commits scanned / no leaks found，rc=0 |
| 全量 pytest | `pytest tests/ -q -rs --cov=app --cov-fail-under=75` | **1320 passed / 451 skipped / 0 failed**，rc=1（仅覆盖率门：无 PG ⇒ 连库用例 skip，TOTAL≈68% < 75） |
| 迁移 | `alembic upgrade head` / 往返 | **未测**（沙箱无 PG） |

skip 构成（451）：`AIDEANBOT_TEST_PG_DSN` 未设置（连库）+ Redis 不可达 4 条，PG 不可达类 0。
对照基线 `SKIP_BASELINE=6` 的口径说明：本机全部 DB 用例都要 skip，远高于基线，故**不适用**
本地 skip 门；该门在有 PG 的 CI 上执行。

## 三、门禁与顺序

提交后立即在 `8135f1a..HEAD` 上复跑 `rounds-check` 与 `evidence-check` 并留读数；两条都要求
**非空批**，且 rc=3 不是通过（S27.7 §9.2）。读数见 `s27_gates_committed.txt`。

## 四、卡面差异（需规划方裁定）

1. **S27.3 的「31 条表达式引用不再命中」无法在今日树面复现**。31 出自
   `02-需求复核与辩证分析.md` §6 对当时树面的 50 条 HIGH 抽样（47 口令赋值形 + 3 厂商键名形），
   规划方未留下可复跑脚本；V0.15.0 重建后文档目录整体搬迁，树面已变。今日同义判据的可复现
   读数是「少报 26 条表达式、新增 10 条 `_TOKEN` 后缀族」。请裁定是否把卡面数字改为
   "由脚本产生的当日读数"。
2. **新增阻塞面（建议登记 P-42）**：`_TOKEN` 后缀族引号字面量仍报，导致 6 份夹具文件被挡
   （`test_auth.py` 3→6、`test_session_store_redis.py` 0→2、`test_manifest_asset_alignment.py` 0→1、
   `test_manifest_state_machine.py` 0→1、`test_push_providers.py` 2→3、
   `EVD-V2-02/prove_article_identity.py` 0→2）。整改 = 把夹具值换成 `SECRET_FAKE` 认得的占位形，
   而这些文件不在本卡「允许修改」内，故不在本卡内动。
3. **本地一个必须清理才能读绿的发现**：`git stash list` 里有一条本会话的备份暂存
   （`backup-before-V15-sync-*`），其中 3 份旧证据 patch 带占位 DSN，被 gitleaks 在
   全历史读成 15 条 leaks ⇒ `evidence-check` 的真实工具步此前恒红。该提交不是 main 祖先、
   未推送、CI 不可见。已先导出补丁备份（`/tmp/s27_stash_backup_full.patch`）再 drop 暂存，
   复读 270 commits / no leaks found。CI 侧基线不受影响；但**本地若再 stash 过带形状的旧证据，
   这个坑会回来**，建议在 conventions 里记一句（未写，等裁决）。

## 五、@ci

第 1 次推送（07053f9 = d32edfc + 范围门读数补档）：

| 工作流 | run | 结论 |
|---|---|---|
| Security | 39268287343 | ✅ success |
| CI | 39268288823 | ❌ **failure** —— backend `Governance gates` 步 rc=1 |
| CI-Windows | 39268287340 | （见下） |

failure 根因不是门逻辑，是 job 级 DSN 让 `prove_dsn_policy.py` 的未配置分支 4 条断言必 FAIL
（详见 `s27_2.txt` §七，本机同变量复现 4 FAIL、置空串 ALL PASS）。已按允许修改面修正该步 env
（两个 DSN 置空串）并补机检断言，先红原文 `s27_2_dsn_env_red.txt`。

第 2 次推送（修正提交）：待填。

## 六、新增待登记 P 项（两件，均要求登记而非本卡内改）

1. **P-42（夹具被 `_TOKEN` 后缀族挡）**：见 §四 2。
2. **P-43（候选）：`EVD-V2-00/prove_dsn_policy.py` 读 ambient env**。该证据脚本的 f/l/m/n
   四条断言只在**未配置**环境成立，而它自己不做隔离 ⇒ 任何在带 DSN 的环境里跑
   `evidence-check` 的机器都会红（本机因为没设 DSN 才一直绿）。本卡在 ci.yml 该步置空 DSN
   只是让门重新可执行，没消掉这个依赖。根治 = 脚本自己 `monkeypatch.delenv` 或子进程隔离，
   文件在 `docs/06_validation/evidence/EVD-V2-00/**`，不在本卡允许修改面。
   （与前一条同源的另一半：若有人把这两个 DSN 从步骤 env 里删掉，机检断言会先红。）
