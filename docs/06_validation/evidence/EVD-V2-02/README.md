# EVD-V2-02 — STEP-02 S2.1.1/S2.1.2/S2.1.3 文章身份解析与委托（本机执行账）

起始基线：`main@b69123f`（STEP-00R 第三轮采纳项入库后）；S2.1.1/S2.1.2 的交付提交是
`78e3378`（其父为 `1470b77`，即 STEP-00R 第四轮处置）；S2.1.3 的交付提交是 `c10b229`
（父 `78e3378`，`git rev-parse --short c10b229^` 可复核）；§4.4/§4.5 的处置批在 `c10b229`
之后的工作区，本文件与 `out_s213.txt` 的sha在提交后由提交说明承接（不在证据里伪造未来 sha）。
> 第二轮复审 F2 指出本行原写「基线 `main@b69123f` → 本包改动」会让人以为工作树直接接在
> `b69123f` 上；`out_run.txt` 头部的 `HEAD=b69123f+工作区未提交改动` 同理，是**采集当时**的
> 事实快照，不是本包的父提交。两处均已改为带父提交的写法。
执行环境：Windows 10 x64 / Python 3.11.9（系统解释器）
依赖实测（`python -c "import X"`，逐一）：**有** pytest 9.1.1、dotenv、anyio；
**无** sqlalchemy、structlog、httpx、pytest-asyncio、coverage；PATH 上**无** `uv`/`ruff`/`make`/`mypy`。
⇒ 卡面验收命令 `uv run pytest --cov=app.services.article_identity --cov-fail-under=100`
在本机不可复现（两个原因：没有 uv，也没有 pytest-cov），本包用 §2 的**三条等价**通道替代，
并把缺口登记在 §5。

> 与 EVD-V2-00R 的一条口径差：本包**不需要** AST 剔除三方 import。
> `article_identity.py` 是纯 stdlib 零 IO 模块，可以真实 import、真实调用。
> 先前文档里「本机没有 pytest」的说法已被第一轮复审推翻（§4 Q-2），此处按实测更正。

## 1. 本卡闭合了什么

| 原子任务 | 状态 | 本机证据 |
|---|---|---|
| S2.1.1 先红用例（`test_article_identity.py`，14 条） | ✅ 真实执行 + 改前红可重放 | §2 两条通道 + §3 `block_article_identity_plugin.py` |
| S2.1.2 实现（`article_identity.py`：`WechatUrlParts` + `parse_wechat_url`） | ✅ 真实加载、语句覆盖 27/27=100% | §2 |
| S2.1.3 `kb._biz_from_url` 委托 | ✅ 改前红可重放 + 改后 11 判据全绿 + 三条反证通道 | §2 通道 C（`prove_biz_delegation.py`）、`out_s213.txt` A–E |
| S2.1.4 删 LIKE 兜底 / S2.1.5 片段长度守卫 | ⏳ 未做 | — |
| S2.2 规范键 | ⛔ 阻塞于 ADR-0011 / D-V2-01（人拍板） | — |

## 2. 三条真实执行通道（都能在别人机器上一条命令复现）

**通道 A — 真实 pytest**（本机有 pytest，只是没有连库依赖）：

```bash
cd apps/api && PYTHONPATH=. python -m pytest tests/test_article_identity.py -q --noconftest -p no:cacheprovider
# → 14 passed, 1 warning in 0.08s
```

`--noconftest` 的理由要写清：默认收集会加载 `apps/api/tests/conftest.py`，它在模块级
`import sqlalchemy`（本机无此包）⇒ 收集失败与业务无关。本用例文件**不消费任何 conftest 夹具**，
所以绕开它是等价的；warning 是 `asyncio_mode` 未知配置项（无 pytest-asyncio），无害。

**通道 B — 纯 stdlib 证明**（`prove_article_identity.py`，另给三条反证通道）：

```bash
PYTHONIOENCODING=utf-8 python docs/06_validation/evidence/EVD-V2-02/prove_article_identity.py
# → 合计 PASS=12 FAIL=0（PI-1..PI-12），用例明细 14 passed / 0 failed，PI-11 覆盖 27/27=100.0%

PYTHONIOENCODING=utf-8 python docs/06_validation/evidence/EVD-V2-02/prove_article_identity.py --self-test
# → SELF-TEST PASS：12 个实现变异体各自让指定用例变红 + 17 个判据样本对敏感 + 4 个等价重构不假红
```

两个数字都由 `len(MUTANTS)`/`len(_JUDGES)+1`/`len(EQUIV_REFACTORINGS)` 动态打印。
`PYTHONIOENCODING=utf-8` 是必需项而非美化：win32 控制台默认 cp936，脚本要打印 `⇒` 与中文
（同类先例见 `EVD-V2-00R/README.md` §3.4 的 F-19 更正）。

判据面（PI-*）分三类，逐条在脚本 docstring 与 `--self-test` 输出里可对：
- **契约面** PI-1/PI-2/PI-3/PI-4/PI-5/PI-6：只依赖白名单标准库、零 IO（含 `s.execute` 换名与
  `__import__`/`eval` 动态逃逸两种绕行）、无 global/属性写、字段序与卡面一致、值对象冻结、
  `idx` 缺省为 `'1'`；
