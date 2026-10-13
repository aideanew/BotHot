# EVD-V2-00R — STEP-00R 测试基线收口（本机执行账）

基线：`main@86269a2`（V0.3.0 规划包入库后）→ 本次提交
执行环境：Windows 10 x64 / Python 3.11（系统解释器）/ **无 venv、未装项目依赖**
（`python -c "import httpx"` → ModuleNotFoundError，`pip list` 无 sqlalchemy/psycopg/
pytest-asyncio；`make` 与 `ruff`/`mypy` 亦不在 PATH）。
执行者约束：本项目「无需安装开发环境和依赖」+ 本任务「不实际启动服务」，故凡需 PG/Redis/
venv 的验收命令一律**不执行**，改为「静态可证部分实跑 + 运行时部分交人工」，逐条见 §4。

## 1. 本卡闭合了什么

| 原子任务 | 状态 | 本机实跑证据 |
|---|---|---|
| S0R.1.2 代理隔离夹具（根因修复本体） | ✅ 代码落地 + 真实执行证明 | §2 全部 24 条 PASS |
| S0R.1.1 `test_env_isolation.py` | 🟡 用例已写，**运行交 venv**（`import httpx`） | §4 交接头目 H-1 |
| S0R.2.1 `tests/fixtures/net.py` + 卡面要求的 4 处收敛 | ✅ 落地 + 机器证明 NR-8/NR-9（判定面覆盖 5 个消费方，见 §2 NR-9 / §7 N-4） | `out_evidence_check.txt` |
| S0R.2.2 chat_sse 未配置守卫 | ✅ 落地（1 处而非 2 处，理由见 §3.2） | NR-10-a/NR-10-b |
| S0R.2.3 陈旧注释清零 | ✅ | NR-11 |
| S0R.4.1 `make evidence-check` | ✅ 目标已写；**本机无 make**，逐条 recipe 等价实跑 7/7 rc=0 | `out_evidence_check.txt` |
| S0R.4.2（本卡新增）harness 编码自适应 | ✅ 修 `prove_dsn_policy.py` 在 GBK 控制台崩溃 | §3.4 |
| S0R.5.1 STEP-00 卡回写更正 | ✅ 追加段（不改历史段落） | 见 V0.2.0 卡末尾 |
| S0R.1.3 / S0R.3.1 / S0R.3.2 | ⏳ 需隔离 PG + venv，交人工 | §4 |
| S0R.3.3 `ci.yml` 注释更正 | ⛔ 需 D-11 人拍板，Agent 不得代决 | §4 |

## 2. 代理隔离的机器证明（`prove_net_isolation.py`）

不能 `import conftest`（模块级 import `sqlalchemy`，本机 `ModuleNotFoundError`；第五轮复审纠正了
本节的旧口径——原先写的是「sqlalchemy/dotenv/pytest 本机皆无」，实测 `pytest` 可导入（9.1.1）、
`dotenv` 可导入。普查读数：**有** `pytest` / `dotenv` / `anyio`，**无** `sqlalchemy` / `httpx` /
`structlog` / `pytest_asyncio` / `coverage` / `psycopg`，PATH 里 `uv` / `ruff` / `make` / `mypy` / `gh`
全都不存在——见 `out_evidence_check.txt` 的依赖实测行，本节不再凭回忆写「本机皆无」），故沿用
EVD-V2-00 已确立的机制：AST 剔除三方 import 后 exec 前缀取真实常量，再**剥掉装饰器
exec `_isolate_proxy_env` 的当前函数体**，用按 `pytest.MonkeyPatch` 语义实现的替身
（`setenv`/`delenv(raising=)`/`undo` 全部作用在真实 `os.environ`，前后由 `sandbox`
快照恢复）驱动它。被执行的是文件里的代码，不是抄本。

```
合计 PASS=24 FAIL=0
SELF-TEST PASS：20 个 conftest 变异体各自让对应断言变红 + 18 个源码探针敏感 + 13 个等价重构不假红
```

（两个数字都由脚本按 `len(MUTANTS)`/`len(TEXT_PROBES)`/`len(EQUIV_REFACTORINGS)` 动态打印；
本节文字复述它们只是为了让人能核对，出现分歧以命令输出为准。）

断言分面（完整输出见 `out_evidence_check.txt`）：
- NR-1/NR-2 `@pytest.fixture(autouse=True)` 且函数级 scope（缺省）；
- NR-3 夹具定义在 DSN 广播语句之后（广播 :75、夹具 :92）⇒ 不改动 S0.1.2 语义；
- NR-4 预置 6 个代理变量 + 污染 `NO_PROXY` 后调用夹具：6 个全清、`NO_PROXY`/`no_proxy`
  均等于契约值 `127.0.0.1,localhost,::1`。
  **win32 口径**：Windows 的 `os.environ` 键大小写不敏感（实测先设 `NO_PROXY=A` 再设
  `no_proxy=B`，进程里只剩一个条目、值为 B），故「6 个变量」在本机实际折叠为 3 个键；
  夹具在两个平台都正确（覆写两次、undo 复原宿主值），但判据强度在 win32 上等于 3 键——
  这一点写进 NR-6 的期望值算法，不在文档里假装跨平台一致（Linux CI 上仍按 6 键 + `None` 判）。
  「小写那一遍有没有真的写」在 win32 上属**行为不可观测**，改由结构判据 NR-14 承接（第二轮复审 N-1）。
- NR-5 干净环境（无代理变量）调用不抛 ⇒ `delenv(..., raising=False)` 生效；
- NR-6 `undo()` 后**在 sandbox 退出之前**取样：`NO_PROXY` 回到宿主原值、`no_proxy` 回到
  宿主原状态、`HTTP_PROXY` 复原 ⇒ 夹具确实经 `monkeypatch` 记账，而不是直写 `os.environ`。
  （早先版本把取样放在 `with sandbox()` 块**之外**，测到的是 sandbox 自己的还原，
  该断言永远不可能红——复审发现后已修，并补了对应变异体。）
- NR-7 清理动作不波及 `AIDEANBOT_TEST_PG_DSN`（广播值仍在）；
- NR-8 `apps/api/tests` 全树 `localhost:9999` 命中 0；
- NR-9 地址常量单点：`fixtures/net.py` 端口为 1；消费方清单为 5 个文件（卡面要求收敛的 4 个 +
  本步新写的 `test_env_isolation.py`，后者是第二轮复审 N-4 补进来的——不列它则它退回字面量时无人报警）。
  判定按 **AST**：「`webhook_url=<REFUSED_HTTP_URL 或其模块级别名>` 实参确实存在」——不是「文件里出现了这个
  名字」；test_w3 的旧常量退化为别名且文件内不再自带 URL 字面量（别名行号动态取，现 :49）；
- NR-10 chat_sse 冒烟的**首条可执行语句**即 `if _PG_URL_SOURCE == "unset": pytest.skip(...)`，
  且所需两个符号已从 conftest 导入；
