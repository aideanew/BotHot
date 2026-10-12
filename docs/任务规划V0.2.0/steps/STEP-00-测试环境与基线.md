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