- **口径面** PI-7/PI-8/PI-9/PI-12：卡面 S2.1.1 的 7 条交付 + 本步补充的 7 条，逐一映射到真实
  用例名（删任一用例名判据即转假）；用例不 import pytest；夹具经 PEP 420 真实解析；
  **每条用例体内都有 assert/raise**（防空壳）；
- **执行面** PI-10/PI-11：真实调用 14 个用例函数、真实语句覆盖 100%。

**通道 C — S2.1.3 委托的机器证明**（`prove_biz_delegation.py`，BD-1…BD-11）。
为什么这条通道必须另建：`kb.py:22-25` 在模块级 import `structlog` 与 `sqlalchemy`，本机两者
皆无（实测收集期 `ModuleNotFoundError: No module named 'structlog'`，见 `out_s213.txt` D 段）
⇒ `tests/test_kb_longlink_ingest.py` 在本机**跑不了**，不是没写。替代机制是 EVD-V2-00 已确立的
AST 切片：从磁盘上的 `kb.py` 里取出 `_biz_from_url` 这**一个**函数节点单独 `compile`+`exec`
（函数体里全是局部导入，不需要执行整个模块），被执行的是文件当前代码。

```bash
PYTHONIOENCODING=utf-8 python docs/06_validation/evidence/EVD-V2-02/prove_biz_delegation.py
# → 合计 PASS=13 FAIL=0（改前同一命令：PASS=3 FAIL=10，rc=1；红态由 OLD_BODY 回写临时副本重放，
#    不 mv、不改工作树，命令与输出都在 out_s213.txt A 段）

PYTHONIOENCODING=utf-8 python docs/06_validation/evidence/EVD-V2-02/prove_biz_delegation.py --self-test
# → 首行「OK 档位自证：绿 rc=0 / 目标缺失 rc=2（INCONCLUSIVE） / 有判据红 rc=1 三档分得开」
# → 次行「OK 退出码自证：子进程真实退出码三档分得开（绿 0 / 目标缺失 2 / 有判据红 1）」
# → SELF-TEST PASS：10 个函数体变异各自让指定判据变红 + 10 个判据样本对敏感 + 7 个等价写法不假红
```

**三档退出码**（第二轮复审 B3/B4：目标函数被整个删掉时，原先也打印一份 FAIL 清单、rc=1，
读者会把它当成普通的红基线——「没测到」冒充「测出红」）。现在 `0` 全绿 / `1` 有判据红 /
`2` INCONCLUSIVE（`_biz_from_url` 不存在，判据无从判定），且 self-test 第一道闸门用
内存里删掉该函数的副本（`_strip_target`，不动工作树）**实测**三档互不相同。
第五轮复审 id 5 追加一条坦白并把它补上：只测 `run()` 的返回值等于没测到 `sys.exit` 那一步，
所以第二道闸门把三种源码形态各写成临时目录里的 `kb.py` 副本，用 `--kb=<路径>` 起**真实子进程**
读回退出码——工作树仍然一个字节没动。

判据分四面：行为面 BD-1…BD-6（长链出号主、与解析侧在**差分语料**上恒等、伪 `biz=` 不退化、
`%3D%3D` 同值、脏类型统一归零）、结构面 BD-7…BD-9（真有调用且调用名没被本地重新绑定、委托源必须是
`app.services.article_identity`、kb 侧不留第二份解析）、反面 BD-10/BD-11（不许 `except` 兜底伪造身份、
不许残留参数字面量做半委托）、反面 BD-12/BD-13（函数体**形状**白名单 + 顶层同名定义只能有一个）。
一条实测副产品值得记住：**半委托**（委托但空串时回退本地再解析一次）在行为面几乎看不出问题，
却同时让 BD-9/BD-11 转红、并把 BD-6 的 int 抛错路径**带回来**——这正是「只测行为」抓不到的形态。
反证通道自身也修过两处：多行变异体原先用**不含缩进**的锚，替换后首行变 8 空格、根本解析不了，
于是结构判据以 `IndentationError` 冒充「致红」；已加 `_parses()` 闸门单独立判 FAIL（复审 D 类）。
第二轮复审 3c 指出该闸门原先**只盖住 MUTANTS/EQUIVS 两条通道**，PROBES 直接把样本喂给判定函数，
坏样本自己解析不了时抛的是未捕获的 SyntaxError——同一个失效模式在第三条通道里还活着；
现三条通道都过闸门。

**BD-7 认别名**（第二轮复审 3e）：判定原先只认裸名 `parse_wechat_url` 与 `模块.parse_wechat_url`，
于是 `from … import parse_wechat_url as pw` / `p = parse_wechat_url; p(url)` 这两种**行为完全正确**的
重构被判成缺陷——正是「假红门禁被人当噪音关掉」的失效形态。现由 `_delegate_aliases()` 只认
三条绑定途径（`from 委托源 import … as A`、`A = 委托名`、`B = A` 传递到不动点），
同时补一条坏样本「别名链造假：改名导入没被调用，调的是本地假函数」证明放开后判据仍不可空过，
并把那两种写法钉成 EQUIVS（`EQUIVS` 3→5 即由此而来）。