- NR-11 「见 conftest 警告」陈旧注释命中 0；
- NR-12 `test_env_isolation.py` 有 3 条用例、每条 ≥1 assert、宿主代理快照在首个用例之前；
- NR-13 conftest 侧常量的契约下限（6 个键逐字、值含回环）；
- NR-14 **结构判据（与平台无关，「每一次写入」都算）**：夹具对 `NO_PROXY` 与 `no_proxy` 的
   **每一次**环境写入，值都必须解析为 `NO_PROXY_ISOLATION_VALUE` 或契约字面量；
   某拼写一次都没写也算不合格。补这条的原因见 §7 N-1——win32 上两拼写指向同一键，
   「小写那一遍没写」属行为不可观测。判据形态演进四轮，每一轮都是被反证逼出来的：
   v1 只比「字面量名集合」→ `setenv("NO_PROXY", "localhost")` 混过去；
   v2 按位置配对但 `setdefault` 只记第一条 → 「先契约值、后坏写」的双写全绿（第四轮复审实测）；
   v3 收集全部写入 + 位置/关键字实参通吃 + `ast.walk` 深入嵌套分支 →
   双写、以及 `if os.name != "nt": setenv("NO_PROXY", "evil")` 这类**平台守卫后的坏写**
   （win32 行为面永远看不见它）都红，而 `setenv(name=…, value=…)` 这种等价写法不假红（§2 通道③）；
   **v4（现版）**补的是 v3 的两个隐含前提——「写入只可能是 `monkeypatch.setenv`」和「名字是字符串字面量」：
   ①手段扩到 `os.environ.setdefault` / `os.environ.update({...})` / `os.environ[…] =` / `os.putenv`
   （第五轮复审 D1：`os.environ.setdefault("NO_PROXY","evil.example")` 全绿——本脚本沙箱把
   `NO_PROXY` 预置成宿主值好让 NR-6 观测 undo，setdefault 因此是空操作，行为面看不见这次写入）；
   ②名字扩到 f-string / 拼接 / 循环变量 / `**{字面量字典}` 展开，且**名字解析不了也照样要求契约值**
   （D2/D3/D4：v3 的 `isinstance(name, ast.Constant)` 一跳就跳过整条写入）。
   「两种拼写都必须被证明写过」这一半没松：否则删掉小写那行又回到全绿。
- NR-15 **结构判据：清理必须遍历模块级 `_PROXY_ENV_VARS`**（迭代源是该 `Name`，或它的可迭代包装
  ——可嵌套 `tuple(sorted(…))`、`reversed`/`map`、推导式源 `[x for x in …]`、海象别名
  `(_vars := _PROXY_ENV_VARS)`；循环体内 `delenv(循环变量, 假值 raising)`，实参按槽位取，
  位置/关键字/`**{…}` 展开都认，`if _name in os.environ:` 守卫下省略 `raising` 也算）。理由是行为判据
  NR-4-a 预设的是**本脚本自己抄的那份清单**——夹具改成硬写六个字面量时当下仍全绿，将来常量新增一项
  而夹具没跟上就无人报警；把常量定义整行删掉时，这条与 NR-13-a 一起红。
  放宽的只有**写法**：迭代源是硬写的同值元组/列表仍然不算接线（那是 NR-15 要抓的形态本身）。
- NR-16 **行为判据：运行期哨兵**（往常量表追加 `AIDEANBOT_SENTINEL_PROXY_VAR`，夹具必须跟着删它）。
  它是 NR-15 的盲区补位：第四轮复审 P-3 造出「真接线循环留在 `if False:` 里、活路径改硬写同值元组」
  的夹具，结构判据照绿（那个循环确实还在文件里），只有注入哨兵看**行为**才能分辨「读常量」与「抄一份」。
  反向亦然：纯写法变化（`list(常量)`）会被结构判据误伤，哨兵却不受影响——两条判据互为补位，
  不是一条款的两遍。
- NR-17 **结构判据：隔离夹具内不得出现任何平台身份读数**（`os.name` / `sys.platform` /
  `platform.*` / `sysconfig.*`，或与 `"nt"`/`"win32"`/`"linux"` 一类平台字面量比较）。
  它是 NR-16 的盲区补位，方向正相反：NR-16 是**运行期**哨兵，因而跑在本机平台上——
  第五轮复审 D5 造的 `if os.name == "nt":` 包住整个清理循环，win32 上守卫为真，
  于是 NR-4-a（六键真的清了）、NR-15（循环仍在遍历常量）、NR-16（哨兵真的被删）三层全绿，
  而 Linux CI 上一个代理变量都不清。这正是第四轮 P-2（守卫后的坏写）的镜像形状：
  同一种平台盲，两面都得用结构面直接禁掉。
  **契约性质**：这是设计约束而不是观测结论——夹具存在的意义就是让测试出站与宿主/平台无关，
  win32 的键折叠已由「两种拼写无条件都写契约值」解决。将来若真要按平台分支，必须先改这条契约
  并交人工裁决，而不是在夹具里加守卫（加守卫当场红 NR-17，变异体 ⑳ 就是钉这一条的）。

变异反证（`--self-test`）：先要求**基准（未变异 conftest）全绿**——否则「变异体让某条变红」
这个信号毫无意义（这条闸门上线当场就抓到我自己写的 `getattr(n, "targets", [n.target])`：
默认值是即时求值，`ast.Assign` 没有 `.target` ⇒ 直接 AttributeError，见 §8）。三条通道——
前两条形如「改坏必须红」，第三条方向相反（「改写法必须不假红」），每条都必要：

1. `MUTANTS`（改 conftest 源码后重跑 `evaluate()`，共二十个变异体）：
   ①去掉 `autouse` → NR-1；②删 `delenv` 循环体 → NR-4-a + NR-15；③`raising=False`→`True` → NR-5；
   ④把回环地址从常量里删掉 → NR-4-b + NR-13-b；⑤**夹具直写 `os.environ` 绕过 monkeypatch** →
   NR-6（第五轮前它还顺带让 NR-14 红，因为 v3 只认 `setenv`；v4 认得 `os.environ[…] =` 这条通道，
   该写入因此「被看见且值合法」⇒ 现在**只** NR-6 红，反证职责由 NR-6 独立承担，见 §10.5）；
   ⑥**删掉小写 `no_proxy` 那一遍** → NR-14；
   ⑦**大写那遍写非契约值**（小写那遍随后把同一个键盖回契约值 ⇒ win32 行为面 NR-4-b 仍绿）→ NR-14；
   ⑧**清理循环与常量脱钩（改硬写元组）** → NR-15 + NR-16；⑨**删掉常量定义整行** → NR-13-a + NR-15
   （必须判红而非 harness 崩溃，否则没有「哪条红」的可核对信号）；
   ⑩`scope="session"`（`autouse` 仍为 True，只有 NR-2 能红）；⑪广播行被改名/挪走 → NR-3；
   ⑫夹具顺手 `delenv` 掉 DSN 变量（清了广播值）→ NR-7；
   ⑬同一拼写「先契约值、后坏写」双写 → NR-14（v2 判据的漏检，见上）；
   ⑭`if os.name != "nt": setenv("NO_PROXY", "evil.example")` 平台守卫后的坏写 → NR-14（本机永不执行），
   第五轮起 **同时** NR-17 红（夹具里出现 `os.name` 读数本身就被禁，见 §2 NR-17）；
   ⑮真接线循环塞进 `if False:`、活路径改硬写同值元组 → 只有 NR-16 红（结构判据的盲区）；
   ⑯**`os.environ.setdefault("NO_PROXY", "evil.example")`** → NR-14（第五轮 D1：沙箱本就预置了
   `NO_PROXY`——NR-6 要靠它看 undo——所以 setdefault 是**空操作**，行为面永远看不见这发坏写；
   而 v3 判据只认 `setenv`，结构面也绿）；
   ⑰**f-string 名 + 平台守卫** `if os.name != "nt": setenv(f"NO_PROXY", "evil")` → NR-14 + NR-17
   （第五轮 D2：名字不再是 `ast.Constant`，v3 的 `isinstance(name, ast.Constant)` 直接跳过整条）；
   ⑱**循环变量名** `for _n in ("NO_PROXY",): setenv(_n, "evil")` → NR-14（第五轮 D3：名是 `Name` 节点）；
   ⑲**`**` 字典展开** `setenv(**{"name": "NO_PROXY", "value": "evil"})` → NR-14
   （第五轮 D4：`call_arg` 只看 `kw.arg`，关键字通道被展开式绕过——这发与等价通道里的
   `delenv(**{…})` 是同一个语法的两面，坏写必须红、合法写法必须绿）；
   ⑳**清理循环被 `if os.name == "nt":` 包住** → 只有 NR-17 红（第五轮 D5，⑭ 的镜像：
   守卫包住的不再是坏写，而是**隔离本身**。win32 上守卫为真 ⇒ NR-4-a/NR-15/NR-16 三层
   ——含运行期哨兵——**全部照绿**，只有 Linux CI 上一个代理变量都不清）。
   ⑩…⑮ 六个个体是第四轮复审逼出来的：此前 `evaluate()` 只重放 NR-1/4/5/6/13/14/15，
   NR-2/NR-3/NR-7 三条判据**没有任何通道能证明它们会红**。
   ⑯…⑳ 五个个体是第五轮复审逼出来的，且**每条都先在我自己机器上跑出过「改前 red=[]」**
   （逐条读数见 §10.1，不在这里转述）。
   ④之所以能红，是因为期望值 `EXPECTED_NO_PROXY` 在 harness 里**写死为契约字面量**
   而不从 conftest 读——否则变异体会连同期望一起改，断言永不可能失败（G-23）。
