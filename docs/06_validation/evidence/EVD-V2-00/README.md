# EVD-V2-00 — STEP-00 测试环境与基线：证据链

对应卡片：[docs/任务规划V0.2.0/steps/STEP-00-测试环境与基线.md](../../任务规划V0.2.0/steps/STEP-00-测试环境与基线.md)
判定方式：**本机静态/AST 证明** + **CI 机器判定**（S0.1.3 只能由 CI 承担，理由见 §2）。
本文所有 `file:line` 均对 **2026-10-12 的工作树** 有效，复现命令见 §7。

---

## 1. 本卡做了什么（逐项对账）

| 子任务 | 落点 | 状态 | 判定证据 |
|---|---|---|---|
| S0.1.1 | `scripts/test-env.sh`（新） | 🟡 写完、`up/down` **未实跑** | `bash -n` rc=0；`env`/端口护栏实跑通过（§5.3） |
| S0.1.2 | `apps/api/tests/conftest.py` | ✅ | `out_prove_dsn_policy.txt`：20/20 ALL PASS（含 9 个下游回退点 + 1 处直接消费者清单）；`--self-test` 反证见 §5.1 |
| S0.1.3 | 连库全量 pytest | ⏳ 交 CI | 本机无依赖且禁启服务（§2）；CI 有 postgres service 且显式设 DSN |
| S0.2.1 | `apps/api/tests/test_w3_push_scheduler.py` | ✅ 改法一（卡片许可的第二方案） | `_REFUSED_WEBHOOK_URL` 两处替换；G-24 无违规；同形风险面见 §6.2 |
| S0.3.1 | `apps/api/tests/fixtures/wechat_urls.py` | ✅ 10 个常量（验收 ≥6） | `python -c "import tests.fixtures.wechat_urls as w; ..."` → `constants= 10` rc=0 |
| S0.3.2 | `apps/api/tests/fixtures/provider_payloads/`（5 JSON + 2 XML + 1 README） | ✅ | `out_prove_provider_shapes.txt`：PASS=32 / FAIL=0；主路径读取键缺失即 FAIL；样本顶层无注记键 |

**本卡整体判「部分完成」**（独立复审结论，非自我淡化）：S0.1.1 的 `up/down` 与 S0.1.3 的
junit（failed=0）都需要真起 PG，属卡片完成定义的硬条件；已把可本机证明的部分全部证完，
其余交 CI 与人工，见 §8。

卡片 S0.3.2 只要求「文件存在 + 头注形状来源」。本 EVD 把验收**升级为机器可验**（形状必须与
现行代码读取路径一致），因为样本是给 S4/S9 当契约锚用的——形状错了会「拿错的形状互相印证」。

---

## 2. 环境事实（决定了证明形态，不是借口）

本机 `D:\Code\AideanBotHot` **没有 venv**，因此：

```
$ ls apps/api/.venv/Scripts/python.exe        → No such file or directory
$ python -c "import httpx"                    → ModuleNotFoundError
$ python -c "import feedparser"               → ModuleNotFoundError
$ python -c "from zoneinfo import ZoneInfo; ZoneInfo('Asia/Shanghai')" → ZoneInfoNotFoundError
```

叠加用户约束「本项目无需安装开发环境和依赖」+「不实际启动服务」，可得：

1. 本机**不能**跑 `pytest`（连 collect 都要 httpx/structlog/sqlalchemy）→ S0.1.3 只能由 CI 判；
2. 本机**不能**起 PG/Redis（`test-env.sh up` 未执行，故其 `up/down` 分支是**未经实跑**的代码）；
3. 凡需第三方库的证明，一律降为 **AST 静态导出** 或 **只 exec 纯标准库函数体**（§3 两种技法）。

`ZoneInfo` 那条**不是**项目依赖缺口——见 §6.4 的更正（本机没有 venv，锁文件里 tzdata 在案）。

---

## 3. D-12 闭合链条（本卡的核心风险）

### 3.1 缺陷本体

旧 conftest 三级解析：`环境变量 > apps/api/.env > _DEFAULT_PG_URL`，第三级是
`postgresql+psycopg://bothot:bothot@localhost:5433/bothot`（**含明文口令字面量**）且只
`warnings.warn` 不拒绝。未设变量时测试真实写入生产形态库（端口 5433 是部署库，
`AGENTS.md` 端口表）。

