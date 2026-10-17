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
