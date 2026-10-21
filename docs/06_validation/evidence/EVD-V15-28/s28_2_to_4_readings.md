# EVD-V15-28 · S28.1.2～S28.4.1 运营可配置读写面执行方读数

> 卡面：`docs/任务规划V0.15.0/steps/STEP-28-采集渠道与分类运营可配置-后端.md`。
> 存储底座（S28.1.1）的读数在同目录 `s28_1_readings.md`；DDL 的取舍在 **ADR-0013**。
> 本文件覆盖 S28.1.2～S28.4.1，交付基线 = `9d112f7`（S28.1.1 + P-60 门禁修复，三绿已取）。

## 1. 先红原文（改前，HEAD=`9d112f7`）

三条判据分开量，因为它们红了会各自伪装成"没事"：

**① 行为红**（scratch 探针 `system_settings` 直接 INSERT 两行真库读数，跑完即清场）：

```
[probe] 库里 system_settings 行数 = 2
[probe] S28.2.1.a  库值 enabled=[tikhub] ⇒ enabled_channels() = ['redfox', 'tikhub']
[probe] S28.2.1.a  库值 default=tikhub ⇒ resolve_default_channel() = 'redfox'
[probe] S28.3.1.a  库值新增「质量·验收」+关键词「验证」 ⇒ categorize('某清洗验证通报','') = '其他'
[probe] S28.3.3 spaces.CATEGORY_ALLOWLIST 是常量还是函数 = frozenset，成员数=7
[probe] S28.2.2 / S28.3.2 新写端点在路由表里的条数 = 0 → []
[probe] 已清场：system_settings 回到 0 行
```

探针刻意带着 `PROBE_SELECTOR` 同款的 WindowsSelector 事件循环策略跑（`conftest.py` 在 import
期就换位，不换位时 psycopg 直接抛 `ProactorEventLoop` 而**根本不发起连接**——那条老坑，
见 `EVD-V7-00W`）。库里真有行、读函数照样回 env 值，这才是卡面 S28.2.1.a 说的"红"，
而不是"脚本跑不起来"。

**② 装载红**（新写的三个测试文件在 HEAD 上）：

```
ERROR tests/test_system_settings.py
ERROR tests/test_discovery_config.py
ERROR tests/test_category_config.py
E   ImportError: cannot import name 'system_settings' from 'app.services'
3 errors in 8.95s
```

**③ 结构红**：路由表里 `/admin/discovery/config`、`/admin/categories` 各 0 条（上面 `[probe]` 第 5 行）。

## 2. 改后绿

| 面 | 命令 | 读数 |
|---|---|---|
| 本卡三文件 | `pytest tests/test_system_settings.py tests/test_discovery_config.py tests/test_category_config.py -q` | **43 passed** |
| 回归面（卡面"0 修改"判据） | 追加 `tests/test_discovery.py tests/test_categorizer.py tests/test_docs_pagination.py tests/test_push_and_hot_rank_matrix.py tests/test_require_roles_single_arg.py` | **82 passed / 0 failed**，其中前三个文件**一行未改** |
| 静态面 | `ruff check app tests` / `mypy app` | rc=0 / `Success: no issues found in 116 source files` |
| 契约面 | `python scripts/gen_contracts.py --check` | 12 项全部「幂等一致」⇒ **本批对契约产物 0 变更**（为什么这是缺陷而不是通过，见 §6） |
| 全量连库 | 见 §8 | 见 §8 |

`test_discovery.py` 里被复用的三条"无库值时逐字一致"判据（`selectionReason == "configured"` /
`"registration-order"` / `"none-available"`）全部原样通过 ⇒ ADR-0013 不变量 1 有了读面证据。

## 3. 端到端读数（卡面 S28.4.2 点名的两条 + 接线一条）

