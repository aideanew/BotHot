# STEP-04 清单资产键对齐与清单状态机

> 基线 main@61358c3｜状态：🟡 进行中（2026-10-17 起）——**S4.1 / S4.2 / S4.3 / S4.4 已交付**：
> `ab1006c1a` 形状 + 形状门（7 条含 7 发反证）+ 写侧算 `article_key`（URL 变了键跟着重算）+
> 入列同事务写 `JobItem.manifest_id` 并置 `ENQUEUED` + Diff 改按 `article_key` 减资产与减在途
> （S4.1.2 的同轮收敛）+ worker 终态回写 `INGESTED/FAILED` + `recover_stale` 回退超时无人认领的
> `ENQUEUED`。**剩 S4.5.1 验收**（P-2 复跑 = 0、全量双环境 0 failed、CI 双绿），只能由 `@ci` 判。
> S4.1.2 那句「同篇短链/长链两形态只入列一次」的成立条件写在 **D-V9-06**：短链与长链的
> `article_key` 本来就分属 `s:`/`b:` 两支、永不相等，靠既有表 `short_link_maps` 把短链那支并到
> 长链键上才谈得上减资产与减在途；**该表还没有映射行时两种形态各排一次队**（首抓后就位，一次性代价）。
> 本机证据面：`test_manifest_state_machine.py` **23 条**、`test_manifest_asset_alignment.py` **15 条**
> （其中 5 条连库用例本机 skip，等 @ci），合跑 `33 passed / 5 skipped`；
> 三发的变异反证各自咬住（并键关掉 ⇒ 2 条红；回写挪到 commit 之后 ⇒ 2 条红；空值守卫删掉 ⇒ 1 条红）。
> 遗留后果与裁决写在 **D-V9-05**（在途面按键减、NULL 键行停入列并计数告警、非法边不抛穿 worker）
> 与 **D-V9-06**（跨键空间并键的真源与局限），重试面未接四态已发布为 **P-18**；
> 并键的短链 token 判定在 `kb.py` 侧还有第二套口径（子串判 host），已发布为 **P-20**（不在本卡所有权内）。历史行文（含"只交付形状层"那段）按当时读数保留，不回改。

| 字段 | 内容 |
|---|---|
| 1 归属（执行者） | 执行Agent |
| 2 验收者（与执行者分离） | 规划方(Hark)，只输出 PASS/FAIL/UNKNOWN |
| 3 难度 / 里程碑 | 高 / M1 |
| 4 来源 | V0.7.0 docs/任务规划V0.7.0/steps/STEP-04-清单资产键对齐与清单状态机.md |
| 5 目标 | 同来源卡；本版不改目标 |
| 6 输入 | 来源卡『输入』+ 本版 01 事实基线（行号以 61358c3 现读为准） |
| 7 输出路径 | 同来源卡 |
| 8 三级任务 | 沿用来源卡编号 Sx.y.z，全文见来源卡；本版未改动 |
| 9 验收 | 来源卡验收 + 当前基线 CI 双绿 + skip≠pass |
| 10 命令 | 来源卡命令；全量回归 `cd apps/api && uv run pytest -q -rs` |
| 11 证据 | docs/任务规划V0.8.0/evidence/61358c3-04/ |
| 12 允许修改 | 同来源卡所有权矩阵（本版 04 §4） |
| 13 禁止修改 | 他卡所有路径；迁移目录（需 DDL 停转 ADR）；历史规划结论 |
| 14 依赖 / 阻塞 | 02、03 / D-V3-01 |
| 15 档位 | T2 |
| 16 升级条件 / 规模 | 来源卡行号漂移>3 处或判据不可满足 ⇒ 停并上报规划方 / ≈1.5 人日 |

## 本版（V0.7.0 → V0.8.0）变更

- 基线改为 61358c3；执行前先现读行号，禁止照抄来源卡读数。
- 所有新增证据件入库前必须 gitleaks 零新增（G-PLAN）。
- 依赖更新为：02、03。

## V0.9.0 → V0.10.0 本卡变更（基线 main@81cb997）

- 本版无实质变更；执行前现读行号（基线 81cb997，自 53ebc4a 起业务代码零改动）。

