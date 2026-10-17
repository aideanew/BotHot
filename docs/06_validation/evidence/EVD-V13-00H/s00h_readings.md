# EVD-V13-00H · 健康/就绪探针有界化（执行方读数）

基线：`main@31a6667`（卡 = `docs/任务规划V0.13.0/steps/STEP-00H-*.md`，裁决 D-V10-02）
执行机器：`@win`（Windows 10.0.19045，无 PG / 无 Redis / 无 LangBot —— 三个依赖在这台机器上**本来就是**黑洞）
执行时间：2026-10-17 18:1x–19:0x Asia/Shanghai

## 1. 为什么判据必须跑在子进程里

如果探针自身无上界，用 pytest 用例去等它，会把**跑测试的那个进程**一起挂住——
工具替被测量死掉，读数就不存在了。所以 `tests/test_health_probe_bounded.py` 让父进程只做两件事：
计时、判 rc；子进程里的 `TestClient` 爱挂多久挂多久，由 `subprocess(timeout=60)` 掐。
子进程的依赖坐标：`DATABASE_URL → 10.255.255.1:5432`（RFC5737 保留地址，不路由、丢包不回 RST）、
`REDIS_URL → 127.0.0.1:1`、`LANGBOT_BASE_URL → http://127.0.0.1:1`。

## 2. 先红读数（S00H.1.1.1，改前）

同一份最终用例，对 `HEAD`（改前）的 `db.py`/`system.py`/`security.py` 跑：

```
4 failed, 1 passed in 41.28s
FAILED ::test_health_and_ready_return_within_bound_under_blackhole_dependencies
FAILED ::test_probes_run_concurrently_not_serially
FAILED ::test_endpoint_budget_is_strictly_inside_the_card_bound
FAILED ::test_probe_paths_are_exempt_in_both_middleware_layers
   AssertionError: 这些探针仍会被限流计数：['/api/v1/system/live', '/api/v1/system/ready']
```

改前逐探针实测耗时（子进程内计时，非推断）：

| 项 | 改前 | 依据 |
|---|---|---|
| `/health` | ≈3.1–4.9s（勉强不进 5s） | 三探针串行：PG 3s + redis 2.11s 叠 langbot 快 |
| `/ready` | **5.29s / 5.34s / 5.46s**（三次独立读数，全部 > 卡面 5s 判据） | 串行 + 限流器在处理器之前先吃一次 Redis 2s |
| 单探针 `_check_pg()` | 3.0s（有 `connect_timeout` 之后） | 改前是"看 TCP 自己放弃"，本机因 Windows 直接抛 `ProactorEventLoop` 错而**恰好**很快；Linux 黑洞则是规划方实测的 45s 不返回 |

## 3. 改后绿读数

```
5 passed in 28.58s          # tests/test_health_probe_bounded.py
71 passed in 39.64s         # tests/test_health_ready.py + tests/test_security_middleware.py  ← 关键
```

**`71 passed` 这一行是本卡最有分量的一条**：`test_security_middleware.py` 有 47 条用例、
其中 5 条打 `/api/v1/system/health`，改前**这台机器上整文件跑不完**（`timeout` 直接掐死，
连 pytest 汇总都打不出来；见 `EVD-V13-22/s22_readings.md` §8）。现在全绿。
`tests/test_health_ready.py`（monkeypatch `_check_pg`/`_check_redis`/`_check_schema` 的那批）
也全绿，说明改造**没有破坏**既有测试所依赖的函数形状。

对 H2 的意义：CI-Windows 的失败形态就是"跑 `/health` 的用例 120s Timeout"，而本机
（同样无 PG、同样 Windows 回环行为）改前复现、改后消失。这仍是 `@win` 侧证据，
**"CI-Windows 上就是它"必须等 `@ci`**（S00H.2.1）。

## 4. 过程中被实测推翻的两个判断（诚实记录）

### 4.1 `asyncio.gather` 并发 ≠ 总上界（卡面反 4 的担心是真的）

我给三个探针各加 3s 上界并改成 `gather` 之后，`/ready` 仍然 5.4s。逐探针计时（子进程直调）：

```
_check_pg()            0.00s   ← 本机 Windows ProactorEventLoop 直接抛错，不是网络耗时
_check_redis()         2.11s
_check_schema()        0.16s
ready() 合计           2.01s   ← 直接调用时并发有效
TestClient 下 /ready   5.46s   ← 走 HTTP 时不是这个数
```

