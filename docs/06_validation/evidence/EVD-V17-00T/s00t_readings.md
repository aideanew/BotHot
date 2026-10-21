# EVD-V17-00T · STEP-00T 原九项第一次执行的读数

> 卡面：`docs/任务规划V0.13.0/steps/STEP-00T-证明判据pytest化与脚本归档.md`。
> V0.14.0 增量 V14.1/V14.2/V14.3 已交付（轮次门、耦合门、`prove_provider_shapes.py` 迁成 pytest 并删除脚本）。
> 本文件记**原九项**（S0T.1.1–S0T.3.3）的第一次执行。允许面 = `apps/api/tests/proofs/**` +
> `docs/06_validation/evidence/**`；`apps/api/app/**` 禁止。本轮**零代码改动**，
> 动卡头状态行属状态表同步，逐条点名在 §5。

## 1. S0T.1 盘点（产出面 `inventory.md`）

| 判据 | 实测 |
|---|---|
| 证据 `.py` 支数 / 行数 | 20 支 / 11495 行（单支最大 2650：`EVD-V2-02/replay_s213.py`） |
| 被 `evidence-check` 复跑的 | 3 支（表里 6 条 spec = 3 支 × 含一发 `--self-test`） |
| 自带 `--self-test` 面的 | 9 支 |
| "已失效"（引用路径已消失） | **0 支**——见 §2 的合成夹具甄别 |
| "重复"（自己点名了一支仍存在的 `tests/**.py`） | 6 支 |

取数方式全部可复算：`EVIDENCE_PROOFS` 从 `scripts/guards.py` **import 后读常量**（不抄表）；
判据函数用 `ast.walk`（含 `async def` 与类内方法）；"它证什么"取 `ast.get_docstring` 首行。
复算脚本 `.staging/s00t_inventory.py`、`.staging/s00t_refs.py` 是 gitignored scratch，不入库。

## 2. 一条被自己否证的代理判据（这是本轮最该留的东西）

"引用路径还在不在"是我给"已失效"挑的代理。它第一次跑出 **5 个"已消失"路径**：
`apps/tests/t_one.py`、`t_broken.py`、`t_gbk.py`、`t_none.py`、`apps/api/tests/x.py`。
如果就此下结论，本卡会写出"4 支判据已经烂掉"——**全是假的**：

- `replay_s213.py:1818` 就地 `(staged / "apps" / "tests" / "t_one.py").write_text(...)`
  创建它自己的合成夹具；`t_broken/t_gbk/t_none` 同一来源；
- `mutate_replay_r9.py:272` 里的 `x.py` 出现在一条**注入用字符串字面量**中（它是变异样本，不是路径）。

⇒ 甄别方法是"回到原文看这个名字是谁造的"，而不是相信正则。修正后：**0 支失效**。
这条被记下来的原因：它正是本仓反复踩的那类"探针近似了判据"（合成树里的路径与仓内路径同形），
而"已失效 = 0"这个结论的价值，完全取决于它有没有被这样查过。

## 3. S0T.2 迁移：本轮未整批执行，且给了不能整批执行的证据

`S00T.V14.3` 能迁 `prove_provider_shapes.py`，是因为它判的是纯函数形状，可原样搬进 `tests/proofs/`。
其余 19 支里有三类搬不动（逐支归因写在 `inventory.md` §4）：

1. **需要临时仓 / 合成树的电池**（`replay_s213.py`、`mutate_replay_r9.py`、`j_attack_r7.py`）——
   它们必须把 harness 复制到只含证据包的目录里跑；这类"会动盘"的脚本今天**故意**不在 `evidence-check` 里。
2. **会动盘的真实文件变异电池**：`s27_3_mutation.py`——逐字节备份 `scripts/guards.py`、施加变异、
   跑该用例文件、还原，再用 sha256 证明还原逐字节。每跑一次改一次工作树，只能留作人工反证。
3. **需要特殊环境的一次性读数探针**：`probe_import_stall.py`——看门狗是
   `faulthandler.dump_traceback_later(WATCHDOG_SECONDS, exit=True)`，且要黑洞 `DATABASE_URL`
   加 `PROBE_SELECTOR=1`（换 `WindowsSelectorEventLoopPolicy`）才复现 pytest 的真实条件。

### 3.1 这一节的归因错过两支，修正按实现重做（第一版留在这是为了可追溯）

第一版把 `mutate_s341.py` 也归进第 2 类，又把 `probe_import_stall.py` 说成"`subprocess` 超时墙"。
两条都被读实现否证/修正：

- `mutate_s341.py`：全文件 `write_text` 计数 **= 0**，变异体是
  `read_text → replace → ast.parse → exec` 进一个内存里造的 `ModuleType`（`_load_mutant`，183 行起）
  ⇒ **它不动盘**，与 STEP-07 那批电池同法，是 **S0T.2.1 的第一顺位迁移对象**，不该在"搬不动"里。
- `probe_import_stall.py`：超时确实存在，但我用来分类的 grep 词是 `timeout|TIMEOUT|subprocess`，
  匹配不到 `dump_traceback_later` ⇒ 那条结论**碰巧成立而推理是错的**，现按实现重写。

⇒ S0T.2 需要**逐支授权**（与 V14.3 当初"逐支 + 两轮复查"的节奏一致），不是本轮能整批推的；
本卡的处置是把"哪些能迁（至少含 `mutate_s341.py`）、哪些迁了会造出假绿、归因是怎么被验/推翻的"
写成一页清单，交规划方按支签字。

## 4. S0T.3 门禁三条

- **S0T.3.1 已成立并被证明**：`pytest tests/proofs --collect-only` ⇒ 33 条；
  `pyproject` 的 `testpaths = ["tests"]`、CI 的命令是 `pytest tests/`（`ci.yml` 的 backend 测试步）
  ⇒ 这 33 条随每一次 `@ci` 执行。ubuntu 侧最近一发总数 `2065 passed + 6 skipped` 与之相容。
- **S0T.3.2 无法执行——上游那道门不存在**：卡面「9 验收」写"evidence `.py` 行数 < 00G 设的上限"，
  但 `scripts/guards.py` 里与 evidence 有关的只有 `EVIDENCE_PROOFS`、`_is_evidence_py`、`coupling_check`、
  `evidence_check` 四处，**没有任何行数上限常量或判定**；STEP-00G 自己的 S0G.3.1–3.3 在卡面上仍未打勾
  ⇒ 没有"当前值"可下调。实测当前值 **20 支 / 11495 行**。登记 `§4 P-59`（属 P-31 那一族：
  "须机械执行"的已签裁决落地率为 0）。
- **S0T.3.3 成立**：本批 `evidence-check` 的真实工具步打印 `no leaks found`（311 commits scanned），
  `gitleaks protect --staged` 亦 0。

## 5. 越界声明与本轮未做

| 文件 | 为何仍改 |
|---|---|
| `docs/任务规划V0.13.0/steps/STEP-00T-*.md` 卡头状态 | 状态表必须与判据结论一致，否则下游读到"未开始"；与 STEP-00R、STEP-00H 同一处置 |
| `docs/任务规划V0.12.0/00-README.md` | 登记 P-59（执行助手指令：新缺陷从 P-50 起登记，不越卡修） |

本轮未做：S0T.2 的逐支迁移（需规划方按支授权）、S0T.3.2 的下调（上游门不存在）。
两条都不是"忘了做"，而是**做完会造出假绿或无的放矢**，因此停在登记与清单。
