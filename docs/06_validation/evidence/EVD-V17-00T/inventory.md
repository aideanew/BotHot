# 证据判据盘点（S0T.1.3 的产出面）

> 对象：`docs/06_validation/evidence/**/*.py`。取数方式全部是**脚本自己报**，没有手填数字：
> - 接线状态：`import scripts/guards.py` 后读 `EVIDENCE_PROOFS` 常量（不是抄表）；
> - 行数：`wc -l` 与 `len(splitlines())` 两种口径互验；
> - 判据函数名：`ast.parse` 后走 `ast.walk`（含 async 与类内方法，早期版本的坑已记在台账）；
> - "引用是否还在"：正则抽出脚本里出现的 `apps/ scripts/ packages/ docs/ .github/` 路径，
>   再逐条 `Path.exists()`；
> - "它证什么"：`ast.get_docstring` 的第一行。
>
> 复算脚本是 gitignored 的 `.staging/s00t_inventory.py` 与 `.staging/s00t_refs.py`——
> 按纪律证据包内不留 scratch（`feedback-verifier-subagent-budget`）。

## 1. 总量

| 维度 | 实测 |
|---|---|
| 证据 `.py` 支数 | 20 |
| 行数合计 | 11495（单支最大 2650：`EVD-V2-02/replay_s213.py`） |
| 被 `evidence-check` 实际复跑的 | **3 支**（`g24_static_check.py`、`prove_dsn_policy.py`、`prove_net_isolation.py`，各带一发 `--self-test`） |
| 自带 `--self-test` 面的 | 9 |
| 引用路径已全部存活 | **20 / 20**（见 §3） |

## 2. 逐支清单

| 脚本 | 行 | 门跑 | 自检 | 文档串自己声明判的东西 |
|---|---|---|---|---|
| `EVD-V15-27/s27_1_probe.py` | 76 | – | – | S27.1：`GUARD_BASE` 在一次性仓库里的三种形态 |
| `EVD-V15-27/s27_3_counts.py` | 147 | – | – | S27.3 / S27.V15.1：新旧命中集合对照（计数由脚本产生） |
| `EVD-V15-27/s27_3_mutation.py` | 102 | – | – | S27.3 五轮变异，每轮必须被 `tests/test_secret_shape_gate.py` 抓住 |
| `EVD-V15-27/s27_5_rounds.py` | 51 | – | – | S27.5 轮次门扩判据的四条反证 |
| `EVD-V15-27/s27_red_repro.py` | 75 | – | – | 把 42 条先红读数重取一份可入库副本 |
| `EVD-V2-00/g24_static_check.py` | 446 | **YES** | YES | G-24 静态自检（无 ruff/mypy 时的机器判据） |
| `EVD-V2-00/prove_dsn_policy.py` | 284 | **YES** | YES | S0.1.2 本机机器证明（纯 stdlib） |
| `EVD-V2-00R/prove_net_isolation.py` | 1246 | **YES** | YES | STEP-00R：测试出站代理隔离 + 同形脆弱点 |
| `EVD-V2-02/block_article_identity_plugin.py` | 55 | – | – | S2.1.1「改前红」的真实 pytest 复现件 |
| `EVD-V2-02/j_attack_r7.py` | 171 | – | – | J 段驱动：改前/改后两版 harness 对同一批输入 |
| `EVD-V2-02/mutate_replay_r9.py` | 1109 | – | YES | M 段反证电池：`replay_s213.py --self-test` 每条判据都要被打红 |
| `EVD-V2-02/mutate_s341.py` | 286 | – | – | S3.4.1 反证电池：每发生产代码变异必须让指定用例变红 |
| `EVD-V2-02/prove_anchor_fallback.py` | 2042 | – | YES | STEP-02 S2.1.4/S2.1.5：锚定兜底的 `LIKE` 真的删了 |
| `EVD-V2-02/prove_article_identity.py` | 778 | – | YES | STEP-02 S2.1.1/S2.1.2：`parse_wechat_url` 真实执行与反证 |
| `EVD-V2-02/prove_biz_delegation.py` | 1461 | – | YES | STEP-02 S2.1.3：`kb._biz_from_url` 真的委托了 `parse_wechat_url` |
| `EVD-V2-02/prove_shortlink_race.py` | 334 | – | YES | STEP-02：`kb._save_short_link` 后发者必须被 savepoint 吸收 |
| `EVD-V2-02/prove_unreachable_branches.py` | 83 | – | – | S3.4.1 残项：两处返回体按构造不可达 |
| `EVD-V2-02/replay_s213.py` | 2650 | – | YES | 重放器：把 `out_s213.txt` 每段命令真正重跑并整份重写证据 |
| `EVD-V5-00S/secret_shape_gate.py` | 49 | – | – | 提交前凭据形门（STEP-00P 的机械判据） |
| `EVD-V7-00W/probe_import_stall.py` | 50 | – | – | STEP-00W S00W.1.1：用 `@win` 栈闭合"import 期卡死"根因 |

