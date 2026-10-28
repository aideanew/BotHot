# STEP-72 交付读数：假上游两件（假 LLM + 假 LangBot）

日期：2026-10-28　执行者：执行助手　档位：opus（卡面 §12）

## 1. 交付面（`git status` 现读，与此处逐条对齐）

| 文件 | 性质 | 规模 |
| --- | --- | --- |
| `scripts/e2e/fake_llm.py` | 新增 | 132 行，标准库 only |
| `scripts/e2e/fake_langbot.py` | 新增 | 118 行，标准库 only |
| `scripts/e2e/run_real_backend.sh` | 修改 | +30 / −6 |
| `docs/06_validation/evidence/EVD-V24-72/` | 新增 | 本目录 7 个读数文件（`s72_readings.md`、`s72_script_checks.txt`、`s72_launcher_checks.txt`、`s72_full_stack_run.txt`、`s72_health_readings.txt`、`s72_fake_llm_curl.txt`、`s72_fake_langbot_curl.txt`） |

两张脚本的表里行数是**lint 后**的现行值：CI 的 lint step 跑 `ruff check app tests ../../scripts`
（`ci.yml:75`）与 `mypy app ../../scripts`（`:79`），两台脚本最初各有 1 处 UP009、若干 UP031 与 1 处 E501，
已按 ruff 修复；响应体与控制流一字未变，这一点由两个 curl 证据文件的「lint 后复跑」段实测背书，
不再是推理。逐条见 `s72_script_checks.txt` 的「lint 后复核」段（含 blob id）。

禁止面同时现读为零改动：`apps/api/app/**`、`apps/api/tests/test_chat_sse.py`、`apps/web/**`、
`packages/contracts/**`、`.github/workflows/ci.yml`。产品侧全部走环境变量（`LLM_API_BASE` /
`EMBEDDING_API_BASE` / `LANGBOT_BASE_URL`）指过来，一个字节没动。

## 2. S72.1 假 LLM：逐条对着产品代码写，而不是对着"一般 OpenAI 兼容"写

| 产品侧锚点（现读行号） | 假服务怎么兑现 | 读数 |
| --- | --- | --- |
| `chat.py:239-248` 请求 `POST /chat/completions` + `Authorization: Bearer` | 只认 `POST /v1/chat/completions`（`path` 精确比对），body 读掉不解析 | curl 原文见 `s72_fake_llm_curl.txt` |
| `chat.py:281-287` 只认 `data: ` 前缀 / `[DONE]` 结束 / `choices[0].delta.content` | 帧由 `_chunk()` 拼 `{"choices":[{"delta":{"content":…}}]}`，尾帧 `data: [DONE]` | 4 帧原文（3 段 + DONE） |
| `chat.py:268` 首 token 超时 = `LLM_FIRST_TOKEN_TIMEOUT`（`chat.py:59` 取值 15.0s） | 首帧**立即**发，不等任何东西 | normal 三次 0.033 / 0.015 / 0.015s（判据 1s，余量约 30 倍） |
| 「响应较慢」degraded 分支 | `?mode=slow`（或 `FAKE_LLM_MODE=slow`）首帧前 sleep 16.0s，跨过 15s 锚点 | 实测 16.015s |
| 上游提前关连接 | `?mode=abort` 发 1 段后直接关连接，不发 `[DONE]` | 逐行原文 1 帧；`[DONE]` 出现次数 0 |
| `reranker.py:99-101`（上游 ≥400 ⇒ 保序回退） | `/v1/embeddings`、`/v1/rerank` 回 404 JSON | 两条 HTTP 404 |

`?mode=abort` 造的是「上游发了一帧就关连接」这个**输入**；产品侧收到它之后走哪一支（正常收尾 /
50002 不可达 / 50001 兜底，兜底见 `chat.py:387-393`）本机**没有验**——那是 STEP-60 的判据，
本卡只保证这个输入可复现。

模式选择的优先级：`?mode=` > 环境变量 `FAKE_LLM_MODE` > `normal`；未知取值回落 `normal`（不报错，避免
拼错一个查询串把整档 e2e 变成"假服务不理你"的静默失败）。

`Connection: close` + 不声明 `Content-Length` 是刻意的：SSE 以连接关闭结束正文，若走 HTTP/1.1 keep-alive
且不给长度，客户端会一直等下一帧——那会让"流没结束"与"服务挂了"在读数上无法区分。

## 3. S72.2 假 LangBot：形状逐字复用 `test_chat_sse.py` 的 `_results()`

| 路由 | 行为 | 依据 |
| --- | --- | --- |
| `POST /api/v1/user/auth` | `{"code":0,"msg":"success","data":{"token":"<fake-token>"}}` | `client.py:52-68` 登录、`_extract_token` `:217-225` 取 `data.token` |
| `POST /api/v1/knowledge/bases/<kb>/retrieve` | 带 `Bearer <fake-token>` ⇒ `{"code":0,…,"results":[{…}]}`；否则 401 | `client.py:198-211`；`client.py:102-103` 判 `code not in (None,0)` |
| `GET /api/v1/knowledge/engines` | 无 token ⇒ 401 带 code 信封；有 token ⇒ 200 `data: []` | `/system/health` 的 langbot 探针打这条（`system.py:124`（`_check_langbot`，探测行 `:138`）） |
| 其它路径 | 404（也带 `code` 信封） | 卡面 S72.2「其它路径回 404」 |

