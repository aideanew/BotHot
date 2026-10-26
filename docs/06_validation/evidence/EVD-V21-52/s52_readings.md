# EVD-V21-52 其余 mock 样例 satisfies 契约类型（执行助手）

平台 @win（Windows 10 x64，Node 24.18、pnpm、便携 PG16.15@5547 自备库），开工 head `b4157a9`
（规划方的 STEP-47 收口批，其父 `f4f0261` 即 STEP-47 代码批）。时间 2026-10-26（Asia/Shanghai）。

## 第 0 步：开工前读规划提交的三条结论（附录 A 第三节第 0 条）

`GET /repos/aideanew/BotHot/actions/runs?head_sha=f4f02615295e98337ccbe33e213b0d4851f39e4e` 匿名现读，
`total_count=3`，三条全部 attempt 1、`status=completed`、`conclusion=success`：

| 工作流 | run id |
|---|---|
| CI | 40203264523 |
| CI-Windows | 40203264350 |
| Security | 40203264404 |

与规划方在 `b4157a9` 里回填的 `EVD-V21-47` §@ci 三个号逐字相同 ⇒ 两侧独立读数一致，队列放行 52。
开工同步核对：`git fetch` 后 `HEAD...origin/main` 为 `0 0`，工作树只含本卡三个未跟踪产物。

## S52.1 先红（覆盖测试）与归一化的两次读数

判据：`MOCK_ROUTES` 每条路由的 pattern 都必须在 `MOCK_CONTRACT_MAP` 里有契约类型名，缺一条即红；
反向（表里登记了但 mock 没注册）同样红。两侧字符串不同形（注册侧是 RegExp 源串、表侧是后端权威
路径串），所以先要归一再能比——**归一化本身是这条判据的成败点**，两次读数都记在这里。

### 第一次读数：归一化写错 ⇒ 假红（原文 `s52_1_red_attempt1_normalized_bug.txt`）

缺失清单把 **22 条全列出来**（含引擎那两条已登记的），不是卡面预期的"缺 20"。两条根因，都在
`normalizeRouteKey` 里：

1. 没剥 RegExp 源串的首尾锚、也没还原 `\/` 的转义反斜杠 ⇒ 注册侧键长成 `GET \/api\/v1\/engines`，
   与表侧 `GET /api/v1/engines` 永不相等。
2. 更隐蔽的一条：**先全局删 `^` 再替换匿名段**，把字符类 `[^/]` 里的插入符也一起删了
   （变成 `([/]+)`），于是 `([^/]+)` 这一步永不命中，带路径参数的路由两侧也永不相等。

这条顺序依赖已写进函数注释（改顺序就红），因为它是"判据自己骗人"的形状：
两侧都归一到了**不可比**的形态，红得很响但红的原因全错。

### 第二次读数：归一化改对后，卡面口径的真先红（原文 `s52_1_red.txt`）

表临时只留引擎两条（STEP-48 已登记的两条）跑 `pnpm exec vitest run tests/s52-mock-contract-coverage.spec.ts`：

- `Test Files 1 failed (1)`、`Tests 1 failed | 1 passed (2)`，命令 rc 非 0（@win，2026-10-26 10:1x）。
- 用例① 红，缺失清单**正好 20 条**：identity 2（`GET /auth/me`、`POST /auth/logout`）、
  public-library 2、ingest 4、notifications 2、spaces 8（含 `POST /spaces`、`GET /spaces`、
  docs 五条、详情、删除）。
- 同一次跑里 `expect(registered.size).toBeGreaterThanOrEqual(22)` 通过 ⇒ 注册侧 22 个归一键彼此不同，
  排除了"归一化把 22 条坍成 1 条导致缺失清单看起来很长但判据空转"这一族假红。
- 用例②（死条目）在同一次跑里绿：表侧只有引擎两条，没有多余登记。

恢复全量 22 条后（本卡最终形态）：该文件 2 条用例绿，见下节 vitest 全量读数。
第 1 轮审查指出"只判 ≥22 判不住坍缩"（23 条坍成 22 也能过），已把这一条换成**三条反坍缩判据**：
归一键数＝注册路由数、注册路由数＝表条目数、绝对下限 22；同时补了第三条用例（表与后端逐条对名）。
处置逐条记在 `review_round1.md`。

