# EVD-V13-14a · STEP-14a 管理端后端补齐（分页统一与 admin 聚合）

> 卡面：`docs/任务规划V0.13.0/steps/STEP-14a-管理端后端补齐-分页统一与admin聚合.md`
> 基线：`b16e2ee`（队列⑭ 收尾后）。本文件先落 S14a.1（现状表 / 映射 / 差异表），实现切片随后追加。
> 卡面字段 11 的证据路径 `docs/任务规划V0.8.0/evidence/61358c3-14a/` 本仓从未建过（P-58/P-65 同形）⇒ 落本目录。

## 1. S14a.1.1 六组端点现状（逐条现读，脚本从 `admin.py` 的路由块直接抽）

抽取口径：从每个 `@router.*` 装饰器到下一个装饰器之间的函数体里读 `require_roles(...)`、
分页形参与响应 `data` 的键。**不是照卡面抄**，也不是照 docstring 抄（docstring 会过期）。

| # | 端点 | 角色门 | 分页形参 | 响应 `data` 形状 | 是分页清单吗 |
|---|---|---|---|---|---|
| 1 | `GET /admin/engines/keys` | operator | 无 | `{masterKeyConfigured, items[]}` | ❌ 注册表全景 |
| 2 | `GET /admin/push/channels` | operator | 无 | `{channels[]}` | ❌ 注册表全景 |
| 3 | `GET /admin/discovery/channels` | operator | 无（缓存读） | `{channels[], defaultChannel, selectionReason, configuredChannels}` | ❌ 就绪度视图 |
| 4 | `GET /admin/ops/liveness` | operator | `max_age_seconds` | `{processes[], maxAgeSeconds, allHealthy}` | ❌ 探针视图 |
| 5 | `POST /admin/push` | operator | — | 回执 `{ok, channel, delivered, reason?}` | ❌ 写操作 |
| 6 | `POST /auth/backchannel-logout` | 服务间（IdP 调用） | — | `{ok}` | ❌ 无消费方，见 P-88 |

**结论一句**：卡面字段 5 说的"6 组管理端点…分页目标壳"里，**六组没有一组是分页清单**——
它们已经是统一 envelope（全部经 `success()`，错误全部走 `errors.global` 码表），
但"分页目标壳"对它们是**空集**。真正的 admin 分页清单是另外 5 个端点：

| 端点 | 角色门 | 现状壳 |
|---|---|---|
| `GET /admin/spaces` | admin | `{items, total, limit, offset}` |
| `GET /admin/spaces/{id}/docs` | admin | `{items, total, limit, offset}` |
| `GET /admin/jobs` | admin | `{items, total, limit, offset}`（经 `JobService.list_job_views_any` 产出） |
| `GET /admin/subscriptions` | admin | `{items, total, limit, offset}` |
| `GET /admin/sources` | admin | `{items, total, limit, offset}` |

⇒ 本卡的实现面按**现读的那 5 个**做，不按卡面那句会落空的"6 组"做。登记 **P-94**。

## 2. S14a.1.2 映射到目标壳（D-V3-02）

目标壳（D-V3-02 原文）：`{items, page, pageSize, total, hasMore}`；存量两壳（9 个 offset / 6 个 page）
**只读兼容**，按 14a/15 收敛。现读的两壳实际形状：

| 壳 | 用在 | 请求形参 | 响应键 |
|---|---|---|---|
| offset 壳 | 上面那 5 个 admin 清单 + 若干非 admin 清单 | `limit`(默认 50，`le=100`)、`offset` | `items,total,limit,offset` |
| page 壳 | `bots.py` / `hot.py` 三处 | `page`(≥1)、`page_size`(默认 20，`le=100`) | `items,total,page,page_size` |

两处偏差必须写出来，否则"收敛到目标壳"会被执行成两种样子：
1. **page 壳的响应是 snake_case**（`page_size`），目标壳要的是 `pageSize`；
2. **两个壳都没有 `hasMore`**，而 `hasMore` 是前端 `usePagedList` 判断"还要不要发下一页"的依据
   （现在它靠 `items.length < pageSize` 猜，等于把"最后一页正好填满"当成"还有下一页"）。