结果条目的形状（**卡面 §3 与 §5 冲突，此处按 §5 走**：卡面 §3 把它写成 `content` 为对象且带 `distance`，
而 §5 要求逐字复用 `_results()`；`_results()` 里 `content` 是**列表**、没有 `distance`，产品侧
`_context_texts` 与 `_filter_by_allowed` 吃的也是列表形。卡面文字未改——§9 的允许修改面里没有卡面 §3）：
`{"content": [{"text": …, "file_name": "fake-doc-1"}], "score": 0.92}`——
`content` 是**列表**（`test_chat_sse.py` 的 `_results()` 就是这么写的），不加 `distance` 等测试里没有的字段。
`file_name` 钉死 `fake-doc-1`：`chat.py:83-96` 的 `_filter_by_allowed` 只保留 file_name 落在候选集合里的条目，
而候选集合来自 STEP-73 种子的 `langbot_file_id`——两边逐字一致，否则检索结果会被全部过滤掉、
`ask` 表现为"检索到了但上下文为空"。

**超出卡面字面的一处，如实登记**：卡面 S72.2 只要求登录 + 检索两条、其它路径 404；本卡多给了
`GET /api/v1/knowledge/engines` 这一条。原因是 `/system/health` 的 langbot 探针（`system.py:124`（`_check_langbot`，探测行 `:138`））
要求「响应是 401 且 body 是带 `code` 的信封」才判 `ok`；不给这条路由时探针读 `unhealthy`，
本卡验收第 7 条「不再是 unreachable」会在字面上成立、实际却没证明"假服务被认出来"。
这条路由不影响产品代码，也不改变"其它路径 404"（引擎清单本身是有依据的真实路由）。

鉴权刻意**比"全放行"更严**：检索与引擎清单都要求 `Bearer <fake-token>`。
令牌占位取尖括号模板形不是风格问题：CI 的敏感形门把「常量名 + 等号 + 引号字面量」判成口令赋值形，
而模板形是那道门自己列的"占位不算秘密"之一 ⇒ 这样写既过门，也不必去 `.gitleaksignore` 登记指纹
（那是 STEP-00S 的归属面，不在本卡）。目的是让「产品没登录就去检索」
这类缺陷在这里红，而不是被假服务兜住。

## 4. S72.3 启动器接线（八处，行号现读）

| 位置 | 内容 |
| --- | --- |
| `run_real_backend.sh:21` | usage 增加退出码 `11` 的说明 |
| `:38` | `--with-fake-langbot) WITH_FAKE_LANGBOT=1 ;;`（未知参数文案同步加它） |
| `:89` | `role_port` 加 `fake_langbot) echo 3291 ;;` |
| `:141` | `stop_all` 命令行白名单加 `*"scripts/e2e/fake_langbot.py"*` |
| `:163` | `pkill` 特征兜底第三条（本 checkout 绝对路径） |
| `:175` / `:181` | 端口终检循环加 `fake_langbot` 与端口 3291 |
| `:240` | `[ "$WITH_FAKE_LANGBOT" = 1 ] && ports_to_check="3291 $ports_to_check"` |
| `:268-271` | 缺文件时报错 `exit 11`（照 fake_llm 的 `:263-266` 的形写） |
| `:292-300` | `== ②b 假 LangBot 上游 :3291 ==`，并在 uvicorn **之前** `export LANGBOT_BASE_URL` |

启动顺序按卡面：假 LLM（②）→ 假 LangBot（②b）→ 后端（③）。`LANGBOT_BASE_URL` 必须在 uvicorn 之前 export：
`settings` 在进程启动时读环境变量，起完再设等于没设。

## 5. S72.4 起栈自测：用启动器本身跑，读数见同目录两个文件

- `s72_full_stack_run.txt`：`--with-fake-llm --with-fake-langbot --no-frontend` 的完整输出。关键行：
  1. `端口检查通过（本次要用：3291 3290 3300）`
  2. `== ② 假 LLM 上游 :3290 ==` → `== ②b 假 LangBot 上游 :3291 ==` → `== ③ uvicorn :3300 ==`
  3. `health 就绪（14s）：{…"deps":{"postgres":"unreachable","redis":"unreachable","langbot":"ok"}}`
     ⇒ **验收第 7 条由启动器自己跑出来**，读数是 `ok`，不是 `not unreachable` 的下限
  4. 收尾 `端口终检 backend :3300 空闲` / `fake_llm :3290 空闲` / `fake_langbot :3291 空闲`，
     之后 `netstat` 读 `(3290/3291/3300 均无监听)` ⇒ **验收第 8 条**
- `s72_launcher_checks.txt`：`bash -n` rc=0、未知参数 rc=64（文案含新旗标）、
  `:3291` 被占时预检 rc=2 且点名 3291、停机终检的红/绿两条路径。