| 判据 | 走的路 | 读数 |
|---|---|---|
| PUT 渠道 ⇒ 调度侧读到新值 | `TestClient.put(/api/v1/admin/discovery/config)` → **直接调** `resolve_default_channel(settings)` | PUT 前 `redfox`（env）→ PUT 后 `tikhub` |
| PUT 分类 ⇒ 入库分类用新值 | `TestClient.put(/api/v1/admin/categories)` → `KnowledgeBaseService.ingest_url`（真入库链，`_StubResolver` 样本标题「清洗规则验证文章」）→ 读 `content_assets.category` | 同一空间内：第一次入库 `其他` ⇒ PUT 后第二次入库 `质量·验收` |
| 轮首接线（跨进程生效路径） | `IncrementalScheduler.run_once()` / `JobWorker.run_once()`，先前 `reset_snapshot()` | scheduler：清空后读到 `redfox` ⇒ 跑一轮 ⇒ `tikhub`；worker：清空后 `其他` ⇒ 跑一轮 ⇒ `质量·验收` |

第三条是本卡目标句「落库后**下一轮** scheduler 与入库分类按新配置执行」里"下一轮"三个字的唯一
落点。`test_scheduler_round_picks_up_the_new_config` / `test_worker_round_picks_up_the_new_categories`
断言的是"跑完一轮之后同步读函数拿得到库值"——接线少一行，用例就红；它不是 mock 调用次数。

## 4. 实现中查出并修掉的一条真缺陷（旧值摘要被自己覆盖）

第一版 `put()` 写成"取行 → 赋新值 → flush → 算旧摘要 → 写审计"。因为 `existing` 与 `row`
是**同一个** SQLAlchemy 实例，赋新值之后再去读 `existing.value` 读到的已经是新值 ⇒
审计里 `old_digest == new_digest`，"改之前是什么"这一格长期是假的，而且**接口照样 200、
用例照样绿**（第一次写没有旧行，什么都看不出）。

抓它的是 `test_put_writes_row_with_actor_and_digest_audit` 里那句
`assert "rss" not in audit["old_digest"]`，本机第一次跑红在：

```
AssertionError: assert ('redfox' in 'enabled=2[redfox,rss] default=rss' and 'rss' not in '...')
```

修法是把摘要提到赋值**之前**（`app/services/system_settings.py` 的 `put()`，代码里留了一行
说明为什么顺序不能换）。这条不是风格问题：审计表如果只会说"改成了什么"，它就不配叫审计。

## 5. 越界声明（逐条，与本卡允许面的差）

| 越界 | 面 | 为什么必须 | 判据 |
|---|---|---|---|
| `apps/api/app/services/scheduler.py` +2 行（1 import + 1 轮首刷新） | 卡面 §5 允许修改**不含**此文件 | 卡面 §0 要求"下一轮 scheduler 按新配置执行"；`registry` 的两个读函数是同步的、拿不到会话，唯一能在 scheduler 进程里合法动库的位置就是它的轮首 | `test_scheduler_round_picks_up_the_new_config` |
| `apps/api/app/services/job_worker.py` +3 行（同上） | 同上 | 分类真正被写进 `content_assets` 的进程是 worker；不接线就是"后台改了、入库照旧" | `test_worker_round_picks_up_the_new_categories` |
| `registry.py` 改动面从"仅两个读函数"扩到 `enabled_channels` / `describe_channels` / `_selection_reason` | 卡面 §5 写「仅两个读函数」 | `_whitelist()` 有 3 个调用点；只把 `_whitelist` 改成库值优先，**空集就从"没配"被读成"全停"再被读成"全开"**——`enabled_channels` 不区分这两者就会把运营的"全停"执行成"全量采集" | `test_empty_db_list_means_no_channel_not_every_channel` |
| 刷新接线用 `refresh_with(factory)`，TTL 内空操作 | — | worker 空转间隔是 10 秒量级；不设 TTL 门就是"每秒查一次库" | `test_refresh_with_is_ttl_gated`（判据是"会话工厂被调几次"，不是返回值） |
| 两处**计数锚**追认：`tests/test_audit_log.py`（写操作 23→25、admin 12→14）与 `tests/test_idor_matrix.py`（操作 93→96、注册面 89→92） | 卡面 §5 只写「tests 新建 + 矩阵追加行」 | 这两条锚的 docstring 自己写着"真加/删端点时来改这条；不要把断言放宽成 `>= 0`"——不改就是恒红，放宽就是没有守卫。改的是**数**，判据形状一处未动 | 全量读数见 §8；且 `test_each_write_operation_emits_exactly_one_audit_record` 的参数化里自动多出这两个新端点，两条都绿（各自恰好一条审计记录）⇒ 新面进了旧守卫，这才是"追认数字"的资格 |