**BD-12 形状白名单 + BD-13 唯一定义**（第五轮复审 id 3 / id 10，两条都在本机复现成功）：
「认别名」只做了**正面**证据——收集过哪些名字可能绑到委托目标，却没检查这些名字之后有没有被
**别的东西再绑一次**。于是三发攻击全部空过（本机实测 rc=0、判据全绿）：
① `from … import parse_wechat_url as pw` 后紧跟本地 `def pw(u)`，调用点拿到的是假函数；
② 真导入之后 `parse_wechat_url = _ext` 重绑到手搓解析器；
③ 文件里追加第二份 `def _biz_from_url(url): return ''`——Python 按模块作用域**后定义覆盖前定义**，
而 `get_fn_node()` 取的是 `ast.walk` 遇到的**第一个**，等于在证明一段死代码。
闭合方式不是把 BD-7 越收越窄，而是补负面证据：BD-12 要求函数体只允许
「文档串 / 委托导入 / 委托绑定 / 返回委托结果的 `.biz`」，白名单之外多一个节点就红
（嵌套 `def`/`class`、控制流、三元与布尔表达式、别的调用点、别的属性、**任何字符串字面量**——
最后这条正是为了堵 `"bi" + "z"` 那种拆开字面量绕 BD-11 的写法）；BD-13 判顶层同名定义计数，
`_top_defs()`/`get_fn_node()` 一并改成**只看顶层、取末位**。
`_shadowed()` 同时把 ①② 两类遮蔽从 BD-7 的可用别名表里剔掉，所以这三发现在是三条判据同时红
（外加差分语料那条行为面），不是靠单点。`PROBES` 6→10、`EQUIVS` 5→7 的增量即由此而来
——新增的两条 EQUIVS（`biz = parse_wechat_url(url).biz; return biz`、
`from app.services import article_identity as ai`）专门盯住白名单最可能的失效模式：**假红**。
同轮还补了一条通道自守：变异体若**在调用期**抛异常（例如导入一个不存在的模块），
原先 `evaluate()` 会带着 traceback 一起崩——通道崩掉不等于判红，self-test 也就给不出结论。
现在行为面每次调用都过 `_biz()` 兜底，把「抛异常」记成该判据红，并钉成一条 MUTANT
（`调用期抛异常…` → 红 BD-1…BD-6 与 BD-12，self-test 不再崩）。

**BD-3 差分语料**（同轮 id 3 的第二层）：恒等判定的样本从夹具 6 条扩到 26 条（新增 20 条对抗形态，
每条对应解析层一条已定或待定口径：`__biz` 优先、空值回落 `biz`、重复参数取首个、键名也被百分号解码
（`%5F%5Fbiz`）、参数名大小写、无值参数、分号不是分隔符、片段与查询的边界、host 无关、
短链路径带 query、值里带编码分隔符）。期望值一律取 `parse_wechat_url(u).biz` 本身，
所以这条判的是「两侧口径是否同一个」，不给解析层自己对错下结论（那是 S2.1.2 的 14 条用例）。
手搓解析器就算骗过白名单，也得先在 20 条形态上逐一对齐才有机会空过。

**用例侧的第二条锚**（第二轮复审 id 2）：`test_delegation_is_the_single_source_of_truth`
原先只写「kb 侧 == 解析侧」，这是同义反复——委托实现下它天然成立，且 `OFFSITE`/`SHORT_1`
两侧都是空串。现每条参数化用例另带一个字面期望（五个值取自磁盘 kb.py 的真实执行，非推断），
两条锚各自的判定力本机实测过（命令见 `out_s213.txt` F 段）：把 kb 侧单独换成恒返回 `""`
⇒ 恒等式与字面锚同时红 3 条；把两侧**共同**换成恒返回 `""`（模拟解析层退化）⇒ 恒等式 5 条全绿
（空过），字面锚仍红 3 条。所以两条锚缺一不可：恒等式抓分叉，字面值抓共同退化。

## 3. 「改前红」现在是可重放的，不再只是推断

卡面 S2.1.1 第 1 步要求「只写测试，模块不存在 ⇒ ImportError 即红」。那个状态当时是**瞬时的**，
第一轮复审 Q-4 判我为「可复现的推断、无运行留档」。现补 `block_article_identity_plugin.py`：
一个只拦 `app.services.article_identity` 这一个模块名的 `sys.meta_path` finder，
等价于「该文件还不存在」，且**不删、不 mv、不改工作树**。

```bash
# 红（实现被拦）。第二轮复审 A2：原先只给 POSIX 的 ':' 分隔形式，在本机（Git Bash，
# os.pathsep=';'）跑出来是 `ImportError: Error importing plugin ... No module named
# 'block_article_identity_plugin'`、rc=1——那是「插件没找到」的假红，不是「模块被拦」的真红。
# 下面两条都是**本机实跑**（同一仓库根、同一解释器）：
PYTHONPATH="apps/api;docs/06_validation/evidence/EVD-V2-02" \
  python -m pytest apps/api/tests/test_article_identity.py -q --noconftest \
  -p block_article_identity_plugin -p no:cacheprovider