## 改动摘要（S52.2–S52.4）

- **新 `apps/web/lib/api/mock-contract-map.ts`**：22 条 `路由 pattern 源串 → 契约类型名`（纯数据，
  逐字镜像后端 `app/contracts/shapes.py` 的 `MOCK_ROUTE_CONTRACTS`，只读）；`_AssertTypesExist`
  元组把 21 个类型名在编译期核对一遍（名字写错 tsc 红）；`normalizeRouteKey` 负责两侧归一。
- **新 `apps/web/tests/s52-mock-contract-coverage.spec.ts`**：三条用例——① 缺登记即红（列缺失清单）
  ② 死条目即红 ③ 表与后端权威源逐条对名。第三条是本卡执行时发现的一个真洞补上的：
  只判覆盖面时，把表里某条的类型名换成**另一个同样存在的契约名**，覆盖面两条仍绿、
  `_AssertTypesExist` 仍绿、`mock-routes.ts` 的 `satisfies` 也仍绿（那里的类型名是就地写的字面量，
  不读这张表）——于是"对照表说了个错的形状"这件事无人管。读数见下节"名对名探针"。
- **`mock-routes.ts`**：22 条路由的样例全部由契约类型约束——命名常量在声明位 `satisfies`
  （`MOCK_ME`、`MOCK_PUBLIC_SPACES`、`MOCK_LINK_RESULT`、`MOCK_RESOLVE_OK`、`MOCK_EXTRACT_OK`、
  `MOCK_LOW_QUALITY`），就地字面量在 handler 返回位 `satisfies`（其余各条）；`sliceMockDocs`
  改成返回契约整页类型。头注释"形状来源"段由"两档口径"改为"22 条全部契约约束 + 对照表唯一来源 + 两道红"。
  引擎两条（STEP-48）形状不变。`sliceMockDocs` 的缺省页宽**保持 100**：`GET /spaces/{id}/docs`
  的后端缺省就是 100（`app/api/v1/spaces.py:211`），与 `/spaces`、`/spaces/public`、通知历史那三条
  走 `limit_offset_query`（缺省 50）不是同一口径——审查者独立复核过这一点，把我准备"顺手对齐成 50"
  的冲动驳掉了。
- **`types.ts`**：15 个与契约同形的手写 interface 改成契约别名（`import type * as Shapes`，
  避开本地同名符号），`Space`/`SpaceDoc` 由此收紧——线上恒有的键不再可选：

| 本地名 | 现在指向 |
|---|---|
| `MeWalletInfo` | `Shapes.MeWallet` |
| `Space` | `Shapes.SpaceView`（`engine`/`engineKbId`/`isPublic` 转必填） |
| `SpaceDetail` | `Shapes.SpaceDetail` |
| `DocStatus` | `Shapes.SpaceDocStatus` |
| `SpaceDoc` | `Shapes.SpaceDocItem`（`category` 转必填） |
| `DeleteDocResult` | `Shapes.DocDeleteResult` |
| `PatchDocResult` | `Shapes.DocCategoryPatch` |
| `BatchDocFailure` | `Shapes.BatchDocFailure` |
| `DeleteDocsBatchResult` | `Shapes.DocsBatchDeleteResult` |
| `RecategorizeDocsBatchResult` | `Shapes.DocsRecategorizeResult` |
| `SpaceDocsPage` | `Shapes.SpaceDocPage` |
| `PublicSpace` | `Shapes.PublicSpaceView` |
| `LinkResult` | `Shapes.LinkResult` |
| `ResolvedArticle` / `ExtractedArticle` / `ExtractedImage` | `Shapes.ResolvedArticleView` / `Shapes.ExtractedArticleView` / `Shapes.ExtractedImageView` |

  语义注释（钱包降级态不得渲成 ¥0.00、`chunks=null` 表示指标不可得不是 0、`total` 与 `items` 同谓词、
  空串=未分类）逐条搬到别名上，没有删。`MeData` 保持原样——它是归一化**视图**不是线上形状。