### 3.2 为什么「删掉常量」不够——9 个下游独立回退点

`prove_dsn_policy.py` 用 AST 扫 `apps/api/tests/`，把 `os.environ.get(VAR, default)` 形态的
回退点全部列出并判定 default 是否生产形态（`:5433` + 口令）。**实测 9 个，9 个全是生产形态**：

| 文件:行 | 生产形态 |
|---|---|
| `apps/api/tests/test_docs_batch.py:45` | ✅ |
| `apps/api/tests/test_idempotency_lock.py:48` | ✅ |
| `apps/api/tests/test_job_worker.py:37` | ✅ |
| `apps/api/tests/test_manifest_sync.py:39` | ✅ |
| `apps/api/tests/test_persistence.py:32` | ✅ |
| `apps/api/tests/test_process_heartbeat.py:40` | ✅ |
| `apps/api/tests/test_scheduler.py:41` | ✅ |
| `apps/api/tests/test_w2_worker.py:27` | ✅ |
| `apps/api/tests/test_w3_push_scheduler.py:46` | ✅ |

这些文件在卡片的 **禁止修改** 集内（「上面未列出的一切」）。卡片只让删 conftest 的常量，
删完之后这 9 处仍会在变量缺席时直连 5433 —— **卡片的允许修改集不足以闭合它自己声明的风险**（§6.1）。

**扫描口径的边界（复审指出的盲区，已补）**：上表只覆盖 `tests/test_*.py` 里
`os.environ.get(VAR, 字面量)` 这一种形态。还存在**第 10 个消费者**走另一条路：

| 文件:行 | 形态 | 值来源 |
|---|---|---|
| `apps/api/tests/test_chat_sse.py:18` | `from conftest import PG_URL`（用于 `:1208`、`:1272`） | conftest 解析结果——未配置时即拒连地址，**不含生产字面量** |

harness 现同时清点两类消费者并**钉死数量**（S0.1.2-o `== 9`、S0.1.2-t `== ['test_chat_sse.py']`），
增减即红，防「已列全」这句话本身腐坏。其余形态已 grep 核清（`rc=1` 即无命中）：
- `os.environ[VAR]` 下标读、`os.getenv(VAR)` 单参读 → `tests/ app/` 全无；
- `test_security_middleware.py:805` 把该变量从**子进程** env 里剔除——剔除后子进程自行解析为
  「未配置 → 拒连地址」，与母进程同构，不构成旁路；
- `test_r48_admin_jobs.py:285`、`test_scheduler.py:663` 两处注释仍写「见 conftest 警告」，
  而 D-12 已删掉那条 `warnings.warn` ⇒ 陈旧注释（两文件均在本卡禁止修改集内，列 §8 移交）。

### 3.3 闭合手段：单点广播（未越界改一个文件）

conftest 在解析完成后执行

```python
os.environ[_TEST_PG_ENV_VAR] = PG_URL   # conftest.py:75
```

**必须赋值、不能用 `setdefault`**：`setdefault` 只在键缺席时写入，而「键存在但值为空串」
（CI 里 `env: AIDEANBOT_TEST_PG_DSN: "${{ secrets.X }}"` 命中空 secret、或本机 `export X=`）
是它无法区分的第三种输入——旧写法在此情形下把空串原样留给下游，9 处 `create_engine("")`
报的是 URL 解析错而非设计中「必然拒连」，且 conftest 自己解析出的规范化值被丢弃。
赋值则让 conftest 成为唯一口径（顺带剥离首尾空白）。
该缺陷由提交前自查发现，并由 §4 的变异体复现（`out_prove_dsn_policy_selftest.txt`：
旧写法广播出的值是 `''`）。

pytest 对同 rootdir 先导入 `conftest.py` 再收集测试模块，故这 9 处模块级 `os.environ.get(...)`
读到的**必然**是 conftest 的值。未配置时该值是保留地址

```python
_REFUSED_PG_URL = "postgresql+psycopg://invalid@127.0.0.1:1/bothot_dsn_unset"
```

端口 1 非 root 无法监听 ⇒ 任何机器上都必然立即拒连 ⇒ 连库夹具走 skip 分支而不是写生产。
`invalid` 是账号名、**无口令段**，不构成凭据形态（§5.4）。