# → rc=2，Interrupted: 1 error during collection，
#   raise ModuleNotFoundError("BLOCKED for S2.1.1 red-check: app.services.article_identity")   ← 真红
PYTHONPATH="apps/api:docs/06_validation/evidence/EVD-V2-02" \
  python -m pytest apps/api/tests/test_article_identity.py -q --noconftest \
  -p block_article_identity_plugin -p no:cacheprovider
# → rc=1，ImportError: Error importing plugin "block_article_identity_plugin"                    ← 假红，勿用
# （Linux/CI 上应反过来用 ':'；分隔符跟 os.pathsep 走，不是脚本能自证的。）

# 绿（同一份用例，去掉 -p）
cd apps/api && PYTHONPATH=. python -m pytest tests/test_article_identity.py -q --noconftest
# → 14 passed
```

`-p` 的加载还有一条隐性前提：插件模块必须真的在 `sys.path` 上，且 `PYTHONPATH` 的相对条目
是**相对当前工作目录**解析的（本机曾先在 `apps/api` 下跑，结果插件根本找不到）⇒ 两条命令都要
从仓库根执行。原始输出（含 rc=2 与 traceback）在 `out_run.txt` A1 段。

## 4. 第一轮独立复审的处置（采纳 / 反驳分开记）

复审由独立子智能体完成，输出 28 项。纪律与前几轮一致：**每条先在我机器上复现，复现出来才改**。

### 4.1 成立并已修

| id | 发现 | 复现 | 落点 |
|---|---|---|---|
| Q-2 | harness 声称「本机没有 pytest」是错的 | `python -c "import pytest"` → OK 9.1.1 | harness 与用例 docstring 改为实测口径（有 pytest、无 sqlalchemy/httpx/coverage），并补通道 A |
| Q-13 | 非 str 入参：`bytes` 得到 **bytes 型 host**（`b'' != ''` ⇒ 下游比较静默判错），`Path`/`int` 抛 AttributeError | `P(None)`/`P(b"...")`/`P(PurePosixPath(...))` | 实现加 `isinstance(url, str)` 守卫归零返回；新增用例 + 变异体「守卫被删」证明其可红 |
| Q-14 | 类 docstring「非微信输入各字段为空串（host 除外）」是**虚假不变式**（`idx` 恒为 `'1'`，外链带微信参数时 biz/mid/sn 全非空） | `P("")` → `idx='1'`；Q-8 反例 | docstring 改为三句话的真实口径（host 原样、解析与 host 解耦、idx 例外） |
| Q-10 | 裸 `+` 被 `parse_qs` 按表单口径还原成空格 ⇒ 同一 base64 `__biz` 的两种书写解出不同值，**一篇文章裂成两条资产** | `P("__biz=MjM5+abc")` → `'MjM5 abc'`，`%2B` → `'MjM5+abc'` | 解析前 `query.replace("+", "%2B")`；新增用例「两种书写解出同一 biz」+ 变异体「退回表单口径」 |
| Q-26 | 用例文件 import 段序违反仓库约定（`app.*` 排在 `fixtures.*` 前），CI `ruff check app tests` 的 I001 预期红 | `g24_static_check.py` 报 I001；对照 `test_alerting_drill.py:14-18` 的真实顺序 | 改为 stdlib → 第三方（`fixtures`）→ 本地（`app`）三段；本机无 ruff，终判仍是推断，故把它列进 §5 交接头目 |
| Q-17 | PI-10 空洞：把 11 条用例体全掏空后 PI-7/PI-10 仍全绿 | 内存内 AST 掏空后复跑 → `11 passed` | 新增 **PI-12**「每条用例体内都含 assert/raise」+ 坏样本「`def test_a(): return None`」证明能红 |
| Q-19 | `j_zero_io` 可被 `__import__("os").popen(...)` 绕过（既无 `import os` 也无 `os.` 前缀） | 三例构造注入，PI-1/PI-2 原形全绿 | 新增 `DYNAMIC_NAMES = {__import__, eval, exec, compile}` 分支 + 两条坏样本 |
| Q-20 | PI-6 过度约束实现形状：把 `_DEFAULT_IDX` 内联成 `or "1"` 这种等价写法会被判红 | 变异「常量在但行为用 `"2"`」→ PI-6 仍真；内联 → PI-6 假 | PI-6 改为「常量形态或内联形态都接受、只拒绝缺省不是 `'1'`」，并新增**第三条反证通道** `EQUIV_REFACTORINGS`（四条，含此例） |
| Q-21 | PI-9 判的是「夹具常量数 ≥9」，删掉一个未被本文件引用的常量照样绿；且「9/10」在三处文档口径不一 | `len(fixtures.wechat_urls.__all__)` → 10，用例 import 9 个 | 改为「用例 import 的每个名字都真实存在」+ 坏样本「引用不存在的名字」；不再对夹具数量设下界 |
| Q-25 | 证据包缺 README、卡面复选框未回写 | `ls EVD-V2-02` 只有脚本 | 本文件 + 卡面 S2.1.1/S2.1.2 复选框与执行记录 |
| Q-24 | 工作树出现非本卡的未跟踪文件 `_workspace/round4_probe.py` | `git status` | 已清除（该脚本的结论已固化进 `EVD-V2-00R` 的 MUTANTS/EQUIV 通道，见 EVD-V2-00R §9） |

### 4.2 复现成立但本步不修（登记为待定项，附理由）

| id | 复审意见 | 我的处置 |
|---|---|---|
| Q-7/Q-8 | `host` 用 netloc（含端口/userinfo），且**非微信域名带 `__biz` 也会被解出**，是碰撞面 | 不擅自加 host 闸门。理由：改前 `kb._biz_from_url` 的行为同样与 host 无关，S2.1.3 委托后加闸门会让**所有非微信源**解析出的 biz 变空串——影响面超出本卡，属 S2.2/ADR-0011 的口径决策。做法是把它**钉成用例**：`test_wechat_params_on_foreign_host_are_still_parsed` 锁现状，另加变异体「擅自加 host 闸门 → 该用例红」，将来定案要改口径必须显式动这条用例。**S2.1.3 落地后此项性质升级**：委托使 kb 侧 100% 继承该口径，`out_s213.txt` B 段 BD-3 的六个样本里就含 `OFFSITE` 与短链伪 `biz=`——即「外链带 `__biz` 也会拿到号主锚」现在是 kb 的行为，不再只是解析层的行为（第二轮复审 B4 另给出微信域名带端口/userinfo 时短链 token 静默归零的对照面）。 |
| Q-6 | `/s/TOK?__biz=…` 时 biz 与 short_token **同时非空** | 本步不选边（卡面未规定）。登记进 S2.2 待定项：规范键必须声明优先级，否则短链与长链两种书写会生成两把键 |
| Q-9 | `idx=0` 保留、`idx=`（空）落到 `'1'`、`idx=%20` 解成空格 | 与卡面「省略 idx ⇒ `'1'`」一致的部分保留；`%20` 这类怪值属**未实测口径**，登记为需真实样本核对项（见 §5） |
| Q-12 | 无 scheme、空串、`//host` 形态、大写 `/S/` 路径 | 空串/垃圾已由 isinstance + urlparse 归零；第二轮复审 F4 指出「有测试」这句对 `""`/无 scheme/`//host` **不成立**（用例文件里查不到这三条，只有 `/S/` 与 IDN 在 B6 组被旁证过）⇒ 更正为「未覆盖，登记待补」，`/S/` 大写路径丢 token 仍是**未定口径**（微信真实短链只有 `/s/`） |
| Q-5/Q-11 | `__biz`/`biz` 重复出现取首个；参数名大小写敏感（`__BIZ=` 失效） | 与既有 `_biz_from_url` 同为 `parse_qs` 口径，改动会牵动非微信源。S2.1.3 未择边（只换委托、不动口径），继续登记待 S2.2 定 |
| Q-27 | 证明脚本有 2 行超 120 列 | 不阻断：CI 只 `ruff check app tests`，`docs/**` 不在 lint 面；文件内已带 `# ruff: noqa: E501`，且 `EVD-V2-00R/` 有 8 行超长前例 |
| Q-15/Q-16/Q-18/Q-22/Q-23/Q-28 | 覆盖分母独立复核（25 行、两口径均 100%、区间放宽一次未用）、分支弧覆盖、判据无永真、范围纪律、无 STEP-01 契约越界、G 组锚点逐字核对 | 复审**判 PASS**，无需动作。其中 Q-22 明确：该时点 `kb.py`/`asset.py` 未被提前改动——这是**第一轮时点**的事实，S2.1.3 落地后 `kb.py` 已按卡面改动（范围见 §6），`asset.py` 仍未动 |

