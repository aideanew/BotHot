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
| S0R.1.2 代理隔离夹具（根因修复本体） | ✅ 代码落地 + 真实执行证明 | §2 全部 20 条 PASS |
| S0R.1.1 `test_env_isolation.py` | 🟡 用例已写，**运行交 venv**（`import httpx`） | §4 交接头目 H-1 |
| S0R.2.1 `tests/fixtures/net.py` + 4 处收敛 | ✅ 落地 + 机器证明 NR-8/NR-9 | `out_evidence_check.txt` |
| S0R.2.2 chat_sse 未配置守卫 | ✅ 落地（1 处而非 2 处，理由见 §3.2） | NR-10-a/NR-10-b |
| S0R.2.3 陈旧注释清零 | ✅ | NR-11 |
| S0R.4.1 `make evidence-check` | ✅ 目标已写；**本机无 make**，逐条 recipe 等价实跑 7/7 rc=0 | `out_evidence_check.txt` |
| S0R.4.2（本卡新增）harness 编码自适应 | ✅ 修 `prove_dsn_policy.py` 在 GBK 控制台崩溃 | §3.4 |
| S0R.5.1 STEP-00 卡回写更正 | ✅ 追加段（不改历史段落） | 见 V0.2.0 卡末尾 |
| S0R.1.3 / S0R.3.1 / S0R.3.2 | ⏳ 需隔离 PG + venv，交人工 | §4 |
| S0R.3.3 `ci.yml` 注释更正 | ⛔ 需 D-11 人拍板，Agent 不得代决 | §4 |

## 2. 代理隔离的机器证明（`prove_net_isolation.py`）

不能 `import conftest`（模块级 import sqlalchemy/dotenv/pytest，本机皆无），故沿用
EVD-V2-00 已确立的机制：AST 剔除三方 import 后 exec 前缀取真实常量，再**剥掉装饰器
exec `_isolate_proxy_env` 的当前函数体**，用按 `pytest.MonkeyPatch` 语义实现的替身
（`setenv`/`delenv(raising=)`/`undo` 全部作用在真实 `os.environ`，前后由 `sandbox`
快照恢复）驱动它。被执行的是文件里的代码，不是抄本。

```
合计 PASS=20 FAIL=0
SELF-TEST PASS：4 个变异体各自让对应断言变红
```

断言分面（完整输出见 `out_evidence_check.txt`）：
- NR-1/NR-2 `@pytest.fixture(autouse=True)` 且函数级 scope（缺省）；
- NR-3 夹具定义在 DSN 广播语句之后（广播 :75、夹具 :92）⇒ 不改动 S0.1.2 语义；
- NR-4 预置 6 个代理变量 + 污染 `NO_PROXY` 后调用夹具：6 个全清、`NO_PROXY`/`no_proxy`
  均等于契约值 `127.0.0.1,localhost,::1`；
- NR-5 干净环境（无代理变量）调用不抛 ⇒ `delenv(..., raising=False)` 生效；
- NR-6 `undo()` 后宿主原貌恢复 ⇒ 夹具是 monkeypatch 语义，不是永久改环境；
- NR-7 清理动作不波及 `AIDEANBOT_TEST_PG_DSN`（广播值仍在）；
- NR-8 `apps/api/tests` 全树 `localhost:9999` 命中 0；
- NR-9 地址常量单点：`fixtures/net.py` 端口为 1、4 个消费方均 `from fixtures.net import`、
  test_w3 旧常量退化为别名；
- NR-10 chat_sse 冒烟的**首条可执行语句**即 `if _PG_URL_SOURCE == "unset": pytest.skip(...)`，
  且所需两个符号已从 conftest 导入；
- NR-11 「见 conftest 警告」陈旧注释命中 0；
- NR-12 `test_env_isolation.py` 有 3 条用例、每条 ≥1 assert、宿主代理快照在首个用例之前；
- NR-13 conftest 侧常量的契约下限（6 个键逐字、值含回环）。

变异反证（`--self-test`）：去掉 `autouse` → NR-1 红；删 `delenv` 循环 → NR-4-a 红；
`raising=False`→`True` → NR-5 红；把回环地址从常量里删掉 → NR-4-b 与 NR-13-b 同时红。
第 4 个变异体之所以能红，是因为期望值 `EXPECTED_NO_PROXY` 在 harness 里**写死为契约字面量**
而不从 conftest 读——否则变异体会连同期望一起改，断言永不可能失败（G-23）。

## 3. 与 V0.3.0 规划文本的三处偏离（已核代码后决定，非疏漏）

> 本节为详版；同一批偏离已在任务书内登记为 `steps/STEP-00R-测试基线收口.md` 执行记录 D-1…D-5
> （D-1 = §3.4 的越路径项、D-5 = 用例由 2 条增至 3 条）。两处口径一致，改一处必须同步另一处。

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
而同目录的 `prove_provider_shapes.py:32`、`g24_static_check.py:20` 早已各带一行
`sys.stdout.reconfigure(encoding="utf-8")`，只有 `prove_dsn_policy.py` 漏了。
实测对比：不带 `PYTHONIOENCODING` 时崩溃、带则 `ALL PASS (20 断言)`；补上同款两行后
默认控制台 rc=0。这意味着「任意机器一条命令复现基线」此前对 win32 开发机**不成立**，
而规划包 F-19 把它记为「本机复跑全部成立」。已修（本卡 S0R.4.2）。

### 3.5 证据输出的两处文案修正（对应任务书 D-6）
`check(label, ok, detail)` 无论通过与否都打印 detail，而 `prove_dsn_policy.py` 里
S0.1.2-b / S0.1.2-r 的 detail 被写成「失败描述句」——断言**通过**时输出仍显示
「conftest 仍含口令字面量」「广播值为空串/None」。复核者会把它读成缺陷，违反
「EVD 可让一周后的人复现」的 Done 口径。现改为观测值：

- S0.1.2-b → `字面量命中 0 处（期望 0）`
- S0.1.2-r → 三个入口的实际广播值（`｜` 分隔）

**断言表达式与判据一字未动**，本文件 §2 的 20/20 与 self-test 结论不受影响。

## 4. 交人工/有依赖环境的项目（附可复制命令）

| # | 项 | 为什么本机不能做 | 命令 |
|---|---|---|---|
| H-1 | S0R.1.1 用例实跑（改前 2 failed / 改后 3 passed） | 用例 import httpx（`WebhookPushProvider`），本机无依赖 | `cd apps/api && HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 uv run pytest tests/test_env_isolation.py -q` |
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