映射方案（本卡实现切片）：新增 `app/schemas/pagination.py`，提供一个依赖 + 一个装配函数：
- 依赖同时接受 `page`/`pageSize`（新口径）与 `limit`/`offset`（旧口径），**旧参数优先**、
  两者都给时以旧参数为准（因为旧客户端只发旧参数，新客户端发新参数，重叠是异常而非选择）；
- 装配函数产出的 `data` = `{items, total, limit, offset, page, pageSize, hasMore}` ——
  **只增键不删键**，所以既有前端（`lib/api/admin.ts` 读 `items/total/limit/offset`）零回归；
- `hasMore = offset + len(items) < total`（用已经拿到的 `total` 算，不额外发一次 COUNT）。

## 3. S14a.1.3 差异表（卡面要求 → 现读事实 → 处置）

| 卡面要求 | 现读事实 | 处置 |
|---|---|---|
| S14a.1.1 列 6 组端点现状 | 六组都不是分页清单；分页面在另外 5 个端点 | 按现读做，登记 **P-94** |
| S14a.2.1 通用 `Page[T]` + `page/page_size` 依赖 | 无共享模块；`app/schemas/` 目录不存在；两个壳各写各的 | 本卡新建 |
| S14a.2.2 offset 端点补 page 字段不破旧客户端 | 5 个端点全是 offset 壳 | 只增键；旧参数继续可用 |
| S14a.2.3 错误统一走 errors.global 码表 | **已经成立**：admin.py 全部经 `success()` / 领域异常，无裸 `JSONResponse(status_code=4xx)` 自造码 | 判「已确认」，并补一条防回归断言（扫 `admin.py` 里自造错误响应 = 0） |
| S14a.3.1 每端点契约测试（jsonschema 校验响应） | 无 `tests/test_admin_contract.py`（卡面输出路径点名的文件不存在，同 P-73 那族） | 本卡新建，按 `api.envelope` 语义真源校验信封 + 按形状校验分页键 |
| S14a.3.2 非 admin 403 / 越权 IDOR | 已有：STEP-01 的 IDOR 矩阵 + STEP-22 的角色门 + 本卡新增 admin 分页用例 | 判「已确认 + 本卡补 1 条」 |
| S14a.3.3 OpenAPI 导出供 15 生成类型 | **与已签裁定冲突**：类型唯一源是 Pydantic 内省 → `packages/contracts`（ADR-0008/D-09），CI 已有 `gen_contracts --check` 漂移门；STEP-15 的 S15.1.2 已判「设计如此」（EVD-V13-15 §1） | 判「设计如此」，登记 **P-93** |
| V0.17 增量 `+1`：P-18 retry 接四态 | `retry_job` / `retry_job_any` 复位 Job/JobItem，但**不碰 `ArticleManifest`** ⇒ 重跑成功后要跨 `FAILED → INGESTED` 这条非法边（D-V2-02），现网后果是可观测面失真 | 本卡实现：retry 同事务 `FAILED → DISCOVERED`（合法边）+ 反证 |

## 4. 登记的两条

- **P-93**：S14a.3.3 要求"OpenAPI 导出供 15 生成类型"，而 STEP-15 的 S15.1.2 已按 D-09 判为
  「设计如此 · 不做」（第二条真相）。同一张依赖链上下游各要一遍，执行方只能选一边。
- **P-94**：卡面字段 5 的"6 组管理端点…分页目标壳"里六组均非分页清单，真实分页面是那 5 个
  admin 清单端点；按卡面字面收口会交付一份"给不需要分页的东西加分页"的改动。

## 5. 实现切片读数

### 5.1 分页目标壳（S14a.2.1 / S14a.2.2）

