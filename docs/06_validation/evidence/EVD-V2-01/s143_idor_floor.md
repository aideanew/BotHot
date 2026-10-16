# S1.4.3 前半批：IDOR 的静态底线抓到两条真实越权（并修好），连库矩阵发布为 P-11

批次：`STEP-01` S1.4.3（越权用例生成）。
基线：`main@6ee9682`。读数标机器位（`@win` = 本机 Win10 + `apps/api/.venv`；`@ci` = GitHub Actions ubuntu）。

---

## 1. 这一批交付了什么（以及为什么分两半）

冻结稿 `docs/任务规划V0.12.0/contracts/identity.schema.json#/x-idor-checklist` 只有两句话，
但它对测试提的要求是**可机械核对**的：

1. 凡路径含 `{space_id}` / `{job_id}` / `{doc_id}` 的端点，必须证明「属主 = 当前 sub」或「rank ≥ operator」，
   二者皆无 → 403(10004) / 404(30004)；
2. 必须为**每个**此类端点生成一条「A 访问 B 的同一 id」用例。

来源卡 `docs/任务规划V0.7.0/steps/STEP-01-采集域契约冻结.md:67-70` 又加了两条纪律：
清单**由路由表枚举生成，不得手写**（S1.4.3.2），以及**反证**——摘掉属主校验至少一条用例要红（S1.4.3.3）。

我把能做到本机验证的那半做了（枚举 + 静态底线），把必须连库的那半发布为 P-11 而没有塞一个空壳进 CI：

- 本机 `5432/5433` 现读均拒连（`socket.connect` TimeoutError，探针 `@win`），
  `conftest.py:100-128` 的 `db_session` 据此 skip；
- 31 条参数化用例如果只有骨架，CI 里要么 error、要么**全 skip 变成假绿**——
  后者正是 U-20 记过的形状（skip ≠ pass）。所以宁可发布，不可粉。

## 2. 静态底线抓到两条真实越权（这是本批的实际产出）

新文件 `apps/api/tests/test_idor_matrix.py` 的 `_identity_usage()` 用 AST 读处理函数：
声明了 `Depends(get_current_user_id)` 却在函数体里一次都不引用的 ⇒ `UNUSED`。

现读结果（`@win`，探针 `.staging/idor_usage.py`）：**31 个受约束的操作里 2 个是 `UNUSED`**——

| 端点 | 现场 | 后果（我读代码确认，不是推断） |
|---|---|---|
| `POST /api/v1/spaces/{space_id}/docs`（`app/api/v1/spaces.py:377`） | 形参 `_user_id` 挂身份依赖，函数体只调 `svc.ingest_url(space_id, payload.url)` | `app/services/kb.py:211` 的 `_ingest_url_inner` 只查 `space is None`，**从不比较 `space.user_id`** ⇒ 任意登录用户可往他人空间写入，并触发计费抓取（TikHub/微信 HTML 详情都是真网络请求） |
| `GET /api/v1/spaces/{space_id}/docs/{doc_id}/status`（`spaces.py:417`） | 同上 | `kb.py:538` 的 `get_doc_ingest_status` 查了 `doc.space_id != space_id`（防跨空间猜 id），但同样不查空间属主 ⇒ 返回体带 `langbotFileId`（引擎侧句柄）与状态，是跨租户的存在性 + 状态泄露 |

两条洞都不是"理论风险"：同域其它端点（`docs:batch`、`docs/{doc_id}` 的 DELETE/PATCH、批量删除）
都有 `owner` 判据并发 30004，唯独这两条漏了——`services/spaces.py:313-322` 的
`_delete_doc(owner=None)` 甚至已经把"`owner=None` 表示无归属约束（`/admin` 跨用户路径）"写成了本仓库的既有约定。

**修复**（沿用同一条既有约定，不新增抽象）：

- `kb.py::ingest_url` / `_ingest_url_inner` / `get_doc_ingest_status` 增 `owner: str | None = None`，
  非空时 `space.user_id != owner` ⇒ 与"不存在"同一个 `ResourceNotFoundError`（30004，不泄露存在性）；