### 4.3 复审自身的一处证据落空

Q-10 引用的知识文档路径 `docs/08_knowledge/RSS分析/output_claude.md:212` 在本仓库**不存在**
（`ls docs/08_knowledge/` → 只有 meetings / retrospectives / technical-notes）。
`+` 的问题本身我复现成立、已按 §4.1 修；但这条「旁证」不采信，也不写进任何结论。
（同类事件见 `EVD-V2-00R/README.md` §8.2——复审是信号源，不是权威。）

### 4.4 S2.1.3（`c10b229`）复审处置——本轮两份报告合并记账

S2.1.3 交付后收到**两份**独立验证报告，编号体系不同：一份按 A–G 分组（下文 id 记作「A–G 报告」），
一份按表格行 1a–6 + Top-priorities 序号（下文 id 记作「1a–6 报告」）。纪律不变：**每条先在本机复现，
复现出来才改**。1a–6 报告的裁决表共 **23 行：19 行 PASS、4 行 DEFECT**——逐行为
`id 2`（用例同义反复）、`3c`（`_parses` 闸门漏盖 PROBES）、`3e`（BD-7 假红）、`3f`（采样上限，
复审自判「按设计、文档已界定范围」）；PASS 的 19 行含 A 段红态重放、B/C 段数字、D 段 rc 归属、
E 段卡面命令、`78e3378` 副本逐字节一致、范围与禁改路径。成立并已修的三项（加 A–G 报告的 B3/B4 共四项）：