2. `TEXT_PROBES`（NR-8..NR-12 读真实文件，改 conftest 变不红它们）：对内存样本源码跑**同一个
   判定函数**，要求基准为真、变异体为假，共十八探——
   「NR-9-b 的四种接线形态（退回字面量 / 只 import 不接到形参 / 丢 import / 经模块级别名）」+
   「NR-8 用例退回 `localhost:9999`」+「NR-11 陈旧注释回潮」+
   「NR-12 三个面各自退化（用例数变 2、某条无 assert、快照移到用例之后）」+
   「NR-9-a 两条（常量退回 9999 假设 / 常量定义整行被删）」+
   「NR-9-c 两条（别名退回自带字面量 / 别名行消失）」+
   「NR-10-a 三条（守卫挪到 import 之后 / 条件在但体内不 skip / 用例函数改名）」+
   「NR-10-b 两条（导入行少 `SKIP_UNSET_REASON` / 导入行整体缺失，守卫自身 NameError）」。
   后九条即第三轮补的 NR-8/NR-11/NR-12 与第四轮补的 NR-9-a/NR-9-c/NR-10-a/NR-10-b：
   补之前它们「0 命中就绿」却**没有任何通道证明能红**。
3. `EQUIV_REFACTORINGS`（第四条通道在第四轮加入，方向相反，共十三条）：**等价重构必须保持全绿**。
   第四轮四条：`setenv(name=…, value=…)`、`delenv(_name, False)`、`delenv(name=_name, raising=False)`、
   `for _name in list(_PROXY_ENV_VARS):`；第五轮再加九条（C1–C8/C10，每修一条之前都实测假红）：
   `raising=0`、迭代源改列表推导 `[x for x in 常量]`、两层包装 `tuple(sorted(常量))`、`reversed(常量)`、
   `map(str, 常量)`、`delenv(**{"name": _name, "raising": False})`、
   `if _name in os.environ: delenv(_name)`（省略 `raising` 但有成员守卫）、
   海象别名 `if (_vars := 常量): for _name in _vars:`、契约值套一层 `str(NO_PROXY_ISOLATION_VALUE)`。
   这些与现写法语义完全一致。前两条通道证明「改坏会红」，
   只有这一条能证明「判据没把合法写法也判红」。这不是假想风险：复审实测修订前
   `setenv(name=…, value=…)` 会让 NR-14 变红、`list(常量)` 会让 NR-15 变红，
   而脆性判据的实际后果是门禁被人当噪声关掉（G-23 的反面同样致命）。
   第五轮那条「ten ordinary equivalent rewrites」的批评成立得比第四轮更狠：一轮之内判据在
   NR-15 上假红 8 次、NR-14 上假红 1 次 ⇒ **放宽的只能是写法，绝不能是语义**（仍必须遍历那个常量、
   仍必须用循环变量名去删、值仍必须能证明是契约值），这一点写进 `delenv_loop_wired()` 的文档串，
   并由 ⑯–⑳ 五个变异体反向钉住（放宽后它们依然红）。

## 3. 与 V0.3.0 规划文本的偏离（已核代码后决定，非疏漏）

> 本节为详版；同一批偏离已在任务书内登记为 `steps/STEP-00R-测试基线收口.md` 执行记录 D-1…D-7
> （D-1/D-6 = §3.4/§3.5 的越路径项，D-5 = 用例由 2 条增至 3 条，D-7 = 本包文档自身的越路径）。
> 两处口径一致，改一处必须同步另一处。

### 3.1 夹具用函数级 autouse，而非卡面写的 session 级
卡文（STEP-00R S0R.1.2）写「`scope='session'` 级等价实现（session 级用
`pytest.MonkeyPatch.context()`）」。函数级逐用例应用**严格更强**：用例内自行 `setenv`
的代理不会泄漏给下一个用例，且无需引入 `MonkeyPatch.context()` 的生命周期管理。
NR-2 把「函数级」钉成契约，将来若改 session 级会红。

### 3.2 chat_sse 只加 1 处守卫，而非卡面写的 2 处
卡文写「两处加守卫」。AST 实测：`create_async_engine(PG_URL)` 的两个调用点
（改前 :1208/:1272）同属一个函数 `test_ask_real_full_chain_smoke`（:1180 起），
第二个是它内部的嵌套生成器 `_real_db`。函数首行 skip 之后第二处不可达——加第二处是
「永远不会执行的分支」，属被禁止的空洞防护。NR-10-a 因此断言「首条可执行语句即守卫」，
比数守卫个数更强。

### 3.3 本卡未把 `NO_PROXY` 当作唯一防线
只设 `NO_PROXY` 不足以确定结果：httpx 对 `NO_PROXY` 的解析随版本与大小写而异，而
**删除代理变量**才是与 httpx 版本无关的口径。夹具两件事都做，NR-4 同时断言两面。

### 3.4 顺手闭合的一处环境脆弱点（规划包未记录）
`prove_dsn_policy.py` 在 Windows 默认控制台（cp936）下会抛
`UnicodeEncodeError: 'gbk' codec can't encode character '\u21d2'` —— 它打印 `⇒` 与中文，
而同目录的 `prove_provider_shapes.py:32-33`、`g24_static_check.py:21-22` 早已各带
`sys.stdout.reconfigure(encoding="utf-8")`，只有 `prove_dsn_policy.py` 漏了。
实测（复审时按 `git show 1af68fc~1:` 取修复前副本、原样在本机跑，rc=1）：修复前会**打印 18 条
PASS 后**在第 19 条（`S0.1.2-o` 标签含 `⇒`，位置 43）崩溃——不是「一条断言都出不来」，
而是**门禁拿不到结论**（`make evidence-check` 的 `set -e` 链在此中断，rc=1）。
带 `PYTHONIOENCODING` 则 `ALL PASS (20 断言)`；补上同款两行后默认控制台 rc=0。
这意味着「任意机器一条命令复现基线」此前对 win32 开发机**不成立**，
而规划包 F-19 把它记为「本机复跑全部成立」。已修（本卡 S0R.4.2）。

### 3.5 证据输出的两处文案修正（对应任务书 D-6）
`check(label, ok, detail)` 无论通过与否都打印 detail，而 `prove_dsn_policy.py` 里
S0.1.2-b / S0.1.2-r 的 detail 被写成「失败描述句」——断言**通过**时输出仍显示
「conftest 仍含口令字面量」「广播值为空串/None」。复核者会把它读成缺陷，违反
「EVD 可让一周后的人复现」的 Done 口径。现改为观测值：

- S0.1.2-b → `字面量命中 0 处（期望 0）`
- S0.1.2-r → 三个入口的实际广播值（`｜` 分隔）

**断言表达式与判据一字未动**：`prove_dsn_policy.py` 仍是它自己的 20 条断言全过（输出尾行
`ALL PASS (20 断言，回退点 9 个已列举)`），本文件 §2 的 NR 结论与 self-test 结论也不受影响。

### 3.6 win32 的 `os.environ` 键大小写不敏感（复审中发现，已写入判据而非只写注释）
实测：`os.environ['NO_PROXY']='A'` 之后再 `os.environ['no_proxy']='B'`，进程环境里只剩
一个条目且值为 `B`。后果有两条，都不显然：

1. 夹具「清 6 个变量」在 win32 上实际折叠为 3 个键——功能仍然正确（两个拼写指向同一键），
   但**判据强度**与 Linux 不同。NR-4-a 的残留清单在两台机器上语义不等价，故 §2 明写口径。
