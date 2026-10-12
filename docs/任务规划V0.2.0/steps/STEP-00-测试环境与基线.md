---
id: STEP-00
title: 测试环境与基线
priority: P0（前置）
depends: —
parallel_with: STEP-10（S10.1）
estimate: 0.5 人日
---

# STEP-00 测试环境与基线

## 目标
让任何执行者在任意机器上用一条命令得到与本规划一致的测试基线（1008 passed 量级），并消除两处会产生假结论的环境脆弱点。

## 依据
- D-12：`tests/conftest.py:36` 默认 DSN 指向 `localhost:5433/bothot`（生产形态库，含口令字面量），未设变量时只告警（`:65-71`）。
- 01 §1.2：不连库时 417 条静默 skip；连库后 1 failed 来自 9999 端口假设。

## 允许修改
`scripts/test-env.sh`（新）、`apps/api/tests/conftest.py`、`apps/api/tests/test_w3_push_scheduler.py`、`apps/api/tests/fixtures/**`（新）、`docs/06_validation/evidence/EVD-V2-00/**`（新）
## 禁止修改
`apps/api/app/**`、`.github/**`、`docker/**`，以及上面未列出的一切。

## 原子任务

| 编号 | 类型 | 动作 | 验收命令（必须可复制） |
|---|---|---|---|
| S0.1.1 | 🛠 | `scripts/test-env.sh up|down|env`：起 PG16@5547、Redis@6390（docker 或本地二进制皆可），`env` 子命令打印 `export AIDEANBOT_TEST_PG_DSN=… DATABASE_URL=…`；端口命中 5433/5435/6379/6380 时 `exit 2` | `bash scripts/test-env.sh up && eval "$(bash scripts/test-env.sh env)" && psql "${AIDEANBOT_TEST_PG_DSN/+psycopg/}" -c 'select 1'` |
| S0.1.2 | 🔴🛠 | conftest：`_PG_URL_SOURCE=="default"` 时把 `PG_URL` 置空，`db_session` 等夹具 `pytest.skip("AIDEANBOT_TEST_PG_DSN 未设置")`；删除 `_DEFAULT_PG_URL` 常量 | 反证：`unset AIDEANBOT_TEST_PG_DSN; grep -c "_DEFAULT_PG_URL" apps/api/tests/conftest.py` 改前 ≥1、改后 0；`pytest tests/test_scheduler.py -q -rs` 改后 skip 原因含 "未设置" |
| S0.1.3 | ✅ | 连库跑全量并入档 | `cd apps/api && alembic upgrade head && pytest tests -q -rs --cov=app --junitxml=../../docs/06_validation/evidence/EVD-V2-00/junit.xml` |
| S0.2.1 | 🔴🛠 | 用例改为注入 `httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused")))` 的 webhook provider，或给夹具 channel 的 webhook_url 用保留地址 `http://127.0.0.1:1`（端口 1 需 root 才能监听） | 反证：`python -m http.server 9999 & pytest tests/test_w3_push_scheduler.py::test_event_delivery_failure_no_reclaim -q` 改前 FAIL、改后 PASS |
| S0.3.1 | 🛠 | `tests/fixtures/wechat_urls.py`：`LONG_A/LONG_B`（同 biz 不同 mid）、`LONG_A_TRACKING`（同篇加 scene/chksm/sn 变体）、`SHORT_1`、`MALFORMED_LONG`（缺 mid）、`OFFSITE`（https://www.ruanyifeng.com/…） | `python -c "import tests.fixtures.wechat_urls as w; print(len([k for k in dir(w) if k.isupper()]))"` ≥ 6 |
| S0.3.2 | 🛠 | `tests/fixtures/provider_payloads/{redfox,dajiala,justoneapi,tikhub,wellbyte}.json`、`rss2.xml`、`atom.xml`；每个文件头注明"形状来源：<client 文件:行 / registry verified_scope / 活体用例号>" | `ls apps/api/tests/fixtures/provider_payloads | wc -l` = 7 |

## 完成定义
S0.1.3 产出 junit 且 failed=0（S0.2.1 修复后）；skip 仅限 LangBot/Redis 类并在 EVD 中列出。

## 回滚
全部为测试侧文件，`git revert` 即可；无数据影响。

## 风险
- 删除默认 DSN 后，本地开发者若习惯不设变量直接跑，会看到大量 skip——这正是期望行为（宁 skip 不写生产）；在 EVD-V2-00 与 `docs/04_engineering/conventions.md` 补一句使用说明（后者属 STEP-11）。

