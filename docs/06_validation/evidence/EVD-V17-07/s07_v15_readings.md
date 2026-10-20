# EVD-V17-07：STEP-07 S07.V15.1～3 存量审计脚本只读化与测试库演练（队列⑧）

- 日期：2026-10-21（Asia/Shanghai）
- 基线：`main@5f8d2d2`（STEP-05 记录提交）
- 卡面：`docs/任务规划V0.15.0/steps/STEP-继承卡增量-V15.md` §「STEP-07 +3」；
  原卡 `docs/任务规划V0.13.0/steps/STEP-07-存量审计与回填.md`（含 2026-10-17 追加的『回填输入清单』）
- 裁决：D-V2-06（已签 A：只读审计 → dry-run 报告 → **先在测试库实跑并验证可回滚** → 生产实跑前必须先备份）；
  D-V12-14（生产存量审计后置，先在测试库写好并演练）；D-V12-05 无关
- 所有权：`scripts/audit/**`（新，Agent-Data W）+ `apps/api/tests/test_audit_scripts.py`（新）+
  `.github/workflows/ci-windows.yml` 阈值（连库用例新增后的既有纪律）+ 本 EVD
- 环境：Win10 + Git Bash；隔离 PostgreSQL 16.4 `127.0.0.1:5547/bothot_test`（超级用户 `postgres`）；
  **生产只读 DSN 未提供 ⇒ 本文所有生产侧读数一律写「未测」，不写 0**

## 0. 开工现读（决定设计的事实在这里，不在代码注释里）

| 事实 | 读数 | 对设计的影响 |
|---|---|---|
| `scripts/` 下有无审计脚本 | 无（`ls scripts` 只有 gen_contracts/guards/entry/迁移探针等 10 项） | V15.1 的"只读化"落成**新建**：一出生就是只读的，而不是把写脚本改窄 |
| `sources` 的唯一约束 | `uq_source_type_external`（`type, external_id`）在位 | A2「同号多源」今天**插不进去** ⇒ 演练期望值 0，且必须给出"0 有来由"的反证用例 |
| `push_tasks.created_by` | NOT NULL + FK → `users.id`，删除规则 `confdeltype='c'`（NO ACTION） | 直接插孤儿行必违反 FK ⇒ 只能**临时绕开 FK 触发器**造形状，且这条只能出现在一次性演练库 |
| `bot_channels.extra_config` | 读侧兼容规则是 `"{" 开头当明文`（`secret_crypto.py:126-141`） | 审计的明文判据必须**同一条规则**，否则审计的 N 与运维看到的 N 不是一回事 |
| 迁移 `ab1005w5b` | 已把存量明文重加密过一次（fail-closed：有存量待迁移而主密钥缺失则中止） | P-39 存量脚本**复用运行时** `encrypt_extra_config/decrypt_extra_config`，不照抄迁移里的 AES 代码（照抄=造第二套口径） |
| 生产只读 DSN | 无（BLOCKING Q-2 至今未给） | S7.1.1/S7.1.2/S7.3.1 三条 👤 全部「未测」 |

## 1. 先红（HEAD 形态：`scripts/audit/` 不存在）

```bash
cd apps/api
python -X utf8 -m pytest tests/test_audit_scripts.py -q
```

```text
ERROR tests/test_audit_scripts.py - FileNotFoundError: [Errno 2] No such file or directory:
... 'D:\\Code\\AideanBotHot\\scripts\\audit\\run_audit.py'
Interrupted: 1 error during collection
```

建造类卡的"改前红"就是**装载不了**：18 条用例一条都跑不成，因为它们钉的判据在 HEAD 上不存在。
演练前后脚本字节用 `md5sum -c` 核回（见 §4 的行尾事故）。

## 2. 实现

### 2.1 `scripts/audit/queries.py`（判据表 + 静态只读门）

- `QUERIES`：A1 裸 token 资产键、A2 同号多源（R-9）、A3 清单 `article_key` 空值、
  A4 短链映射目标仍是裸 token、A5 `push_tasks.created_by` 孤儿行、A6 `extra_config` 明文行、
  A7 前导零 `b:` 键（`split_part(k,':',3) LIKE '0%'`，清单 + 资产两列合计）；
- `PLAINTEXT_SHAPE_SQL` 是 A6 与 P-39 脚本**共用**的同一条判据（`LIKE '{%' AND <> '{}'`）；
- `is_read_only()`：单条、无分号、以 `select|with` 开头、写关键字按**词界**匹配（`created_by`
  不能被判成 `create`，注释里藏的 `drop` 要判出来）。