四处接线 + 一处锚追认，都留在卡面 §0 的目标句内，没有一处是"顺手加的"。反过来说：**卡面 §5 的允许面与 §0 的目标
句不自洽**——这条已登记为 P-61 的第二个后果（见 §7）。

## 6. 契约步（卡面 §2「先写契约再写实现」）：三条路都量过，没有合法的那条

`gen_contracts --check` 12 项幂等一致，读起来像"契约面通过"，实际含义是**本批对契约 0 变更**。
0 变更不是执行方偷懒，而是三条可选路径各有硬墙（前两条实测，第三条按台账口径）：

1. **`packages/contracts/src/**` 手写 DTO** ⇒ 那里全是生成物，头一行就写「请勿手动修改
   （--check 幂等门禁）」，`check()` 是**逐字节**比较（`scripts/gen_contracts.py:320`）⇒ 手改必红。
2. **在 `app/contracts/collection.py` 加模型**（本卡最初的裁定，`s28_1_readings.md` §5 第 2 条）
   ⇒ 生成器会把新模型摊成 `collection.schema.json` 的新 `$defs`，而语义比对门
   `apps/api/tests/test_collection_contract.py:1064` 对"生成物有、冻结稿没有"的 def 是
   **无条件红**（`{name}: 生成物多出一个 def（稿里没有 ⇒ 谁加的？）`），这条分支不查任何登记表
   ⇒ 唯一出路是改冻结稿，而那是卡面 §6 的禁改面 + 卡面字段 7 的升级条件（"需要改冻结契约 ⇒ 停，
   交规划方"）。
   **本节同时推翻 `s28_1_readings.md` §5 第 2 条**："放进已映射的 collection 域因此只扩 schema、
   不动生成器"这句在我自己写的判据下不成立，写它是没跑比对门就下结论。
3. **新起一个契约域** ⇒ 需要规划方先落一份冻结稿（前例：STEP-13 的 `engine` 域，
   `docs/任务规划V0.12.0/contracts/engine.schema.json` 在稿集里先存在）。执行方自造冻结稿
   = 造合同，越权。

⇒ 卡面的契约步**交回规划方**（P-61）。本批的形状事实来源仍是 `admin.py` 里那两个请求模型，
它们经 OpenAPI 内省可见（`DiscoveryConfigRequest` / `CategoryConfigRequest` / `CategoryItemRequest`），
所以 14b 页面接线的依据是有的，缺的是 `packages/contracts` 里那一份生成物。

## 7. 登记给规划方的两条（不自开修复）

- **P-61**：STEP-28 卡面的契约步无合法实现路径（§6 三条实测），且 §5 允许面缺 §0 目标句
  必需的轮首接线点（§5 表前两行）。处置口径：要么由规划方落一份 `admin_config` 冻结稿并给
  `DOMAIN_*` 表加登记位，要么把"契约 DTO"从本卡验收面移出、并进 14b。
- **P-62**：422 响应体回显被拒的输入值。实测（不连库，直接喂模型）：
  `DiscoveryConfigRequest.model_validate({... 'redfox_api_key': 'SENTINEL-VALUE-ABCDEFGH'})`
  的 `errors()[0]` 键集是 `['input', 'loc', 'msg', 'type', 'url']`，`input` 就是那个值；
  而 `app/main.py:127` 把 `exc.errors()[:1]` 原样塞进 `failure(10005, …)` 的 message
  ⇒ 调用方往配置接口夹带凭据时，会把自己的凭据串拿回响应体（以及任何记响应体的日志）。
  不是越权读取，但是**把凭据从内存搬进日志**。修法在 `main.py` 的校验处理器（本卡禁改面之外
  但也在允许面之外），且会影响所有域的错误文案 ⇒ 交规划方定口径。
  本卡自己那层的错误文案已经做了不回显（`system_settings._readable()` 只报「字段 + 原因」）。

## 8. 门禁与基线（本机全量，两形状同一天）

同一份代码跑两次全量，差别只在环境变量——这是 D-V10-11 要求的"按族测量"，不是拿一个数猜另一个。
下表是**第 2 轮**（含 `spaces.ensure_loaded` 那一条补的用例）的终值；第 1 轮的同一形状读数写在 §11。