- **`mock-data.ts`**：`MOCK_SPACES` 两条补 `engine`/`engineKbId`/`isPublic`，`MOCK_DOCS` 六条补
  `category: ""`（空串=未分类，与原行为同形：分类过滤与 `:categories` 枚举都按假值判未分类）。

## P-122 七处逐条对账

| # | 漂移 | 现在 | 证据位置 |
|---|---|---|---|
| ① | `/auth/me` 样例是归一化后的扁平形 | 改为线上嵌套形（`user` + `wallet` 两子对象 + 顶层降级标记），`satisfies MeView`；`normalizeMeData` 两种形态都吃，页面零改动 | 先跑现有用例 `pnpm exec vitest run tests/me-normalize.spec.ts tests/mock-routes.spec.ts` ⇒ **8 + 10 = 18 passed**（@win，改前基线同读数一致）；e2e ② "登录 → 首页已登录（昵称 + 退出）"绿 |
| ② | `/auth/logout` 返回空 | 返回登出回执对象，`satisfies LogoutResult` | `mock-routes.ts` 的 logout handler |
| ③ | `GET /spaces`、`GET /spaces/public` 缺整页三键 | 两条都回 `items/total/limit/offset`，limit/offset **回显请求值**；缺省页宽取后端 `limit_offset_query` 的 50（`apps/api/app/api/deps.py:41`），不写死 20 | `satisfies SpacePage` / `satisfies PublicSpacePage`；反证③ 见下节 |
| ④ | `POST /spaces` 缺 `engine`/`engineKbId`/`isPublic` | 三键补齐（builtin + 与 id 同源的 kb 标识 + 非公共），`satisfies SpaceDetail`（后端创建响应复用详情形状，`app/api/v1/spaces.py:141` 明写） | 反证不重复；键集合由 `satisfies` 钉住 |
| ⑤ | `DELETE /spaces/{id}` 缺 `engineResidue` | 补该键为"无残留"（演示态不调引擎，不可能有残留），`satisfies SpaceDeleteResult` | 反证② 见下节 |
| ⑥ | `GET /spaces/{id}` 未命中 mock 抛 30101 | 改抛线上码 30004 | 后端锚：`apps/api/tests/test_spaces_api.py:239` `test_get_space_invalid_id_maps_30004`；`grep -rn "30101" apps/api/app apps/api/tests` 零命中（限定源码目录复算过一次，不带目录限定时会连 `apps/api/.venv` 里的二进制一起扫——那条命中与本判据无关）。这一处连带出的前端缺陷登记为 P-123，见末节 |
| ⑦ | 手写类型把线上恒有的键写成可选 | `Space.engine/engineKbId/isPublic`、`SpaceDoc.category` 随别名转必填；15 个类型整体别名化 | typecheck 0 错 + 下表调用方修正 |

## 调用方修正（卡面第 10 格允许面：类型收紧后的标注/夹具补默认值，不改渲染逻辑）

改完 `types.ts`/`mock-routes.ts` 后第一次 `pnpm run typecheck` 报 **7 条**（原文
`tsc1.txt`，未入库；都在测试夹具），逐条修法（下表行号 = tsc 报出的位置，改后会位移）：

| tsc 报出行 | 修法 |
|---|---|
| `tests/engine-switcher-states.spec.tsx:61` | 夹具补 `isPublic: false` |
| `tests/r026-doc-batch.spec.tsx:84` | `article()` 的 `category` 由"可能 undefined"改为缺省补空串 |
| `tests/r11-admin-console.spec.tsx:88` | 同上 |
| `tests/r043-spaces-list.spec.tsx:80/90/91` | `MockSpace` 与 `mkSpace()` 补 `engine`/`engineKbId`/`isPublic` 默认值 |
| `tests/r054-space-detail-honesty.spec.tsx:76` | `BASE` 补 `isPublic: false` |

  卡面第 10 格的夹具允许面）：