2. `test_env_isolation.py` 的宿主快照原先按 `endswith("PROXY")` 过滤，会把夹具**覆写**的
   `NO_PROXY` 也当成「宿主代理」——宿主只要设了 `NO_PROXY`（Clash/v2ray 类代理的常规配置，
   正是本步要对付的环境）③ 就必红，把一次成功的覆写判成泄漏。现改为只快照
   「夹具承诺删除的那 6 个键」（`_DELETED_NAMES`），并把这条理由写在常量注释里。

### 3.7 本机回环对闭包端口是 DROP 而非 REJECT（第二轮复审期间实测的新环境事实，F-24）
`socket.create_connection(('127.0.0.1', P), timeout=1.0)` 在 P = 1、9、80、5547、59999 上
**全部**返回 `TimeoutError`（耗时恰为超时值 1.0 秒），而 `os.environ` 里没有任何代理变量。
即：本宿主网络层对回环 SYN 是**丢弃**，不是拒绝——与「`REFUSED_HTTP_URL` 会立刻 ECONNREFUSED」的直觉相反。

为什么这不动摇本卡结论（也别被它误导成「夹具失效」）：
- 判据锚的是「**不出现 HTTP 状态码**」（`test_env_isolation.py` ②、`prove_dsn_policy` 的同形判据），
  不是「出现拒连异常」。REJECT 走 `httpx.ConnectError`、DROP 走 `httpx.ConnectTimeout`，
  两者都命中 `webhook.py:48-51` 的失败分支、`retryable=True`、reason 里都没有 `HTTP ` ⇒ 断言在两种宿主上都成立。
- 反过来，若某宿主的代理/TUN 真的**应答**了该请求（STEP-00 的原始症状：回 HTTP 404），
  reason 会出现 `HTTP ` ⇒ 用例变红。**探测力正好落在需要它的位置。**
- 代价是时间：`_WEBHOOK_TIMEOUT = 10`（`webhook.py:12`），本机每次经该 URL 的用例约阻塞十秒，
  比「秒拒」的假设慢一个量级 ⇒ 见 §4 H-1 的时长预期，勿把慢当成挂死。
- 名字层面：`REFUSED_HTTP_URL` 在本机是误称。不改名的理由是它已是跨四个文件的单点常量
  （改名会牵动 NR-9 的消费方清单与卡面原文），故在此登记为已知语义偏差。

## 4. 交人工/有依赖环境的项目（附可复制命令）

| # | 项 | 为什么本机不能做 | 命令 |
|---|---|---|---|
| H-1 | S0R.1.1 用例实跑（卡面写「改前 2 failed / 改后 2 passed」，那是它只预见 2 条用例；本文件有 3 条 ⇒ 在有代理的宿主上期望 **改前 3 failed / 改后 3 passed**，若宿主只设 `NO_PROXY` 则 ③ 为 skip 而非红）。**时长预期**：在回环为 DROP 的宿主（本机即此类，见 §3.7）每条走 `REFUSED_HTTP_URL` 的用例会阻塞约 `_WEBHOOK_TIMEOUT=10` 秒，且 reason 为「webhook 请求超时」而非拒连——两者都仍满足断言 | 用例 import httpx（`WebhookPushProvider`），本机无依赖 | `cd apps/api && HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 uv run pytest tests/test_env_isolation.py -q` |
| H-2 | S0R.1.3 双环境全量一致 | 需隔离 PG16@5547（不起服务约束） | 见卡内 `eval "$(bash scripts/test-env.sh env)"` 那条 |
| H-3 | S0R.3.1 `test-env.sh up/down` 实跑 | 需 docker/本地 PG 二进制 | `bash scripts/test-env.sh up && eval "$(bash scripts/test-env.sh env)" && psql "${AIDEANBOT_TEST_PG_DSN/+psycopg/}" -c "select 1" && bash scripts/test-env.sh down` |
| H-4 | S0R.3.2 连库全量 + coverage.json 入档 | 同 H-2 | `uv run pytest tests -q -rfs --cov=app --cov-report=json:.../coverage.json` |
| H-5 | S0R.3.3 `ci.yml:28-32` 注释更正 | **D-11 未拍板**（`.github/**` 越权）；Agent 不得代决 | 授权后：改注释 + `! grep -n 'conftest 默认 DSN' .github/workflows/ci.yml` |
| H-6 | `make evidence-check` 本体 | 本机无 make | `make evidence-check`（Linux/CI 直接可跑；recipe 已核对 tab 缩进） |

另：STEP-00R 验收第 6 条「skip 仅剩 LangBot/Redis 类」依赖 H-2 的 `-rs` 输出，本机无法判定。

## 5. 反自证声明

- 本文所有「✅」均可由 §2 的命令复现；「🟡/⏳/⛔」写明缺的是什么，不含混。
- 本卡**没有**运行任何 pytest 用例（本机 conftest 无法 import），凡「测试会绿」的表述均为
  交接头目而非结论。
- 本卡**没有**改 `apps/api/app/**`：`webhook.py:33` 的 `trust_env` 行为原样保留（N-02，
  生产侧是否绕代理属 U-08）；根因在测试侧隔离，不在生产侧。
- 独立验证者须重跑 `make evidence-check`（或 `out_evidence_check.txt` 首行注明的等价链），
  并对 H-1/H-2 在有依赖的机器上补判。
- §3.7 的 F-24 是本卡**新做的主动探测**（纯 stdlib 出站连接，未启服务、未装依赖），不是引用他人结论；
  它推翻的是我自己写在 D-4 的「充分条件」措辞，不是夹具本身——若下一位复核者只看到 §2 那行
  「合计 PASS=24」而没读 §3.7，最可能犯的错是「以为该 URL 一定会秒级拒连」。
  （此处的数字会随判据增删而漂移，凡引用它都以 `prove_net_isolation.py` 当场输出为准，
  不以本句为准——第四轮复审就是拿旧数字对不上新脚本这一件事来检查我的。）

## 6. 独立复审记录（第一轮，verifier 子智能体）

复审对 §1–§5 逐条判 PASS/FAIL/UNKNOWN 并**推翻了三处**，全部已修（本轮改动即下面的落点）：

| 复审发现 | 判定 | 处置 |
|---|---|---|
| `test_env_isolation.py:31` 宿主快照按 `endswith("PROXY")` 过滤 ⇒ 含 `NO_PROXY`，在只设 `NO_PROXY` 的宿主上 ③ 必红 | FAIL（真缺陷，会伪装成「测试失败」） | 改为只快照夹具承诺删除的 6 键；理由写入常量注释（§3.6） |
| `prove_net_isolation.py` NR-6 取样在 `sandbox.__exit__` **之后** ⇒ 断言永远不可能红（G-23 违例） | FAIL（空洞断言） | 取样移到块内、期望值按平台分档；新增变异体「夹具直写 os.environ」证明它现在能红（§2 NR-6） |
| NR-9-b 只判「常量名出现在文件里」，退回字面量/只 import 不接线都探不到 | FAIL（弱判据） | 改 AST 判形参接线 + 别名闭包；新增 `TEXT_PROBES` 通道（4 条内存样本探针）证明其敏感性 |
| 「一条断言都出不来」是夸大：修复前实际打印 18 条 PASS 后在第 19 条崩溃、rc=1 | 表述不实 | 按复现实验改写 §3.4 与 `01…复核.md` §5.3 F-19 行；复现方式：`git show 1af68fc~1:<路径>` 取副本原样跑 |
| `g24_static_check.py:20` 引用落空（守卫在 :21-22）；`test_w3_push_scheduler.py:44 区` 应为 :49 | 锚点错 | 已改；NR-9-c 的行号改为脚本内动态求值，不再手写 |
| `5c8552b` 同时改了 `01…复核.md`/`00-README.md`/STEP-00R 卡本身，均不在本卡「允许修改」内，且未登记偏离 | 越路径未申报 | 登记为 D-7（含理由：落库复核必须与本卡同批入库才自洽），并把「允许修改」行的「仅补 2 行」更正为「2 行 UTF-8 保护 + 2 条 detail 文案」 |
| README §3 标题写「三处偏离」实为 5 小节、交叉引用写 D-1…D-5 而卡面已到 D-6 | 口径漂移 | 标题去数字、交叉引用改 D-1…D-7，并声明「两处口径一致，改一处必须同步另一处」 |