---

## 执行记录（2026-10-12，Agent 侧完成度＝部分）

| 子任务 | 状态 | 实际落点与偏差 |
|---|---|---|
| S0.1.1 | 🟡 部分 | 脚本已写并通过 6 条**不启服务**的验收（`bash -n`、`env`、端口护栏 rc=2、非法子命令 rc=64）。`up/down` 需 docker，与「不实际启动服务」约束冲突 ⇒ **未执行**，卡片验收命令（`up && … && psql -c 'select 1'`）本机未满足。 |
| S0.1.2 | ✅ 达成（口径已改） | 卡片原写「把 `PG_URL` 置空 + 删常量」不足以闭合 D-12：`tests/` 另有 **9 处**模块级 `os.environ.get(VAR, 生产字面量)`（卡片依据只提 conftest）与 **1 处** `from conftest import PG_URL`（共 10 个消费者）。现实现为两级解析 + 未配置时广播**保留地址 `127.0.0.1:1`**（端口 1 非 root 不可监听 ⇒ 必拒连），广播用**无条件赋值**（`setdefault` 在「键存在但空串」时是空操作，会把空串漏给下游）。证明：`EVD-V2-00/prove_dsn_policy.py` 20/20 + `--self-test` 变异反证。 |
| S0.1.3 | ⏳ 交 CI | 本机无 venv 且禁启服务 ⇒ 连库 pytest 只能由 CI postgres job 判；结论回填至 EVD §5/§8。 |
| S0.2.1 | ✅ | 采卡片许可的第二方案（webhook_url → `http://127.0.0.1:1/…`），两处夹具替换。**卡片反证无效**：`python -m http.server 9999` 返回 501，而 `webhook.py:46` 判 `>=500` 为可重试 ⇒ 改前也 PASS，构造不出「改前 FAIL」；能致假绿的是 **2xx** 监听者。见 EVD §6.2。 |
| S0.3.1 | ✅ | 10 个常量（验收 ≥6）。 |
| S0.3.2 | ✅（验收命令需修订） | 目录为 **8 个文件**（5 JSON + 2 XML + `README.md`），卡片写的 `wc -l` = 7 已不成立 ⇒ 修订为 = 8。JSON 样本刻意**不含**注记键（形状忠实），prose 迁至同目录 `README.md`；`prove_provider_shapes.py` 断言「主路径读取键缺失即 FAIL」（实测 redfox 3/3、dajiala 5/5、justoneapi 10/10、tikhub 8/13、wellbyte 10/10）。 |

### 本卡暴露、但不属本卡修复范围的缺陷（已移交，详见 EVD-V2-00 §8）
1. **`_ID_KEYS` 交集空**：Dajiala/JustOneAPI/TikHub/Wellbyte 归一化行键与 `manifest.py:51` 无交集
   ⇒ 清单**永不入库**且只计 `skipped`、不报错不告警。成本量级为**每号每轮 1–2 次调用**
   （`manifest.py:217` 的 `len(rows) < size` 首页即止 + 四家 `page>1` 返回空），
   不是早期记录的「最多 20 次」——该错误结论已在 EVD §6.3 更正。属 STEP-03。
2. `test_alerting_drill.py:100`、`test_bots_logs_filter.py:27`、`test_wb_push_hardening.py:79`
   仍是 `localhost:9999` 同形假设 ⇒ 建议新增 **S0.2.3**。
3. `test_chat_sse.py:1208`/`:1272` 建引擎不在 try 内 ⇒ 特定组合下**报错而非 skip**。
4. 三个证明脚本未进 CI ⇒ 夹具头 60+ 条 `file:line` 引用无门禁，会静默腐坏。
5. 陈旧注释：`test_r48_admin_jobs.py:285`、`test_scheduler.py:663` 仍称「见 conftest 警告」；
   `ci.yml:28-32` 仍描述「conftest 默认 DSN 指 5433」的旧行为（改 `.github/**` 需另行授权）。

### 已推翻的本卡早期结论（保留痕迹，勿复用）
- 「Windows 缺 tzdata ⇒ 项目依赖缺口」：**错**。`uv.lock:865-868` 中 psycopg 3.3.5 依赖
  `tzdata (marker sys_platform=='win32')` ⇒ 按锁安装即得；本机崩是因本会话无 venv。

---

## 复核更正（2026-10-12，由 STEP-00R 回写；本节只追加，上文原样保留）

### S0.2.1 的根因判断被推翻：环境代理，而非端口占用