**安全性质与体面性质的区分**（复审指出，成立）：「不写生产」对所有 10 个消费者都成立；
但「skip 而非报错」只对经 `db_session` / 自带 try-except 守卫的用例成立。
`test_chat_sse.py:1208`、`:1272` 两处 `create_async_engine(PG_URL)` **不在** try 内，
其前置守卫是 `:1201` 的 LangBot 可达性判断——若某天 LangBot 可达而测试库未配，
这两条会以拒连**报错**（红）而不是 skip。方向是安全的（宁可吵也不写生产），
但不是卡片设想的「体面 skip」，列 §8 移交为独立子任务。

广播值本身由 harness 从 exec 出的真身命名空间取 `ns["_broadcast"]` 观测，四档都是
**观察到的赋值**而非推断：env 档 → 用户 DSN（c/e）、env 空串档 → 拒连地址（p）、
env 纯空白档 → 拒连地址（q）、env 带空白档 → 剥离后的 DSN（s）、仅 `.env` 档 → 文件值（m）。

### 3.4 skip 原因文案与 CI 门禁的耦合（关键约束）

`ci.yml:148`：`pg_skips = [s for s in skips if "PG" in s[1] and "不可达" in s[1]]`，命中即门禁违规。
新文案 `SKIP_UNSET_REASON`（conftest.py:42-45）含 "PG"（`AIDEANBOT_TEST_PG_DSN`）但**刻意不含**
「不可达」——它表达的是「没配」而非「配了连不上」。harness 双向断言：
`含「未设置」= True`、`含「不可达」= False`（S0.1.2-j / S0.1.2-k）。

CI 侧 `ci.yml:51` 是**字面量**（不经 secrets 插值），所以 CI 里不会出现「键存在但值为空」这一
输入；赋值语句回写的正是它自己提供的那个值（剥离首尾空白后逐字相同），下游 9 处读到的 DSN 不变
⇒ 连库用例照常真实执行，本次改动不会把 CI 掏空成「全 skip 绿」（backend job 实测见 §5）。
空串档是本机/自托管场景的加固，不是已观测到的 CI 故障。

### 3.5 另一处同族脆弱点（S0.2.1）

`test_w3_push_scheduler.py` 的投递失败类用例原先假设「9999 端口无人监听」。
`app/providers/push/webhook.py:39-40` 对 `200 <= status < 300` 判 `delivered=True`：
一旦本机 9999 被任意回 2xx 的服务占用，PushLog 不再落 failed →
`test_event_delivery_failure_no_reclaim` 假失败（01 §1.2.1 记录的 1 failed 即此）。
两处夹具的 `webhook_url` 改为 `http://127.0.0.1:1/bothot-hook-no-listener`，
与本机端口占用**解耦**（拒连 ⇒ `webhook.py:50-51` 的 `except Exception` 恒返 `retryable=True`）。

---

## 4. 新增证据脚本的判定形态

| 脚本 | 技法 | 为什么可信 |
|---|---|---|
| `prove_dsn_policy.py` | AST 取 conftest「第一个装饰器之前」的模块前缀，剥掉三方 import、stub `dotenv_values` 后 **exec 真身**；再用 `src_text=` 注入**变异体**（广播语句换回旧实现 `setdefault`）复跑同两档输入 | 执行的是当前源码，不是抄本；改坏 conftest 立即反映为 FAIL。`--self-test` 进一步证明 p/s 两条断言**对旧实现敏感**（变异体广播出 `''` 与带空白值 ⇒ 变红），排除「永真断言」（G-23） |
| `prove_provider_shapes.py` | A 组 AST 从 5 个 Provider 的 `query_work_list` **导出** `.get("K")` 全路径再定位样本；B 组 exec `rss.py` 的 `_parse_feed` 链与 `manifest.py` 的 `_map_row` 链，把样本真跑；C 组行键 ∩ `_ID_KEYS` | 脚本内不写死任何上游键名，代码漂移即 FAIL |
| `g24_static_check.py` | 标准库复核 `ruff check app tests` 选中规则族的可机检子集 + **7 条变异自检** | `--self-test` 证明每条规则真能捕获；否则「无违规」是空话 |

五份 stdout 已入档：`out_prove_dsn_policy.txt`、`out_prove_dsn_policy_selftest.txt`、
`out_prove_provider_shapes.txt`、`out_g24_static_check.txt`、`out_g24_selftest.txt`。