复审**确认无需动作**的部分（独立重跑得出）：NR 20/20 与 5 变异体、`make evidence-check` 等价链 7× rc=0、
`localhost:9999` 命中 0、D-2/D-3/D-4 的实现形态声明、F-19=32、F-16/F-20 行号、F-23 epoch 陷阱的算术、
`git status` 干净。**复审未被推翻也未被复跑的一项**：任何需要 pytest/PG 的结论——仍是 H-1…H-6。

## 7. 独立复审记录（第二轮，针对第一轮修复后的 `884572d`）

第二轮复审的对象是「修复有没有引入新问题」，推翻四项（N-1…N-4，全部已处置）并给出一个
我当时判为「理论风险」的推测（下面最后一行）——该推测随后被实测证实，反而成了本文件 §3.7 的新事实。

| id | 复审发现 | 判定 | 处置 |
|---|---|---|---|
| N-1 | 夹具「也写了小写 `no_proxy`」在 win32 上**行为不可观测**（与 `NO_PROXY` 同一个键）⇒ 若那一遍被删掉，NR-4/NR-6 全都不会红 | FAIL（探测力缺口） | 新增结构判据 **NR-14**：AST 取 `monkeypatch.setenv(...)` 的实参字面量集合，要求含两个拼写；配对应变异体「删掉小写那一遍 → NR-14 红」证明其可失败性。断言数由 20 → 21 |
| N-2 | `evaluate()` 里存在重复的 `except Exception as exc:`，第二个永不可达（我第一轮合并时留下的死代码） | FAIL（代码缺陷） | 删除重复分支；重跑确认 21/21 |
| N-3 | D-7 把越路径改动**申报**了，但「允许修改」清单里仍然没有那三份文档 ⇒ 申报 ≠ 授权 | 流程缺陷 | 在卡面「允许修改」显式补入并标注「经人工追认前视为待批」；不同意可单独 revert 文档提交，代码侧结论不受影响 |
| N-4 | `CONSUMERS` 漏了本步新写的 `test_env_isolation.py`（它自己也用 `webhook_url=REFUSED_HTTP_URL`，:54）⇒ 它退回字面量时无人报警 | FAIL（清单不完整） | 补入，消费方由 4 → 5；NR-9-b 标签改为按 `len(CONSUMERS)` 动态生成，避免再漂移 |
| — | 推测：删代理变量只覆盖「进程环境里有代理」这一种接管形态，TUN/透明代理不受 `os.environ` 支配 | 潜在缺陷（当时不可证） | 本机实测 → 回环闭包端口一律 **DROP**（`TimeoutError`）而非 REJECT，见 §3.7 / F-24；判据改锚「不出现 HTTP 状态码」，并在卡面 D-4 撤销「充分条件」的说法 |

第二轮复跑确认（不是我声明，是它独立跑出来的）：修复后 harness 结论成立、`--self-test` 全绿、
`localhost:9999` 仍为 0 命中。它**同样未能**运行任何 pytest 用例（无 venv），故 §4 的 H-1…H-6 一项未消。

## 8. 独立复审记录（第三轮）——采纳项与不可复现项分开记账

第三轮派的是只读复核子智能体（要求：不改文件、不实跑服务）。它的输出**一部分成立、一部分我复现不出来**，
两栏都记，避免「复审说过」被当成「事实」。

### 8.1 成立并已采纳（四处强化；该轮时点为 22 条断言 / 九个变异体 / 九探，第四轮之后是 23 / 十五 / 十八 + 四条等价重构，见 §9；第五轮之后是 24 / 二十 / 十八 + 十三条等价重构，见 §10）

| 项 | 成立的理由（不是因为它说了，而是我自己核过） | 落点 |
|---|---|---|
| NR-14 从「比名字集合」升级为「按位置配对（名 → 值）」 | 只比集合会漏 win32 上 `setenv("NO_PROXY", "localhost")` + 紧随其后小写那遍覆写回契约值的形态：行为面 NR-4-b 全绿 | `no_proxy_pairings()` + 变异体「大写那遍写非契约值 → NR-14 红」 |
| 新增 NR-15：清理必须遍历**模块级真有赋值**的 `_PROXY_ENV_VARS` | NR-4-a 预设的是本脚本自抄的清单 ⇒ 夹具改硬写元组时当下全绿；常量将来增项而夹具没跟上无人报警 | `delenv_loop_wired()` + 两个变异体（脱钩 / 删常量定义） |
| NR-8 / NR-11 / NR-12 三个面补内存样本反证 | 此前它们「0 命中就绿」，没有任何通道证明能红——正是 G-23 禁止的形态 | `literal_hits()` / `isolation_case_layout()` 提出来给判定函数与探针共用，新增五条探针 |
| ②（拒连用例）reason 白名单 | 「不含 `HTTP `」放行的文案其实只有两种，写死第三种就该红，防止 Provider 失败分类变更时悄悄绿 | `test_env_isolation.py` ②，注释指向 §3.7/F-24 |
| `--self-test` 先要求基准全绿 | 基准若本来就红，「变异体让它红」毫无信息量 | `self_test()` 开头的 baseline 闸门 |

baseline 闸门上线当场抓到**我自己**写的缺陷：`getattr(n, "targets", [n.target])` 的默认值是
即时求值，`ast.Assign` 没有 `.target` ⇒ `AttributeError`。这条被记在这里而不是抹掉，
因为它正是「自己复核自己」最容易漏的那类错误——判据函数在真实 conftest 上从未跑到过那一行。

### 8.2 复现不出来、已按事实驳回的两条

| 复审断言 | 我的复核 | 结论 |
|---|---|---|
| 「你新建了 `apps/api/tests/fixtures/__init__.py`，工作区干净是因为它已被提交」 | `ls apps/api/tests/fixtures/` → 只有 `net.py`/`wechat_urls.py`/`provider_payloads/`/`__pycache__`；`git log -- apps/api/tests/fixtures/__init__.py` → 空（该路径从未进过历史）；`git show --stat 1af68fc` 的文件清单里也没有它 | **不成立**。没有这个文件，我也没提交过它 |
| 「因此 `import fixtures.net` 失败，README 里那句『实测 OK』是伪造；请删掉该小节或改写成『按 PEP 四二零推断可用』」 | 两点都要纠正：①**README 里从来没有过那句结论**——`grep -n 'fixtures.net\|命名空间\|namespace\|__init__' README.md` 只命中 §1 表格与 §2 NR-9 的文件名，没有任何「import 实测 OK」的表述，所以「伪造」指控所指的对象不存在，我也无从「删掉该小节」；②它真正关心的那个风险（没有 `__init__.py` 会不会导入失败）我今天亲测：`python -c "import sys; sys.path.insert(0,'apps/api/tests'); import fixtures.net as n; print(n.REFUSED_HTTP_URL)"` → 打印 `http://127.0.0.1:1/bothot-hook-no-listener`、rc=0。机制是 PEP 四二零命名空间包：`tests/` 在 `sys.path` 上时 `fixtures` 无需 `__init__.py`。**同一机制早就在整个测试树上生效**——
`apps/api/tests/__init__.py` 也不存在（`ls` 实测 No such file），而那五个文件从 `1af68fc` 起就写着
`from fixtures.net import REFUSED_HTTP_URL`（`test_alerting_drill.py:15`、`test_bots_logs_filter.py:16`、
`test_wb_push_hardening.py:15`、`test_w3_push_scheduler.py:19`、`test_env_isolation.py:25`），
它们在 CI 里被正常收集（AGENTS.md 记的一千零二 passed 含这些文件）。所以「补 `__init__.py`」不是修复而是改变导入语义 | **不成立**（结论层面也不成立）。不新增 `__init__.py`，也不把一条能跑通的事实改写成「推断」 |