| 形状 | 命令 | junit 读数 |
|---|---|---|
| 连库（`bothot_test`@5547，PG 16.4） | `pytest tests -q --junitxml=…` | **2121 tests / 0 failed / 0 errors / 6 skipped**（终端行 `2115 passed, 6 skipped`） |
| 无 DSN（`env -u AIDEANBOT_TEST_PG_DSN -u DATABASE_URL`，与 CI-Windows 同形状） | 同上 | **2121 tests / 0 failed / 0 errors / 612 skipped**（终端行 `1509 passed, 612 skipped`） |

`SKIP_BASELINE_WIN`：**578 → 612**。算式是测量值相加，不是余量：

| 族 | 条数 |
|---|---|
| `tests/test_system_settings.py`（写侧与轮首刷新的连库用例） | 6 |
| `tests/test_discovery_config.py` | 10 |
| `tests/test_category_config.py`（参数化按条计：5 条非法清单各一条；含第 2 轮补的 1 条） | 16 |
| `tests/test_audit_log.py::test_each_write_operation_emits_exactly_one_audit_record` 随新写端点变长（23 → 25） | 2 |
| 合计 | **34** ⇒ 578 + 34 = 612，与全量实测 `total_skipped=612` 一致 |

其余门：

| 门 | 读数 |
|---|---|
| `ruff check app tests` / `mypy app` | rc=0 / `Success: no issues found in 116 source files` |
| `python scripts/gen_contracts.py --check` | 12 项幂等一致（=契约面 0 变更，见 §6） |
| `alembic heads` | `ab1006c4a (head)` 单头（本批未加迁移） |
| `scripts/check_docs_consistency.py` | `23 个路径引用，0 个不存在`，rc=0 |
| `entry.py guard-ports / guard-structure / guard-versions / evidence-check / rounds-check` | 见 §11（提交后跑，读数不预判） |
| `@ci`（ubuntu，验收面）run id | 待回填（见 §11） |

## 9. 局限（先说，不等被问）

- **快照不是广播**。改了配置后，另一进程最多 60 秒内还按旧值跑；"下一轮生效"对
  scheduler / worker 成立（轮首各刷一次），对一个刚好卡在窗口里的请求不成立。ADR-0013 §5 已写。
- `peek()` 在**从没刷过的进程**里返回 None ⇒ 该进程第一轮走 env 兜底。这是"启动即生效"与
  "同步函数不查库"二者之间必须选的一个，我选了后者（STEP-00H 刚把"外部依赖卡住调用方"这一族收口）。
- 分类改名**不回写历史**（卡面 §1 的既定口径）；`content_assets.category` 里旧名仍在，
  筛选与人工纠偏都还能看见它，删除保护就是为此而存在。
- `其他` 这个名字在服务层是**镜像常量**（`system_settings._DEFAULT_CATEGORY`）——
  `categorizer` 要读 `system_settings` 的快照，反向 import 会成环。漂移风险由
  `test_default_category_mirror_matches_the_categorizer` 钉住，不是靠注释。
- 本卡未做：`packages/contracts` 的 DTO（§6/§7）、前端页面（14b，禁改面）。

## 10. 一条只有"全量跑"才暴露的门（登记 P-63）

本卡四个断言结构化日志的用例（`test_put_writes_row_with_actor_and_digest_audit`、
`test_first_write_reports_no_old_row`、`test_refresh_drops_unknown_key_and_unreadable_value`、
`test_refresh_with_swallows_a_dead_database`）在单跑时全绿，放进全量跑一起红了四条，
红法是同一种：

```
assert changed, logs
E   AssertionError: []
E   assert []
```

也就是 `structlog.testing.capture_logs()` **一条都没抓到**。第一轮假设"日志没打"是错的——
同批不连库的 `caplog` 用例证明日志确实到了 stdout。真因在装配参数上：
`apps/api/app/core/logging.py` 的 `configure_logging()` 用 `cache_logger_on_first_use=True`，
structlog 的懒代理在**第一次被调用**时就把绑定结果缓存下来；此后 `capture_logs()` 换掉全局配置
也换不到那个已经绑好的 logger。全量里 `app.services.system_settings` 的 logger 第一次被用是在
`test_category_config.py`（字母序在前，且窗外），所以后面所有捕获窗都看不见它。
`test_audit_log.py` 之所以一直绿，是它的 logger 第一次被用恰好落在自己的捕获窗内。