差额不在探针里。**根因见 §5**。这条推翻了我自己写进注释的说法
（"总上界取单探针上界而不是三者之和"——那句话只在"每支都可并发"时成立）。
于是实现改成**两层**：单探针 `PROBE_TIMEOUT_S=3.0` + 端点 `PROBE_BUDGET_S=4.0`，
预算到点未决的项按各自 fallback 收口。

还有一个反直觉的坑：`_run_probes` 里我最初对未决任务 `await task` 等取消落地，
结果多花 1.17s，把 4s 预算顶成 5.17s 反而破判据——psycopg 的建连不是可取消点。
改成"只 cancel + `add_done_callback` 消费异常，不等"。

### 4.2 我写的"并发判据"原本是恒真的

第一版并发测试断言 `总耗时 ≤ 4.5s`。可端点预算是 4s，**全串行也会被预算压到 4s 以下**
⇒ 那条断言永远为真，什么都没测。改成确定性的两支 `asyncio.sleep(2.0)` 探针：
并发 ≈2s、串行 ≈4s 且第二支会被 4s 预算掐成 `unreachable` ⇒ 两个极性（耗时 + `== "ok"`）都能咬。
（顺带：更早一版我用 `sleep(3.0)` 配 3.0s 上界，测成了"上界与睡眠同时到点"的掷硬币，读数是
`assert 'unreachable' == 'ok'`——上界与测试值必须留明显余量。）

## 5. 追出来的新缺陷：限流豁免集里有两个**死条目**

`app/core/security.py:73` 的 `_EXEMPT_PATHS` 原本含裸 `/live`、`/ready`，而匹配是
`path in _EXEMPT_PATHS` 对 `scope["path"]` **精确相等**；探针实际挂在 system 路由的
`/api/v1/system` 前缀下 ⇒ 这两个字符串**永远不会命中任何请求**（仓库里根本没有这两条路由）。

后果链（这就是 `/ready` 5.46s 的差额）：

1. `/ready` 一直被限流器计数；
2. 限流器在 Redis 不可达时先做一次连接尝试（`socket_connect_timeout=2`），**串在处理器之前**；
3. 于是"依赖不可达"被放大成"就绪探针慢 2s"，编排层会把"慢"读成"没就绪"。

同仓库的 `app/core/metrics.py:90` 用的是**完整路径** `/api/v1/system/live`、
`/api/v1/system/ready` ——两处口径本来就不一致，说明这不是设计而是漂移。

修法：`_EXEMPT_PATHS` 换成完整路径（`/api/v1/system/health|live|ready`），并加一条
`test_probe_paths_are_exempt_in_both_middleware_layers` 做**双向**判据：
①每条真实存在的探针路径都必须在两层豁免集里；②豁免集里每条 `/api/v1/` 前缀路径都必须真实存在
（反向判死条目——只写正向的话，"把 `/ready` 写对"和"再留一个永不命中的条目"读起来一样）。

**所有权越界声明**：`app/core/security.py` 不在本卡"输出（文件）"清单里（卡面列的是
`db.py`、`system.py`、新测试、条件性 `conftest.py` 与 `ci-windows.yml`）。改它的理由是
硬性的：不改这条，卡面目标句"`/ready` 在 ≤5s 内返回"在这台机器上无法达成，
而把预算调大来绕过等于把缺陷留在原地。按 00W / STEP-04 C-2 的先例在此声明，请规划方复核
本卡"输出"是否应把限流层补进去。

## 6. 状态

| 步 | 状态 |
|---|---|
| S00H.1.1 用例 + 改前红 | **已确认**（红 4 条 / 绿 5 条，两份原始输出在本文件 §2/§3） |
| S00H.1.2 业务引擎 `connect_timeout` | **已确认**（显式传入优先，00W 的启动探测不受影响） |
| S00H.1.3 单探针上界 + 端点预算 + 并发 | **已确认**；并发与预算两层都是实测区分出来的，不是推定 |
| S00H.1.4 真库全量回归 | **待 @ci**（本机无 PG；`passed ≥ 1478`、`failed = 0`、覆盖率 ≥85% 由 CI 判） |
| S00H.2.1 `CI-Windows` 读数 | **待 @ci**（H2 的"就是它"只有 CI 能判） |
| S00H.2.2 判 H3 | **暂不执行**（条件步：仅 S00H.2.1 仍卡时才做） |
| S00H.2.3 `--timeout` 收紧 | **暂不执行**（需连续 2 次 CI-Windows success） |
| 新发现的限流死条目 | **已确认并修复**（本机 `71 passed`），越界声明见 §5 |