### 2.2 `scripts/audit/run_audit.py`（只读执行器）

- DSN 只能参数传入，脚本内**没有默认连接串**；
- 每条取数前一句 `SET TRANSACTION READ ONLY`，并回读 `SHOW transaction_read_only`；
  落不回 `on` 就 rc=2 且明说"读数不作数"；
- `--self-test-write-refused`：在同一只读事务里主动试 `CREATE TABLE bothot_audit_write_probe`，
  **必须被拒**；没被拒就抛错拒签所有读数；
- 输出只有 id/名称/计数/只读标志——不含行内容、URL、正文、凭据。

### 2.3 `scripts/audit/p39_reencrypt.py`（P-39 存量，默认 dry-run）

- `--apply` 必须同时给 `--allow-hosts`，且 DSN 的 host 必须在白名单里，否则 rc=2 拒写
  （这是"本脚本不执行于生产"的机械形式）；
- `plan()` 逐行加密后**立刻解密回读**，与原文不一致就整批 `RuntimeError`（一行都不写）；
- 写完复查：A6 计数应归 0，且每行解密回读等于原文；第二次跑时判据选不出行 ⇒ 幂等；
- 日志只报渠道 id 与明文字符数 + 首尾各一个字符，正文一个字不进日志。

### 2.4 零迁移、零契约变更

`alembic heads` 单头 `ab1006c1a`；`gen_contracts --check` 12 项 `幂等一致` rc=0。
A5/A6 都读既有列，演练绕过 FK 触发器只发生在一次性测试库，不改 schema。

## 3. 测试库演练读数

播种（tag `s07drill`，跑完清理）：2 条裸 token 资产、4 条 `article_key IS NULL` 清单、
2 条裸 token 短链映射 + 1 条规范键对照、3 条明文 `extra_config` + 1 条 `'{}'` 对照、
1 条 `created_by` 指向已删用户（绕 FK 触发器造）、2 条 `external_id` 互不相同的源。

单条命令：

```bash
cd apps/api
AIDEANBOT_TEST_PG_DSN=... python -X utf8 -m pytest tests/test_audit_scripts.py -q -rs
```

```text
18 passed in 0.88s
```

审计读数（`test_drill_audit_counts_equal_the_seeded_shape` 断言的是整个字典，不是逐条码尾）：

| id | 读数 | 播种数 | 说明 |
|---|---:|---:|---|
| A1 | 2 | 2 | 裸 token 资产键 |
| A2 | 0 | 0 | **约束使然**：`uq_source_type_external` 在位，同号第二行插不进去（反证用例见 §4 注） |
| A3 | 4 | 4 | `article_key IS NULL` 清单行 |
| A4 | 2 | 2 | 短链映射目标仍是裸 token（对照行的 `s:` 键没被算进来） |
| A5 | 1 | 1 | `created_by` 孤儿行 |
| A6 | 3 | 3 | 明文 `extra_config`（`'{}'` 那条对照未被算进） |
| A7 | 0 | 0 | 实测无此类：播种的 `b:` 键 mid 段都不带前导零 |

每条取数的 `transaction_read_only` 实际值都是 `on`（断言在循环里）。

P-39 三态：
- dry-run：A6 前后都 3，未写库；
- `--apply --allow-hosts 127.0.0.1`：A6 → 0，三行解密回读与原文逐字一致，
  第二次跑判据选不出行且 rc=0（幂等）；
- `--apply --allow-hosts prod-db.internal`：rc=2，A6 仍 3（目标门挡住）。

## 3b. 一次"单跑绿、全量红"：`get_settings` 的 lru_cache

单跑本文件 18 条全绿；放进全量真库套件后变
`2 failed, 2058 passed, 6 skipped`，两条红的原文都是：

```text
E   app.core.errors.DependencyUnavailableError: [50002] PUSH_SECRET_MASTER_KEY 未配置
```

根因不是脚本，是我的用例：`secret_crypto._master_key()` 读的是 `get_settings()`（带 lru_cache），
而我在用例里只 `monkeypatch.setenv`。单跑时我的用例最先建 Settings，所以 env 生效；
全量里早有别的用例把 Settings 缓存住（值是空串），之后再改 env 也读不到。
仓库里同一条坑已被 `tests/test_r11_engine_keys.py:51` 写明（"改 env 后必须 cache_clear 才生效"），
我照同一个修法加 `p39_master` 夹具：`setenv → get_settings.cache_clear() → yield → 再 clear 一次`
（teardown 那次是防我这把密钥带着缓存流给后面的用例）。
修完两向都验过：`test_audit_scripts + test_r11_engine_keys + test_embedding` 任取两个顺序都是
`62 passed`，真库全量复跑回到 `2060 passed / 6 skipped / 0 failed`（§6）。