| id（出处） | 复审意见 | 复现 | 落点 |
|---|---|---|---|
| 3e（1a–6） | BD-7 假红：`from … import parse_wechat_url as pw` 与 `p = parse_wechat_url; p(url)` 两种**行为完全正确**的重构被判成缺陷 | 按复审给的构造改 `NEW_BODY` → `evaluate()` 返回 `['BD-7']` | `_delegate_aliases()` 认三条绑定途径；两种写法钉成 `EQUIVS`（3→5）；另加坏样本「别名链造假」（`PROBES` 5→6）证明放开后仍不可空过 |
| 3c（1a–6） | `_parses()` 闸门只盖住 MUTANTS/EQUIVS，PROBES 直接把样本喂判定函数 ⇒ 坏样本自己解析不了时抛未捕获 SyntaxError 冒充「判到假」 | 造一条缩进错的坏样本 → `self_test` 崩在 SyntaxError | 三条通道都过闸门，解析不了的样本单列 FAIL「样本无法解析」 |
| B3/B4（A–G） | `_biz_from_url` 被整个删掉时仍打印一份 FAIL 清单、rc=1 ⇒「没测到」冒充「测出红」，与红基线无法区分 | 内存里删掉函数后跑 `main()` → rc=1 | 三档退出码 `0/1/2`，`2`=INCONCLUSIVE；`self_test` 首道闸门用 `_strip_target()` **实测**三档互不相同（C 段首行） |
| id 2（1a–6） | `test_delegation_is_the_single_source_of_truth` 是同义反复，且 `OFFSITE`/`SHORT_1` 两侧都是空串 ⇒ 对该二例即使 kb 恒返回 `""` 也绿 | 参数化逐个驱动：`""` 侧 `"" == ""` 成立 | 每条参数化另带一个字面期望（五个值取自磁盘 kb.py 真实执行）；两条锚的分工实测在 F 段（F-3 都红 3 条；F-4 共同退化时恒等式 0 红、字面锚仍红 3 条） |

复现不成立（两项）与「成立但无需动作」（一项）：

| id（出处） | 复审意见 | 我的处置 |
|---|---|---|
| A5（A–G） | 旧实现对 bytes 抛 `ValueError` | 不采信：`parse_qs(urlparse(b"...").query)` → `{b'__biz': [b'AAA']}`，旧实现对 bytes 返回 `''`；复审把 `parse_qs` 直接喂了整条 URL。BD-6 的措辞（「None 与 bytes 静默空串，只有 int 抛」）维持 |
| D 类（A–G） | 「先委托、空串时再本地覆写」的形态 11 条判据全绿 | 不采信：实测该形态红 `BD-9`/`BD-11`（并带回 BD-6 的 int 抛错路径）——这正是「半委托」那条变异体的内容 |
| 3f（1a–6） | 采样上限：只喂 6–7 个 URL，中转里藏特殊分支可绕过行为面 | 复审自己判为「按设计、文档已界定范围」，不动作；BD 面是**接线与口径**门禁，不是全域等价性证明（§7 已写明通道 C 不能证明什么） |

### 4.5 本轮自查（未等复审，本机 `g24_static_check.py`）

| 文件 | 规则 | 复现 | 处置 |
|---|---|---|---|
| `tests/test_kb_longlink_ingest.py` | I001 import 段序 | g24 报「`from fixtures.wechat_urls` 应排在 `app.services.kb` 之前」 | 按仓库真实段序（stdlib → 第三方 `fixtures` → 本地 `app`，锚 `tests/test_article_identity.py:34` 与 `:46`）重排，`out_s213.txt` G 段复跑 0 违规。**教训**：第一轮复审 Q-26 修的正是同一条 I001，新文件又犯一次 ⇒ §5 J-2（CI `ruff check app tests`）不是可选项，本机静态自检只能降险、不能定判 |
| `prove_biz_delegation.py` | F401 死导入 | `git show c10b229:… \| grep -c ModuleType` → 1（只在 import 行出现，全文件未使用） | 删除该行；G 段复跑 0 违规 |
| `prove_article_identity.py:520` | E501（141 > 120 列） | g24 报出 | **不修**：`docs/**` 不在 CI lint 面（CI 只 `ruff check app tests`），且该文件 `:37` 已有 `# ruff: noqa: E501`——g24 不解析 noqa 所以仍报。前例见 §4.1 Q-27 |
| `prove_biz_delegation.py:363`（第五轮处置批新增的 `ok_val` 表达式） | E501（121 > 120 列） | `g24_static_check.py` 在本轮 G 段**先报出**（`合计违规 1 条`、rc=1），我没有放过 | 把三段 `or` 折成 `_bind_value_ok()` 辅助函数；G 段复跑 `合计违规 0 条`（`out_s213.txt` 现行 G 段就是修后的）。这条正是上一条教训的复发生效：本机 g24 报了就要当场处理，别指望「反正 CI 不看 docs」 |

## 4.6 第五轮复审（对处置批 `b45777a`）——三条空过的复现与闭合

