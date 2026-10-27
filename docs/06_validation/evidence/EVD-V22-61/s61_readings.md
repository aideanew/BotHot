# STEP-61 `MeWallet` 契约封闭 读数（执行助手，2026-10-27）

> 卡：`docs/任务规划V0.22.0/steps/STEP-61-MeWallet契约封闭.md`；原子步与判据按
> `docs/任务规划V0.22.0/08-阶段A执行细则.md` §4（08 自己声明与卡面冲突时以 08 为准）。
> 执行顺序按 08 §6：61 先落（最小、独立，让 62 能开 NF/C 三行）。

## 0. 开工前置（现取）

- 基线：`main@291d530`（D-V22-06 改派 + 08 细则）。`git fetch` 后 `origin/main...HEAD` = `0 0`，工作树干净。
- 上一规划头 `4ea83c4` 三条 attempt 1 全 success：CI 40498791658 / CI-Windows 40498791644 / Security 40498791858。
- 本基线 `291d530` 读取时：CI 40502460931 success、Security 40502461066 success、**CI-Windows 40502461082 仍
  `in_progress`**。按 D-V22-01 的"卡收口不等 CI"开工，但把"它此刻不是红"写清楚；若它随后转红，
  本卡的连库读数不受影响（docs-only 提交），我会停下报告而不是掩盖。
- 本机 PG@5547 预检（先连再跑，不接受"有监听就算"）：`server_version_num=160015`、
  `alembic_version` 一行、head `ab1006c2a`。

## 1. 61.1 先红（原文 `s61_1_red.txt`）

- 命令：`pytest tests/test_shapes_response_contract.py -q -k "me_wallet"`（只加了新用例，其他一字未改）。
- 读数：`1 failed, 1 passed, 16 deselected, 1 warning in 8.09s`，失败原因是
  `Failed: DID NOT RAISE ValidationError`（`tests\test_shapes_response_contract.py:101`）——
  改前 `extra="allow"`，多一个 `internalNote` 不抛，正是本卡要钉的那件事。
- 状态自证（"红确实跑在未改代码上"）：那一刻 `git diff --name-only` 只有
  `apps/api/tests/test_shapes_response_contract.py` 一条；`apps/api/app/contracts/shapes.py` 的
  `git hash-object` 与 `HEAD:` 同值（`bc34dfcc090e710c317a9e9b08d925723d4c732c`），冻结稿同值
  （`4a033950d02c38b009bd338f20e37b89986a1bb4`）。

## 2. 61.2/61.3 交付面（三处形状 + 三处配套）

| 处 | 改动 | 可复算读数 |
|---|---|---|
| `apps/api/app/contracts/shapes.py` | `MeWallet.model_config` 由 `extra="allow"` 改 `"forbid"`；类 docstring 写明封闭后只剩五键、与 `_WALLET_KEYS` 必须同步 | 模块 docstring 里"本模块唯一 `extra="allow"` 的是 MeWallet"那段一并改写（见 §4 越界 (d)） |
| 冻结稿 `docs/任务规划V0.12.0/contracts/shapes.schema.json` | 只改 `MeWallet` 的 `"additionalProperties"` 一行（08 §4 判据"diff 仅 1 行"） | `git diff --numstat` = **1/1**；差异行体逐字 = `-      "additionalProperties": true,` / `+      "additionalProperties": false,`；文件 sha256 前 16 位 `7041e120ed4d4e71` → `5719f763c1cde719`，字节 18033 → 18034（LF，CRLF 计数 0） |
| 产物 `packages/contracts/**` | `python scripts/gen_contracts.py` 重生成 | `--check` rc 0（幂等，8 个 dto 域 + 7 个 schema 域）；`packages/contracts/schemas/shapes.schema.json` numstat **2/2**——除了 `additionalProperties` 那一行，还有一行 `MeWallet.description`：**类 docstring 会进产物的 def description**（这条是本次实测到的生成器行为，STEP-57 那次核的是"模块 docstring 不进根 description"，两者不冲突，记下来免得下次再猜） |
| `apps/api/tests/test_shapes_response_contract.py` | 新用例 `test_me_wallet_rejects_a_key_the_contract_does_not_publish`（红转绿）；原 `test_me_wallet_is_the_only_open_object` 改名并升级为 `test_no_object_definition_is_open`（`open_defs == []`，且所有 `type:object` 都 false） | 旧名记在这里供检索；改名理由：封闭后"唯一开放对象"这个标题本身就成了假陈述 |
| `apps/api/tests/test_me_wallet_projection.py` | 新增 `test_degraded_shape_and_contract_agree_on_the_five_keys`（61.3：`_WALLET_UNAVAILABLE ⊆ _WALLET_KEYS`、`_WALLET_KEYS == 五个键`、`MeWallet.model_fields == 五个键`、`extra == "forbid"`） | 卡面第 13 格（降级常量含五键外键 ⇒ 停）**未触发**：现值三键 `balanceYuan/currency/available` |
| `apps/web/tests/s55-mock-runtime-shape.spec.ts` | 那条"MeWallet 开放 ⇒ 多键该放行"的断言（注释 + 断言共 2 行，HEAD 里 MeWallet 的多键断言只有这一条）翻成"封闭 ⇒ 多键必须报"（见 §4 越界 (b)） | `pnpm exec vitest run tests/s55-mock-runtime-shape.spec.ts` → `Test Files 1 passed (1)`、`Tests 2 passed (2)` |

