# 数据库噪声登记：合法 skip 的理由族与 IntegrityError 的两套判别式

> 本文件是 STEP-00R「skip 固化」的落盘面。卡面写的输出路径
> `docs/任务规划V0.8.0/evidence/61358c3-rv/db_noise.md` **在本仓不存在**（V0.8.0 的证据目录
> 从未建到该路径），按现行约定改落工程文档，漂移登记为 `§4 P-57`。
> 读法：这里只回答"某条用例为什么可以不跑"，**不回答"它跑过了没有"**——后者只认 `@ci` 读数。

## 1. 为什么 skip 需要一张登记表

本项目的全量门禁同时存在两个方向相反的失败模式：

- **假绿**：连库用例因为环境不具备而静默 skip，读数却按"通过"上报。
  对策是 CI 的 skip 计数门（`SKIP_BASELINE` / `SKIP_BASELINE_WIN`，阈值由测量值钉死、不留余量）。
- **假红**：把环境造成的合法 skip 当成回归。
  对策就是下面这张族表——每族的**理由原文 token** 由门逐字匹配，放宽成正则就会把新造的假 skip 认成合法。

所以这张表的判据不是"我觉得合理"，而是"CI 里那条计数与族的读数"。

## 2. 合法 skip 的族（现读，2026-10-21）

| 族 | 理由原文的匹配 token | ubuntu `CI` | `CI-Windows` | 本机 `@win` 真库 |
|---|---|---|---|---|
| PG-DSN-未设置 | `AIDEANBOT_TEST_PG_DSN 未设置` | 0 | 469 | 0 |
| PG-不可达 | `PG 不可达` / `PG:5433 不可达` | 0 | 104 | 0 |
| Redis-不可达 | `Redis 不可达` | 3 | 3 | 3 |
| LangBot-不可达 | `LangBot :5300 不可达` | 2 | 1 | 2 |
| 代理变量未设 | `宿主未设这 6 个待清代理变量` | 1 | 1 | 1 |
| **合计** | — | **6** | **578** | **6** |

三列各自的判据来源（都不是抄来的，且**分族行是门自己打的**）：

- **`CI-Windows`** 那一列取自 run 39536915781 的门输出原文：`windows 门禁：failed=0 total_skipped=578 baseline=578`
  加五行 `族 … = N`。注意 `LangBot` 在 Windows 上是 1 而不是 2——门禁的归档是**按表序首命中**，
  同一批 skip 在不同平台上可能被归进不同族，所以族构成只能读门的输出，不能由本机分布外推。
- **ubuntu `CI`** 的权威判据是门自己打印的那行，取自 run 39559617499：
  `skip 门禁：total_skipped=6 baseline=6 pg_unreachable=0` ⇒ **PG 不可达类 = 0**，
  即那几百条连库用例是真跑了（D-XX「skip ≠ 通过」的机检形态）。
  族的**构成**则由逐条 `SKIPPED [1] …` 原文核对（run 39554810994 与 39536915806 各 6 条，两发一致）；
  基线值取自 `ci.yml` 里的 `SKIP_BASELINE: "6"`。
  补记一条取数教训：这一行我第一次没抓到，原因是我的过滤式要求行里含 `=` 且以"门禁"开头，
  而那行的前缀是 `skip ` —— 过滤式比目标行窄就会得到"没有这行"的假阴性。
- **本机 `@win` 真库**取自本批的 junit（`tests=2067 failures=0 errors=0 skipped=6`）。

三列的读法各不相同，别把它们当同一个数：

- **ubuntu `CI`**：job 带 postgres service ⇒ 两族 PG 计数恒为 **0**，这是"连库用例真跑了"的正面证据
  （D-XX「skip ≠ 通过」的机检形态）。`SKIP_BASELINE=6`，构成只有 Redis/LangBot/代理三族。
- **`CI-Windows`**：job **故意不起任何依赖服务**，所以 PG 两族整批出现，578 是测量值。
  这张表里 Windows 那一列不参与"是否真跑"的证明，它只证明"没有新增未知族的 skip"。
- **本机 `@win` 真库**（隔离 PG 16.4 起在 5547，DSN 由 `AIDEANBOT_TEST_PG_DSN` 注入）：
  PG 两族为 0，与 ubuntu 同形，所以本机是全平台上唯一能同时验"真跑"与"零失败"的环境。

**新增连库用例时该改哪一格**：只改 `SKIP_BASELINE_WIN`（抬到实测值，不留余量，D-V10-11）；
ubuntu 侧只有在依赖服务变化时才动 `SKIP_BASELINE`。程序写在 `cross-platform.md` §8。

## 3. 逐条清单（本机真库，`@win` 2026-10-21）