新建 `apps/api/app/schemas/pagination.py`（+ `app/schemas/__init__.py`，目录此前不存在）：
`PageParams` / `page_query` / `make_page_query` / `Page[T]` / `page_shell()`。
5 个 admin 分页端点全部改接该依赖，响应 `data` 变成
`{items, total, limit, offset, page, pageSize, hasMore}` —— **只增键**，
所以 `lib/api/admin.ts` 与 `usePagedList` 读旧键的代码一行没改也不该改。

三条不是"顺手"的决定，写清楚为什么：

1. **上限逐端点声明**（`make_page_query(default_size=100, max_size=200)` 只给
   `/spaces/{id}/docs`）：它的历史上限是 200，其余是 100。收成一个全局值就等于偷偷改掉一边
   ——收紧会让旧客户端的 `?limit=200` 直接 422，放宽会把另一个端点的 DoS 面撑开。
   判据：`test_docs_endpoint_keeps_its_own_wider_page_size_cap`。
2. **旧参数优先**：给了任一 `limit`/`offset` 就整段按旧参数解释。两壳参数同时出现是异常而不是
   一种选择，静默换算会拼出"第 2 页但每页 50 条"这种没人要的位置。
   判据：`test_page_query_precedence_and_defaults`（纯函数，不连库）。
3. **`hasMore` 用已经拿到的 `total` 算**，不额外发一次 COUNT：多那次 COUNT 的读数与本轮
   `items` 不是同一时刻，反而会把"正好填满的最后一页"判成还有下一页。
   判据：`test_has_more_is_false_on_an_exactly_filled_last_page`。

### 5.2 一条先红读数（这条决定本卡剩下的写法）

`test_r48_admin_routes_registered` 与另两条先红，红因不在断言而在 **`create_app().openapi()`**：

```
pydantic.errors.PydanticUserError: `TypeAdapter[typing.Annotated[ForwardRef(
"Annotated[int | None, Query(ge=1, le=max_size, ...)")] ...]]` is not fully defined
```

`make_page_query` 是闭包依赖，注解里带着运行期值 `max_size`；一旦模块写了
`from __future__ import annotations`（PEP 563 把注解变成字符串），pydantic 在生成 OpenAPI 时
重建不了这个 `ForwardRef`。报错点离改动处两跳远（在本模块写注解，在 `app.openapi()` 才炸）。
处置：`pagination.py` **不写** future import，并把原因写进模块 docstring；
防回归判据 `test_openapi_builds_and_documents_both_paging_dialects`（同时断言
`limit/offset/page/pageSize` 四个查询参数都在稿上）。

### 5.3 调用面回归：两个既有测试直接 await handler 传元组

全量跑（真库）抓到 2 条红：`tests/test_wc_pagination.py` 的
`test_admin_list_spaces_pagination_shape` / `test_admin_list_subscriptions_pagination`
直接 `await admin_list_spaces(..., paging=(50, 0))`，依赖类型换成 `PageParams` 后
报 `'tuple' object has no attribute 'limit'`。
处置：**只改调用面**（传 `PageParams(50, 0)`），四条断言（total/limit/offset/items 长度）一字未动
——它们锁的是响应形状，与依赖类型无关。这是 `tests/test_wc_pagination.py`，
在卡面字段 12 的三个路径之外 ⇒ 越界声明，登记 **P-95**。

（同族教训已生效：改签名后跑的是**全量**而不是"相关邻居测试"，这两条红因此在本轮本地出现，
而不是在 CI 上。）

### 5.4 S14a.2.3 与 S14a.3.1

- S14a.2.3 判**已确认**：`admin.py` 里 28 处 `JSONResponse(status_code=200`、
  非 200 自造状态码 **0 处**，错误全部经 `errors.global` 码表。补一条扫源码的防回归判据
  `test_admin_module_never_fabricates_error_responses`（扫源码，不扫行为措辞）。
- S14a.3.1 新建 `tests/test_admin_contract.py`：每个响应都过
  `jsonschema.validate(body, packages/contracts/schemas/api.envelope.schema.json)`，
  所以"信封不合冻结契约"会在这里红，而不是在前端解包时红。