## 3. 卡面第 10 格读数（本机，两种读法都留）

1. **不设 DSN**：`134 passed, 9 skipped, 1 warning in 171.48s (0:02:51)`。9 条 skip 全部是
   `test_shapes_response_contract.py` 的连库反向核，消息 `AIDEANBOT_TEST_PG_DSN 未设置`。
   这一版读数我保留而不是删掉——它同时是本仓 skip 语义的一次对照：没库时是 skip 不是 fail。
2. **设 `AIDEANBOT_TEST_PG_DSN` 后**（同一个 5 文件命令）：`143 passed, 1 warning in 201.61s (0:03:21)`
   ⇒ **0 skipped**，`MeWallet` 的真端点反向核在封闭后仍然通过（真 `/me` 响应不含契约外键）。
3. `python ../../scripts/gen_contracts.py --check` rc 0；`pnpm exec tsc --noEmit` rc 0；
   `ruff check app tests ../../scripts` rc 0；`mypy app ../../scripts` rc 0（134 source files）。

按 D-V22-01：本机没有跑全量 pytest / 全量 vitest / 门链，只跑了卡面第 10 格与"我改到的那一个前端文件"。
另记一次自身失误：第一次跑交付链时我把暂存面条数写成 11，链里的
`test "$(git diff --cached --name-only | wc -l)" = 11` 把提交拦下（CHAIN_RC=1、HEAD 未动、12 条改动留在
暂存区）；实际是 12 条（6 处代码/产物/稿 + 2 份证据 + 台账 + 卡表 + 07 + 卡面）。这道自锁就是为这一刻留的。

## 4. 越界申报（卡面第 6 格之外的一节）

- **(a) `apps/api/tests/test_shapes_response_contract.py`**：卡面第 6 格给的是 `apps/api/tests/test_contract_*.py`
  与该投影测试文件，不含 `test_shapes_*`。但 08 §4 的 61.1 明确点名"在
  `test_shapes_response_contract.py` 加用例"，而 08 自己声明冲突以它为准 ⇒ 按 08 执行并在这里申报。
  同文件里那句"唯一开放对象"的断言是本卡必须改的第二处（不改就必然红）。
- **(b) `apps/web/tests/s55-mock-runtime-shape.spec.ts`**：卡面允许面写的是 `apps/web/**` 的
  "类型（仅 tsc 要求时）"，而 tsc 这次没红（rc 0）——翻这条断言的依据不是 tsc，是 s55 门自身的判据：
  它钉的是"`MeWallet` 开放时多键该放过"，`MeWallet` 一封闭它必然红。同款翻长在 STEP-57 第 1 轮做过并
  作为越界申报入证（`EVD-V21-57/s57_readings.md` §5），当时随封闭一起退回；这次封闭落地，配套跟上。
  改动 = 2 行（注释 + 断言翻向）+ 1 个局部变量名，未动样例数据、未动 `checkShape`/`auditDefs` 本体（复查独立核过 diff 只有 +3/−2）。