| 漏项 | 为什么 tsc 看不见 | 修法 |
|---|---|---|
| `tests/r11-admin-console.spec.tsx:94` 的 `SPACES` 两条 admin 夹具缺 `isPublic`（第二条还缺 `engineKbId`） | 该常量无类型标注，消费方 `listAdminSpaces` 的 mock 是**无类型的 `vi.fn()`** ⇒ 赋值不构成对 `AdminSpace` 的检查 | 标成 `AdminSpace[]`（它 extends 已收紧的 `Space`）并补齐三键；这是 ⑦ 想关的那一族在测试面的残留 |
| `MOCK_PUBLIC_SPACES` 在收紧时丢了直接约束 | 它只被 handler 的 `satisfies PublicSpacePage` 间接覆盖：少键会红，但 mock 侧**多写一个契约里没有的键**不会红 | 声明位补 `satisfies PublicSpaceView[]`，与"命名常量在声明位 satisfies"的本卡口径重新一致 |

补一句 `AdminSpace` 的线上形状核实（收紧成契约别名前必须问的问题）：admin 读面与用户读面
**同源同形**——`app/api/v1/admin.py:185` 的说明写着"engine/engineKbId/isPublic + 增量三字段
ownerId/ownerSub/ownerNickname"，构造处在 `app/services/spaces.py:685` 与 `:717` 两支视图里都写
`engineKbId`（缺列回空串），所以 `AdminSpace extends Shapes.SpaceView` 不是把类型编宽，
与线上相符；夹具里那条 `engine: ""` 也是后端会出现的形状（空串而非缺键）。

渲染组件除下面"越界申报"一处外零改动；`app/**`、`packages/contracts/**`、`apps/api/**` 零改动。

## 越界申报（附录 A 第四节第 3 条）

改了什么：`apps/web/components/useSpaceDetail.ts:166` 的入口判断一行，把线上码 30004 并入
"404 语义空态"分支（原来只认 30101 与 10102）。

为什么不改不行：卡面第 6 格与 P-122 ⑥ 要求把 mock 的详情未命中改抛 30004（与后端一致）。
改完后演示态与线上同形，而这一行是它的直接消费方——不改它，`pnpm run test:e2e` 的
`e2e/trunk.spec.ts` ⑦「无效 id 空态」必红（阻塞门禁），三绿拿不到。
现读证据：后端全仓不存在 30101，`GET /spaces/{id}` 未命中的线上码是 30004
（`apps/api/tests/test_spaces_api.py:239-244` 直接把码位钉在断言里）；同仓另有三处
（`PublicLibraryPicker.tsx:66`、`SubscribeShortcut.tsx:53`、`useSubscriptions.ts:135`）
本来就把这两个码并列处理。改动严格限于这一个条件式，无渲染逻辑变化。

副产读数（缺陷证明，非顺手修）：改前 mock 抛 30101 恰好落进这一行，于是**演示态一直显示
"未找到该知识空间"空态，而真后端下同一页面永远落错误横幅**——404 空态对真实链路从未生效过。
已登记 **P-123**（含 `lib/api/spaces.ts:48` 注释仍写 30101/10102 的失真、以及
`types.ts` `ERROR_MESSAGES` 里 30101 这一条僵尸文案），本卡不继续扩大改动面。

## 反证（S52.5，四个域各删一个契约键 ⇒ tsc 红）

脚本逐次"删一键 → 跑 `pnpm run typecheck` → 立刻还原"，结束后按 sha256 证明
`mock-routes.ts` 字节回到原样（`restored sha256 match ... True`，@win，2026-10-26）：

| 域 | 删掉的契约必填键 | tsc rc | 首条报错（行号=探针当时，本卡后续又动过该文件，不要当现读行号用） |
|---|---|---|---|
| identity（logout 回执） | 回执对象改为空对象 | 2 | `TS1360: Type '{}' does not satisfy the expected type 'LogoutResult'`（`mock-routes.ts:329`） |
| spaces（删除空间） | `engineResidue` | 2 | `TS1360: Type '{ ok: true; }' does not satisfy the expected type 'SpaceDeleteResult'`（`:665`） |
| spaces 列表（整页） | `total` | 2 | `TS1360: Type '{ items: SpaceView[]; limit: number; offset: number; }' does not satisfy the expected type 'SpacePage'`（`:563`） |
| notifications（历史页） | `unread_total` | 2 | `TS1360: ... does not satisfy the expected type 'NotificationHistoryPage'`（`:486`） |