另：它中途报过一句「`SELF-TEST FAIL`（小写 `no_proxy` 变异体没让 NR-14 红）」，我在同一工作副本上
连续多次 `--self-test` 都是该项 OK；它自己随后也改口「按未复现处理」。因此该项**不作为缺陷**记账，
但它提示了一件事：反证通道必须自带基准闸门（见 8.1 末行），否则「OK/FAIL」的读起来一样可信。

**自我更正（第四轮期间发现，针对上表第二行里我自己给的证据）**：那条驳回理由写的是
`grep -n 'fixtures.net\|命名空间\|namespace\|__init__' README.md`「只命中 §1 表格与 §2 NR-9 的文件名」——
这个 grep 从它被写进 §8.2 的那一刻起就会**匹配它自己所在的这几行**（模式串就抄在正文里），
今天实测命中 7 行（:16、:58 是我原指的两处；:283、:284、:285、:286、:288 全是本行所在的 §8.2）。
所以「只命中两处」这句话在写入当时成立、现在已不可复现，属**会自毁的取证方式**。
驳回那条指控真正依赖的证据只剩一样：`python -c "…import fixtures.net…"` 打印出常量值、rc=0，
以及 `git log -- …/__init__.py` 为空。引用「grep 命中几处」时必须同时给出排除自匹配的方法
（`grep -v '命名空间\|__init__' ` 之类不可靠，正解是把模式串放进文件而非命令行、或只对新写内容跑）。

### 8.3 为什么这轮还留着一个「复审者说的不对」的记录

前两轮它推翻的每一项都成立，我据此改了判据；第三轮的两条不成立。**两种都要写下来**——
只登记「被推翻后修了什么」会把复审记录变成权威记录，而它只是一个（很有用的）信号源。
可复现性判据始终是本文件 §2/§4 的命令，不是任何一方的口头结论。

## 9. 独立复审记录（第四轮，两份并行报告）——先复现，再处置

第四轮派了两个互相不知情的独立复核子智能体，两份报告结论方向一致但措辞不同。纪律照旧：
**每一条都先在我自己的机器上造出可执行的反例，复现出来才算缺陷**；处置表里同时记
「复现不出来 / 我不接受」的项。复现脚本 `_workspace/round4_probe.py`（临时产物，不入库）
把十类变异/重构喂给 `H.evaluate()`，下表「修前 → 修后」两列即它的实测差值。

### 9.1 成立并已采纳（旁路类：判据本该红却绿）

| id | 复审发现 | 复现（修前 red） | 处置（修后 red） |
|---|---|---|---|
| P-1 | `no_proxy_pairings()` 用 `setdefault` 收集 ⇒ 同名**只记第一条**写入；「先契约值、后坏写」的双写全绿 | `[]`（用例 2） | `['NR-14']`：改为收集**全部**写入、逐条要求契约值（§2 NR-14 v3），并落为变异体 ⑬ |
| P-2 | 坏写藏在平台守卫里（`if os.name != "nt": setenv("NO_PROXY","evil")`）在本机**行为不可观测**，而 v2 判据按「配对」组织，嵌套分支里的写入取不到 | `[]`（用例 3） | `['NR-14']`：改用 `ast.walk` 深入嵌套 + 名字/值各自按槽位取；落为变异体 ⑭ |
| P-3 | NR-15 只要求「夹具体内存在一个遍历 `_PROXY_ENV_VARS` 的循环」⇒ 把真接线循环塞进 `if False:`、活路径改硬写同值元组，结构判据照绿 | `[]`（用例 10） | `['NR-16']`：新增**运行期哨兵**——往常量表追加 `AIDEANBOT_SENTINEL_PROXY_VAR`，夹具必须真的遍历常量才会删它；落为变异体 ⑮ |
| P-4 | `evaluate()` 只重放 NR-1/4/5/6/13/14/15 ⇒ NR-2（scope）、NR-3（广播先于夹具）、NR-7（不清 DSN）**没有任何通道能证明会红**，属 G-23 禁止的「永不可能失败」形态 | **第五轮复核更正过此格**（原写「用例 1 / 8 / 9 全部 `[]`」）：⑩ `scope="session"` → `[]`、⑪ 广播改名 → `[]`、⑫ 用**字面名** `delenv("AIDEANBOT_TEST_PG_DSN", …)` → `[]`，但⑫ 按变异体实际写法用**常量名** `delenv(_TEST_PG_ENV_VAR, …)` → `['NR-4-a(异常 NameError)','NR-5']`——即修前它并非「绿」而是**被别的判据误抓**（删掉未定义的别名后夹具体 exec 就 NameError）。读数取自 `git show b69123f` 副本的 `evaluate()`，可复跑（§10.1） | `['NR-2']` / `['NR-3']` / `['NR-7']`：`evaluate()` 扩到重放这 3 条 + 三个变异体 ⑩⑪⑫；NR-7 有了自己的判据后，⑫ 不再靠 NameError 碰运气 |
| P-5 | NR-9-a、NR-9-c、NR-10-a、NR-10-b 同样只读真实文件、无反证通道（与第三轮补 NR-8/11/12 的缺陷同形，我上轮只补了一半） | 未复现（性质同上，判定函数根本没有可注入样本的入口） | 抽出 `refused_url_shape` / `alias_only` / `smoke_guard_shape` / `guard_symbols_imported` 四个判定函数，新增九探（探针总数 9 → 18） |

### 9.2 成立并已采纳（脆性类：合法写法被判红）

这一类方向相反，是 P-1…P-5 之外我原本完全没设防的一面：**判据过严会让门禁变成噪声**，
而被人关掉的门禁等于没有门禁。复现（修前均为误红）：

| id | 合法重构 | 修前 red | 修后 red |
|---|---|---|---|
| B-1 | `setenv(name="NO_PROXY", value=NO_PROXY_ISOLATION_VALUE)` | `['NR-14']` | `[]` |
| B-2 | `delenv(_name, False)`（`raising` 改位置实参） | `['NR-15']` | `[]` |
| B-3 | `delenv(name=_name, raising=False)` | `['NR-15']` | `[]` |
| B-4 | `for _name in list(_PROXY_ENV_VARS):` | `['NR-15']` | `[]` |

处置：判定侧新增 `call_arg(call, index, param)`——位置与关键字实参通吃；迭代源接受
`Name` 或一层 `list/tuple/sorted` 包装；并**新增第三条反证通道** `EQUIV_REFACTORINGS`，
把这四条写法固化成「必须保持全绿」的回归样本（`self_test()` 末尾逐条打印实际红项）。
两条通道的方向因此互补：`MUTANTS` 证明「改坏会红」，`EQUIV_REFACTORINGS` 证明「换写法不假红」，
缺任何一条，另一条的结论都不完全可信。

### 9.3 成立但属文档/锚点层面

| 复审发现 | 复现 | 处置 |
|---|---|---|
| `test_env_isolation.py` ② 的失败文案引用 `webhook.py:52`，而该文件只有 51 行 ⇒ 悬空锚 | `wc -l` + 直接读文件：`retryable=True` 实际在 `:49`（超时支）与 `:51`（异常支） | 断言消息改为同时指出两行；同类风险顺带清掉：注释不再写单行号 |
| 该文件 docstring 声称「③ 的 skip 分支已在无代理宿主验证」——**本机从未运行过该用例**，属过度声明 | 无运行证据可支撑（H-1 未消） | 改为设计意图 + 显式写明「③ 的 skip 分支与 ①② 的真实通过尚未在本机验证（无 venv/httpx，登记为 H-1）」 |
| §2 结尾写「chat_sse 冒烟首行守卫已就位」易被读成「该用例跑过」 | AST 判定确实只证明文本层 | 结论行改为「按 AST 位置判定为『文本层就位』（该用例本身未执行，见 H-1）」 |
| `out_evidence_check.txt` 头部写「无 PYTHONIOENCODING」，但中文输出要可读就必须设它 ⇒ 存档与实跑条件不符 | 本机 cp936 控制台实测 | 重新生成时如实记录 `PYTHONIOENCODING=utf-8` |

