STEP-55 反证批第一轮（已被 s55_probe_readings.md 的最终字节批次取代，留档）
==========================================================================

留这一份的唯一理由：**驱动原文里那次"旧门全绿"的对照是在第一版核对器上取的**，而第二轮的 A/B 两行
虽然在同一份 `mock-routes.ts` 上（sha `afff9029…` 前后相同），核对器本身已经变了三轮。
两份都在，读者可以自己比"改前旧门看不见"这一半在两版核对器上的表现。
闭合证据以 `s55_probe_readings.md`（A–H 批）为准，本文件不作判据。

时间 2026-10-26 14:24～14:29，@win；当时的字节：
`s55-mock-runtime-shape.spec.ts` sha `51acc0eb4777ef47`、`check_module_coverage.py` sha `a49c45075c3842dd`、
`mock-routes.ts` sha `afff902942a71965`。

驱动原文（MUTATED / rc / RESTORED）：

```
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
MUTATED d_route_id -> s55-mock-runtime-shape.spec.ts sha a75c1aa315056904 (was 51acc0eb4777ef47)
rc_d_s55=1
RESTORED d_route_id sha 51acc0eb4777ef47 == 51acc0eb4777ef47 -> True
MUTATED e_stale_override -> s55-mock-runtime-shape.spec.ts sha 489c0bf3c5a601ab (was 51acc0eb4777ef47)
rc_e_s55=1
RESTORED e_stale_override sha 51acc0eb4777ef47 == 51acc0eb4777ef47 -> True
MUTATED f_encoding -> check_module_coverage.py sha 9af5c2c6554c164f (was a49c45075c3842dd)
rc_f_pytest=1
RESTORED f_encoding sha a49c45075c3842dd == a49c45075c3842dd -> True
=== 还原后的工作树 ===
 M apps/api/tests/test_module_coverage_gate.py
 M apps/web/lib/api/spaces.ts
 M apps/web/lib/api/types.ts
 M scripts/check_module_coverage.py
?? apps/web/tests/s55-mock-runtime-shape.spec.ts
?? docs/06_validation/evidence/EVD-V21-55/
```

原文产物：`s55_probe_a_s52.txt`、`s55_probe_a_tsc.txt`（0 字节＝跑了且零错）、`s55_probe_a_s55.txt`、
`s55_probe_b_tsc.txt`、`s55_probe_b_s55.txt`、`s55_probe_c_s55.txt`、`s55_probe_d_s55.txt`、
`s55_probe_e_s55.txt`、`s55_probe_f_pytest.txt`。
第一轮没有 G/H 两条（捕获组计数与分页回显那两道钉是第二轮审查后才加的），也没有 F 的判红那侧裸读数。
