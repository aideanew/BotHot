# STEP-56 契约覆盖面孤儿判据（P-126）+ 两处文档纠真

> 基线 main@97c929e｜状态：⬜ 执行助手｜裁决 D-V21-16

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手 Agent-Guard（S56.4 Agent-Doc） |
| 2 来源 | P-126；STEP-53 复查遗留两处文字 |
| 3 目标 | 契约里任何一个 def 如果既没有真端点反向核、也不被另一个"被核过的 def"用 `$ref` 引用，测试就红；引擎域与 shapes 域用同一张覆盖面表 |
| 4 输出 | **S56.1** 新静态守卫（放在 `apps/api/tests/test_shapes_response_contract.py` 或新文件 `test_contract_def_coverage.py`）：读 `packages/contracts/schemas/{engine,shapes}.schema.json`；"已核集合"＝两域真端点反向核用例实际覆盖的契约名（从两个测试模块里现读的名字表，不手抄）；沿 `$ref` 闭包求可达集；断言 `全部 def − 可达集 == ∅`，红时打印孤儿名。**S56.2** `test_engine_response_contract.py:60` 的子串判据换成与 `test_shapes_response_contract.py:88` 同形的正则。**S56.3** `test_contract_jsonschema.py:274` 由"交集比对"改为"名字集相等 + 逐个比对"。**S56.4** `02-需求复核与辩证分析.md:29` 的"24 条"改 22；`EVD-V21-47` 不回改原文，在该目录新增 `ERRATA.md` 一行注明行号漂移（43→50）及原因 |
| 5 验收 | ① 先红：在 shapes.py 临时加一个无人引用的 def 并重新生成 ⇒ 新守卫红、旧门全绿（原文入证，sha 还原）② 删掉 engine 反向核两条连库用例 ⇒ 新守卫红 ③ S56.3 改后若现有产物真有名字集不等 ⇒ **不放宽**，登记 P 号交回 ④ 全量 + 三绿 |
| 6 允许修改 | `apps/api/tests/**` 中上述三个测试文件及新文件；S56.4 两处文档 |
| 7 禁止修改 | `apps/api/app/**`、`packages/contracts/**`、`scripts/gen_contracts.py` |
| 8 规模/档位 | ≈0.4 人日｜sonnet（S56.4 haiku） |
| 9 熔断 | 同判据 2 次 FAIL ⇒ 停 |
| 10 SKIP_BASELINE_WIN | 新守卫不连库则不动；若连库按测量值抬 |
