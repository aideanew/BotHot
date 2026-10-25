# STEP-47 其余 mock 域的响应形状契约（P-82 第二刀）

> 基线 main@9028b89（开工现读 bfd6d82）｜状态：✅ 代码已交付（2026-10-25，规划方；@ci 待回填）｜版本 V0.21.0｜裁决 D-V21-08～10

| 字段 | 内容 |
|---|---|
| 1 归属 | **规划方**（Contract 列；与 46 同模式） |
| 2 切片 | SL-SHAPE |
| 3 来源 | P-82；mock 表 22 条路由（`apps/web/lib/api/mock-routes.ts` pattern 列表；原记 24 为口误，现读 22，其中引擎 2 条已由 46 做） |
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
1. [x] **S47.1 identity + notifications**：`MeView`（含 `MeUser`、开放的 `MeWallet`）、`LogoutResult`、`NotificationHistoryPage`/`NotificationItem`、`NotificationReadResult`
2. [x] **S47.2 spaces**：`SpacePage`/`SpaceView`、`PublicSpacePage`/`PublicSpaceView`、`SpaceDetail`/`SpaceStats`（create/get/patch 三处同形）、`SpaceDeleteResult`、`LinkResult`
3. [x] **S47.3 docs + resolve + extract**：`SpaceDocPage`/`SpaceDocItem`/`SpaceDocStatus`、`DocCategoryList`、`DocCategoryPatch`、`DocDeleteResult`、`DocsBatchDeleteResult`/`BatchDocFailure`、`DocsRecategorizeResult`、`IngestAccepted`/`DocIngestState`/`DocIngestStatus`、`ResolvedArticleView`、`ExtractedArticleView`/`ExtractedImageView`
4. [x] **S47.4 路由→契约登记表**：后端一侧 `MOCK_ROUTE_CONTRACTS`（`app/contracts/shapes.py`），测试 `test_mock_route_table_matches_the_frontend_one_to_one` 按前端分发器"首个命中"同序逐条钉住 22 条；前端 `mock-contract-map.ts` 由 STEP-52 照它写
5. [ ] **S47.5** @ci 三绿（推送后回填）

## 交付摘要（2026-10-25）
- 模块：单模块 `apps/api/app/contracts/shapes.py`，域名 `shapes`（D-V21-08）；稿 `docs/任务规划V0.12.0/contracts/shapes.schema.json`；产物 `packages/contracts/schemas/shapes.schema.json`、`packages/contracts/src/shapes/dto.ts`；`index.ts` 导出 30 个类型。
- 登记：`CONTRACT_SCHEMA_MODULES`、`CONTRACT_TS_DOMAINS`、`test_contract_jsonschema.DOMAINS`、`test_collection_contract` 的域表同批加 `shapes`（后者不在第 10 格原列，越界申报见证据）。
- 反向核：`apps/api/tests/test_shapes_response_contract.py` 17 条（6 条牙齿/机器表 + 7 条连库 + 3 条桩端点 + 1 条静态覆盖守卫）；每个响应契约至少一条真端点核过，可选键（`providerUnreachable`）、数组元素（`failed[]`、`images[]`）都要求真被吐出来过一次。
- 后端路由与 service 零改动。新登记 P-121（钱包透传）、P-122（前端漂移清单，交 52）。
- 升级条件（第 14 格）未触发：`/auth/me` 三分支是"可选键"不是联合形。
