# STEP-73 读数：`/chat` 可检索种子

## 1. 交付物与口径

| 文件 | 性质 | 说明 |
| --- | --- | --- |
| `scripts/e2e/seed_chat_space.py` | 新增 264 行 | 四张表幂等 upsert + 进程内两遍自证；stdout 首行 `space_id=<uuid>` |
| `scripts/e2e/run_real_backend.sh` | 改 ① 段（⑤b） | 在 ⑤ 种子会话之后调用它，把 id 追加成 seed 文件的 `space <id>` 行；新增退出码 12 |
| `docs/06_validation/evidence/EVD-V24-73/` | 新增 | 本目录 |

**直写表是测试夹具，不是产品路径（D-V24-12）**。产品侧建空间/建文档走 `app/services/**` 里
「LangBot 建库 → 拿 `kb_uuid`/`file_id` → 落 `knowledge_documents`」那一整条链；本卡交付的脚本绕过它，
只为把 D-V24-12 需要的三个值摆进库。它**不**证明产品具备直写表能力，也**不**覆盖建库、上传、ingest、
删除任何一条真实路径——后续引用本卡时不能把它写成"产品的建库链路已验证"。

为什么必须有这条种子：`chat.py:83-96` 的 `allowed_file_ids` 取自本空间的
`knowledge_documents.langbot_file_id`；集合为空时 `_filter_by_allowed` 会把假 LangBot 返回的那一条整体
过滤掉，`ask` 表现为"检索到了但上下文为空"。那不是缺陷，是没种子。

## 2. 卡面逐条对账

| 卡面验收 | 读数 | 结论 |
| --- | --- | --- |
| `ast.parse` 通过 | `s73_static_checks.txt` §1：`ok` / rc=0 | ✅ |
| 连跑两次：第二次不新增行 | 脚本进程内两遍 apply + 两遍行数打印（`_apply` → `_counts` → `_apply` → `_counts`），不一致即 rc=4；**真库读数见 §5（CI）** | ⏳ 待 §5 |
| `select langbot_file_id, status … where space_id=<id>` 得 `fake-doc-1` / `READY` | 脚本末尾打印 `document: … langbot_file_id='fake-doc-1' status='READY'`；**真库读数见 §5** | ⏳ 待 §5 |
| `select langbot_kb_uuid from knowledge_spaces where id=<id>` 非空 | 打印 `space: … langbot_kb_uuid='fake-kb-1'`；**真库读数见 §5** | ⏳ 待 §5 |
| 假 LangBot 的 `file_name` 与种子 `langbot_file_id` 逐字相同 | `s73_static_checks.txt` §2：`seed_chat_space.py:64 FILE_ID = "fake-doc-1"` / `fake_langbot.py:36 FILE_NAME = "fake-doc-1"` | ✅ |
| `ask` 的 SSE 里出现 `delta` 帧（不是 `error` 30002） | **本卡未证**：需要「真库 + 假 LLM + 假 LangBot + uvicorn」四件同时在跑并发一次 SSE；本机无库（见 §4），CI 的 e2e-real 也不启假上游。归 STEP-60 的验收 | ⏳ 归 STEP-60 |
| 不改 `apps/api/app/**`、不改 `models/entities.py` | `s73_static_checks.txt` §0 的 `git status`：改动只有 `scripts/e2e/` 两个文件 + 本证据目录 | ✅ |

## 3. 卡面与本卡实做的四处出入（不代改卡面，登记给规划方）

1. **§5 步 4 与 §7 的路径**写的是 `cd apps/api && python scripts/seed_chat_space.py`，而 §4/§6/§9 写的是
   `scripts/e2e/seed_chat_space.py`。按 §9「允许修改」落笔的是后者（`apps/api/scripts/` 下没有该文件，
   且该目录被 §10 列为"复用不改"的一面）。启动器因此用 `(cd "$REPO_ROOT/apps/api" && python
   ../../scripts/e2e/seed_chat_space.py)`——cwd 留在 `apps/api`（同 ⑤，为了 `import app.*` 与 `.env`
   口径）。**第 1 轮曾写成 `../scripts/…`，在 e2e-real 上 rc=12**，详见 §5.1。
2. **§5 步 2 的 `app.core.db`**：现读的会话工厂在 `app/db.py`（`create_engine_and_session`），
   `app/core/` 下没有 `db` 模块。按现读的模块落笔。
3. **§4 的"在 `:299` 的种子步骤之后"**：行号已漂——`:299` 现在是 ②b 假 LangBot 段的末行；真正的种子
   会话段是 ⑤（`:325-344`），插入点在 `:347`。按语义（"种子会话之后、⑥ 探针之前"）落笔，行号现读见
   `s73_static_checks.txt` §7。