复审报告给的是 10 行裁决表 + 5 条优先级，其中 **2 行 DEFECT**（`id 3`、`id 10`）。
两条都在本机复现成功（复现脚本的攻击体后来固化成 harness 里的 `_HANDROLLED`/`MUTANTS`，
不再依赖一次性脚本），另有 1 条我按复审给的构造补强：

| id（出处） | 复审意见 | 本机复现（改前） | 落点（改后，均可复跑） |
|---|---|---|---|
| 3a2（1a–6） | `import parse_wechat_url as pw` + 本地 `def pw(u)` 遮蔽别名 ⇒ 调的是假函数，判据全绿 | `evaluate()` 返回空集、`run()` rc=0（11 条判据全绿）| `_shadowed()` 把被重新绑定的名字剔出可用别名 ⇒ BD-7 红；BD-12 形状白名单 ⇒ 红；BD-3 差分语料 ⇒ 红（`out_s213.txt` H-1） |
| 3c（1a–6） | 真导入后 `parse_wechat_url = 手搓解析器` 重绑 ⇒ 正面判据仍看得见那次导入与那次调用 | 同上，rc=0 | 同上（H-2）；重绑的右值不在白名单的三种绑定里，直接红 |
| 10（1a–6） | 追加同名顶层定义时 `get_fn_node` 取**第一个**，而 Python 取**最后一个** ⇒ 证明的是死代码 | `dup = src + "def _biz_from_url…return ''"` → 判据全绿 rc=0，且 `get_fn_node` 落在 587 行（真实绑定在 598 行）| `_top_defs()` 只看顶层、`get_fn_node` 取末位；新增 BD-13 判计数（H-3 追加式红 BD-13+行为面，H-4 前置式**只**红 BD-13 ⇒ 该判据不冗余）；`--self-test` 里两向各一条 MUTANT |
| 5（1a–6） | rc=2 那档只在 `run()` 返回值层面证过，`sys.exit` 到进程退出码那一步没跑 | 复现成立（脚本里无从构造，属实） | 新增 `--kb=<路径>`，第二道闸门用临时副本起真实子进程读回退出码，三档实测 `0/2/1`（C 段次行）；工作树未动 |
| 4（1a–6） | docstring 里「其余一律不认，否则『随便调个函数』也算委托」「证明放开后判据仍不可空过」被 3/10 推翻 | 复现成立（文案过强） | 措辞改为「只认三条绑定途径，**且被本地重新绑定过的名字一律剔除**」，并把「不可空过」的证据从 1 条坏样本升到 3 条（`PROBES` 6→9）+ BD-12/BD-13 两条负面判据 |
| 3-LEGIT（1a–6） | BD-8 是集合归属：一次**未被使用**的正确导入就能满足它 | 复现成立（`article_identity` 与 `kb_legacy` 双导入、后者遮蔽同名）：BD-8 仍判真，但 BD-7 因遮蔽剔除转红、BD-12 因调用点不再算委托调用而红（两种导入顺序都测，均红） | 不收紧 BD-8（它的职责是「委托源对不对」，收紧会与 BD-7 重叠成同一条判据的两份表述）；该形态钉成 `PROBES` 的一条判据级坏样本（判据不 exec，所以不必真有一个 `kb_legacy` 模块） |

复审里**不采信**的一条：`id 5` 中「23 行=19+4 的普查不可从本仓库独立核验」——那是对**上一轮报告**
的计数，出处已在 §4.4 标明（报告本身是外部输入，不是仓库产物），无需动作。
`id 9` 的「卡文件不在允许修改清单内」属自我申报，§6 与卡面 D-05/D-07 已登记，非隐藏越界。

## 5. 交人工 / 有依赖环境的项目

| # | 项 | 为什么本机不能做 | 命令 |
|---|---|---|---|
| J-1 | 卡面原验收命令（带覆盖率门禁） | 无 `uv`、无 `pytest-cov` | `cd apps/api && uv run pytest tests/test_article_identity.py -q --cov=app.services.article_identity --cov-fail-under=100` |
| J-2 | ruff I001 终判 | 无 `ruff`（本机只有 `g24_static_check.py` 的等价静态检查报 I001） | `cd apps/api && uv run ruff check app tests` |
| J-3 | `idx=%20`、参数名大小写、`/S/` 大写路径三条口径 | 需微信真实抓取样本，本机不抓取（不启服务） | 对现有 `Source.url` 样本跑 `parse_wechat_url` 分布，交 STEP-06/07 |
| J-4 | 全量连库回归（S2.3） | 需隔离 PG16@5547 | 见 STEP-00R §4 H-2 的 `test-env.sh env` 链 |
| J-5 | `tests/test_kb_longlink_ingest.py` 的 pytest 实跑（S2.1.3 的用例面） | `kb.py:22-25` 模块级 import structlog+sqlalchemy，本机收集期即失败（实测 `out_s213.txt` D 段）；本机侧只由通道 C 承担 | `cd apps/api && uv run pytest tests/test_kb_longlink_ingest.py tests/test_article_identity.py -q -k biz` |

## 6. 范围与偏离声明