### 9.4 复现不出来、不予采纳（连同证据一并留下，供第五轮驳回或翻案）

| 复审断言 | 我的复核 | 结论 |
|---|---|---|
| 「应把夹具改为 session 级以匹配卡面，函数级是偏离」 | 卡面偏离已在 §3.1 登记并给出「函数级严格更强」的理由，NR-2 把它钉成契约；第四轮还为此加了变异体 ⑩ | **不采纳**：这是已申报且有反证的设计决策，不是疏漏。改 session 级会让用例内 `setenv` 泄漏给后续用例 |
| 「NR-16 与 NR-15 重复，删掉一条」 | 见 §2 NR-16 与 §9.1 P-3：用例 10 只有 NR-16 能红，而 B-4（`list(常量)`）只有 NR-15 不红才行——两者互为盲区补位，且各有一条变异体 | **不采纳**：合并即回到 P-3 的盲区 |
| 「`test_env_isolation.py` 应加第 4 条用例覆盖 HTTPS」 | 夹具清的是 `_PROXY_ENV_VARS` 全部 6 键，HTTPS 与 HTTP 走同一段循环；加一条只是把同一判定再跑一遍 | **不采纳**：不增加探测力，且第 4 条会牵动 NR-12 的用例数契约（改了要同步判据，无收益） |

### 9.5 本轮净变化（可核对）

- 断言 22 → **23**（新增 NR-16）；`MUTANTS` 九 → **十五**；`TEXT_PROBES` 九 → **十八**；
  新增 `EQUIV_REFACTORINGS` **四**条（第三条反证通道）。
- `evaluate()` 覆盖的 conftest 判据**由 9 条扩到 13 条**（第五轮复核更正：原写「8 条扩到 11 条」
  两头都不对——补 NR-2/NR-3/NR-7 是三条，但同轮还让 NR-16 进了 `evaluate()`，
  且修前基线本就是 9 条而非 8 条）。读数不是回忆：对 `git show b69123f` 与 `git show 1470b77`
  两份副本的 `evaluate()` 函数体做 AST 扫描、收集其中出现过的 `NR-*` 字面量，
  得 9 → 13；本第五轮处置再加 NR-17 ⇒ **14** 条。
- 三个测试文件侧修复：悬空行号、docstring 过度声明、结论行措辞。
- 未变化：夹具源码本身（`conftest.py:91-97` 一字未动——本轮改的全是判据与证据层），
  `REFUSED_HTTP_URL`、`_PROXY_ENV_VARS`、`NO_PROXY_ISOLATION_VALUE` 三个契约常量，以及 §4 的 H-1…H-6。

## 10. 独立复审记录（第五轮，针对 `1470b77`）——先复现，再处置

第五轮复核者的总评是「四条修复与账目是真的、可复现；但 NR-14 仍被任何非字符串字面量的名字写法
和 `os.environ.setdefault` 绕过，NR-15/NR-16 被 `if os.name == "nt":` 包住清理循环绕过——
正是本轮声称关掉的那一类平台盲的两面；另有十条合法等价写法假红，以及两处记账不实」。

纪律照旧：**每一发都先在我自己机器上喂给 `evaluate()` 跑出读数，复现出来才算缺陷**，
处置表里的「修前 / 修后」两列全部是实测差值，不是转述。复现用的两份修前副本由
`git show 1470b77:…/prove_net_isolation.py`（旁路与脆性的修前线）与
`git show b69123f:…`（§9.1 P-4 的修前线）取，逐条读数可同样复跑；
修后线固化在 harness 里：单命令 `--self-test` 即复跑 二十变异 + 十八探针 + 十三等价。

### 10.1 成立并已采纳（旁路类：判据本该红却绿）

| id | 攻击体 | 修前 `evaluate()` red | 修后 red | 处置 |
|---|---|---|---|---|
| D1 | `os.environ.setdefault("NO_PROXY", "evil.example")` 追加在契约写入之后 | `[]` | `['NR-14']` | NR-14 v4 把写入手段扩到 `setenv`/`putenv`/`setdefault`/`update`/下标赋值五类；落为变异体 ⑯。**这条尤其阴**：沙箱为了让 NR-6 能看 `undo` 而预置了 `NO_PROXY`，所以 `setdefault` 在行为面是**空操作**——只有结构面能红 |
| D2 | `if os.name != "nt": monkeypatch.setenv(f"NO_PROXY", "evil.example")` | `[]` | `['NR-14', 'NR-17']` | 名字解析扩到 f-string / `+` 拼接 / 循环变量 / `**` 展开，且**名不可判时照样要求契约值**（举证责任压回写入方，见 §10.3）；平台读数由 NR-17 直接禁；落为变异体 ⑰ |
| D3 | `for _n in ("NO_PROXY",): monkeypatch.setenv(_n, "evil.example")` | `[]` | `['NR-14']` | 同 D2 的名字通道（`_binding_map` 把 `for` 目标、字面量赋值、海象绑定都算上）；落为变异体 ⑱ |
| D4 | `monkeypatch.setenv(**{"name": "NO_PROXY", "value": "evil.example"})` | `[]` | `['NR-14']` | `call_arg` 补 `kw.arg is None` 的字典展开分支；落为变异体 ⑲。这一发与等价通道里的 `delenv(**{…})` 是同一语法的两面：**坏写必须红、合法写法必须绿** |
| D5 | 清理循环整体包进 `if os.name == "nt":` | `[]` | `['NR-17']` | **新增 NR-17**（下节详述）；落为变异体 ⑳ |

D5 值得单独记：它是第四轮 ⑭ 的**镜像**——⑭ 是「守卫包住坏写」，D5 是「守卫包住隔离本身」。
win32 上守卫为真，于是三层判据（行为面 NR-4-a、结构面 NR-15、运行期哨兵 NR-16）**全部照绿**，
只有 Linux CI 上一个代理变量都不清。前两轮我给 NR-14 加过平台盲区（§9.1 P-2），
却没给「清理侧」加同一条——**同一形状的盲区必须在两侧同时堵**，这已经是我第二次在这上面被抓住了。

### 10.2 NR-17（本轮新增判据）：隔离夹具内不得出现平台身份读数

- 判据：`_isolate_proxy_env` 函数体内不得有下述读数——根为 `os`/`sys`/`platform`/`sysconfig` 且属性属于
  `name`/`platform`/`system`/`uname`/`getwindowsversion`/`machine` 的属性访问（即 `os.name`、
  `sys.platform`、`platform.system()`、`sysconfig.platform` 这一类），**以及**任何与平台字面量
  （`nt`/`posix`/`java`/`cli`/`win32`/`cygwin`/`aix`/`darwin`/`linux`/`freebsd`/`openbsd`/`netbsd`/`sunos`）
  做的比较。
- 为什么必须是结构判据而不是行为判据：本机的运行期哨兵 NR-16 跑在**本机平台**上，
  平台分支在 win32 上永远「表现正确」——**行为不可观测的缺陷只能由契约面承接**（与 §3.6 的
  键折叠同一处置思路，那条也是这么落到 NR-14 的）。
- 为什么它是**契约变更**而非纯技术判断：「夹具与平台无关」是本项目对隔离的设计要求，
  真要引入平台分支必须先改这条契约并交人工裁决，而不是在夹具里悄悄加 `if os.name`。
  因此它由变异体 ⑳ 钉住，而不是留在注释里。
- 实测（本机）：`PASS NR-17 隔离夹具内没有任何平台身份读数… :: 平台读数=无`；
  基准 conftest 全绿，D2/D5 两发各自让 NR-17 变红。

### 10.3 成立并已采纳（脆性类：合法等价写法被判红）

同一轮里判据在**另一头**假红了九次——修前逐发实测（对 `1470b77` 版 `evaluate()`），修后全部归零：