三发读数的形状（都是本机、真库 DSN）：

| 命令 | 读数 |
|---|---|
| `pytest tests/test_system_settings.py -q` | 43 passed（窗内首次绑定 ⇒ 看得见） |
| 同一批放进全量 | `7 failed, 2107 passed, 6 skipped`（其中 4 条就是上面这四发） |
| `pytest tests/test_observability.py tests/test_system_settings.py -q` | 30 passed（反证：只要窗外先用过一次就触发） |

处置只写在**测试侧**：`tests/test_system_settings.py::_captured()` 在捕获窗内重新
`structlog.get_logger(LOGGER_NAME)` 换一个未缓存的代理，退出时还原模块属性——不改生产配置、
不改全局状态、不放松断言（断言仍是 dict 级字段比对）。生产侧那条开关（"测试期不缓存绑定"）
与 P-53 的用例密封 fixture 属同一面，登记交回，不在本卡顺手做。

**为什么这件事值得单独一节**：它的失败方式是"日志一条都没抓到"，而不是"字段不对"。
下一个人踩到时很可能去放宽断言或删掉用例，那等于把 STEP-31 立的审计可查面自己关掉。

## 11. 第 2 轮：后端进程才是漏掉的那一侧

第 1 轮（`05ff3ff`）把"下一轮生效"接到了 scheduler 与 worker 两个常驻进程的轮首，契约面按 §6 交回，
三绿读数：

| 工作流 | run id | head_sha | 结论 |
|---|---|---|---|
| CI（ubuntu，验收面） | 39589338420 | `05ff3ff` | ✅ success |
| CI-Windows | 39589338546 | `05ff3ff` | ✅ success（`SKIP_BASELINE_WIN=611` 命中，无 skip 门禁红） |
| Security | 39589338654 | `05ff3ff` | ✅ success |

**但接口这一侧漏了**，而且是用户最直接碰到的那条路。`system_settings` 的快照只会被
`put()` / `get()` / `refresh()` 所在的那个进程填充；backend 没有"轮首"这个概念，重启之后快照是空的。
于是：运营配好一个新分类 ⇒ 分类页（走 `get`）看得见 ⇒ 但**下一次有人拿它去纠偏文档分类会被 10005 拒**，
因为 `SpaceService.validate_category` 读的是默认清单。这个形状比"没生效"更坏：它一半生效。

补法是 `system_settings.ensure_loaded(session)`（TTL 内空操作，读不到就沿用最后已知值且不让请求失败），
在 `spaces.py` 的三个调用点前各加一行：单篇纠偏、批量纠偏、`:categories` 呈现序。
这三处都落在卡面允许面对 `spaces.py` 的限定上（"仅分类校验/呈现序"），不算越界。

判据与反证（不能只说"我接上了"）：

| 步 | 读数 |
|---|---|
| 新增用例 | `test_service_path_reads_the_db_value_by_itself`：绕开 `put()`（它会顺手刷快照），用裸 ORM 写配置行 + `reset_snapshot()`，再走 `SpaceService.update_doc_category` ⇒ 新类被接受且出现在 `list_doc_categories` 里。**25 passed**（与 `test_docs_pagination.py` 同跑） |
| 变异反证 | 把其中一行 `ensure_loaded` 注释掉 ⇒ 同一条用例 **FAILED**（`1 failed in 1.45s`）；还原后 `grep -c MUTATION-PROBE` = **0**，三处调用点齐全（`:448 / :637 / :796`） |
| 空间面回归 | `test_category_config + test_docs_pagination + test_r02_batch_docs + test_spaces_api` ⇒ **76 passed / 0 failed** |
| 全量两形状 | 连库 `2121 tests / 0 failed / 6 skipped`；无 DSN `2121 / 0 failed / 612 skipped`（§8） |

**局限要说全**：`ensure_loaded` 让 backend 在 TTL 内最多落后 60 秒，这与 ADR-0013 §5 是同一条代价，
不是新增的洞；而 `session=None` 的内存桩装配（既有测试里常见）返回 False、读默认清单——
那条路径本来就没有库可读。