4. **实体列比卡面 §3 多一张表**：`ContentAsset.source_id` 是非空外键 ⇒ 必须先有 `sources` 行。
   按 §11 阻塞条件①「按实际列补，不改实体」落笔：脚本用 `(type, external_id)` 幂等地补一条
   `web / r24-fake-source` 的源，不碰实体、不加迁移。

## 4. 本机局限（不伪造，写清读数从哪来）

- **本机没有可用的 PostgreSQL**：`5547 / 5433 / 6380` 三个历史端口全无监听，机器上没有 `docker`、
  也没有 `pg_ctl.exe`（`C:\Program Files`、`C:\Users`、`C:\ProgramData` 与 `D:` 四处按名字找过）。
  因此卡面那四条"跑完后 `select …`"的读数**不可能在本机产出**，一律改取 CI 的 `e2e-real` job
  （它在 postgres service 上真跑启动器，含 ⑤ 与 ⑤b）。
- **进程内两遍 ≠ 两个进程**：第二遍走的是"已存在 ⇒ 只更新"那条分支，与跨进程第二次跑同一条代码路径，
  区别只是共用同一个进程与连接池。这条差别不改"第二次没有新增行"这个判据，但引用时不要把前者写成
  后者（证据里 §5 的读数是**一次** CI 跑的两次 apply，不是两次 CI 跑）。
- **脚本的两条 fail-closed 分支（rc=3 无用户 / rc=4 幂等破了）本机未执行**——它们都要真库才能触发。
  rc=12 那侧（启动器 ⑤b 的入口）已逐条取证，见 `s73_branch_proof.txt`（第 2 版五个用例，含"变异回
  `../scripts` 必须红"那一条）。
- **第 2 轮本机真跑过一次**（venv 解释器、`cd apps/api`、`../../scripts/e2e/seed_chat_space.py`）：
  越过路径与导入，止于 `psycopg.errors.ConnectionTimeout` / `sqlalchemy.exc.OperationalError`
  （`localhost:5432` 无监听）。原文见 `s73_static_checks.txt` §12——它证明"本机唯一缺的是库"，
  不证明脚本对真库的行为。

## 5. 真库读数（CI `e2e-real` job）

### 5.1 第 1 轮红（head `0e53199`，run `40708063479`，job `e2e-real` id `122888809302`）

⑤b 打印的原文（来自该 job 的 `10_Start real stack…` 步骤日志）：

```
== ⑤b /chat 可检索种子（STEP-73：直写表是测试夹具，不是产品路径，D-V24-12）==
    python: can't open file '/home/runner/work/BotHot/BotHot/apps/api/../scripts/e2e/seed_chat_space.py': [Errno 2] No such file or directory
❌ /chat 种子不合格（脚本 rc=2、space_id 取到 ''）；输出见上，不猜
== 失败退出 rc=12：拆除本脚本起过的进程 ==
```

根因：启动器先 `cd "$REPO_ROOT/apps/api"`（距仓根**两**级），调用却写成 `../scripts/e2e/…`，
解析到 `apps/scripts/`（不存在）。rc=2 是 `python` 打不开文件的退出码，不是脚本自己的返回码。

为什么第 1 轮的取证没拦住：`s73_branch_proof.txt` 第 1 版把 `python` 整体换成不校验参数的桩，
等于把"解释器能不能找到这个文件"一起替换掉了。第 2 版已把 cwd 与参数解析做成断言（桩 rc=67 / rc=66），
并加了 E 变异用例——当前字节绿、变异红，两者对照才算证明。

修复：`../scripts/e2e/…` → `../../scripts/e2e/…`，并在该行上方留一句说明"`../../` 与 cwd 是同一个约定"。

### 5.2 第 2 轮（修复后）真库读数

待本提交的 @ci 回填：从 `e2e-real` job 的 `10_Start real stack…` 步骤日志里取 ⑤b 的
`space_id=` / `pass1 counts:` / `pass2 counts:` 与四行 `space:/source:/asset:/document:` 读数。

## 6. 证据文件

- `s73_static_checks.txt`：ast / 两侧 grep / ruff / mypy / `bash -n` / 不建用户的静态面 / 接线点 /
  行数 / **路径按 `cd apps/api` 解析（fixed=True、old=False）** / 本机真跑止于 DB 不可达
- `s73_branch_proof.txt`：⑤b 新增段的五分支取证（happy / 缺脚本 / 脚本非零 / 取不到 space_id /
  **变异回 `../scripts` 必须红**），被测字节由 `sed` 从启动器现读截取，不是手抄副本