- S14a.3.2 判**已确认 + 本卡补 1 条**：角色门与 IDOR 由 STEP-01 矩阵 / STEP-22 门 /
  `test_r48_*` 覆盖；本卡补的是"清单端点在新依赖下仍然 403/10004"这一格由既有
  `test_admin_r48_role_gate_and_requires_login` 继续守住（未改动）。

### 5.5 P-18：retry 接回清单四态（V0.17 增量那一项）

`retry_job` 与 `retry_job_any` 各加一行 `await self._reopen_manifests(failed)`（同事务、commit 前）：
只动 `FAILED` 的清单行，走迁移表里已有的合法边 `FAILED → DISCOVERED`
（`state_machine.py:37`，注释就写着"人工重试"）。`ENQUEUED`/`DISCOVERED` 不抢——
那是 stale 回退那条路的职责。

- 判据：`test_retry_reopens_the_failed_manifest`（真库，断 DB 事实不是断日志）。
- 反证：把 `retry_job_any` 里那一行换成 `pass` ⇒ 该用例红
  （`AssertionError: 清单行没被拉回 ⇒ 重跑成功后 worker 撞非法边，读数失真`），改回后绿。
- `job_worker._apply_manifest_status` 的 docstring 里"P-18 已记，修复点在 retry 路径"那句
  现在有了实现，不必改文案（它描述的就是这个位置）。

## 6. 读数汇总与三绿

| 项 | 读数 |
|---|---|
| 全量真库套件（本机隔离 PG） | **2239 passed / 6 skipped / 0 failed**（17m48s）。上一张卡的锚是 2231 passed / 6 skipped ⇒ 本卡 +8，全部来自 `tests/test_admin_contract.py`；skip 族未变（仍是 LangBot/Redis 不可达那 6 条） |
| 分页批的先红读数 | 同一套件跑到 2 failed（`test_wc_pagination.py` 两条，`'tuple' object has no attribute 'limit'`）⇒ §5.3 处置后复跑 0 failed |
| OpenAPI 那条的先红读数 | `PydanticUserError: TypeAdapter[... ForwardRef(...le=max_size...) ...] is not fully defined` ⇒ §5.2 处置后转绿，并留下 `test_openapi_builds_and_documents_both_paging_dialects` 作防回归 |
| `ruff check app tests` | All checks passed |
| `mypy app` | Success: no issues found in **119** source files（新增 `app/schemas/` 两个文件在覆盖面内） |
| CI / CI-Windows / Security | `fbb0409`：CI success 39782742068、**Security 🔴 39782742059**、**CI-Windows 🔴 39782742078**。Security 的命中是测试夹具里 Job 的幂等键字面量被 `generic-api-key` 判成凭据 ⇒ `1872910` 把夹具值对齐到本仓既有冒号约定（列名与领域值都没动，本地以仓库根配置复扫该文件 0 命中），那一次红不重跑、不改写。CI-Windows 的红是 skip 门禁按设计工作：`failed=0 total_skipped=658 baseline=653`，+5 全是本卡新增的连库判据（另 3 条不连库）⇒ 按 D-V10-11 把 `SKIP_BASELINE_WIN` 抬到 **658**（锚 `run 39782742078 @fbb0409`，未知族 0）。`1872910` 的 Security 仍 🔴 39784495358，读数 `commit=fbb04092 …:156`——**CI 扫的是历史 blob，而豁免指纹写在下一笔 `41c2124` 里**，所以这一格红是"晚一笔"的必然，不是修复无效。本卡验收锚 = `41c2124`（含 658 基线 + fbb0409 指纹），三维读数待回填 |

## 7. 交回规划方的两条

- **P-95**：本卡为适配调用面改了 `tests/test_wc_pagination.py`，它在字段 12 之外。
- **P-96**：`hasMore` 后端已经发出来了，前端 `usePagedList` 仍按 `totalPages` 自己算
  ——D-V3-02 说的"按 14a/15 收敛"只走完服务端那一半。