## 3c. 取 DSN 这件事被一条既有治理门改了写法

第一版演练夹具直接 `from conftest import PG_URL`。跑 `entry.py evidence-check` 时
`EVD-V2-00/prove_dsn_policy.py` 的 **S0.1.2-t** 报红：

```text
FAIL S0.1.2-t 直接 import conftest.PG_URL 的模块已被清点（现恰 1 处） ::
实测 [('test_audit_scripts.py', 42), ('test_audit_scripts.py', 242), ('test_chat_sse.py', 18)]
```

那张账（"DSN 消费者已被清点"）属 STEP-00R 的密封面，不归本卡改 ⇒ 我改自己的取法：
`script_dsn` 夹具从 `db_session` 的引擎上拿 URL。这一改顺带白拿三件好处：

1. DSN 未设置 / PG 连不上时的 skip 由 conftest 自己发，本文件不再自造第二套 skip 文案
   （也就不会去碰 `ci.yml:187` 的 `"PG"+"不可达"` 分类）；
2. 计数回到 `现恰 1 处`，S0.1.2-t 绿；
3. 取绑定时的坑也记一下：conftest 的 `db_session` 是**绑在 Connection 上**的，
   `session.get_bind()` 返回 Connection 而不是 Engine，直接 `.url` 会 `AttributeError`
   （第一版只在 `test_chat_sse.py` 先跑的场合暴露）。现在写成
   `getattr(bind, "engine", bind).url` 两种都吃。

判据不是"我看它顺眼"，是四组顺序都跑过：

```text
tests/test_audit_scripts.py                                   18 passed
tests/test_chat_sse.py tests/test_audit_scripts.py            53 passed, 2 skipped
tests/test_audit_scripts.py tests/test_chat_sse.py            53 passed, 2 skipped
tests/test_r11_engine_keys.py tests/test_embedding.py tests/test_audit_scripts.py   62 passed
```

（第三行是"我先跑"、第二行是"别人先跑"，两向都绿才叫顺序无关；`test_r11_engine_keys.py`
那一组专门用来把 `get_settings` 的 lru_cache 预先污染，配 §3b 的夹具一起验。）

## 4. 反证电池（脚本侧 6 发，字节级读写还原 + `md5sum` 核对）

| 变异 | 读数 |
|---|---|
| S1 明文判据丢掉 `<> '{}'` | `5 failed, 13 passed` |
| S2 A3 极性反转（`IS NULL` → `IS NOT NULL`） | `1 failed, 17 passed` |
| S3 目标门恒放行 | `2 failed, 16 passed` |
| S4 只读静态门恒放行 | `7 failed, 11 passed` |
| S5 取数前不发 `SET TRANSACTION READ ONLY` | `1 failed, 17 passed` |
| S6 `plan()` 去掉逐行回读比对 | `1 failed, 17 passed` |
| 对照组 | `18 passed` |

S5 第一版锚点命中 2 次（`run_query` 与 `write_probe` 里都有那句 `SET TRANSACTION READ ONLY`），
按"锚点必须唯一"的纪律**取消该发**而不是随便挑一处；把锚点扩成两行（含后一句 `observed = str(`）
后补跑成上表。

### 4b. 行尾这件事我量错过一次，记下来

- 电池第一版用文本模式 `read_text/write_text` 还原：Python 在 win32 会把 `\n` 写成 `\r\n`，
  于是 `md5sum -c` 报三个脚本不匹配。当时我用 `grep -c $'\r' 文件` 数 CR 行，得到的数
  **等于文件总行数**——这个写法在本机 Git Bash 里模式没被传进去，grep 退化成"数所有行"，
  读数毫无意义（我差点据此得出"已经转回 LF"的假结论）。
- 换成权威工具后事实是清楚的：`git ls-files --eol` 对四个新文件都报 `i/lf`（**入库位一直是 LF**，
  `.gitattributes` 的 `* text eol=lf` 生效，提交里从没带进 CRLF），而 `w/crlf` 只是工作树被
  文本模式写回后的状态；`tr -cd '\r' | wc -c` 归一后 CR 字节数=0。