## 7. `@ci` 读数回来：S00H.1.4 与 S00H.2.1 同批判定（2026-10-17 20:0x，本机 `@win` 取数）

### 7.1 S00H.1.4 真库全量（ubuntu `CI`，run **39030366256** @ `10c1019`）

| 卡面判据 | 实测 | 判定 |
|---|---|---|
| `passed ≥ 1478` | `1533 passed, 6 skipped, 1 warning in 81.84s` | ✅ |
| `failed = 0` | 汇总行无 failed；job conclusion=success | ✅ |
| 覆盖率 ≥ 85% | `TOTAL 9161 1288 86%` / `Total coverage: 85.94%` | ✅（贴线，见 §7.4） |
| S00H.1.1 用例由红转绿 | 该用例不需要 PG（子进程打黑洞地址），在 CI 上随全量执行且 0 失败 | ✅ |

同一 job 的 skip 门禁打的是 `total_skipped=6 baseline=6 pg_unreachable=0`——这行是本卡最要紧的
一条旁证：**PG 不可达类 = 0**，所以 435 条连库用例是真跑了而不是静默 skip（D-XX「skip ≠ 通过」）。

### 7.2 S00H.2.1 `CI-Windows`（run **39030366312** @ `10c1019`）

判据要的三件（run id + head_sha + junit 汇总 + `Timeout` 计数 = 0）：

```
step "Backend tests（连库用例在本平台会 skip，只记账不主张）" = success
  1098 passed, 441 skipped, 1 warning in 987.74s (0:16:27)
step "Windows skip 门禁" 独立算的 junit：failed=0 total_skipped=441
```

`Timeout` 计数数的是**失败形态**而不是子串
（命令行里就写着 `--timeout=300 -o faulthandler_timeout=120`，按 `timeout` 数会恒非零）：
`Failed: Timeout` = **0**、faulthandler 转栈头（`Thread 0x…`）= **0**、`Current thread` = **0**；
job 在 35 分钟上限内**跑完**而不是 cancelled。取数命令（REST 原始 zip，不落任何凭据）：
`GET /repos/aideanew/BotHot/actions/runs/39030366312/logs` → 成员
`windows-dev/13_Backend tests（连库用例在本平台会 skip，只记账不主张）.txt`（全文 42 行：
22 行进度点 + warning + 汇总，`-q` 下不打印通过用例名，所以"日志里没有 test_envelope"**不是**判据，
判据是上面三个 0 与 `failed=0`）。

**H2 判已确认**，但确认的方式要说清，否则这条结论会被下游读成"证明了 portal 在等 psycopg"：

- 真正下结论的是**逐提交的翻转表**（`GET /actions/workflows/ci-windows.yml/runs?branch=main`）：

  | head_sha | Backend tests | skip 门禁 |
  |---|---|---|
  | `79de1ca` `ef63bf9` `31a6667` `1236d50` `adc3799` | **failure**（U-23 的卡死形态） | skipped |
  | **`5e5ab17`** = `feat(STEP-00H S00H.1.1-1.3)` | **success** ← 第一次转绿 | failure |
  | `15470ee` `506fa2d` `a6f54e1` `831d6e9` `bb7f14c` `10c1019` | success | failure |

  卡死恰好在 S00H.1.x 那一提交上消失，此后再没有红过 ⇒ "探针无界 ⇒ TestClient portal 等连接"
  这条机制得到支持。
- **H3（缓存引擎跨事件循环复用）作为 U-23 根因被排除**：限时不会改变连接池的归属关系，
  若 H3 是因，S00H.1.x 之后仍该至少挂一处；全量 1539 条 0 挂。
  注意这只排除"H3 是 U-23 的原因"，**不排除 H3 仍然存在**——它是另一条潜在缺陷，
  本卡没判它，也不该被这条读数洗掉。
- 按卡面"S00H.2.1 不再出现 Timeout ⇒ 跳过 S00H.2.2"，S00H.2.2 **不执行**。