---

## 5. 机器判定原始结果

### 5.1 S0.1.2 —— `prove_dsn_policy.py`
```
ALL PASS (20 断言，回退点 9 个已列举)
```
其中：`_DEFAULT_PG_URL` 命中数 0（S0.1.2-a）、conftest 内无凭据字面量（b）、env 档（c/d）、
广播值=解析值（e）、未设置→空串（f）、未设置→拒连地址且不含 5433（g/h/i）、
文案含「未设置」不含「不可达」（j/k）、空白 env 视为未设置（l）、`.env` 档（m）、
`.env` 空值视为未设置（n）、**空串/纯空白 env 也广播拒连地址（p/q）、三档广播值皆非空（r）、
带空白 env 广播剥离值（s）**、下游回退点 9 处全为生产形态（o）。

`--self-test`（变异反证，`out_prove_dsn_policy_selftest.txt`）：
```
OK  S0.1.2-p 空串 env 广播拒连地址：现行='postgresql+psycopg://invalid@127.0.0.1:1/bothot_dsn_unset'（断言成立）｜setdefault 变异体=''（断言变红）
OK  S0.1.2-s 带空白 env 广播剥离值：现行='postgresql+psycopg://bothot:bothot_ci@localhost:5547/bothot_test'（断言成立）｜setdefault 变异体='  postgresql+…test  '（断言变红）
SELF-TEST PASS：两条新断言对旧实现敏感
```

### 5.2 S0.3.2 —— `prove_provider_shapes.py`
```
合计 PASS=32 WARN=10 INFO=11 FAIL=0
```
容器层级逐条硬断言并通过：`$.data.list`(RedFox)、`$.data` **本身即数组**(Dajiala)、
`$.data.MsgList.Msg`(JustOneAPI / Wellbyte——TC-A4-04 看错的那层)、`$.data.data`(TikHub)。
RSS 组是**真执行**：`rss2.xml`/`atom.xml` 良构 → `_parse_feed` 各产 2 行 → 全部可被 `_map_row` 消费。
WARN 的 10 条 = 5 条 TikHub 兜底变体（`data.articles` 与 item 顶层 `content_url/title/digest/create_time`，
AST 判定为 OR 链非首项 ⇒ 允许缺席）+ 4 条 §6.3 的行键缺口 + 1 条 §6.4 的 tz 替身声明。

**强度口径已按复审意见收紧**（不拿 PASS 计数当成绩）：
- 旧版 `rows_found >= 3` 是地板值（justoneapi 实际命中 10 也只需 3）→ 现改为
  「**主路径**读取键缺失即 FAIL」，兜底变体才降 WARN；实测 redfox 3/3、dajiala 5/5、
  justoneapi 10/10、tikhub 8/13（5 条为兜底）、wellbyte 10/10。
- 新增「JSON 样本顶层无注记键」断言（历史版本把 `_shape_source` 塞进响应体，
  使「样本 == 上游形状」这句话自带一个上游不会给的键）⇒ 注记 prose 迁到
  `apps/api/tests/fixtures/provider_payloads/README.md`，样本回归字面形状。
- B 组 `expect=2` 是**我对样本条目数的声明**（自指风险已认识），其承重在于
  「解析器真跑出来的行数/键名与声明一致」，不是「样本印证样本」。

### 5.3 S0.1.1 —— `scripts/test-env.sh`（只跑了不启服务的部分）
```
bash -n scripts/test-env.sh                          rc=0
bash scripts/test-env.sh env                         → 3 行 export
AIDEANBOT_TEST_PG_PORT=5433 … env                    rc=2   （端口法：拒绝复用部署库）
AIDEANBOT_TEST_REDIS_PORT=6379 … env                 rc=2
AIDEANBOT_TEST_PG_PORT=80 … env                      rc=2   （<1024 越界）
eval "$(bash scripts/test-env.sh env)" && echo ${AIDEANBOT_TEST_PG_DSN/+psycopg/}
  → postgresql://bothot:bothot_ci@localhost:5547/bothot_test
bash scripts/test-env.sh bogus                       rc=64
```
⚠ **边界**：`up` / `down` 分支需要 docker 或本地 PG 二进制，属「启动服务」，**本卡未执行**。
因此 S0.1.1 的验收命令（`up && eval && psql -c 'select 1'`）**本机未满足**，须由有 docker 的
执行者或后续会话补跑；脚本自身在头部注释里也写明了这一点，避免被当作已验。