- 本包交付 **S2.1.1 + S2.1.2 + S2.1.3**；S2.1.4/S2.1.5 未做（`asset.py` 零改动，
  复审 G 段独立确认）。S2.1.3 对 `kb.py` 的改动**只有一个 hunk**：
  `git diff 78e3378 -- apps/api/app/services/kb.py` → `3 insertions(+), 5 deletions(-)`，
  且都在 `_biz_from_url` 函数体内（`kb.py:587-591`）；`_find_source_by_anchor`（`kb.py:343`）
  的调用点、`_article_key`、LIKE 兜底一律未动，分属 S2.1.4/S2.1.5。
  两点读数口径要注意：①「一个 hunk」是**默认上下文**下的 `git diff`，加 `-U0` 会因
  docstring/导入块与 return 行之间的空行而拆成 2 个 hunk；②`grep -c '^-'` 数出来是 6，
  因为把 `--- a/…` 文件头也算进去了——以 numstat 的 `3/5` 为准。
- **两轮处置批（§4.4/§4.5 的第二轮、§4.6 的第五轮）都没有再动 `kb.py`**：
  `git diff c10b229 -- apps/api/app/services/kb.py` 为空（本轮复跑确认）。
  改动面只有 `prove_biz_delegation.py`（判据、档位、通道自守）、`test_kb_longlink_ingest.py`
  （用例的第二条锚 + import 段序，第二轮改）、本 README 与 `out_s213.txt`
  （重新整份生成，A–H 八段；H 段就是第五轮三条空过的闭合实测）。
  harness 新增的 `--kb=<路径>` 只服务于 self-test 的子进程退出码自证，
  **默认路径仍是 `apps/api/app/services/kb.py`**，验收命令不变。
- 新增文件都在卡面「允许修改」或「证据路径」内：`tests/test_kb_longlink_ingest.py` 是卡面
  允许路径；`prove_biz_delegation.py`、`out_s213.txt`、`block_article_identity_plugin.py` 与本
  README 落在证据路径 `docs/06_validation/evidence/EVD-V2-02/`。
- 实现里两处**超出卡面字面**的口径（`+` 按字面加号、非 str 归零）与本包补充的 7 条用例，
  已同步登记到卡面执行记录 D 项；不同意者可单独 revert，通道 A 的用例随之回到 7 条。
  S2.1.3 委托后这两条口径**自动生效于 kb 侧**（委托即继承解析口径），见卡面 D-06。

## 7. 反自证声明

- 本文每个 ✅ 都可由 §2/§3 的命令复现；pytest 与 stdlib runner 跑的是**磁盘上的同一份代码**。
- 「14 passed」不含任何连库用例；通道 A/B 从未执行 kb/asset 侧代码。S2.1.3 之后
  `app/services/kb.py` 的 `_biz_from_url` **已被改动**（这是本步的交付物本身，原文「没有改
  `kb.py`」的声明随之作废，改由上一条的 diff 命令界定范围）；`kb.py` 其余部分与 `asset.py` 未动。
- 通道 C 的 exec 只覆盖 `_biz_from_url` 一个函数节点：**它不能证明 kb 的入库链路正确**
  （那需要 J-5 与 J-4），只能证明「这个函数当前确实委托了解析层、且解析口径单点」。
- 覆盖率是**语句覆盖**（`sys.settrace`），不是分支覆盖——复审 Q-16 另用自写弧采集核对了唯一
  那条 If 的两条弧，但那不是本脚本的门禁项，别把它读成「分支覆盖 100%」。
- 三条反证通道各自的方向：变异体证明「改坏会红」，样本对证明「判据能假」，等价重构证明
  「换写法不假红」。缺任意一条，另两条的结论都不完全可信。
- 读 `out_s213.txt` 的 rc 要分档：`0` 全绿 / `1` 有判据红（真红基线）/ `2` **INCONCLUSIVE**
  （目标函数不在文件里，判据压根没跑）。把 2 当成 1 读，就是把「没测到」读成「测出红」。
  本轮起这一映射**测了两层**：`run()` 返回值 + 临时副本子进程的真实退出码（C 段次行）。
- BD-9 的名字名单（`parse_qs`/`urlparse`/`urllib`）是**必要不充分**条件：第五轮复审用
  `str.split("?")` 手搓解析就绕过了它，也绕过了「把 `"biz"` 拆成 `"bi" + "z"`」的 BD-11。
  充分性现在靠 BD-12（形状白名单，含「除文档串与导入路径外不许出现任何字符串字面量」）
  加 BD-3 的 26 条差分语料。**仍然不是全域等价性证明**：语料是有限的 26 条，白名单是按
  当前 7 条 EQUIVS 校准的。真要改形状，先加 EQUIV 再加实现——顺序反了就是假红门禁。
- BD-13 只判**顶层**同名定义计数：嵌在别的函数里的同名 `_biz_from_url` 不是模块属性，
  `from app.services.kb import _biz_from_url` 拿不到它，所以那种形态由 `has_target()`
  直接落进 INCONCLUSIVE（rc=2），不会伪装成红基线。
- F 段的 F-3/F-4 是**判定力模拟**：用 `lambda u: ""` 顶替实现来问「这条锚会不会空过」，
  不是对磁盘代码的执行——对磁盘代码的真实执行只有 F-1/F-2 与 B 段。两者的结论不可互换。