四份原文存本目录 `tsc_probe_*.txt`；四次都只报这一条错、还原后再跑 0 错。
这一族读数是卡面验收 ③ 要的"样例删一键 ⇒ tsc 红"，同时也是"旧形状确实不满足契约"的正面证明：
identity / spaces / 整页 / notifications 四域的旧样例形状与 P-122 列的逐条对得上。

### 名对名探针（用例③ 的"改前红"，@win 2026-10-26）

把对照表里 notifications/read 那条的类型名换成**另一个确实存在的契约名**（notifications/history 那个），
其余不动，跑两条命令：

| 命令 | rc | 读数 |
|---|---|---|
| `pnpm exec vitest run tests/s52-mock-contract-coverage.spec.ts` | **1** | 用例③红，diff 精确指出被换掉的那一行；`Test Files 1 failed (1)`、`Tests 1 failed \| 2 passed (3)`（原文 `mirror_name_swap_red.txt`） |
| `pnpm run typecheck` | **0** | 0 错——即"改名漂移"编译期看不见，只靠覆盖面两条用例判不住 |

还原后按 sha256 证明 `mock-contract-map.ts` 字节回到原样（`restored sha256 identical: True`）。
随后 `pnpm run test:unit` 复跑 **52 files / 423 passed**（比改前多 1 条＝新增用例③）。

## 对照表与后端权威源的机器对账

`map_vs_shapes_py_crosscheck.txt`（由临时脚本逐行比对，脚本不入库）：
前端 22 条 ↔ `app/contracts/shapes.py` 的 `MOCK_ROUTE_CONTRACTS` **顺序与内容逐条 same**，
21 个不同契约名（`SpaceDetail` 被 `POST /spaces` 与 `GET /spaces/{id}` 共用），
且这 21 个名字全部能在 `packages/contracts/src/index.ts` 的导出面里找到（脚本核过，零缺失）。

## 所有权与字节面

`git diff --name-only` 只有 10 个跟踪文件：本卡允许面 8 个（`mock-routes.ts`、`types.ts`、`mock-data.ts`
＋ 5 个因类型收紧而改的测试夹具）+ 越界申报 1 个（`useSpaceDetail.ts`）+ P 表 1 个；
另有 2 个新增代码文件（`mock-contract-map.ts`、`s52-mock-contract-coverage.spec.ts`）与本证据目录。
`apps/api/**`、`packages/contracts/**`、`scripts/**` 零命中。
`git diff --stat` 为 183 插入 / 179 删除——工作树里几个文件是 CRLF（本机 `core.autocrlf=true` 的既有
状态，未被本卡改动的 `public-library.ts`、`notifications.ts` 同样是 CRLF），而 `.gitattributes`
的 `*.ts text eol=lf` 把入库字节定为 LF ⇒ 提交后不产生整文件空白重写。

## 本机复跑（@win，按 `.github/workflows/ci.yml` 与卡面第 8 格同序）

- 前端四步（最终形态复跑）：`pnpm run typecheck` 0 错；
  `pnpm exec tsc --noEmit -p ../../packages/contracts/tsconfig.json` 0 错；
  `pnpm run test:unit` **52 files / 423 passed**（含 `s52-mock-contract-coverage.spec.ts` 3 条、
  `mock-routes.spec.ts` 10 条、`me-normalize.spec.ts` 8 条）；`pnpm run lint` 0 警告 0 错误。
  补用例③之前的一次同形读数是 **422 passed**（`s52` 文件当时 2 条）；两次都不许与"三绿"混读——
  最终入库形态是 423。