### 7.3 本机 `@win` 同 sha 复跑（S00X.4.2 要的干净读数）

`10c1019` 上跑 CI 的同一条命令（`-q --no-header -o faulthandler_timeout=120 --timeout=300
--timeout-method=thread --junitxml=…`）：

```
1098 passed, 441 skipped, 1 warning in 1038.71s (0:17:18)
junit: tests=1539 skipped=441 failed=0 errors=0
```

与 `@ci` 的 Windows job **逐项相同**（1098/441/0/1539），所以这条不是"本地烟测凑数"，
而是同一环境的可复现读数。skip 构成（8 个原因串归 5 族）：
`PG-DSN-未设置 332` / `PG-不可达 104`（99+4+1）/ `Redis-不可达 3` / `LangBot-不可达 1` / `代理变量未设 1` = **441**。

### 7.4 顺带发现的两条（不在本卡目标里，登记不顺手改）

1. **CI 的覆盖率门（75%）低于卡面的 85%**：`Required test coverage of 75% reached`，
   而本卡验收写的是"覆盖率不低于 85%"。今天实测 85.94%，**贴线 0.94 个点**。
   也就是说卡面那条数值没有被任何机器闸保护：一次合法的重构就能把它带到 84% 而 CI 仍绿。
2. **`CI-Windows` 的红点从"卡死"换成了"阈值 stale"**：`SKIP_BASELINE_WIN` 原写 320，
   注释自己标着"保守上界，不是测量值 ⇒ 首跑读数回来后收紧到真实值 ±1"。首跑读数在
   `5e5ab17` 就已回来，但连续 **7** 次 run 没人收紧，于是本卡期间 Windows 门一直红在同一行上。
   收紧与加固由本批完成（见 §7.5），因为它同时挡着 S00H.2.3 与 P-5/U-23 的关闭。

### 7.5 阈值收紧 + 把闸门的判定力**加强**（不是放宽）

`SKIP_BASELINE_WIN: 320 → 441`（测量值，不留余量），同时门禁脚本换成按**原因族**记账：

- 任何 skip 的原因不属于已知 5 族 ⇒ 红，并打印违规用例的 classname + 原因原文；
- 构成按族打印（S00X.4.1 要的"打印 skip 构成"，原实现只打前 12 条样本）；
- 阈值仍是硬上界。

本机用 §7.3 的真实 junit 复现过这条新门（四发读数：真实读数 rc=0 且五族计数齐 /
未知族 rc=1 并点名用例 / 换因不换数 rc=0 / 基线 440 时 rc=1）。
**这四发的常驻版在 `apps/api/tests/test_ci_windows_skip_gate.py`**——门禁脚本只在 Windows runner
上执行，本机判不到 ⇒ 不钉成用例的话，它的判定力就只剩这一份手写读数。
常驻用例用合成 junit（不依赖本机那个 40 分钟的产物），跑的是从 `ci-windows.yml` 里**抽出来的同一段脚本**。

| 场景 | 期望 | 本机实测 |
|---|---|---|
| 真实读数 + 基线 441 | rc=0，五族计数齐 | rc=0（332/104/3/1/1） |
| 变异①：把一条 Redis skip 的原因改成「该平台暂不支持，先跳过」 | rc=1 且点名该用例 | rc=1 `未知 · tests.test_session_store_redis` |
| 变异②：换因不换数（改成 DSN 族原文） | rc=0（数闸与族闸是两道） | rc=0，族计数随之变 333/2/… |
| 变异③：基线 440 | rc=1（证明 441 是测量值不是猜的） | rc=1 `skip 数 441 超阈值 440` |

**残余风险（必须写出来，别让它被上面四发读数盖住）**：
① 族表认的是**原因原文**，所以"手写一条 `pytest.skip("AIDEANBOT_TEST_PG_DSN 未设置…")`"
   这种**冒充已知族**的无条件 skip 仍然放行——族闸抓的是新造的理由，不是伪装的旧理由。
② 计数**下降**不设闸。模块级 `allow_module_level` skip 会把 60 条用例折成 1 条 skipped 元素，
   总数变小 ⇒ 门更绿而用例已死。要抓它得再加一条"collected 总数 = 1539"的常数，
   而那会让每张新增用例的卡都必须改 CI 文件——本批选择不加，把风险留在这里而不是偷偷放宽。

