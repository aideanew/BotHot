STEP-55 反证批 A–H（最终交付字节上跑）
======================================

目的：本轮新增/收紧的每一条判据，都要各自证明"它会红"——否则它只是一段没跑过的代码。
平台 @win（Windows 10 x64）；代码基线 `e4a9a67` + 本卡未提交改动；2026-10-26 20:05～20:12（Asia/Shanghai）。
这一批是**第二轮**（同一套判据在第一轮字节 `51acc0eb…`/`a49c4507…` 上也红过，那份原文仍在
`s55_probe_*.txt` 与 `s55_probe_readings_round1.md`），因为核对器在那之后又被审查改动过三轮
（own() / 装载期体检扩到七条 / 捕获组计数 / 分页回显那一发），证据必须落在交付字节上。
驱动 `probes2.sh` + 打补丁器 `probe_patch.py`（都在会话临时目录，**不进仓库**：证据目录里的 `.py`
会被 D-V4-03 耦合门当成待纳管的复跑件；判据本体在两处常驻面上——本卡新用例与 `test_module_coverage_gate.py`）。
手法：唯一整行锚点（命中数≠1 就中止且不写字节）→ 跑 → 记 rc → 还原 → 比 sha256。
产物原文 `s55p2_*.txt` 十三份，逐字未删。

## 驱动原文（MUTATED / rc / RESTORED 三段一组；restore 行必须 True）

```
=== 交付字节的 sha（跑探针之前先记）===
apps/web/lib/api/mock-routes.ts afff902942a71965
apps/web/tests/s55-mock-runtime-shape.spec.ts 6140ecb525c486bd
scripts/check_module_coverage.py c17583d1aff3d30b
apps/api/tests/test_module_coverage_gate.py 56d5b5173b46fd56
MUTATED a_extra_key -> mock-routes.ts sha 49703998a1440e18 (was afff902942a71965)
rc_a_s52=0
rc_a_tsc=0
rc_a_s55=1
RESTORED a_extra_key sha afff902942a71965 == afff902942a71965 -> True
MUTATED b_missing_key -> mock-routes.ts sha 81cbcb44fc19379f (was afff902942a71965)
rc_b_tsc=2
rc_b_s55=1
RESTORED b_missing_key sha afff902942a71965 == afff902942a71965 -> True
MUTATED c_bounds -> mock-routes.ts sha c0de5df56efc3c6e (was afff902942a71965)
rc_c_s55=1
RESTORED c_bounds sha afff902942a71965 == afff902942a71965 -> True
MUTATED d_route_id -> s55-mock-runtime-shape.spec.ts sha 2fd7aa883c0ddb01 (was 6140ecb525c486bd)
rc_d_s55=1
RESTORED d_route_id sha 6140ecb525c486bd == 6140ecb525c486bd -> True
MUTATED e_stale_override -> s55-mock-runtime-shape.spec.ts sha c30358aaf83d1b81 (was 6140ecb525c486bd)
rc_e_s55=1
RESTORED e_stale_override sha 6140ecb525c486bd == 6140ecb525c486bd -> True
MUTATED f_encoding -> check_module_coverage.py sha ace06d7fa6e6fd49 (was c17583d1aff3d30b)
rc_f_pytest=1
rc_f_red_plain=1
RESTORED f_encoding sha c17583d1aff3d30b == c17583d1aff3d30b -> True
MUTATED g_param_names -> mock-routes.ts sha 9746537e3866f518 (was afff902942a71965)
rc_g_s55=1
RESTORED g_param_names sha afff902942a71965 == afff902942a71965 -> True
MUTATED h_no_echo -> mock-routes.ts sha 7476b4c4f8630fd2 (was afff902942a71965)
rc_h_s55=1
RESTORED h_no_echo sha afff902942a71965 == afff902942a71965 -> True
=== 还原后工作树（应只剩本卡交付面）===
 M apps/api/tests/test_module_coverage_gate.py
 M apps/web/lib/api/spaces.ts
 M apps/web/lib/api/types.ts
 M scripts/check_module_coverage.py
?? apps/web/tests/s55-mock-runtime-shape.spec.ts
?? docs/06_validation/evidence/EVD-V21-55/
=== 交付字节 sha 复核（与 before 逐字相同才算还原）===
sha_all_equal=True
```

