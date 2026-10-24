# STEP-47 其余 mock 域的响应形状契约（P-82 第二刀）

> 基线 main@9028b89｜状态：⬜ 规划方待做（STEP-46 @ci 三绿后开工）｜版本 V0.21.0

| 字段 | 内容 |
|---|---|
| 1 归属 | **规划方**（Contract 列；与 46 同模式） |
| 2 切片 | SL-SHAPE |
| 3 来源 | P-82；mock 表 24 条路由（`apps/web/lib/api/mock-routes.ts` pattern 列表） |
| 4 目标 | mock 表里每条路由对应的线上 `data` 形状都在 `app/contracts/` 有唯一源并出 TS |
| 5 输入 | `app/api/v1/{auth,spaces,resolve,extract,system}.py` 的 `success(data=...)` 点及其 service 返回；前端 `lib/api/types.ts` 的 `MeData`/`PublicSpace`/`LinkResult`/`ResolvedArticle`/`ExtractedArticle` 等 |
| 6 输出 | 新契约模块 `app/contracts/api_shapes.py`（或按域拆，开工时定，以生成器 `$defs` 无冲突为准）+ 对应稿 `docs/任务规划V0.12.0/contracts/<域>.schema.json`；`CONTRACT_SCHEMA_MODULES`/`CONTRACT_TS_DOMAINS`/`test_contract_jsonschema.DOMAINS` 同批登记；每域一组反向核用例 |
| 7 验收 | ① 每条 mock 路由在登记表里能找到契约类型（机器表：路由 pattern → 契约名，测试逐条断言非空）② 每个契约类型至少一条真端点反向核 ③ gen --check、契约比对、全量三绿 |
| 8 命令 | 同 46 第 8 格 + 新增用例文件 |
| 9 证据 | `EVD-V21-47/` |
| 10 允许修改 | `apps/api/app/contracts/**`、`scripts/gen_contracts.py`、`packages/contracts/**`、稿目录、`apps/api/tests/test_*_response_contract.py`、`test_contract_jsonschema.py` 的 DOMAINS 表、`ci-windows.yml` SKIP 基线 |
| 11 禁止修改 | 任何路由与 service 的返回值（发现后端形状不合理 ⇒ 登记 P 号，不顺手改） |
| 12 依赖 | STEP-46 ✅@ci ｜ Blocks：STEP-52 |
| 13 档位 | opus |
| 14 升级条件 | 某端点 data 在不同分支返回不同形状（联合形）且无法用 `anyOf` 如实表达 ⇒ 停，登记 P 号裁定 |
| 15 规模 | 大，≈1.5 人日（拆三批：identity+notifications / spaces / docs+resolve+extract） |
| 16 熔断 | 同判据 2 次 FAIL ⇒ 停 |

## 三级任务
1. [ ] **S47.1 identity + notifications**：`MeData`、logout 结果、notifications history（分页壳）与 read 结果
2. [ ] **S47.2 spaces**：list（limit/offset 分页壳）、public、detail、create、patch、delete、links
3. [ ] **S47.3 docs + resolve + extract**：docs list/categories/patch/delete/recategorize/status/create(202)、resolve、extract
4. [ ] **S47.4 路由→契约登记表**：`packages/contracts` 外的一张机器表（放 `apps/web/lib/api/mock-contract-map.ts` 由 STEP-52 消费），本卡只出契约名清单写进证据
5. [ ] **S47.5** @ci 三绿