- mock UI e2e（CI 的阻塞门禁，本机复跑；`rm -rf .next && NEXT_PUBLIC_API_MOCK=true pnpm exec next build`
  后 `PORT=3456 pnpm run test:e2e`，绕开 `prebuild` 的生产守卫与 Next 不按 `NEXT_PUBLIC_*` 失效的构建缓存）：
  - 改前（只做了 ⑥、未改前端分支）：`1 failed / 28 passed / 11 skipped`，红在
    `e2e/trunk.spec.ts:158` 用例 ⑦「无效 id 空态」——定位器等待空态文案超时 10s，原文
    `e2e_mock_before_fix.txt`。这条红同时是 P-123 的缺陷证明。
  - 越界修正后：`31 passed / 0 failed / 11 skipped`，trunk ①–⑨ 全绿（含 ② 登录→已登录、
    ⑦ 无效 id 空态、⑧ 登出、⑨ 链接入库主链路）；11 条 skipped 是真后端档与 admin 四屏的闸门用例
    （`E2E_REAL_BACKEND` 未置 1），原文 `e2e_mock_after_fix.txt`。
- 后端全量基线（本卡零后端改动，仍按附录 A 第五节复跑；逐条 rc、skip 构成、两条红的归因都在
  **`backend_local.md`**，这里只摘结论）：
  - `ruff` 0、`mypy` 0（122 文件）、`alembic heads` 单一头 `ab1006c2a`、
    `gen_contracts --check` 0（契约生成物零漂移）、`check_docs_consistency` 0（含本卡新写的 P 表行）。
  - `alembic upgrade head` 这条**环境缺项红**（rc=1，连 `localhost:5433` 超时）：CI 的 backend job
    在 job 级 env 同时给迁移库与测试库两个变量（`ci.yml:47-51`），我这条链只给了测试 DSN。
    本机 5433 无监听 ⇒ 连接从未建立，没有任何库被动过迁移；如实记红，不写成"通过"。
  - `pytest` 全量：**2 failed, 2464 passed, 6 skipped, 4 deselected**，1809.26s，`TOTAL 88.99%`。
    两条红 = `test_scheduler.py::test_daily_jobs_enqueue_after_0630_with_frozen_clock`
    （固定 id/sub 直插用户，持久库连跑必红 = **P-120 原文**）与
    `test_w2_worker.py::test_hot_cluster_job_consumed_by_worker`（`actual=QUEUED`，
    P-120 裁定行预告的残留取件同族，判**部分确认**，等 STEP-54 修完清场再证）。
    本卡 `apps/api/**` 零改动，两条都不是本卡引入；CI 用新库，`f4f0261` 的 @ci 是 2466/6/0。
  - 模块覆盖率门本机判 **rc=2**：不是达标率问题（全局 88.99% 在阈上），而是这道门在 @win
    拿不到自己的输入——键形与 `_match` 的前导斜杠 needle 不相容，8 条阈值 key 全判"命中 0 个"；
    附录 A 第五节给的命令形式（在 `apps/api` 下不带 `--json`）也走不通。已登记 **P-125**（含逐键实测表）。
- 新增连库用例：无 ⇒ `SKIP_BASELINE_WIN` 不动（起点 692，STEP-47 已抬，本卡不碰该文件）。

## @ci（推送后回填，2026-10-26 11:1x–11:3x @win，Asia/Shanghai）

交付头 `0aa2923`（基线 `b4157a9`，推送前后均 `HEAD...origin/main` = `0 0`）。
三条工作流全部 **attempt 1、status=completed、conclusion=success**：

| 工作流 | run id | 日志级读数（匿名 REST 拿号 + 签名 URL 取 zip 原文） |
|---|---|---|
| CI | 40263352699 | backend **2466 passed / 6 skipped / 4 deselected**（246.92s），`Total coverage: 88.91%`，`skip 门禁：total_skipped=6 baseline=6 pg_unreachable=0`，模块覆盖率门 `✅ 全部模块与全局达标`；frontend `Test Files 52 passed` / `Tests 423 passed`；mock UI e2e `31 passed (1.4m)` |
| CI-Windows | 40263352628 | backend **1780 passed / 692 skipped / 4 deselected**（1149.64s），`windows 门禁：failed=0 total_skipped=692 baseline=692`（零余量，基线不动 ✓）；frontend `52 files / 423 tests` |
| Security | 40263352616 | `pip-audit：🔴 0 / 🟡 0`、`pnpm audit：🔴 0 / 🟡 0`、`trivy：🔴 0 / 🟡 0`、`gitleaks：✅ 未检出明文密钥` |