- `spaces.py` 两条路由把形参从 `_user_id` 改成 `user_id` 并透传 `owner=user_id`，docstring 补上越权口径；
- 后台调用者**故意不传**：`services/job_worker.py:137`（逐篇消费，无 HTTP 调用者）与
  `services/scheduler.py:207`（日报前兜底重算）保持 `owner=None`，行为逐字不变。

## 3. 反证与它的边界

- 静态面的反证：`test_wiring_guard_is_falsifiable` 用三个合成处理函数跑同一判据，
  声明不用 ⇒ `UNUSED`、透传 ⇒ `threaded`、`require_roles` ⇒ `role`。三条里任何一条读成别的值，这条守卫就是装饰。
- 枚举的反证：`test_route_enumeration_covers_the_openapi_surface` 用 OpenAPI 面做交叉核对
  （现读：OpenAPI 88 个操作，枚举 93 个，差集恰好是 `/docs`、`/docs/oauth2-redirect`、
  `/openapi.json`、`/redoc`、`/metrics` 这 5 个不入文档面的路由）。
  这条同时守着本版 FastAPI 的 `_IncludedRouter` 陷阱：`app.routes` 一层读不出 `path`，
  照朴素写法读会得到 **0 条**带路径参数的路由、整张矩阵静默变空。
- 期望码的反证：`test_denial_vocabulary_comes_from_the_frozen_draft` 的判据**从稿面文本读**
  （403/404/10004/30004 必须出现在 `x-idor-checklist` 里），不是我把常量写死了再说一遍。
  顺带钉住一条来源卡与稿面的差异：来源卡写「404(30001/30004)」，而 30001 是
  `SpaceNotFoundError`（`app/core/errors.py:152`），这些路由并不发它；把 30001 也当合法出口
  等于合并"空间不存在"与"不属于你"两种语义——稿面刻意用同一个 30004 来不泄露存在性。
- **边界（必须说清）**：AST 底线是**下界**，不是安全证明。它只排除"身份被丢弃"这一类；
  `threaded` 之后有没有真的比较 `space.user_id`，静态面不知道，也不假装知道——那是 P-11 的连库矩阵要判的。

## 4. 读数

- `pytest tests/test_idor_matrix.py tests/test_collection_contract.py -q` → **179 passed** `@win`
  （其中本批新文件 **10 条**，`test_collection_contract.py` 169 条）
- `ruff check tests/test_idor_matrix.py app/services/kb.py app/api/v1/spaces.py` → `All checks passed!` `@win`
- `mypy tests/test_idor_matrix.py app/services/kb.py app/api/v1/spaces.py` → `Success: no issues found in 3 source files` `@win`
- 受影响面的既有测试：`pytest tests/test_be02_engine_routing.py tests/test_idempotency_lock.py tests/test_spaces_api.py -q`
  → **26 passed, 16 skipped** `@win`（182.91s；16 条 skip 全部是连库面，本机无 PG）
- 枚举现读（`@win`）：路由 93、带路径参数 47、落在稿面规则内 31（admin 9 / 非 admin 22）、
  规则外的属主 id 操作 16

## 5. 我**没有**做什么

- 没有做 A-vs-B 的逐端点 HTTP 用例（P-11），也没有为此写一个会在 CI 里 error 或全 skip 的骨架；
- 没有扩 `x-idor-checklist` 的参数集（P-12 属裁决，实现者没资格替合同加面）；
- 没有跑全量后端套件复验这次服务签名变更（本机无 PG；`@ci` 读数待推送后取 run id + head_sha + conclusion）；
- 没有做 S1.4.3.3 要求的**动态**反证（摘掉属主校验 ⇒ 用例变红）——它依赖 P-11 的连库矩阵才能跑；
  本批只有静态反证（`test_wiring_guard_is_falsifiable`），两者不是同一件事，我不把它当同一件事记账。

---

## 6. 独立验证返工（第十一轮）：修复是真的，但**修复本身没有反证**