### 5.4 秘密扫描边界
`scripts/test-env.sh` 用 `bothot_ci`，落在 `.gitleaks.toml:53` 白名单
`(?:bothot|bothot_dev|bothot_ci|aideanbot|nobody|nosuch|not_a_secret)` 内；
`.gitleaks.toml:30` 的规则要求「协议 + 账号 + 冒号 + 口令 + at 号」连成一体的邻接形状，
`_REFUSED_PG_URL` 是 `invalid@127.0.0.1:1`（无冒号口令段）→ 不匹配。
本卡**没有**引入任何新凭据字面量，且删除了 conftest 里旧的一处。
**但同一形态的字面量仍活在别处**（本卡未动，须如实记边界而非宣称「已清干净」）：
`ci.yml:50-51`（service 口令，CI 内网一次性容器）、`alembic.ini:4`（宿主裸跑迁移目标，
`test_db_url_resolution.py` 正是锁定「`DATABASE_URL` 压过它」的契约）、
`test_db_url_resolution.py:9-10`（作为被测契约的输入常数）、
以及 9 个测试文件各自的 `os.environ.get(..., 生产字面量)` 默认值（§3.2 表，本卡靠广播屏蔽）。
另一处不同面的暴露：`app/core/config.py:20` 的 `database_url` 缺省指 **`:5432`**（容器内端口），
广播机制管不到 settings——本机与 CI 的 5432 均无监听（CI service 映射 `5433:5432`，`ci.yml:41`），
故不构成活体风险，但记为「未闭合面」而非「已闭合」。

---

## 6. 卡片与现实偏差（必须回写大纲，逐条带反证）

### 6.1 允许修改集不足以闭合 D-12
卡片「依据」写「删除 `_DEFAULT_PG_URL` 常量」，但 §3.2 的 9 个文件被「未列出即禁止」挡在门外。
本 EVD 用 conftest 广播在不越界的前提下收口。**建议**：大纲把 S0.1.2 的动作改述为
「删常量 **+** 未设置时广播拒连地址，使下游模块级回退点一并失效」，并注明依赖
「pytest 先导入 conftest」这一顺序保证。

### 6.2 两条反证命令证不到它们声称的东西
- **S0.1.2 反证**：`pytest tests/test_scheduler.py -q -rs` 看 skip 原因含「未设置」。
  但 `test_scheduler.py` 不使用 `db_session`，它的 skip 来自**自己**的守卫
  （`test_scheduler.py:79` `pytest.skip(f"PG 不可达（…）")`），文案与 conftest 无关。
  照原反证跑，改前改后都「通过」，属不可能失败的断言。已改用 exec 真身的 harness 代证。
- **S0.2.1 反证**：`python -m http.server 9999` 起来后请求返回 **501**，
  `webhook.py:41-46` 的失败分支带 `retryable=resp.status_code >= 500`（`:46`）→ 501 亦判可重试，
  与拒连**同结果**，改前用例照样 PASS，构造不出「改前 FAIL」。真正的假绿需要 **2xx** 监听者。
  本卡选择保留端口 1 是**从根上去掉假设**，而不是去复现一个更难复现的反证。

### 6.3 新发现（本卡未修，属 S2/S4/S9）
4 个付费 Provider 归一化后的行键只有 `{url, title, digest, publish_time}`（AST 导出），
与 `manifest.py:51` `_ID_KEYS = ("workUuid", "work_uuid", "uuid", "id", "articleId", "article_id")`
**交集为空** ⇒ `_map_row` 在 `manifest.py:144-146` 返回 None ⇒ `sync_source` 走
`manifest.py:210-212` 的 `report.skipped += 1`。**后果是「清单永远不入库且只有 skipped 计数、
不报错不告警」**（数据黑洞），RedFox 对照成立：其原始行 2/2 全部映射成功
（`workUuid` 命中、`workUrl` 命中、北京时间串按 `+08:00` 落地）。