上方执行记录把 S0.2.1 判为 ✅，理由是把 URL 换成 `127.0.0.1:1` 后「端口 1 非 root 无法监听
⇒ httpx 必抛 ConnectError ⇒ `delivered=False`」。**该推理只在无代理的环境里成立**；
改后同一条用例仍然红。真实链路（证据
`docs/任务规划V0.3.0/evidence/proxy_rootcause_4afaedd.txt`，@4afaedd，隔离 PG16@5547）：

| 段 | 观测 | 由此得出 |
|---|---|---|
| §A | 进程环境存在 `http`/`https` 代理键（只列键名） | 出站流量默认被宿主代理接管 |
| §B | 保留代理跑 `test_event_delivery_failure_no_reclaim` ⇒ `assert 0 == 1`，左侧是 `PushTask.retry_count` | 失败没推进重试簿记 |
| §C | 有代理时直调 provider 打 `127.0.0.1:1` ⇒ `delivered=False retryable=False reason="webhook 返回 HTTP 404"` | **拿到了 HTTP 状态码** |
| §D | 清除代理变量 ⇒ `reason="webhook 推送异常: All connection attempts failed"`、`retryable=True`，11 passed | 拒连才是用例设计的那个分支 |

判据：**一次被拒绝的连接不可能产生 HTTP 状态码**——看见 404 本身就是「请求根本没到达
`127.0.0.1:1`」的证明，404 来自中间代理自己。机制：`app/providers/push/webhook.py:33` 的
`httpx.AsyncClient` 未显式关闭 `trust_env`（缺省 True，读 `HTTP_PROXY`/`HTTPS_PROXY`），
`webhook.py:46` 又以 `retryable=resp.status_code >= 500` 把 4xx 判为不可重试
⇒ `retry_count` 永不推进 ⇒ 用例红。

与本节开头那条「已推翻结论」同类：**测试的成败不能取决于本机代理配置**。

### 状态改判与闭合位置

- S0.2.1：✅ → 🟡（根因判断错误、失败未消除）→ **由 STEP-00R 闭合**。落点：
  `apps/api/tests/conftest.py:92` 新增 autouse `_isolate_proxy_env`（清 6 个代理变量 +
  置 `NO_PROXY`/`no_proxy`，:87–:88 定义），拒连地址收敛为单一口径
  `apps/api/tests/fixtures/net.py:17` `REFUSED_HTTP_URL`，并新增
  `apps/api/tests/test_env_isolation.py` 把「代理被清干净」「失败以 ConnectError 形态出现
  而非 HTTP 状态码」两条断言写成会因回归而红的门。
- 本卡「已移交缺陷」项 2（三处 `localhost:9999` 同形假设）：已改为 `REFUSED_HTTP_URL`
  （现行号 `test_alerting_drill.py:101`、`test_bots_logs_filter.py:28`、
  `test_wb_push_hardening.py:80`——比上方记录里的 :100/:27/:79 各下移 1，因为新增了 import 行）。
- 本卡「已移交缺陷」项 3（`test_chat_sse.py` 建引擎不在 try 内 ⇒ 特定组合下报错而非 skip）：
  已在 `test_ask_real_full_chain_smoke`（:1180）函数首句加守卫
  `if _PG_URL_SOURCE == "unset": pytest.skip(SKIP_UNSET_REASON)`（:1191–:1192，
  两处 `create_async_engine` 同属本函数，一处即覆盖）。
- 本卡「已移交缺陷」项 4（证明脚本无门禁）：已加 `Makefile:173` `evidence-check` 目标
  （DSN 策略 + Provider 形状 + G-24 静态 + 网络隔离，含变异反证）；CI job 仍待授权。
- 本卡「已移交缺陷」项 5（陈旧注释）：`test_r48_admin_jobs.py`、`test_scheduler.py` 已改为
  两级解析口径描述；`ci.yml:28-32` 仍描述旧行为——改 `.github/**` 需 D-11 授权，未动。

### 本步反自证声明

STEP-00R 未执行 pytest（本会话无依赖，且受「不实际启动服务」约束）。静态可证部分由
`docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py` 承担（20 断言 + 4 个变异体
各自让对应断言变红）；运行时部分（双环境全量 `failed=0`、两份 junit 逐条一致）
列为 EVD-V2-00R §4 移交项 H-1…H-6，附可复制命令，不得当作已验证。
生产侧 `trust_env` 按 N-02 保持不变（浏览器/运维出站仍需代理）。