验证者（基线 `196a808`）先证实了 §2 的事实链：`git show 6ee9682` 里两条路由的 `_user_id` 确实零引用、
`kb.py` 三处只查 `space is None`；修复**完整**——owner 判据是 `_ingest_url_inner` 的第二条语句，
在 resolve/短链映射/落库之前，两条出口（不存在 / 不属于你）走同一个 `ResourceNotFoundError`；
其它调用者（`job_worker.py:137`、`scheduler.py:207`）保持 `owner=None` 属实；
`ensure_kb` 的两个调用点都在门后。**没有发现第二条同类洞**：22 条 `threaded` 逐条进服务追，
`spaces.py` 177/236/325/440/486/689/755/781、`jobs.py:64`、`subscription.py:206/280/287/499`、
`engines.py:169-170` 都在真比 `user_id`。六组数字（93/47/31/9+22/16/88）逐一复测一致。

它抓到三条"前提坏了还能读绿"的守卫，三条都是我的：

| 抓到的 | 实测 | 处置 |
|---|---|---|
| G3 **全仓库没有一条用例能证明 owner 门存在** | 把 `kb.py` 的 owner 判据整行删掉，本机可跑的整套测试仍全绿（路由级用例要 PG ⇒ skip；服务级用例全以 `owner=None` 调用） | 新增 `test_owner_gate_rejects_a_stranger_without_a_database`（桩 repo，四向：他人空间拒 / owner 相符过门 / `owner=None` 过门 / 不存在与不属你同码）。**并做了变异实测**：临时删掉两处 owner 子句 ⇒ 该条立刻红（`1 failed, 13 passed`），还原后 `14 passed`，`git status` 对 `kb.py` 干净 |
| G1 `test_denial_vocabulary…` 是常量对字面量 | `DENIAL_STATUSES == {403, 404}` 永真；`"403" in blob` 会被 `24030` 这类长数字串喂饱 | 改为从稿面抽出所有 3–5 位数字串，先要求集合恰为那四个（多一个少一个都红），再**由它推导**两个常量 |
| G2 OpenAPI 交叉核对是单向的 | 一只整组 `include_in_schema=False` 的路由器会**同时**从两侧消失，守卫仍绿 | 新增 `test_enumeration_accounts_for_every_registered_router`：对 `APP_ROUTERS`(现读 15 只) + `metrics_router` 逐只数操作 ⇒ 89，枚举 93 = 89 + 4 个文档路由 |
| G3' HTTP 层可能吃 `owner=None` 默认值 | 现有 AST 底线只查"路由引用了参数"，把 `user_id` 打进日志也算 `threaded` | 新增 `test_http_routes_never_rely_on_the_fail_open_default`：AST 扫 `app/api/v1/**` 对 owner 门方法的调用，必须显式 `owner=`；同时断言**扫到的调用数 ≥ 2**，防"空扫=绿" |

另有一条我原来没写的**过度声称**：`PATCH /spaces/{space_id}/public` 的门不是 `space.user_id`，
而是 `PUBLIC_ADMIN_ALLOWLIST` + `owner_type == "system"`（`services/public_library.py:34-43`）。
它不是 IDOR（非 allowlist 者对系统空间一律拒），但我的守卫把它读成 `threaded` 属于"用了身份 ≠ 按属主判"。
处置是把它列进 `NON_OWNER_ROLE_GATED` 并加一条守卫：这张表里的端点必须仍在清单内、且守卫仍把它读成
`threaded`——**让下界这个词不再误导**，而不是假装 AST 能看出机制。

`owner=None` 的默认值我**保留**（不改必填）：`services/spaces.py::_delete_doc` 已定了同一条约定，
本仓库口径一致比"这一条更严"更有价值；真正的风险面是"以后新路由忘了传"，那由 G3' 那条静态守卫拦。

读数（`@win`）：`pytest tests/test_idor_matrix.py -q` → **14 passed**（原 10，+4 条反证）；
变异实测 → **1 failed, 13 passed**；`ruff check tests/test_idor_matrix.py` 干净、
`mypy tests/test_idor_matrix.py app` → `Success: no issues found in 113 source files`；
合跑 `test_idor_matrix.py + test_collection_contract.py` → **183 passed**。

状态：S1.4.3 的**静态面已带反证**（含"修复本身"的反证），连库面仍是 P-11；
`kb.py` 的 owner 门在本机可跑范围内现在能被抓住，但路由级 A-vs-B 证据仍然只有 `@ci` 能给。