- **(c) 冻结稿 `x-invariants` 的两条声明没有改**：改完 `additionalProperties` 之后，
  `"除 MeWallet 外所有对象 additionalProperties=false…"` 与 `"MeWallet 正常分支是主平台钱包对象原样透传…故开放（P-121）"`
  两句成了假话。08 §4 61.4 的判据是**冻结稿 diff 仅 1 行**，所以我不动它们——
  该文件只有规划方能落笔（D-V21-20），文字订正已登记为 **P-130** 交回。
- **(d) 两处描述性文字**：`shapes.py` 的模块 docstring（"本模块里唯一 `extra="allow"` 的是 `MeWallet`…"）与
  `test_me_wallet_projection.py` 头部（"契约侧至今仍是开放对象…"）。卡面写"仅 `MeWallet`"，
  这两段都只描述 `MeWallet` 本身；留着就是源码里存假陈述，所以改了，且都记在本节。
- **(e) 复查抓到的一处我没有申报的假话（判 FAIL 后补上）**：
  `docs/任务规划V0.22.0/01-事实基线与进度.md` §3 的 U3 行现在整行不成立——它写"投影已发、**契约仍开放**"，
  并把 `apps/api/app/contracts/shapes.py` 的 `extra="allow"` 与冻结稿的 `additionalProperties: true` 当证据引；
  本卡把这两处都反过来了。**我不改它**：那是规划方的本版事实基线，不在 61 的允许面（第 6 格）里，
  也不在 62（`docs/02_requirements/**` + `ci.yml` 一行）或 63（CHANGELOG + AGENTS 版本块）的允许面里，
  08 全文对 `U3` 零命中 ⇒ 这是一行"没人认领的过期事实"。已并进 **P-130** 的交回内容（同处还有
  `AGENTS.md` 版本块里"仍是唯一开放对象"那句现在时陈述——它由 STEP-63 发 v1.1.5 时整块改写，本卡不动）。

## 5. 卡面第 9 格熔断自查

`前端读了五键外字段 ⇒ 停`：不触发。`apps/web` 侧读 wallet 的位置只用 `balanceYuan`、`currency`、`available`
（`apps/web/lib/api/types.ts:72,79`），mock 样例也只给 `wallet: { balanceYuan: "128.50", currency: "CNY" }`
（`apps/web/lib/api/mock-routes.ts:311`）⇒ 封闭后没有前端读取点变成契约外键。

## 6. 闭合与余项

- **P-121 就此闭合**：泄露那半条由 STEP-57 的投影断掉（`685e3f8`），判形那半条由本卡补上——
  三处形状（冻结稿 / `shapes.py` / 产物）一致封闭，且有常驻用例钉住"两侧键集必须同源"。
- **本卡不销的账**：P-129 裁定行记的"可选键被上游显式发成 `null` 时按『给了值』原样带出"仍留
  （卡面未规定，本卡不自扩规则）；P-128（`data` 发成列表时 `/auth/me` 仍 500）与本卡无关、仍只有登记行。
- **新登记 P-130**：三处"要改的文字都不在本卡允许面内"合到一行交回——冻结稿 `x-invariants` 那两条文字
  （见 §4 (c)）、`docs/任务规划V0.22.0/01-事实基线与进度.md` §3 的 U3 行（见 §4 (e)）、
  `AGENTS.md` 版本块里"仍是唯一开放对象"那句现在时陈述（由 STEP-63 整块改写，故本卡不动），归规划方落笔。
- 交回规划方一处口径确认：卡面第 6 格与 08 §4 对 `test_shapes_response_contract.py` 的归属不一致（§4 (a)），
  本次按 08 执行；下次这类"08 点名而卡面没给"的文件，是改卡面还是保留冲突，请定一个口径。