| 等价写法 | 修前 red | 修后 red |
|---|---|---|
| `delenv(_name, raising=0)` | `['NR-15']` | `[]` |
| `for _name in [x for x in _PROXY_ENV_VARS]:`（列表推导） | `['NR-15']` | `[]` |
| `for _name in tuple(sorted(_PROXY_ENV_VARS)):`（两层包装） | `['NR-15']` | `[]` |
| `for _name in reversed(_PROXY_ENV_VARS):` | `['NR-15']` | `[]` |
| `for _name in map(str, _PROXY_ENV_VARS):` | `['NR-15']` | `[]` |
| `delenv(**{"name": _name, "raising": False})` | `['NR-15']` | `[]` |
| `if _name in os.environ: delenv(_name)`（省略 `raising`） | `['NR-15']` | `[]` |
| `if (_vars := _PROXY_ENV_VARS): for _name in _vars:` | `['NR-15']` | `[]` |
| `setenv("NO_PROXY", str(NO_PROXY_ISOLATION_VALUE))` | `['NR-14']` | `[]` |

处置原则只有一句：**放宽的只能是写法，语义一条没松**——`delenv_loop_wired()` 仍然要求
「遍历那个常量 + 用循环变量名去删」，运行期一致性另由 NR-16 兜；NR-14 仍然要求
「两种拼写都被证明写过 + 每一次写入都取契约值」。九条写法全部固化为 `EQUIV_REFACTORINGS`
回归样本（通道由四条扩到十三条），所以「这次改绿了」不等于「判据不再脆」——下一个人改坏判据会当场红。
上表最后一条的修法是：值侧允许一层 `str()` 包装与 `strip()` 族无参方法调用；
倒数第二条（成员守卫下省略 `raising`）由 `_guarded_by_membership()` 精确识别
「守卫用的名字就是被删的那个名字」，而不是「体内只要出现过 `in os.environ` 就放行」。

### 10.4 成立但属记账层面（三处，全部可核）

| 复审断言 | 我的复现 | 处置 |
|---|---|---|
| §2 开头写「模块级 import sqlalchemy/dotenv/pytest，本机皆无」——对 pytest 与 dotenv **不成立**，且与同目录 `out_evidence_check.txt` 里的依赖普查自相矛盾 | 逐个 `importlib.import_module` 实测：**有** pytest（9.1.1）/ dotenv / anyio，**无** sqlalchemy / httpx / structlog / pytest_asyncio / coverage / psycopg；`shutil.which` 实测 PATH 里 uv/ruff/make/mypy/gh **全都不存在** | 该句改为按实测列出「有/无」两份清单（六个缺失包 + 五个缺失工具），并把读数指向 `out_evidence_check.txt` 的依赖实测行——**以命令输出为准，不以我的回忆为准**；本轮重新整份生成的该文件把这条普查放在第 4 行 |
| §9.5 写「`evaluate()` 判据由 8 条扩到 11 条」 | 对两份历史副本的 `evaluate()` 函数体做 AST 扫描收集 `NR-*` 字面量：`b69123f` = 9 条、`1470b77` = 13 条、本轮 = 14 条（补 NR-17）。原表述两头都错，且漏了 NR-16 也是同轮进 `evaluate()` 的 | 已按实测改写 §9.5，并写明扫描方法，让下一个复核者能复跑而不是信我 |
| §9.1 P-4「用例 1 / 8 / 9 全部 `[]`」对第三发不成立 | 用 `b69123f` 版 `evaluate()` 跑四个变体：⑩ `[]`、⑪ `[]`、⑫ 字面名写法 `[]`、⑫ **变异体实际写法**（`delenv(_TEST_PG_ENV_VAR, …)`）= `['NR-4-a(异常 NameError)', 'NR-5']` | 已把该格换成上面这段带四个读数的表述：修前那一发不是「绿」，而是**被别的判据误抓**——NameError 恰好掩盖了「没有 NR-7 这条判据」的事实。这类「碰巧红」必须点名，否则我会以为自己早就有覆盖 |

### 10.5 本轮净变化（可核对）

- 断言 **23 → 24**（新增 NR-17）；`MUTANTS` **十五 → 二十**；`TEXT_PROBES` **十八（未变）**；
  `EQUIV_REFACTORINGS` **四 → 十三**；`evaluate()` 可输出的判据标签 **13 → 14**。
  这些数字全部由脚本按 `len(...)` 动态打印，与本文文字不一致时以输出为准。
- **一处反证集中红（不是新增判据的副作用，而是 v4 放宽写入通道的直接结果）**：变异体 ⑤
  （夹具直写 `os.environ`）由 `['NR-14', 'NR-6']` 变成 `['NR-6']`——因为 v4 现在认得
  `os.environ[…] =` 这条写入通道，该写入「被看见且值合法」，NR-14 不该再红。
  NR-6 是行为面判据（夹具必须经 `monkeypatch` 而非直写环境），反证职责仍完整；
  已在 §2 ⑤ 就地更正，不留旧说法。
- 判据侧新增/改写的函数：`env_writes()`（五类写入）、`_names()` + `_binding_map()`
  （名字静态解析，不可判 ⇒ 举证责任倒置）、`_is_contract_value()`（`str()`/`strip` 族/单占位 f-string）、
  `platform_reads()`（NR-17）、`delenv_loop_wired()`（写法放宽、语义不松）、
  `_guarded_by_membership()`、`call_arg()`（`**` 展开）。
- **未变化**：`apps/api/tests/conftest.py`（`git diff 1470b77 -- apps/api/tests/conftest.py` 为空，
  夹具源码 `:91-97` 一字未动）、`tests/fixtures/net.py`（同样为空）、
  三个契约常量、§4 的 H-1…H-6。本轮改的全是判据与证据层。

### 10.6 残留欠账（明账，不粉饰）

| 项 | 实测 | 为什么本轮不修 |
|---|---|---|
| 「把遍历逻辑抽到模块级 helper、夹具只调用它」这种**合法**重构会假红 | 修后 `evaluate()` 给 `['NR-15', 'NR-4-a(异常 NameError)', 'NR-5', 'NR-16(异常 NameError)']` | 两个原因叠加：① harness 只 exec 夹具体，模块级函数不在命名空间里 ⇒ 得到的是 NameError 转成的红，而不是一次干净判定；② NR-15 的契约就是「**夹具自己**在体内遍历常量」——要接住 helper 化就得让判据沿调用图找被调函数，而「那个函数是否活、是否无条件执行」正是静态面看不见的一面（⑮ 靠运行期哨兵 NR-16 才堵得住）。本轮选择把契约写在明处：确需 helper 化时先改判据并交人工裁决，而不是让判据悄悄变宽 |
| NR-14 的举证责任倒置有代价 | 夹具里任何**名字解析不了**的环境写入都必须取契约值，否则红；反之，字面的非代理名（实测 `setenv("AIDEANBOT_X", "1")`）判据不动 | 这是 D2/D3 两条旁路的对价：宁可让「解析不了」落到红的一侧，也不能让它落到绿的一侧。后果是夹具若将来要设置一个名字来自模块常量的环境变量，需要显式改判据——可接受，因为夹具的职责就是隔离，往里加别的写入本就该被追问 |
| NR-17 禁的是**读数**，不是「所有平台差异」 | 变异体 ⑳ 钉住；改这条属契约变更 | 若某天确实需要「Windows 上少清一个变量」，必须先经人工裁决改契约，不能在夹具里加 `if os.name`。这条边界写在这里，是为了让下一个人不会把它当成可绕的实现细节 |
| harness 自身的静态门禁覆盖不到 `docs/**` | `scripts/g24_static_check.py` 的 `DEFAULT_FILES` 是硬编码清单，`Makefile` 调它时不带参数 | 本轮按现有清单跑（E501 计数与基线一致、无新增违规）。真正的终判是 CI 的 `ruff check app tests`（H-1 那类交接头目之外的 J-2），而 `docs/**` 下的验证脚本按当前清单不在 lint 范围——**这一句就是这条欠账的账目**，不假装它已闭合 |