## 裁决已签（V0.11.0 第四节第 2 步 · 2026-10-15 12:04）
| 项 | 变化 |
|---|---|
| D-V2-02 | 已签 A：`article_key` 列 + `job_items.manifest_id` + 四态 `DISCOVERED→ENQUEUED→INGESTED/FAILED`（stale 回退 DISCOVERED）。**新增硬要求**：迁移必须带 `downgrade`，且在 CI ubuntu 上跑 `upgrade→downgrade→upgrade` 往返 |
| D-V3-01 | Diff 判据改用 `article_key`，渠道 id 不参与跨层匹配 |
| 验收面 | 本卡 Done 只能由 `@ci` **ubuntu-latest** 判定；`@win` 读数只算开发烟测，`@linux` 为依赖机本地验证 |
| 标签 | 依 D-V6-01，本卡 `@dep` 已全部改写为 `@linux`/`@ci` |

## 本卡口径更正（2026-10-17，S4.2 交付与其补完轮）

四条都是"卡面写的与仓库现读不符"，按现读改卡、不改代码去凑卡：

| # | 卡面原说 | 现读 | 处置 |
|---|---|---|---|
| C-1 | 所有权列 `packages/contracts/src/subscription/dto.ts（生成）` | `ArticleManifest` **不在 TS 契约生成集里**：`grep -rn "^export interface" packages/contracts/src/*/dto.ts` 无该模型，`subscription/dto.ts` 也不含它。S4.2 唯一的契约落点是 `ingest/dto.ts` 的 `JobItem.manifest_id: string \| null`（+1 行） | 契约层的 `article_key` 目前只在 pydantic 侧（`app/contracts/collection.py`，形状门 `test_placeholder_values_are_not_valid_keys_and_the_asymmetry_is_deliberate` 判它必填）。**要不要把 ArticleManifest 纳入 TS 生成集**是新增裁决点，归 01（契约冻结）判，不在本卡偷做 |
| C-2 | 「迁移必须可 downgrade，并在 CI ubuntu 上跑往返」（D-V2-02 硬要求，卡面 §1 亦列为验收） | 该步 **2026-10-17 之前无人执行**：`.github/workflows/` 全量搜 `downgrade` 零命中，CI 只有 `upgrade head` | 已补：`ci.yml` backend job 新增 "Migration roundtrip (upgrade head → downgrade -1 → upgrade head)"。这条改动**越出本卡所有权**（CI 由 00C/00E 家族持有），按"裁决已签而执行面缺失"处理，越界记录在 `10-…第三批.md` §10.2 |
| C-3 | 卡行 13「禁止修改：迁移目录（需 DDL 停转 ADR）」与来源卡所有权「`apps/api/alembic/versions/ab1006c1a_*.py（新）`」 | 两条互相顶：本卡的 S4.2.1 就是**要**新增一个迁移文件，而 D-V2-02 已签该迁移的形状 | 按来源卡所有权 + 已签裁决执行（新增文件不等于改既有迁移）。**请规划方裁定**行 13 是否应改写为"禁止修改已入库迁移的既有步骤" |
| C-4 | 卡面 §1 的 `P-2` = 已 READY 篇下轮 Diff 新增数应为 0 | 同号在 00-README §4 = glossary 锚漂移、在 02 §1 = M-2 多源串号 | 三套编号并存，不改号（重编会撞歪九份执行记录的交叉引用）；引用一律带来源标注，声明见 `00-README.md` §4 抬头 |
| C-5 | 所有权矩阵的 W 列只点名 `manifest.py / subscription.py / job_worker.py / entities.py` | S4.4 落地必然还要动两处：`app/services/state_machine.py`（加 `"manifest"` 域——四态迁移表的既有真源，不加就等于在 manifest 里另养一份迁移表）与 `app/core/config.py`（卡面 S4.4.3 自己点名的 `manifest_enqueued_ttl`） | 两处都在 04 §5 的 **API 列**（`apps/api/app/services/**` 是整列所有权，`app/core/**` 未列入矩阵），所以**不构成跨列越界**，但确实超出本卡"点名的函数"清单——按 00W 的跨所有权先例在此声明，请规划方复核矩阵是否该把 `app/core/config.py` 补进某一列 |