| 用例 | 族 | 理由原文 |
|---|---|---|
| `test_chat_sse::test_ask_real_langbot_smoke` | LangBot-不可达 | LangBot :5300 不可达或未注入管理员凭据，跳过真实冒烟 |
| `test_chat_sse::test_ask_real_full_chain_smoke` | LangBot-不可达 | 同上（全链形态） |
| `test_session_store_redis::test_session_roundtrip_and_token_rotation` | Redis-不可达 | 测试 Redis 不可达（ConnectionError），拉起容器后复跑 |
| `test_session_store_redis::test_session_ttl_and_missing_key` | Redis-不可达 | 同上 |
| `test_we_notifications::test_notifications_real_redis_forwarding` | Redis-不可达 | 逐字原文是一条 f-string，把 `settings.redis_url` 与异常类名内插进去（本机渲染出的形状是"无口令的 localhost:6379 + TimeoutError"）。这里**不复制渲染结果**：DSN 形状正是敏感形门的扫描面，抄进来会让本文自己变成下一发命中 |
| `test_env_isolation::test_host_proxy_state_is_not_inherited` | 代理变量未设 | 宿主未设这 6 个待清代理变量，本条对照在此环境下无判定力（①②仍有） |

最后一条值得单独说明：它 skip 的**不是功能缺失**，而是"这一半对照在没有代理的机器上没有判定力"，
同文件的另两半（①②）照常跑。这种"部分无判定力"的 skip 是最容易被读成"整条用例没跑"的形态，
所以理由原文必须把剩下的判定面写进去。

## 4. `IntegrityError` / `DataError` 的归类（S0R.1 的判定）

判据实体是这条命令，不是本文抄的数字：

```bash
git grep -n 'IntegrityError' -- apps/api/app   # 生产侧（含 import 与注释行）
git grep -n 'IntegrityError' -- apps/api/tests # 测试侧
git grep -n 'DataError' -- apps/api            # 第二族
```

现读结果分三块说：

1. **`DataError` 在本仓 0 命中。** 卡面要抽的是"IntegrityError/DataError 行"，第二族在 `apps/api` 里
   从来没有出现过——所以 S0R.1.1 对它的正确读数不是"本轮没有"，而是"这一族在本项目不存在用例面"。
   这条要说死，否则下一轮又去 grep 一遍然后记成"新发现"。
2. **生产侧 19 行全部是"预期"，且分两套判别式**（这不是缺陷，但下游必须知道，因为它决定
   "新写一处并发 upsert 时该照哪个模板"）：
   - **重查判别式**（`app/repositories/job.py`、`asset.py`、`user.py`、`services/kb.py` 三处、
     `services/manifest.py`）：savepoint 内插入 → 捕获 `IntegrityError` → 按预期的键重查 →
     **重查为空就原样上抛**。判据是"这行到底存不存在"，所以非唯一约束的失败（NOT NULL、FK）不会被掩盖。
   - **约束名判别式**（`app/services/spaces.py`，`if "uq_space_user_name" in str(exc.orig or exc)`）：
     命中才映射成 30006，否则上抛。判据是"错误文本里有没有那个约束名"。
     局限要写清：它对 DB 错误文本敏感，且若将来出现**名字包含该子串**的另一个约束，会映射错。
     今天两条判据在各自场景都成立，但**没有任何一道门钉住"新代码必须选哪一种"**——这是本节唯一的
     可改进项，属结构性观察，不是缺陷行，因此不开卡。
3. **测试侧 12 行**都在断言预期（`pytest.raises(IntegrityError)`、并发收敛"无未捕获 IntegrityError 冒泡"、
   以及用 `IntegrityError(...)` 伪造冲突以验证映射），不属于噪声。

**本批空集是怎么被证明为空的**（不是"没读到"）：真库全量 `2061 passed / 6 skipped / 0 failed`，
junit 总账 `tests=2067 failures=0 errors=0 skipped=6`，而 `-q` 模式下无失败就不打印 traceback——
所以日志里六族关键字 0 命中**是结果而不是取证失败**。
判据实体是那张 junit 计数，不是我对日志的目测。

> S0R.1.3「缺陷项开新卡」因此没有产出：本轮没有需要归类的缺陷行。这条"无"必须和它的判据一起写，
> 否则下一轮会把"没写"读成"没查"。

## 5. 耗时分布（R-V14-05 欠的那一条，本轮补上）

本机真库全量 `1366.19s`（`@win`，含 setup/teardown），单用例最长 `27.68s`
（`test_push_and_hot_rank_matrix::test_operator_write_surface_matches_d_v12_12`），
**超过 120s 的条数 = 0**。这条读数是 `CI-Windows` 把 `--timeout` 收到 120 的旁证之一
（同一阈值由 `faulthandler_timeout=120` 在 CI 上独立验证，见 `EVD-V13-00H` §10）。

时间戳要写清：这次全量跑在 STEP-07 的防复发用例并入**之前**（`2061 passed` 那一次），
所以它覆盖的是当时的 2067 条收集数。新增的 5 条都是非连库的静态/参数化断言（单文件实测 `1.33s` 跑完），
不会把上界推近 120s——这个结论的方向是"更保守"，不是"更危险"，但引用这条读数时别说成"当前套件的最新耗时分布"。

## 6. 维护规则

- 族的 token 取自 conftest/用例里的**理由原文**，改原文必须同批改门里的 token，否则该条落进"未知族"变红——
  这是设计上的，不是 bug。
- 新增一族时，先在这里写清"它证明什么、不证明什么"，再进门。族的数量由 CI 的门报，不在本文抄数字。
- 常驻反证：`apps/api/tests/test_ci_windows_skip_gate.py`（合成 junit + 四发极性），
  它在 `@ci ubuntu` 上也在判 Windows 门的逻辑。