## 3. 分类判定（S0T.1.1 要的"有效 / 重复 / 已失效"）

判据用的是可复算的两条代理，**不是主观印象**：

- **"已失效" = 引用路径已消失**：20 支里 0 支。抽出来的"消失路径"共 5 个
  （`apps/tests/t_one.py`、`t_broken.py`、`t_gbk.py`、`t_none.py`、`apps/api/tests/x.py`），
  逐条查回原文后**全部是电池自己造的合成夹具**：
  `replay_s213.py:1818` 就地 `write_text` 建 `t_one.py`，`mutate_replay_r9.py:272` 把 `x.py`
  放在一条注入用字符串字面量里。所以这一类的正确判定是"合成名被我的路径正则当真路径读了"，
  不是"判据失效"。⇒ **本轮无"已失效"项**，且这个"无"带着它的判据。
- **"重复" = 文档串自己点名了一支 `tests/**.py`**：6 支命中，且点名的测试文件**都还在**
  （`test_secret_shape_gate.py`、`test_guard_rounds.py`、`test_article_identity.py`、
  `test_provider_contract.py`、`test_rss_provider.py`、`test_asset_fragment_guard.py`、
  `test_kb_longlink_ingest.py`、`tests/conftest.py`）。
  ⚠️ "重复"在这里的含义是**同一判据有两份实现**（一份在 pytest、一份在这支脚本），
  **不等于该删**：这些脚本多数是"变异/电池"侧——pytest 里的是**被判对象**，脚本是**打红它的那一手**。
  删之前必须证明后一半已经有人接得住，见 §4。

## 4. S0T.2（迁移）本轮未执行，以及为什么这不是"漏做"

V0.14.0 增量 `S00T.V14.3` 已经迁成 pytest 并删掉了 `prove_provider_shapes.py`——那一支能迁，
是因为它判的是**纯函数形状**，可以原样搬进 `apps/api/tests/proofs/`。
本轮盘出来的其余 19 支里有三类**搬不动**的，硬搬会造出假绿。归因是**读实现**得出的，不是读文档串猜的——第一版我按 `mkdtemp` / `timeout` 两个词 grep，结果错过两支（见 §4.1）：