**成本结论已更正（本 EVD 首版与 `ea0ea71` 提交信息都写错了，此处为准）**：
首版称「`saw_existing` 恒 False ⇒ 翻满 `max_pages` ⇒ 每号每轮最多 20 次付费调用」。
独立复审反驳并被核实为真，漏看了终止条件 ②：
- `manifest.py:217-218` `if len(rows) < size: break`，`size` = `_page_size`
  （`manifest.py:172` 缺省取 `app/providers/redfox/client.py:51` 的 `PAGE_SIZE = 20`）；
  4 家首页返回 4/10/8/10 条 ⇒ **第 1 页即止 = 1 次调用**；
- 即便某页返回 ≥20 条，4 家都 `if page > 1: return []`
  （`dajiala.py:91`、`justoneapi.py:101`、`tikhub.py:102`、`wellbyte.py:118`）
  ⇒ `manifest.py:205-206` 空页 break ⇒ **上界 2 次**。

故正确的量级是 **每号每轮 1–2 次调用**，不是 20 次；缺陷严重性从「烧钱」重述为
「零入库 + 无告警 + 花费虽小但仍为纯浪费」。

### 6.4 时区库：首版归因错误，已推翻（不是项目缺口）
首版据「本机 `ZoneInfo('Asia/Shanghai')` 抛 `ZoneInfoNotFoundError`」+「`pyproject.toml:6-23`
依赖表不含 `tzdata`」判为**项目依赖缺口**。独立复审指出并经验证：
`apps/api/uv.lock:865-868` 里 `psycopg 3.3.5` 的 dependencies 含
`{ name = "tzdata", marker = "sys_platform == 'win32'" }`（`tzdata 2026.3` 见 `uv.lock:1346`）
⇒ 按锁文件安装（`uv sync`，或 CI 的 `pip install -e ".[dev]"` 拉 psycopg）在 Windows 上**自动获得**
tzdata。本机崩的真实原因是**本会话没有 venv**（用户约束「无需安装开发环境和依赖」，§2），
与依赖表无关。保留的次级事实（不再称「缺口」）：7 个模块在 import 期即
`ZoneInfo("Asia/Shanghai")`（`manifest.py:48`、`hot.py:38`、`feed_service.py:38`、
`hot_cluster.py:45`、`hot_scorer.py:35`、`job_worker.py:68`、`push_template.py:19`），
在无 tz 数据库的环境（如 `python:slim` 镜像未装 `tzdata` apt 包）会 import 失败——
镜像层是否自带时区数据属 Dockerfile 核查项，不在本卡范围，列 §8。
本 EVD 的 B/C 组因此使用固定 `+08:00` 等价替身（Asia/Shanghai 自 1991 年起无夏令时，
对本卡断言等价），并在 `out_prove_provider_shapes.txt` 里以 WARN 显式声明，不做静默替换。

### 6.5 卡片外的同形脆弱点（本卡禁止修改，需新子任务）
`webhook_url="http://localhost:9999/…"` 的同形假设另存在于 3 个文件：
`test_alerting_drill.py:100`、`test_bots_logs_filter.py:27`、`test_wb_push_hardening.py:79`。
S0.2.1 只覆盖 `test_w3_push_scheduler.py`。**建议**：新增 S0.2.3 收口这 3 处，或并入 S9。

### 6.6 其它核实
- `source_resolver.py` 实际位于 `app/providers/source_resolver.py`（非 `app/services/`）。
- conftest 旧注释称下游回退点「7 个」，AST 实测 **9 个**，注释已按实测更正。
- `tests/fixtures/` 无需 `__init__.py`：pytest `prepend` 导入模式下 `tests` 是命名空间包，
  `python -c "import tests.fixtures.wechat_urls"` rc=0（在 `apps/api` 下）。
- **自查发现并已当场修掉的缺陷**（首版实现自身的漏洞，非卡片要求）：广播原写
  `os.environ.setdefault(...)`，在「键存在但值为空串」时是空操作 → 下游 9 处拿到 `""`，
  `create_engine("")` 抛的是 URL 解析错而不是设计中的「必然拒连」，skip 文案也随之失真。
  已改为无条件赋值（`conftest.py:75`），并补 S0.1.2-p/q/r/s 四条断言 + 变异反证（§5.1）。
  影响面复核：三档输入下都不会连生产库（空串同样被拒），故属**正确性/可观测性**加固，
  非凭据泄漏类缺陷——记录时不夸大意涵。