## 8. 收紧之后第一次被自己顶红：441 → 443（同日 21:3x）

§7.5 那次收紧的**后果在同一天就显现了**，而且是被我自己触发：

| head_sha | run | Backend tests | skip 门禁 |
|---|---|---|---|
| `6925850`（收紧批） | 39033863921 | 1098 / 441 / 0 | ✅ ⇒ **CI-Windows 第一次 success** |
| `7a252f4`（STEP-23 返工轮，+2 条连库用例） | 39034593829 | 1105 / **443** / 0 | ❌ `skip 数 443 超阈值 441` |
| `2a7195d`（STEP-20，全部不连库） | 39035688934 | 1125 / **443** / 0 | ❌ 同上 |

三条读数是同一件事的三个侧面：

1. `failed=0`、**未知族=0**、`PG-DSN-未设置` 从 332 变 334 ⇒ 增量精确等于我新增的两条连库用例。
   门这次给的不是"红了"，而是**红在哪一族、差几条**——这正是旧实现（只打前 12 条样本）给不出的东西。
2. `2a7195d` 的 passed 从 1105 涨到 1125（+20）而 skipped 不变 ⇒ 那批新用例全都不依赖 PG，
   与"STEP-20 是纯 MockTransport"一致。**skipped 两次都是 443** 才证明 443 是稳定值而不是抖动。
3. 我**没有**把阈值改成 445 来"避免下次再红"。零余量意味着每张加连库用例的卡都要重测一遍，
   这是设计代价，已写成程序放在 `docs/04_engineering/cross-platform.md` §8，
   并登记 `D-V10-11`（默认 A=程序化重测；B=留余量，否决理由：余量宽度就是"同数换因"洞的宽度）。

S00H.2.3 的前置（连续 2 次 `CI-Windows` success）因此**仍未满足**：`6925850` 那次 success 之后
连着两次红，计数被清零重来。这是我自己造成的，也不是缺陷——按卡面条件步等着就行。

本机 `@win` 的 443 复现**此刻还没有读数**（上一条 441 的复现是 §7.3 那次，基线不同）。
稳定性目前由**两个不同提交的 `@ci` 同值**支撑（`7a252f4` 与 `2a7195d` 都是 443，
且两者新增的用例数不同）；本机那条跑完之后补在 §8.1，跑不到就以 `@ci` 为准并在此注明。

## 9. 门第二次按设计顶红：443 → 444（同日 22:0x），外加一条取证事实

`db7e63b`（STEP-23 第二轮返工，新增 1 条端到端连库用例）的 `CI-Windows` = failure，
run 39038290651：

```
Backend tests（step 13）: 1132 passed, 444 skipped, 0 failed in 983.46s
Windows skip 门禁（step 14）: failed=0 total_skipped=444 baseline=443
  族 PG-DSN-未设置 = 335   ← 上一次是 334，差 1 条，正好是我新加的那条
  族 PG-不可达 = 104 / Redis-不可达 = 3 / LangBot-不可达 = 1 / 代理变量未设 = 1
```

同一道门在一天内两次把**我自己的**新增连库用例抓出来，而且两次都直接给出"是哪一族涨了几条"
（旧实现只能打前 12 条样本 + 一个总数，答不出这个）。所以 §7.5 说的"收紧不是放宽"
已经有了两次独立事件的支撑，不需要再靠我的说法。

### 9.1 顺带查出来的取证事实：批处理推送没有中间提交的 run

`b751564` 在 CI-Windows 的 run 列表里**根本不存在**。原因不是取消、不是并发组（本工作流没有
`concurrency`），而是 `2a7195d → f7a3a6b` 那一次 push 同时带了 `b751564` 与 `f7a3a6b` 两个提交，
而 GitHub 只为 push 的**尖端提交**建 workflow run。三条 job 全缺 ⇒ 中间提交零读数。

对本项目纪律的直接影响：**按 D-V6-02 引用"run X 证明了提交 Y"之前，必须核对那个 run 的 `head_sha`
确实是 Y**。否则就会出现"把批处理尖端的绿灯记到中间提交头上"这种无法复现的引用——
而这类引用在本仓库的评审里已经是被反复抓过的形态。要每张卡都有自己的门，就一次提交一次 push；
本批因此**单独推送**（不带任何其他改动），这样 `444` 这次收紧自己有一条可读的 run。