1. **要动盘：临时仓 / 合成树电池**——`replay_s213.py`（9 处 staging 迹象、`git checkout`、20 次 `write_text`）、`mutate_replay_r9.py`（4 处 + `shutil.copy`）、`j_attack_r7.py`（2 处 + `write_text`）。它们刻意把 harness 复制到只含证据包的目录里跑（这正是本仓对探针的要求）；搬进 pytest 就要在 CI 里建临时仓并写文件——`evidence-check` 现在不跑它们，恰恰因为它们**会动盘**。
2. **要动盘：直接改真实文件再还原**——`s27_3_mutation.py`。它自己的文档串写明做法是"逐字节备份 `scripts/guards.py` → 施加一处定点变异 → 跑该用例文件 → 记录 rc → 从备份还原 → 用 sha256 证明还原是逐字节的"。这类只能作为**人工反证**留形：它每跑一次就改一次工作树。
3. **要特殊环境的一次性读数探针**——`probe_import_stall.py`：看门狗是 `faulthandler.dump_traceback_later(WATCHDOG_SECONDS, exit=True)`（**不是** `subprocess` 的 timeout，所以按 `timeout` grep 会误判成"它没有超时"），且需要黑洞 `DATABASE_URL` 与 `PROBE_SELECTOR=1` 换事件循环策略才能复现 pytest 的真实条件。它产出的是一份**读数文本**，不是一条可重复断言。

### 4.1 一支被我误判、其实可以迁的

`mutate_s341.py` 一开始被我放进第 2 类。查实现后**否证**：它对源码只做
`read_text → replace → ast.parse → exec 进一个内存里造的 ModuleType`（`_load_mutant`，183 行起），
**全文件 `write_text` 计数 = 0**，即它不动盘——与 STEP-07 那批电池用的"内存变异体"同一手法。
⇒ 它是 **S0T.2.1 的第一顺位迁移对象**（"每发生产代码变异必须让指定用例变红"完全可以参数化进
`tests/proofs/`），不属于"搬不动"。这条修正留档而不抹掉：下一次有人 grep 到它时，需要知道它是
被怎么验过的，以及为什么第 2 类里只剩一支。

⇒ S0T.2 的"有效判据逐个迁为 pytest，参数化"在**没有逐支安全分级的授权**前不能整批执行；
本卡的处置是把"哪些能迁（至少含 `mutate_s341.py`）、哪些迁了会造出假绿、为什么"写成上面三类加 §4.1，
交回规划方按支授权（节奏与 `S00T.V14.3` 的"逐支 + 两轮复查"一致）。

## 5. S0T.3 门禁三条的实测状态

| 项 | 状态 | 读数 |
|---|---|---|
| S0T.3.1 proofs 目录纳入 CI pytest | **已成立（本轮证明）** | `pytest tests/proofs --collect-only` ⇒ 33 条；`pytest tests/ --collect-only` 的收集面里含 `proofs`；CI 的命令是 `pytest tests/`，`pyproject` 的 `testpaths = ["tests"]` ⇒ 这 33 条随每一次 `@ci` 跑。ubuntu 侧总数 `2065 passed + 6 skipped` 与之相容 |
| S0T.3.2 evidence 行数上限下调到实测值 | **不能执行——上游那道门不存在** | 卡面「9 验收」写"evidence `.py` 行数 < 00G 设的上限"，而 `scripts/guards.py` 里与 evidence 相关的只有 `EVIDENCE_PROOFS`（复跑表）与 `_is_evidence_py`/耦合门（D-V4-03），**没有任何行数上限常量或判定**；STEP-00G 自己的 `S0G.3.2「设新上限=当前值，超限 evidence-check 报红」`在卡面上仍是未打勾的三级任务 ⇒ 没有"当前值"可下调。实测当前值：**20 支 / 11495 行**。登记 `§4 P-59` |
| S0T.3.3 gitleaks 0 新增 | **成立** | 本批 `evidence-check` 的"真实工具步"打印 `311 commits scanned / no leaks found`；`gitleaks protect --staged` 亦 0 |

## 6. 一句话总结（给下游）

证据包**没有失效判据**，但**95% 的判据脚本不在任何门的复跑面里**（20 支中只有 3 支被 `evidence-check` 跑），
而"行数上限"这道本该约束它的门从未落地。这两件事合起来才是本卡真正的读数：
**脚本继续增长不会变红，脚本悄悄烂掉也不会变红。**