---

## 7. 复现命令（逐条可复制，均不启服务、不装依赖、不连库）

```bash
cd /d/Code/AideanBotHot
PYTHONIOENCODING=utf-8 python docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py        # 期望 rc=0
PYTHONIOENCODING=utf-8 python docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py --self-test  # 期望 SELF-TEST PASS
PYTHONIOENCODING=utf-8 python docs/06_validation/evidence/EVD-V2-00/prove_provider_shapes.py   # 期望 rc=0
python docs/06_validation/evidence/EVD-V2-00/g24_static_check.py                               # 期望 rc=0
python docs/06_validation/evidence/EVD-V2-00/g24_static_check.py --self-test                   # 期望 7/7
bash -n scripts/test-env.sh && bash scripts/test-env.sh env                                    # 期望 rc=0 + 3 行 export
cd apps/api && python -c "import tests.fixtures.wechat_urls as w; print(len([k for k in dir(w) if k.isupper()]))"  # ≥6
ls apps/api/tests/fixtures/provider_payloads | wc -l                                           # =8（5 JSON + 2 XML + README）
python -c "import json,glob;print([f for f in glob.glob('apps/api/tests/fixtures/provider_payloads/*.json') if '_shape_source' in open(f,encoding='utf-8').read()])"  # 期望 []
```

`PYTHONIOENCODING=utf-8` 是必需的：Windows 控制台默认 GBK，中文证据会花屏（脚本内也已
`sys.stdout.reconfigure`，双保险）。

---

## 8. 未闭合 / 移交下一步

**卡片状态判「部分完成」**（S0.1.1 的 `up/down`、S0.1.3 的 junit 未达），下表逐项给落点：

| # | 未闭合项 | 性质 | 建议落点 |
|---|---|---|---|
| 1 | S0.1.3 连库全量 pytest + junit（failed=0） | 需真起 PG | 交 CI postgres job，推送后以 run 结论回填 §5 |
| 2 | S0.1.1 `test-env.sh up/down` | 需 docker | 有 docker 的执行者补跑；端口护栏与 `env` 分支已验（§5.3） |
| 3 | §6.3 四家付费 Provider 行键与 `_ID_KEYS` 交集空 ⇒ 清单永不入库且无告警 | 数据正确性 | STEP-03（渠道行契约归一）；严重性按 §6.3 更正后的「1–2 次调用/零入库/静默」述，勿沿用「20 次」 |
| 4 | §6.5 三处 `localhost:9999` 同形假设（`test_alerting_drill.py:100`、`test_bots_logs_filter.py:27`、`test_wb_push_hardening.py:79`） | 测试脆弱 | 新增 S0.2.3 收口，或并入 STEP-09 夹具整理 |
| 5 | `test_chat_sse.py:1208`/`:1272` 的引擎创建不在 try 内 ⇒ 特定组合下**报错而非 skip**（§3.3） | 测试体面性 | 与 #4 同批（属连库守卫统一化） |
| 6 | 三个证明脚本（`prove_dsn_policy` / `prove_provider_shapes` / `g24_static_check`）**不在 CI** ⇒ 夹具头 60+ 条 `file:line` 引用与主路径键覆盖无门禁，会静默腐坏 | 证据可持续 | 新增 job（或并入 `check_docs_consistency`）跑 stdlib-only 脚本；本机无需依赖即可跑 |
| 7 | 陈旧注释：`test_r48_admin_jobs.py:285`、`test_scheduler.py:663` 仍写「见 conftest 警告」（该 `warnings.warn` 已被 D-12 删除）；`ci.yml:28-32` 注释仍描述「conftest 默认 DSN 指 5433」的旧行为 | 文档漂移 | 与 #4/#5 同批清理；`ci.yml` 改动需另行授权 |
| 8 | §6.4 更正后的次级问题：Dockerfile 基础镜像是否自带 tz 数据库 | 部署核查 | STEP-11 收口前做一次镜像层核验 |
| 9 | `ea0ea71` 提交信息里的「最多 20 次付费调用」结论错误（不 amend，历史不改） | 记录 | 以 §6.3 为准；后续引用该缺陷时读本文件而非提交信息 |

本卡代码改动均在测试侧，回滚 `git revert` 即可，无数据影响。