- `s72_script_checks.txt`：`ast.parse` 通过、零第三方 import、卡面 §7 三条命令逐字真跑。
- `s72_fake_llm_curl.txt` / `s72_fake_langbot_curl.txt`：两个服务的响应原文（不是摘要）。

**S72.4 勾选的含义要收窄**：它表示「起栈自测这一步已执行、读数已记录」，**不**表示卡面 §2 的目标
「`POST /api/v1/chat/ask`（带 cookie）收到 `delta` 帧而不是 30002」已达成——那一半需要 PG + 会话/
空间知识库种子（STEP-73），本机在第 ⑤ 步就 rc=5。§2 目标整体达成与否由 STEP-73 与 STEP-60 的读数判。

本机走到哪一步就停在哪一步，没到的地方不伪造：

| 卡面 rc | 本机读数 | 原因 |
| --- | --- | --- |
| `5`（种子不合格） | 命中 | 本机无 PG：traceback 末行 `psycopg.errors.ConnectionTimeout`，指明 `port: 5433`。种子归 STEP-73 |
| `7/8`（前端/ready） | 未执行 | `--no-frontend`；前端归 CI 的 e2e-real job |
| `11`（缺 fake_langbot.py） | 未执行 | 触发它要先挪走本卡交付物；静态读已登记在 `s72_launcher_checks.txt` §⑤ |
| 迁移步（①） | 跳过 | `E2E_SKIP_MIGRATE=1`，本机无 PG |

## 6. 验收标准逐条对账

| 卡面验收 | 读数 | 结论 |
| --- | --- | --- |
| 两个脚本 `ast.parse` 通过 | 见 `s72_script_checks.txt` 两节 | ✅ |
| 两个脚本零第三方 import | `sys.stdlib_module_names` 判定：非标准库模块 0 | ✅ |
| `auth` 返回体含 `"token"`，`_extract_token` 能取到 | 原文 `{"code": 0, …, "data": {"token": "<fake-token>"}}`，token 在 `data.token`（`_extract_token` 的第一顺位） | ✅ |
| `retrieve` 的 `data.results[0].content.file_name == fake-doc-1` | 形状自检行 `file_name= fake-doc-1` | ✅ |
| 首个 `data: ` 帧在连接后 1s 内 | 0.033 / 0.015 / 0.015s；lint 后复跑 0.027 / 0.015 / 0.016s（`s72_fake_llm_curl.txt` 两节） | ✅ |
| `bash -n` 通过 | rc=0 | ✅ |
| 起栈后 `/system/health` 的 `langbot` 不再是 `unreachable` | `"langbot":"ok"`（启动器 ④ 行） | ✅（强于下限） |
| `--stop` 后 3290/3291 均无监听 | 端口终检三行全绿 + `netstat` 全空 | ✅（本机） |
| `@ci` 的 `Stop stack` 仍 success | 由本卡推送后的 run 读；卡面同轮登记 | ⏳ 提交后读 |
| 本卡不改 `apps/api/app/**` | `git status` 现读：改动只有 `scripts/e2e/**` + 证据目录 | ✅ |

## 7. 保真度：不可证，不写成"与真实上游一致"

**这一条必须直说**：假服务能证明的只有「产品代码在这几条路径上按 `chat.py` / `client.py` 现读的行为
处理本服务发出的字节」。它**不能**证明与真实 SiliconFlow / LangBot 等价，理由三条：

1. 契约是从产品**消费端**读出来的，不是从上游规范读出来的。厂商在未被读到的字段上（错误信封的具体形状、
   限流响应、keep-alive 行为、编码细节）与假服务不同，本服务一律不模拟。
2. 假服务只覆盖 `chat.py:239-287`（流式问答）与 `client.py:52-68` / `:198-211`（登录、检索）这几条路径。
   建库、上传、ingest、删除、`list_kb_files` 等 `client.py` 里的其它方法**一条都没实现**，打过去就是 404。
3. 本卡的验收第 7 条只说明"探针把本服务认成活的 LangBot"，不说明"真实 LangBot 在同样配置下也会被判 ok"。

因此 STEP-60 / STEP-73 引用本卡的读数时，只能说「在假上游下链路通」，不能说「产品与真实上游一致」。

## 8. 已知局限（不修，登记给规划方）

- `code: 0` 信封的 `msg` 字段假服务写 `"success"`；产品侧 `client.py:103` 只在 `code != 0` 时读 `msg`，
  故该字段对本卡判据无影响，但它不是从上游实测来的形状。
- `/system/health` 的 langbot 探针在本机读的是「经 Windows 系统代理」的结果（httpx `trust_env` 默认开），
  直连环境下停止假服务会读到 `unreachable`，本机读到 `unhealthy`。两种都不是 `ok`，
  归因（假服务停掉 ⇒ 不再是 ok）成立，但**本机读不到 `unreachable`** 这一点已写进
  `s72_health_readings.txt` §C，避免后续把本机读数当 CI 读数引用。