- 第二版电池改用 `read_bytes/write_bytes`，"字节级还原 OK"这一列才是它字面的意思。
  教训：**还原核对要么用字节级工具，要么用 `git ls-files --eol` 分清 index 与工作树**，
  别拿一个会静默退化成"数所有行"的命令充数。

## 5. 门禁读数

- `ruff check tests/test_audit_scripts.py scripts/audit` → rc=0（`app tests` 全量也 rc=0）
- `mypy app` → `Success: no issues found in 115 source files`
- `alembic heads` → `ab1006c1a (head)`；`gen_contracts --check` → 12 项 rc=0
- 无 DSN 单文件：`11 passed, 7 skipped`；7 条 skip 由 conftest 的 `db_session` 直接发出
  （理由即 `SKIP_UNSET_REASON`，刻意不含「不可达」，与 `ci.yml:187` 的 PG 静默门分类同源，见 §3c）
  ⇒ `SKIP_BASELINE_WIN` 由 571 抬到**测量值 578**（571 + 7，不留余量）

## 6. 全量读数与三 CI

### 6.1 真库全量（隔离 PG16@5547）

```text
2060 passed, 6 skipped, 1 warning in 909.31s (0:15:09)
REALDB_RC=0        junit: tests=2066 skipped=6 failures=0 errors=0（D:/tmp/s07c_pytest_realdb.xml）
```

总数核对：STEP-05 交付后是 2048（2042+6），本卡 +18 ⇒ 2066 ✅；skip 构成仍是
LangBot/Redis 不可达 5 + 代理对照 1，`pg_unreachable=0`。

（修复前那一轮的读数是 `2 failed, 2058 passed, 6 skipped`，两条红都是 §3b 记的
`get_settings` 缓存问题，不是被测代码的问题——原文已留在 `D:/tmp/s07_full_realdb.txt`。）

### 6.2 CI-Windows 同形状（无 DSN）

```text
1488 passed, 578 skipped, 1 warning in 1037.43s (0:17:17)
WIN_RC=0           junit: tests=2066 skipped=578 failures=0 errors=0（D:/tmp/s07c_pytest_win.xml）
```

passed `+11`（离线判据 11 条）、skipped `571 → 578`（7 条演练用例按
`SKIP_UNSET_REASON` 族 skip）⇒ `SKIP_BASELINE_WIN` 抬到**测量值 578**，不留余量。

### 6.3 三 CI

（待回填）

## 7. 未做的事与如实未测

1. **生产面三条 👤 全部未测**：S7.1.1（生产只读副本跑 `audit_article_keys.sql`）、
   S7.1.2（抽样 20 条 `article_manifests.url` 判 RedFox workUrl 形态、关闭 U-01）、
   S7.3.1（dry-run 报告 → 人签 → 实跑 → 复跑审计）。
   原因只有一个：**生产只读 DSN 没有**（Q-2 BLOCKING 至今未给）。
   按 D-V2-06 已签 A 的停止条件，卡在这一步向用户索取，其余步骤（脚本 + 测试库演练）照做。
2. **原卡 S7.2.1 / S7.2.2 的两个回填脚本未做**（`backfill_article_keys.py`、
   `missing_articles_report.py`）：V0.17 队列⑧只排了 S07.V15.1～3，
   而回填实跑要人签 dry-run（本卡无生产读数可签）。做了脚本也没有能安全跑的地方，
   故留给生产 DSN 到位之后；本卡把**审计面**先做全（A1/A3/A4/A7 正是回填脚本的输入形状）。
3. **演练绕过 FK 触发器**是造 A5 孤儿形状的唯一办法（NO ACTION 的 FK 既不让直接插孤儿、
   也不让删被引用的用户）。手法：`SET session_replication_role = replica` → 删用户 → 改回 DEFAULT，
   只作用于一次性测试库，跑完 `_purge` 清场。生产上这条脚本**只读数，不改数据**。
4. A2/A7 的读数是 0，但两条都不是"查询恒等于 0"：A2 有反证用例（插同号第二行必
   `UniqueViolation`），A7 有播种对照（带前导零的形状我没种，种的就是 0——
   卡面『回填输入清单』第 3 行要求"实测为 0 必须写 0，不要留空"，此处按字面执行）。
5. 付费/外部凭据无关；未发任何真实推送、未连生产库。
6. P-50～P-53 未动；本卡未新增 P 项。