两条与本机读数的对照，逐条说明而不是并排了事：

- **本机 2464 passed / 2 failed vs @ci 2466 passed / 0 failed**：差的正是那两条 P-120 家族用例
  （固定 id 直插用户 + 残留 Job 被 w2_worker 吃走）。CI 每次新容器新库 ⇒ 不触发；
  这条对照本身就是"属本机持久库问题、不属代码问题"的证据（同树两侧计数只差这两条）。
- **本机 vitest 423 vs @ci（两平台）423**：逐字相同 ⇒ 新增用例③"读后端 `shapes.py` 源文件"在
  Linux 与 Windows 两侧都取到了同一份文件（cwd 相对路径口径成立，`ci.yml` 前端 job
  `working-directory: apps/web`、`ci-windows.yml:289` 同）。
- **本机 mock e2e 31 passed vs @ci `31 passed (1.4m)`**：逐字相同 ⇒ 越界申报那一行确实把
  trunk ⑦ 从红修回绿，且后续的类型层改动（`satisfies`、头注释）没有改变运行时行为。

## 完成判据对照（卡面第 7 格 + 附录 A 第十节格式）

| 判据 | 读数 |
|---|---|
| ① 先红：覆盖测试在只有引擎域登记时红，列出缺失路由数 | ✅ 缺 20 条（原文 `s52_1_red.txt`）；同批另存一次"归一化写错 ⇒ 22 条全列"的假红与根因（`s52_1_red_attempt1_normalized_bug.txt`） |
| ② 改后 typecheck / vitest / lint 绿 | ✅ 0 错 / 52 files 423 passed / 0 警告（本机与 @ci 两平台同数） |
| ③ 反证：任一域样例删一键 ⇒ tsc 红（≥3 个域） | ✅ 四个域各一次（TS1360 四份原文）+ 名对名探针一次（用例③红、tsc 绿）+ 摘 satisfies 探针一次（两道门都绿 ⇒ P-124） |
| ④ 三绿 | ✅ 见上表，同一 head `0aa2923`，attempt 1 |
| P-82 / P-122 闭合 | ✅ 见 P 表末两行（本卡收口批登记） |
| 卡面三级任务逐条判定 | ✅ S52.1–S52.5 全部有读数，勾选见卡面 |
| 未做 / 交回 | P-123（前端错误码对账 + 两处僵尸文案）、P-124（22 条运行时键集合门）、P-125（模块覆盖率门 @win 不可复算）；本卡零后端改动，`SKIP_BASELINE_WIN` 不动 |

## 推送凭据口径（安全铁律对账）

GCM 本机已无可用的 `github.com` 凭据（`credential.interactive=false` 下报
"unable to get password from user"，非交互模式不会弹窗）。按项目单页授权改走内嵌 PAT：
令牌由脚本在**进程内**从单页读出，写入 `/tmp` 下一次性凭据文件（`stat` 读到 mode=600），
用 `-c credential.helper=store --file=…` 消费，**同一条命令内 `rm -f` 并核实文件不存在**；
remote URL 未动（`git remote -v` 仍是无凭据的 https 地址），推送输出经
`sed 's/[A-Za-z0-9_]{30,}/***REDACTED***/g'` 兜底过滤，全程无一处回显令牌正文。
第一次尝试在代理上撞到 `schannel: failed to receive handshake`（TLS 抖动），
原样重试一次即成功（`b4157a9..0aa2923`），未改任何 git 配置、未走直连兜底。
读 @ci 日志时同样只用进程内令牌，且不跟随 `/logs` 的 302 转发凭据（先取 Location，再无凭据取签名体）。