`mock-routes.ts` 不在 `git status` 里、且四份文件的前后 sha 逐字相同 ⇒ 产品样例零改动（卡面第 11 格），
本轮所有探针都只在这四份文件上"改完立刻还原"。

## 逐条判据与红因原文摘要

| # | 探针改了什么 | 覆盖面门 s52 | tsc | 新形状门 s55 | 红因（逐字抄自原文） |
|---|---|---|---|---|---|
| A | `DELETE /spaces/{id}` 摘 `satisfies` **并**多一个契约外键 | **0（看不见）** | **0（看不见）** | **1（抓住）** | `SpaceDeleteResult←DELETE /api/v1/spaces/{id}.probeExtraKey：契约 properties 里没有此键（additionalProperties:false）` |
| B | 同一条只删契约必填键（`satisfies` 留着） | — | 2（TS1360） | 1 | `SpaceDeleteResult←DELETE /api/v1/spaces/{id}.engineResidue：契约必填，样例里没有这个键` |
| C | 页宽默认 50→0（越 `minimum:1`） | — | 未跑（dto 里 `limit: number`，0 合法 ⇒ 结构性判不住，见 `packages/contracts/src/shapes/dto.ts:117`） | **1** | `PublicSpacePage←…limit：不满足契约的 minimum=1（实为 0）`、`NotificationHistoryPage←…`、`SpacePage←…`（三个分页壳各判一次） |
| D | 详情路由的样例路径指向列表路由 | — | — | **1** | `GET /api/v1/spaces/{id}：分发器匹配到的是另一条路由（表里 "GET /api/v1/spaces/{seg}"，实际 "GET /api/v1/spaces"）` |
| E | 样例输入表留一个旧路由名 | — | — | **1** | `ROUTE_OVERRIDES 里有对照表没有的键：GET /api/v1/无此路由` |
| F | 摘掉 stdout 编码钉 | — | — | pytest **1** + 原样命令 **1** | `UnicodeEncodeError: 'gbk' codec can't encode character '\u2705'`（判绿末行）；另跑判红那侧：`'gbk' codec can't encode character '\u274c'`（`s55p2_f_red_plain_console.txt`，崩在 `print(f"❌ 覆盖率门判红/判 NOT-PASS（rc={rc}）")` 那一行）⇒ **两侧都补了原文，审查说的"❌ 那侧没有裸读数"已闭合** |
| G | 删掉某条路由的 `paramNames: ["spaceId"],` | — | 0（类型层看不见：paramNames 本来就可选） | **1** | `PATCH /api/v1/spaces/{id}/engine：pattern 捕 1 段，paramNames 只声明 0 个`（旧写法 `if (paramNames?.length)` 会整条跳过这一判据，正是审查点名的洞） |
| H | 把分页 handler 的 `Number(query.get("limit") ?? MOCK_PAGE_LIMIT)` 换成写死 `50` | — | 0（还是合法 number） | **1** | `GET /api/v1/spaces（带 query 的分页回显）：分页 limit 没回显请求值（query 里是 7，响应给的是 50）` |

三点如实：

1. **A 行是 P-124 的正面闭合证明，且这次是在最终字节上**：同一份漂移，STEP-52 的覆盖面门 rc=0、
   `tsc` rc=0，只有新的运行时形状门 rc=1。第一轮那三份 `s55_1_red_*` 出自核对器被改写前的字节，
   留着只为记"改前旧门全绿"的历史对照，不作为闭合证据。
2. **H 第一次跑是 0（假过），不是我写错了断言，是我打错了探针的位置**：锚点原本落在
   `notifications/history` 那个分页壳（`items: [], total: 0`），而我那发回显探针打的是 `GET /api/v1/spaces`——
   改了没被那发探针经过的 handler，红才怪。把锚点挪到 `items: MOCK_SPACES` 那一处才是 rc=1。
   这条按原样记：`rc_h_s55=0` 那一次不算证据，第二次才算；探针打错位置比判据写错更隐蔽，
   因为它给的是"绿"，而绿看起来像"判据没问题"。
3. **C/G/H 三行共同说明这道门比 `tsc` 严**：`limit: 0`、`limit` 不回显、捕获组与参数名脱钩，
   在类型层全是合法的 `number`/合法的可选字段。这正是"运行时形状门"存在的理由——
   契约声明的是**取值与回显口径**，不是类型。
