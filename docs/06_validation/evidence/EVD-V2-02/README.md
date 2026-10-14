# EVD-V2-02 — STEP-02 S2.1.1…S2.1.5 文章身份解析、委托与锚定去 LIKE（本机执行账）

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
| S2.1.1 先红用例（`test_article_identity.py`，条数现读 `grep -cE "^(async )?def test_" apps/api/tests/test_article_identity.py`，本行不抄） | ✅ 真实执行 + 改前红可重放 | §2 两条通道 + §3 `block_article_identity_plugin.py` |
| S2.1.2 实现（`article_identity.py`：`WechatUrlParts` + `parse_wechat_url`） | ✅ 真实加载；语句覆盖以 `python docs/06_validation/evidence/EVD-V2-02/prove_article_identity.py` 末行 PI-11 那条读数为准（分子分母都现打，本行不抄） | §2 |
| S2.1.3 `kb._biz_from_url` 委托 | ✅ 改前红可重放 + 改后 BD 判据全绿 + 三条反证通道（变异 / 样本对 / 等价写法，三个数由 `prove_biz_delegation.py` 末行现算打印，本行不抄）+ 档位/退出码/编码三层自证（仅 BD 侧三层，PI 侧只有编码那一层） | §2 通道 C（`prove_biz_delegation.py`）、`out_s213.txt` A–N（第九轮起含 M 落盘自证与 N 变异电池；**段数与行数不抄在本行**——现读 `grep -c '^########## ' out_s213.txt` 与驱动末行「写出 …（N 行、M 段）」，——第十一轮复审 id 36 报回过同一类「现为」抄件，本行这一处是第十二轮自查（§4.13 id 47 同批）补上的） |
| S2.1.4 `_find_source_by_anchor` 删 LIKE 兜底 + 锚查询 `.limit(1)` | ✅ 本机由 O 段那台证明面承担（AF-B1…B6 行为面 + AF-S1/S2/S6 结构面：AST 取磁盘 kb.py 的**当前函数体**真实 exec，配一台如实实现 `limit(1)` 截断与多行抛错的记账假会话；B6 是第十四轮补的那格——生产量级的 18 字符键也不下发 URL 列 like 条件，判的是**假会话收到的条件**而不是源码里的 `.like(` 字形）；连库那条交 §5 J-6 | §4.14、§4.16 C1、`out_s213.txt` O 段 |
| S2.1.5 `get_by_url_fragment` 片段长度守卫（阈值取卡面的 8） | ✅ 同上（AF-A1…A5：短片段**零条 SQL**、返回 None、恰一条 WARNING 且事件名点名、边界卡在 8/7）；连库那条交 §5 J-7 | §4.14、`out_s213.txt` O 段 |
| S2.2 规范键 | ⛔ 阻塞于 ADR-0011 / D-V2-01（人拍板） | — |

## 2. 三条真实执行通道（都能在别人机器上一条命令复现）

**通道 A — 真实 pytest**（本机有 pytest，只是没有连库依赖）：

```bash
cd apps/api && PYTHONPATH=. python -m pytest tests/test_article_identity.py -q --noconftest -p no:cacheprovider
# → 14 passed, 1 warning in <redacted>s
```

（这一行原先写的是 `in 0.08s`。第九轮复审 id 6 指出：本包把留档里的墙钟统一归一化成
`in <redacted>s`，却在 README 的「真实执行通道」里留了一条每次重跑必不同的读数——同一个标准
不能只对留档生效。复现命令本身没变，变的只是那句读数。）

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
`PYTHONIOENCODING=utf-8` 从这一版起**只影响输出好不好读，不再决定脚本活不活下来**：win32 控制台
与重定向管道默认 cp936，编不出脚本要打印的 `⇒`，原先不带该变量就在 print 处
`UnicodeEncodeError`（既非绿也非红）。两个脚本现在各自在入口把 stdout/stderr 钉回 UTF-8
（`_ensure_utf8_stdout()`），并且 self-test 里多了一档**编码自证**——用 cp936 输出流把
`--self-test` 自己再跑一遍，要求 rc=0 且无 traceback。同类先例见 `EVD-V2-00R/README.md` §3.4 的
F-19 更正；这条是本卡 §4.9 记的两处自查之一。

判据面（PI-*）分三类，逐条在脚本 docstring 与 `--self-test` 输出里可对：
- **契约面** PI-1/PI-2/PI-3/PI-4/PI-5/PI-6：只依赖白名单标准库、零 IO（含 `s.execute` 换名与
  `__import__`/`eval` 动态逃逸两种绕行）、无 global/属性写、字段序与卡面一致、值对象冻结、
  `idx` 缺省为 `'1'`；
- **口径面** PI-7/PI-8/PI-9/PI-12：卡面 S2.1.1 的 7 条交付 + 本步补充的 7 条，逐一映射到真实
  用例名（删任一用例名判据即转假）；用例不 import pytest；夹具经 PEP 420 真实解析；
  **每条用例体内都有 assert/raise**（防空壳）；
- **执行面** PI-10/PI-11：真实调用 14 个用例函数、真实语句覆盖 100%。

**通道 C — S2.1.3 委托的机器证明**（`prove_biz_delegation.py`，BD-1…BD-16）。
为什么这条通道必须另建：`kb.py:22-25` 在模块级 import `structlog` 与 `sqlalchemy`，本机两者
皆无（实测收集期 `ModuleNotFoundError: No module named 'structlog'`，见 `out_s213.txt` D 段）
⇒ `tests/test_kb_longlink_ingest.py` 在本机**跑不了**，不是没写。替代机制是 EVD-V2-00 已确立的
AST 切片：从磁盘上的 `kb.py` 里取出 `_biz_from_url` 这**一个**函数节点单独 `compile`+`exec`
（函数体里全是局部导入，不需要执行整个模块），被执行的是文件当前代码。

```bash
PYTHONIOENCODING=utf-8 python docs/06_validation/evidence/EVD-V2-02/prove_biz_delegation.py
# → 合计 PASS=16 FAIL=0（改前同一命令：PASS=6 FAIL=10，rc=1；红态由 OLD_BODY 回写临时副本重放，
#    不 mv、不改工作树，命令与输出都在 out_s213.txt A 段）

PYTHONIOENCODING=utf-8 python docs/06_validation/evidence/EVD-V2-02/prove_biz_delegation.py --self-test
# → 首行「OK 档位自证：绿 rc=0 / 目标缺失 rc=2（INCONCLUSIVE） / 有判据红 rc=1 / 解析不了也按 2 档报…」
# → 次行「OK 退出码自证：子进程真实退出码分得开，且无一把它崩成 traceback（绿 0×3 含 BOM / 目标缺失 2 / 有判据红 1 / 解析不了 2；除基准外全在 win32 默认的 cp936 输出流下跑）」
# → 三行「OK 编码自证：--self-test 全程在编不出 `⇒` 的 cp936 输出流下跑完，rc=0 无 traceback，
#    且子进程 stdout 里确实打印过 ⇒（靶子在场）…」——这一行也是第八轮才有的，见 §4.10 id 3
# → SELF-TEST PASS：24 个函数体变异各自让指定判据变红 + 26 个判据样本对敏感 + 11 个等价写法不假红

PYTHONIOENCODING= python docs/06_validation/evidence/EVD-V2-02/prove_biz_delegation.py --self-test
# → 裸跑（故意不给编码变量）同样 SELF-TEST PASS，rc=0，stderr 零 traceback——改前这里是崩溃，见 K 段
```

**三档退出码**（第二轮复审 B3/B4：目标函数被整个删掉时，原先也打印一份 FAIL 清单、rc=1，
读者会把它当成普通的红基线——「没测到」冒充「测出红」）。现在 `0` 全绿 / `1` 有判据红 /
`2` INCONCLUSIVE（`_biz_from_url` 不存在、或**整份文件解析不了**，判据无从判定），且 self-test
第一道闸门用内存里删掉该函数的副本（`_strip_target`，不动工作树）**实测**三档互不相同。
第五轮复审 id 5 追加一条坦白并把它补上：只测 `run()` 的返回值等于没测到 `sys.exit` 那一步，
所以第二道闸门把三种源码形态各写成临时目录里的 `kb.py` 副本，用 `--kb=<路径>` 起**真实子进程**
读回退出码——工作树仍然一个字节没动。第七轮复审后这道闸门又加两件事：副本清单里加
「带 BOM 的基准」与「解析不了的副本」，并且**任何一档的 stderr 里都不许出现 traceback**
（改前这两发是崩溃，不是裁决；见 §4.8 的 J-9/J-10）。副本驱动里原先写死的
`PYTHONIOENCODING=utf-8` 也换成了 win32 默认的 cp936——把变量写死等于把崩溃面永远挡在自证之外。
第三道闸门是本轮新加的**编码自证**：前两道都测不到这个失效面，因为 `main()` 打印的字符 GBK 全编得出来，
真正编不出来的是 `--self-test` 自己标签里的 `⇒`，所以这一档把**父进程本身**放进被测面（cp936 下重跑
`--self-test`，要求 rc=0 且无 traceback）。它不是装饰：把 `_ensure_utf8_stdout()` 那行调用注掉，
这一档当场变红（`out_s213.txt` K.2/K.5 就是这条改前复现，K.1/K.4 是裸跑不崩的正面记录）。
第八轮复审 id 3 又指出这一档还剩一条**假绿**通道：子进程被 `BD_NO_NEST`/`PI_NO_NEST` 挡着不递归，
它只跑「档位 + 退出码 + 标签打印」，而这些标签里到底还有没有 ⇒，父进程原先并不知道——靶子被抽掉
（例如日后有人把标签里的 `⇒` 换成 `->`）时，这一档会照样报 OK。现在多要一条：子进程 stdout 里必须
真的出现过 ⇒，否则 `FAIL 编码自证：…一个靶字（U+21D2）都没有`。复现是 K.3/K.6：`sed 's/⇒/->/g'`
整份替换后跑 `--self-test`，那一档立刻红。判据里的靶字因此写成转义形式 `"\u21d2"`——写成字面 ⇒ 的话，
那条 sed 会连判据本身一起改掉，检查就自我失效了（第一版真的踩中，实测记录在同一段）。

判据分五面：行为面 BD-1…BD-6（长链出号主、与解析侧在**差分语料**上恒等、伪 `biz=` 不退化、
`%3D%3D` 同值、脏类型统一归零）、结构面 BD-7…BD-9（真有调用且调用名没被本地重新绑定、委托源必须是
`app.services.article_identity`、kb 侧不留第二份解析）、反面 BD-10/BD-11（不许 `except` 兜底伪造身份、
不许残留参数字面量做半委托）、反面 BD-12/BD-13（函数体**形状**白名单 + 模块作用域只有被 exec 的那一份
绑定）、反面 BD-16（**封闭世界**：整份文件里不许出现任何能改写模块命名空间的设施）、
边界外扩面 BD-14/BD-15（BD-14：委托结果必须**经数据流**真的喂进锚定查询的 `Source.external_id`
那一侧，宿主定义唯一、实参语义上是 URL、调用点不许自己解析；BD-15：目标函数能被单独 exec——
它是行为面六条的前提，打印时排在最前，编号按追加顺序以免打乱既有锚）。
一条实测副产品值得记住：**半委托**（委托但空串时回退本地再解析一次）在行为面几乎看不出问题，
却同时让 BD-9/BD-11 转红、并把 BD-6 的 int 抛错路径**带回来**——这正是「只测行为」抓不到的形态。
另一条同类副产品是第六轮的 D2：**函数内部正确**与「这个正确实现真的在起作用」是两件事，
前者管不到后者，所以证明面必须越过函数边界一次（BD-14）。
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
（第五轮只做到「数顶层 def」，第六轮 D1 证明这仍然不够——非 def 的模块级绑定照样能换掉活绑定，见 §4.7。）
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

## 2b. 重放 `out_s213.txt` 的落点：干净视图（第十五轮的现场，不是可选项）

留档重放器 `replay_s213.py` 判的是**磁盘上的代码**，而本机的工作树是多个会话共用的。
第十五轮那趟实测到两档读数（同一份 AF 台）：脏工作树上
`FAIL 基准（未变异）就有红判据：['AF-B6', 'AF-S7']`，`da4095a` 的干净视图上同一台 `SELF-TEST PASS`——
差别不在我这一批，而在别人**尚未提交**的在飞改动（见 §4.17 那三条环境事实）。顺带说清留档头部那句「范围内未提交 N 项」在干净视图里的含义：**它读的是叠进那棵树的本批文件**，不是主工作树的真实脏度——所以头部那个 N 与 §2b 第 2 步的清单必须逐行对得上，对不上就是叠错了。
所以重放按下面这条走，别人在飞的件不会被读成我的缺陷，我自己的件一件都不会漏：

```bash
# 0) 全程从仓库根出发。§2/§3 的读者常被留在包目录里，而 cp 的相对源路径与 git 的
#    pathspec 都按**当前目录**解析——在子目录里跑这些命令会拿到 `cannot stat` 与空结果。
cd /d/Code/AideanBotHot
# 1) 取一份干净树（不动主工作树、不动别人的改动）。BASE = 本批的**父提交**；
#    目录名带批次号，免得与并行会话的临时 worktree 撞车（现读：`git worktree list`）。
git worktree add --detach /tmp/r16main 1a7e37e^
# 2) 只把**本批改动的文件**叠上去。清单现取自己那批：`git show --name-only BASE..HEAD`
#    或按提交说明点名的那几份；这里**绝不能**用 `git diff --name-only`——共享工作树里
#    那份清单会把别人的在飞件一起叠进来，等于把污染搬进"干净"视图。
#    第十五轮那批是五份，形状如下（换成本批的清单即可）：
for f in docs/06_validation/evidence/EVD-V2-02/replay_s213.py \
         docs/06_validation/evidence/EVD-V2-02/prove_anchor_fallback.py \
         docs/06_validation/evidence/EVD-V2-02/prove_biz_delegation.py \
         docs/06_validation/evidence/EVD-V2-02/mutate_replay_r9.py \
         apps/api/tests/test_asset_fragment_guard.py; do cp "$f" /tmp/r16main/"$f"; done
#    叠完先对账：`git -C /tmp/r16main status --short` 必须恰好是这几行，一行不多一行不少
# 3) 在干净树里跑门 + 整份重放（三道门各自末行给条数/发数，本节不抄）
cd /tmp/r16main/docs/06_validation/evidence/EVD-V2-02
PYTHONIOENCODING=utf-8 python prove_anchor_fallback.py --self-test
PYTHONIOENCODING=utf-8 python replay_s213.py --self-test
PYTHONIOENCODING=utf-8 python replay_s213.py            # 写干净树里那份 out_s213.txt
# 4) 交付者本人按字节拷回本包。哈希要比的是**产物 vs 仓库里既有那份留档**，
#    不是同一次 cp 的两端（那种比法恒成立，等于没比）：
sha256sum out_s213.txt /d/Code/AideanBotHot/docs/06_validation/evidence/EVD-V2-02/out_s213.txt
#   ↑ 拷回**之前**跑这一条：两个号数应当不同（不同才说明产物是新的）；
#     若相同，说明这一批根本没改变留档，那要问的是为什么没改变。
cp out_s213.txt /d/Code/AideanBotHot/docs/06_validation/evidence/EVD-V2-02/
sha256sum out_s213.txt /d/Code/AideanBotHot/docs/06_validation/evidence/EVD-V2-02/out_s213.txt
#   ↑ 拷回**之后**再跑一次同一条：这时两数才该相同，且这一对与上一对不同
git -C /d/Code/AideanBotHot worktree remove --force /tmp/r16main
#    为什么必须 `--force`：那棵树里带着叠进去的改动与重放生成的留档，不加就
#    `fatal: contains modified or untracked files`（rc=128）而收尾跑不通。
#    安全前提：移除前 `git -C /tmp/r16main status --short` 逐行确认没有**别人**的件，
#    且产物已经按上面那对哈希取回主树——这一步删的只是自己造的那份视图。
```

四点不假装：① 留档里的**绝对路径**是环境噪声（D 段那行 pytest 的 `ImportError while importing test module
'…\apps\api\tests\…'` 在干净树里指向临时目录，在仓库里指向仓库根），本包从来不声称 `out_s213.txt`
跨机器逐字节可复现，声称的是**每一段的 `$ ` 命令能重跑并给出同一个裁决**；
归一化只管墙钟与内存地址那类每跑必变的数。
② **字节数还随换行口径变**，所以 `N-iso` 那行的字节数只在同一口径下可比。本机 `core.autocrlf=true`：
`git worktree add` 检出的那份是 CRLF，比 blob 多出正好「行数」个字节（每行一个 `CR`）——
第十六轮复核实测同一份留档 116680 B（blob，也是驱动 `write_bytes` 落盘的那种 LF）↔ 117547 B（检出 CRLF），
差 867 = 该份的行数（现读：`git cat-file -s $(git rev-parse HEAD:docs/06_validation/evidence/EVD-V2-02/out_s213.txt)`
与 `wc -c < docs/06_validation/evidence/EVD-V2-02/out_s213.txt` 并读，再看 `grep -c "" …`）。
要跨口径比，比**行**而不是比字节。
③ 干净视图只解决「别人的在飞件不算我的读数」，它**不**替别人的代码改动背书——那一半要靠对账，见 §7。
④ 第十五轮那两档 AF 读数是**同一份 AF 台在两个磁盘状态**上的读数，但「变异 38 发」那一档只在
叠了本批件之后成立；纯 `da4095a` 那份是 32 发。别把 38 当成 BASE 的属性。

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
| A5（A–G） | 旧实现对 bytes 抛 ValueError | 不采信：parse_qs(urlparse(b"...").query) → {b'__biz': [b'AAA']}，旧实现对 bytes 返回 ''；复审把 parse_qs 直接喂了整条 URL。BD-6 的措辞（「None 与 bytes 静默空串，只有 int 抛」）维持 |
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

## 4.7 第六轮复审（对处置批 `a15a55b`）——四条活绑定空过 + 越界证明 + 崩栈面的复现与闭合

复审报告给了 6 条 DEFECT（D1–D6）。**D1–D5 在本机全部复现成立**，D6 是措辞与记账。
复现锚**不是一次性脚本**：六发攻击体全部固化进 harness——`MUTANTS` 16 条里本轮新增 6 条、
`PROBES` 21 条里本轮新增 11 条，单命令 `--self-test` 即可复跑；原始读数在 `out_s213.txt` I 段
（I-1…I-10，逐条标了对应的复审编号）。首轮我用一个临时脚本 `_workspace/repro_r6.py` 试探，
九发全 `rc=0`、红判据为空集——该脚本已删除，**不作为证据锚**（本包惯例：可复跑的证据只有
`prove_*.py` 与被引用的 `out_*.txt`）。

| id | 复审意见 | 本机复现（改前） | 落点（改后，均可复跑） |
|---|---|---|---|
| D1 | BD-13 只数**顶层 def**，而模块作用域里非 def 的绑定同样能换掉活绑定：`_biz_from_url = lambda url: ''`、`globals()['_biz_from_url'] = …`、`if True: def _biz_from_url`（顶层 `if` 不产生作用域）、`del _biz_from_url` | 四发全部 `evaluate()` 空集、`run()` rc=0，而同一份源码 import 进来 `_biz_from_url(LONG_A)` 给的是 `''`／名字直接消失 | `_module_bindings()` 收遍模块作用域所有动过该名字的语句（`Assign`/`AnnAssign` 带值/`AugAssign`/`Delete`/`For`/`With as`/walrus/`Import` 别名/嵌套在顶层 `if`·`try`·`with` 里的 def），并对 `globals()`/`locals()`/`vars()`/`exec`/`eval`/`setattr`/`delattr` 与目标名同现的语句按「动态重绑」记账；BD-13 改判「**只有被 exec 的那一份 def 动过绑定**」⇒ 四发各红 BD-13（`out_s213.txt` I-1…I-4），I-9 另用最小源码钉住「后写覆盖」这条语言事实 |
| D2 | 证明面不越出函数边界：把 `kb.py:343` 的 `_biz_from_url(url)` 换成就地 `url.split("__biz=")[-1]…`，13 条判据全绿——函数内部对，但委托结果根本不再进查询，而卡面标题写的正是「号主锚不再为空串」 | `rc=0`、红判据空集（BD-9/BD-11 只扫 `get_fn_node`，看不见调用点） | 新增 **BD-14**：`_find_source_by_anchor`（`kb.py:336`，是 `async def`——写判据时第一版按 `FunctionDef` 找不到它，先红了一次）必须①有对目标名的调用、②实参是其自身入参、③结果进到 `Source.external_id` 的比较里、④不许对自己的入参做 `split`/`partition`/`strip` 一类加工 ⇒ 该发变异红 BD-14（I-8），`external_id` 改名、去掉调用两发坏样本各红一次（`PROBES` 21 条里占两条） |
| D3 | README 两处陈旧计数（`:27` 的「11 判据 / A–E」、`:67` 的「BD-1…BD-11」） | 复现成立（本轮之前一次改判据没同步过 §1/§2 的表） | 当时改为 `15 判据 / A–I`、`BD-1…BD-15`；**第七轮之后又变三次**（现 `16 判据 / A–N`（十九段）、`BD-1…BD-16`，见 §4.8/§4.9/§4.10）——判据四条计数从头到尾没动，动的只是留档段数，所以这一格是本表里唯一**每轮都必然过期**的格子，第九轮的 `A–M → A–N` 就是照着这条扫出来的。这条正好证明「每轮改判据必须回头扫 §1 §2 §6 §7」不是套话：第八轮复审 id 2 抓到的就是**我自己**没扫这一格，处置见下一段，而 §4.10 那张表写下「改为 A–M」时这一格其实还是旧的，本轮才真的补上。**第十轮（id 18/19）抓到同一类缺陷挪到了留档头部**——头部那句「判据条数：16 条」与「试满 5 次」当时仍是抄写，处置是由 `bd_ids()` / `ATTEMPTS` / `PAUSE` 现算，并给它配了机检（M 段「头部现算」3 条 + 电池 N-17）；从那一轮起，凡能被驱动打印的号数（判据条数、留档行数、工作树未提交项数）一律不再抄进文档 |
| D4 | BD-12 白名单有四个漏检面：`AnnAssign` 的右值与入参重绑没查（只查 `ast.Assign`）、多目标/元组目标整条跳过、`List`/`Tuple`/`Subscript` 不在禁用节点里、`decorator_list` 从不看 | 四发 `rc=0`：`url: str = parse_wechat_url(url).biz; return url`、`parse_wechat_url, extra = …`、`return [parse_wechat_url(url).biz][0]`、`@staticmethod` | `ast.Subscript` 进禁用节点；绑定语句统一处理 `Assign`+`AnnAssign`（目标必须是单个 `Name`、右值必须落到委托根、入参不许被重绑）；`decorator_list` 非空即红 ⇒ 四发各红 BD-12（I-5…I-7 与 `PROBES` 的装饰器样本） |
| D5 | 装饰器引用模块级名字时 `run()` 直接带 `NameError` traceback 崩掉——三档退出码一条都没打印，「崩」既不是绿也不是红，常崩的门禁会被当噪音关掉 | 复现成立（改前 stderr 有 traceback、stdout 停在目标行） | `_try_load()` 兜住 exec，`run()` 先下 **BD-15**「目标函数能被单独 exec」，exec 不成则六条行为判据各记一次红（占位实现调用即抛，红得可读）；MUTANT `装饰器引用未定义名字` 钉住 ⇒ I-10 实测 `rc=1`、`stderr 里有无 traceback = False` |
| D6 | §7 只承认「白名单按当前 7 条 EQUIVS 校准」，没给出**欠接纳**的实数 | 复现成立（本轮量了） | 实测：7 发「仍然委托、只是换个写法」的形态里 **5 发会红 BD-12**（`if not url:` 前置守卫、加一行日志、`str(...)` 包一层、`biz_of_url(url)` 门面、把解析层挪进子包），只有「先取 `parts`/`biz` 局部变量」这 2 发绿。写进 §7 当作明账，不写成「白名单已完备」 |

一条复审附带提到、我改掉的次要项：`--self-test` 原先恒读真实 `kb.py`，`--kb=<路径>` 只作用于
`main()`——于是「在临时副本上自证」这话名不副实。现在 `self_test()` 也走 `_kb_override()`，
基准里没有委托锚时早退并说明原因。

不采信/不收紧的一条：D1 里「用 `importlib` + 打桩 `sys.modules` 把整份 `kb.py` 真 import 进来，
直接断言活绑定 identity」。**不做**的理由不是嫌麻烦：打桩出来的 `structlog`/`sqlalchemy` 与真实
依赖的行为并不等价，一旦证据依赖打桩，它证明的就不再是「这台机器上的 kb.py」，而是
「打桩 + kb.py」这个组合；改判 AST 绑定集合是同一结论的弱证明，但**不引入新的环境假设**。
代价（动态 exec 类花招仍可能漏）写进 §7。

## 4.8 第七轮复审（对处置批 `5288f1f`）——属性形态重绑、共现≠数据流、两发把脚本崩掉

报告给了 5 组指控（N1、N2、N3、N4、N5）。**N1/N2/N3/N4 在本机全部复现成立**（改前 15 条判据
`rc=0`、红判据空集），N5 只有一半成立（下面单列）。复现锚同样不是临时脚本：本轮把八发攻击固化成
`MUTANTS` 的 8 条新增（16→24）、`PROBES` 的 5 条新增（21→26）、`EQUIVS` 的 2 条新增（9→11），
原始读数在 `out_s213.txt` **J 段**——J 段跑的是**两版 harness 对照**（改前取自
`git show de78125:…prove_biz_delegation.py`，改后取自工作区），逐条打印 `改前 rc/红/traceback`
与 `改后 rc/红/traceback`，所以「改前空过」这句话现在是可重放的实测，不是叙述。

| id | 复审意见 | 本机复现（改前） | 落点（改后，均可复跑） |
|---|---|---|---|
| N1/N2 | BD-13 的绑定扫描只摊平 `Name`/`Tuple`/`List`/`Starred`，于是**属性形态**的模块级写入一个字没改目标名却换掉活绑定：`sys.modules[__name__]._biz_from_url = lambda url: ''`、`del sys.modules[__name__]._biz_from_url`，以及 `del` 之后再加一个模块级 `def __getattr__`（PEP 562：名字查不到时由它造一个）；`from x import *` 同理——绑进来什么由**对方模块**说了算 | 四发全部 `rc=0`、红判据空集（J-1…J-4），而 `import` 拿到的确实不再是那份 def | `_attr_bound()` 把 `Assign`/`AugAssign`/`AnnAssign`/`NamedExpr`/`Delete` 目标里的 `ast.Attribute.attr` 收进绑定集；`__getattr__` 体内出现目标名字面量即算动过绑定；星号导入保守算动过。**并新增 BD-16 封闭世界**（下一段），因为这类的攻击面是 Python 的名字查找协议而不是某条语法，补形状永远慢一步 |
| N3 | BD-14 的四条检查全是**共现**：宿主里有调用、有 `external_id` 比较、实参是入参、没自己 `split`——四件事同时成立却可以互不相关。三发实测：①`_biz_from_url(url)` 单独一句结果丢弃、锚只用 `article_key`；②结果丢弃 + kb 里再起一个本地解析器当真锚；③`_biz_from_url(article_key)` 把主键当 URL 传 | 三发全部 `rc=0`（J-5…J-7）| BD-14 改成**数据流**：`_flows_into_anchor()` 先收「值里直接含委托调用」的绑定名，再沿别名传两跳到不动点，最后要求 `Source.external_id` 那一侧引用其中之一（或调用本身写在那一侧）；另加两条——宿主同名定义必须**唯一**（`_caller_anchor_fns` 由 `next(ast.walk(...))` 改成按行号排序取末位，见 N4），实参必须**语义上是 URL**（与目标函数形参同名或名字含 `url`）⇒ 三发各红 BD-14 |
| N4 | 旧 BD-14 用 `next(ast.walk(tree))` 取宿主，BFS 不受行号约束 ⇒ 同名重复时可能证明到**早该被后写覆盖的那一份**；报告构造了三份同名方法、活的那份不用委托结果 | 复现成立但**报告那份构造本身解析不了**（见 N5）：我按类体缩进真正复制一份同名方法后，改版判据 `rc=0`、15 条全绿 | BD-14 收到 `len(hosts) > 1` 即红，并把「活的是末位那份」写进 detail ⇒ J-8 改后红 BD-14（同时报「没有调用」「没有 external_id 比较」两条，红得可定位） |
| N5 | 两发输入把**脚本自己**崩掉而不是给出裁决：攻击体本身 `IndentationError`、以及文件带 UTF-8 BOM 开头 | 复现成立：改前 `rc=1` 而 stderr 是 traceback（J-9/J-10），「崩」既不是绿也不是红 | `run()` 开头加 `parse_err()` 闸门，解析不了单落 **INCONCLUSIVE=2** 档并打印一句原因；读文件统一走 `_read_kb()`（`utf-8-sig`，CPython 自己接受 BOM，判据不该因此崩）；退出码自证的副本清单加「带 BOM 的基准」与「解析不了的副本」，并且**任何一档的 stderr 里出现 traceback 都算 FAIL** |

**BD-16 的口径（本批改判的核心判断，单列因为它是「换思路」而不是「补形状」）**：
立「封闭世界」契约——被证明的这份文件里不许出现 `sys.modules`、`globals()/locals()/vars()`、
`exec()/eval()`、接收者是命名空间或属性名恰为目标名的 `setattr()/delattr()`、星号导入、
模块级 `def __getattr__`；要用其中之一**必须先经人工裁决改契约**。名单是封闭的、可判定的，
且实测 `kb.py` 现在全部零命中（`getattr` 有 9 处但它是只读的，造不出绑定，故不在名单里），
所以这条今天就能绿。扫描范围是**整份文件**而不是只顶层：顶层调用一个体内含 `exec` 的函数
与直接 `exec` 等价。

本轮也被自己的等价通道抓出一条**假红**（这条最值钱，因为它证明通道在起作用）：
`_dynamic_rebind` 原先按「整条顶层语句的 unparse 里同时出现目标名和 `setattr`」判动态重绑，
而类体的 unparse 包含**整个类**——调用点里那句 `_biz_from_url(url)` 因此与类内任意一处
`setattr(rec, "url", …)` 共现，把 BD-13 判红。EQUIVS 新增的「ORM 对象上的正当 setattr」这条
当场变红，暴露了这个盲区。改法是收窄共现单位到**单条语句**（`def`/`class` 头除外，它们的
名字由 `_binds_target` 管），方法体内的 `globals()['_biz_from_url'] = …` 仍然会红——那条语句
自己就提到目标名。BD-13 的 MUTANT `globals() 动态重绑` 现在同时红 BD-13 与 BD-16（`out_s213.txt`
I-2 的读数已从 `['BD-13']` 变成 `['BD-13', 'BD-16']`，这就是「整份重放而非追加一段」的原因）。

不采纳的一条：N5 里「在文件末尾追加 `this is not python`」。**复现不成立**——那一行在 Python 里
是合法表达式语句（`this is not python` 是 `is not` 比较），`ast.parse` 从不报错，所以它既没让脚本
崩、也没让任何判据该红而没红。真按「追加非 Python」打，落点是 J-9 那一档（INCONCLUSIVE）。
这条写出来是为了记账，不是为了反驳：它提醒我「攻击体自己解析不了」和「攻击体合法但无效」是两类事。

本轮收紧的**代价**（明账，写进 §7）：① BD-16 见到任何模块级 `__getattr__` 就红，哪怕它与目标名
无关；② BD-14 的 URL 判定依赖形参名（含 `url` 子串或与目标形参同名），宿主把 URL 形参改名成
`link` 时会假红——那是契约变更要人来更正，不是判据缺陷；③ 数据流只做名字传播（≤3 跳），
经由 `dict`/属性/闭包传递锚点仍能躲过；④ `_flows_into_anchor` 认「锚点侧引用了那个名字」，
把锚点先塞进 `self.xxx` 再比较是下一个盲区，本轮没堵。

## 4.9 提交前自查（未等复审）——一处崩溃面，和一处**我自己的留档谎话**

这一节不是复审提出的，是准备 `git commit` 前把两条命令按卡面原样再跑一遍时撞出来的。两条都记，
因为第二条比第一条严重：它说明本卡前面那句「A–J 全部段落都在同一版 harness 上重放」当时不成立。

| id | 现象 | 复现 | 落点 |
|---|---|---|---|
| S-1 | 裸跑 `python prove_biz_delegation.py --self-test`（不给 `PYTHONIOENCODING`）以 `UnicodeEncodeError` 崩掉，rc=1 但既不是绿也不是红 | win32 管道默认 cp936，`MUTANTS`/`PROBES`/`EQUIVS` 的标签里有 `⇒`，print 到那里就炸。两个脚本同一症状，拼装证据的临时驱动 `_workspace/gen_s213_r7.py` 也是（它先炸给我看了一次） | 入口 `_ensure_utf8_stdout()` 把 stdout/stderr 钉回 UTF-8；self-test 新增**编码自证**档：cp936 下把 `--self-test` 再跑一遍（`BD_NO_NEST`/`PI_NO_NEST` 防递归），要求 rc=0 且无 traceback。改前复现与现态记录都在 `out_s213.txt` K.1–K.6：把那一行调用注掉，K.2/K.5 立刻红，所以这档是承重的 |
| S-2 | 上一版重放驱动 `_workspace/gen_s213_r7.py` 按 `^$ ` 前缀找命令，且**取走前缀再输出**（`cmd_lines[0][2:]`）⇒ 每重生成一次就丢一批把手，而把手一丢，下一趟就**不跑而直接抄旧输出**，且不报错。第八轮复审 id 3 拿这条去对仓库里的文件，发现我记错了对象：**已提交的那几份一直是完好的**（`git show b45777a:…out_s213.txt` 实测 7 段 / 7 条 `$ `，`de78125` 版 9 段 / 9 条），丢把手只发生在 `_workspace/` 里那份没入库的草稿上。所以「第七轮那份只剩 J 段有」这句话说的是**不可复核的东西** | 原先写的反证是 `grep -c cp936 _workspace/out_s213_new.txt` 得 0——那条依赖一个不入库的草稿，会话结束就没人能再跑（第八轮复审判它不可采信，判得对）。现在换成在库、逐字可跑的一条：`python docs/06_validation/evidence/EVD-V2-02/replay_s213.py --self-test`（留档 M 段），它对「把手缺失 / 整段无命令 / heredoc 配对断了 / 第一条非注释行是读数」四种输入分别要求 raise 或取到同一条命令，取不到就停下而绝不返回旧读数 | 新驱动 **`replay_s213.py` 落在本包内**（不再放 `_workspace/`，理由见下一段）：按段落版式取命令（标题后第一条非 `#` 非空行，heredoc 取到配对的 `PY`），输出时**统一补上 `$ ` 前缀**（不再自我剥除）；取不到命令一律 `raise ValueError`；**L 段机检**「每一段都留得下一条 `$ ` 命令」，缺一段就点名段号并让驱动 rc≠0；**M 段机检**取命令这条通道本身（L 只数把手，判不了把手后面是不是命令）。J 段的攻击驱动也从「内嵌 92 行到留档里」改成在库件 `j_attack_r7.py`。本行写下时那一批的留档是 18 段（A–J、K.1–K.6、M、L），且全部是那次真跑出来的；段数此后动过，一律以留档 L 段现打印的 `段数（含本段）：` 为准，本节不复制它 |

两件驱动**入库**这一步不是整理癖：`_workspace/` 不入库，那么「每次改 harness 都要重跑重放器」这条纪律
在仓库里就只剩 README 的一句话，会话一结束就没人执行；`j_attack.py` 那 92 行此前是**抄进**留档的，
在库版本与留档里的副本各一份、必然漂移。现在两者都是本包的文件，命令指向它们本身。

S-2 的边界要说清，别顺势夸大，也别把已入库的账本一起抹掉：仓库里 `b45777a`/`de78125` 两份留档的把手
**实测一条不缺**（7/7、9/9），所以我先前写在格子里的「已提交的那份也丢过把手」是错的，已更正。
我**同样没有**证据说第七轮那份草稿里的读数是假的（H-0 写着 16 条全绿、I-2 写着 `['BD-13','BD-16']`，
都对得上那一版 harness）。能被一条命令钉住的只有**机制**：那个驱动取不到命令时不 raise 而返回旧文本，
于是「没跑到」可以冒充「跑到了」，且抄得不报错。现在这件事由 M 段每天判一次（取命令的四种坏输入各自要求
raise 或取到同一条，另有字节层写入判据与写入通道若干；**条数与分组小计由 `check()` 记账、末行现打印，
本节故意不抄那个数字**——抄一次就漂一次，第九轮的「11 条」正是这么对不上的，见 id 10–17），
驱动里也真的改成了 raise-first。
所以「本文件全部段落都在同一版 harness 上重放」这句话，此前靠的是叙述，现在靠两段：L 段数把手、
M 段判驱动自己的两条通道（取命令 + 落盘回读）；而且 L 读的是**交付出去的这一份**（驱动先落文件、再跑 L、
最后回填 L 的输出，回填后还要把整份按**字节**读回来核对逐位相同——文本模式回读会被 CRLF 骗过，id 10），
不是运行前那一刻的半成品。
本项目反复踩的是同一个坑：一句不能被一条命令反驳的声明，等于没有声明。

代价（写进 §7）：① `_ensure_utf8_stdout()` 改的是**进程级** stdout/stderr，被别的脚本 import 时会连带
生效；② 编码自证档会让 `--self-test` 的耗时翻倍（子进程把全套变异再跑一遍）；③ 子进程真是崩在 print 上时，
它的 stdout 缓冲区随异常退出一起丢掉，traceback 文本自己也含 `⇒`、写 stderr 时二次失败，所以 FAIL 分支
只能落一句兜底文案而不是抄出异常原文（K.2/K.5 的读数就是那句兜底）；④ 命令是按**版式**识别的（标题后第一条非 `#` 行），不是按显式标记；`$ ` 前缀现在只出现在输出侧。
将来若有人在标题和命令之间插一条以 `python`/`cd` 开头的话，取到的命令就错了——L 段能抓到「某段没有
`$ ` 命令」，抓不到「某段取错了命令」。真要钉死，得把每段命令抽成驱动里的清单，那是下一步的账。

## 4.10 第八轮与第九轮：独立验证子智能体的报告逐条复现

ids 1–9 = 第八轮（对提交 `0161bcd`，报告 4 条 MAJOR + 5 条 MINOR，id 9 是本批收尾自己撞出来的）。ids 10–17 = 第九轮（对提交 `dcb1ffb`，报告 2 条 MAJOR + 6 条 MINOR；按报告的 id 1…8 顺序记账，其中 10←九轮 1、11←九轮 2、12←九轮 3、13←九轮 4、14←九轮 5、15←九轮 6、16←九轮 7、17←九轮 8；报告 8 条全部复现成立，无需打折的一条都没有——上一轮那种「部分成立」这次没出现。id 10 里那条「说谎的落盘」判据不在报告里，是我用它给的反证电池自己跑出来的一发；此处原写「第 11 发」，第十轮 10-13 抓到那是手抄序号、电池此后两度扩编早已对不上，现在它在 N 段里是 **N-07**，序号一律以 `mutate_replay_r9.py --print-labels` 或留档 N 段现读为准，本节不复制它们）。

处置批入库后按项目纪律交给另一个子智能体独立复核。它报回 13 项，其中 4 项判 MAJOR。
**每一条我先在本机复现再处置**（历史上「复审报了但复现不成立」已发生过两次，这轮也有）：

| id | 现象 | 复现 | 落点 |
|---|---|---|---|
| 1 | 留档里记了 pytest 的**墙钟**：`out_s213.txt` D 段 `1 error in 0.48s`、E 段 `5 passed … in 0.10s`。这两个数每次重跑必不同，于是「每个 ✅ 都能由命令复现」在字面上被两条读数破坏 | 让它的重放器跑同一份 D/E 命令，得到 `0.90s` / `0.26s`——同一版代码，读数不同 | 驱动 `run_cmd()` 把 `\bin \d+\.\d+s\b` 归一化成 `in <redacted>s`，并在文件头写明「凡 `in <redacted>s` 都是归一化掉的墙钟，除这一处外段体读数全是命令的真实输出」。归一化比「保留不可复现的数」诚实 |
| 2 | README `:305` 的 D3 格子里还写着「现 `16 判据 / A–J`」——被本提交自己改成了 A–L，等于同一批文件里两处互相矛盾 | `grep -n 'A–J' README.md` 命中该行 | 改为 `A–M`（十八段）。D3 这一行本来就写着「每轮改判据必须回头扫 §1 §2 §6 §7」，这次是**我自己**没扫 |
| 3 | 编码自证档还剩一条**假绿**通道：子进程被 `BD_NO_NEST` 挡着不递归，因此不打印本档自己的 OK 行；更要紧的是父进程从没检查子进程输出里到底还有没有 ⇒——标签里的靶字哪天被换成 `->`，这一档照样报 OK | 按它给的思路实测：`sed 's/⇒/->/g'` 整份替换后跑 `--self-test`，第一版**确实报 OK**（因为判据里的字面 ⇒ 也被同一条 sed 改掉了，检查自我失效） | 三处：① 加 `no_target` 判据，子进程 stdout 里没有 ⇒ 就 `FAIL … 一个靶字（U+21D2）都没有`；② 判据里的靶字改写成转义形式 `"\u21d2"`，使那条 sed 改不到判据本身（这一步是踩出来的，不是先想到的）；③ FAIL/OK 文案改成不依赖靶字的措辞。复现记录在 `out_s213.txt` K.3/K.6，正面记录在 K.1/K.4 与 C 段 |
| 4 | `replay_s213.py` docstring 写「只读工作树与被测文件」——不成立：它会重写本包内**被跟踪的** `out_s213.txt`，K 段命令还会在本包目录落 `_tmp_ng.py`（用完即删） | 在 `0161bcd` 的干净 worktree 里跑一次驱动，`git status` 立刻显示 ` M …out_s213.txt` | docstring 改成如实列「写什么」：重写留档 + 临时副本 + 删除回读，且**不写任何被测文件**；顺带承认 L 段只判把手在不在，把手后面是不是命令由**新增的 M 段**判（`replay_s213.py --self-test`，取命令通道的 6 条反证，坏输入一律要求 raise 而不是返回文本；第八轮收尾又给同一档补了写入回读五条（3 判据 + 2 端到端），见 id 9） |
| 5 | `j_attack_r7.py` 的 J-0 打印「判据条数直接看 C 段（改前 15 条 / 改后 16 条）」——那是**硬编码字符串**，而它实测的只有红条数（两版都是 0）。加一条判据，这行字不会变红，基准随时烂掉 | 读它的代码即可确认；且 `grep -c 'FAIL BD'` 两侧同值 | J-0 改为**测量**两版各自下过裁决的判据集合，并与驱动里登记的 `EXPECT = {改前 15, 改后 16}` 比对，不符则 `bad` 记账、`J-13` 报「对照自洽性不符」、脚本 rc=1。现在留档里的 `判据条数 = 15 / 16` 是跑出来的 |
| 6 | 父进程用 `encoding="utf-8"` 解码**子进程在 cp936 下的输出**，却没有 `errors=` ——一旦子进程真的吐出非 UTF-8 字节，父进程 `UnicodeDecodeError`，正是本卡要消灭的「没有裁决」第三态，只不过换了位置 | 它构造的变异 X3（`reconfigure` 只带 `errors="replace"` 不钉 encoding）实测让 BD 的 `--self-test` 以父进程 traceback 收场、**一道闸门读数都没打印** | 四处捕获统一加 `errors="replace"`（BD 两道子进程档、PI 编码档、`j_attack_r7` 取 `git show`）；裁决面从「子进程会不会崩」扩到「父进程解码会不会崩」 |
| 7 | 留档头部把「HEAD=…+工作区未提交改动」和「Python 3.11.9」写死在模板里 | 在干净工作树（它的 worktree）上跑，头部照样自称「有未提交改动」 | 头部改由现场测量：`git status --porcelain -- docs/06_validation apps/api` 决定「工作树干净 / 含未提交改动 N 项」，版本与平台取 `sys.version`/`sys.platform`。现在头部那行读的是 `HEAD=0161bcd｜含未提交改动 N 项｜Python 3.11.9｜win32` |
| 8 | 两处措辞失真：卡面 D-11 说「三道自证」并把 PI 侧也算成三档（PI 只有编码那一档），另有一处 `` `$ \` `` 的反引号转义残留 | 读 `prove_article_identity.py --self-test` 的读数只有一行 `OK 编码自证` | 卡面与 §1 表格都改成「BD 侧三层 / PI 侧一层」，转义残留清掉 |
| 9 | **本批收尾自己撞出来的**（不在它的报告里）：重放器整份跑完，最后一次回填 `out_s213.txt` 抛 `OSError [Errno 22]`（成因当时写成「win32 上文件被瞬时占用」，**那是猜的，已被 id 11 的实测推翻**），驱动就此终止，而磁盘上留下的是 **L 读数位还空着的半成品**——`write_text` 之后没有任何回读，「写出 431 行」只是驱动自己的一句 print | 同一条命令立刻重跑就成功（431→432 行、18 段），说明是竞态不是逻辑错；把 `OUT` 指到一个目录上跑 `write_out`，实测得到 `落盘或回读抛异常：PermissionError: [Errno 13]…` 而不是异常穿透 | 新增 `write_ok`（回读必须与写入相同才算成；仍留着占位符 = 半成品冒充成品；其余 = 长度不一致）与 `write_out`（写→回读比对，最多 5 次；失败**返回原因而不 raise**——本项目「崩栈不是裁决」），`main()` 两处写入都走它，失败打印 `FAIL 交付…` 并 rc=1。M 段于是从 6 条涨到 **11 条**（取命令 6 + 写入判据 3 + 写入端到端 2）——**这 11 条里的「逐字相同」是文本层比对，第九轮复审 id 1 证明它能被 CRLF 绕过，见 id 10；条数现已涨到 30 且由代码现算，第十轮的三条新账见 §4.11 的 id 18–21**。顺带把一条**依赖**写进 docstring：A–I 的命令取自上一版留档，删掉 `out_s213.txt` 就断自举（本轮实测：删掉后驱动以 `FileNotFoundError` traceback 收场）——现在落一句 `FAIL 交付：… 先 git checkout -- <该文件>` 并 rc=1 |
| 10 | **MAJOR**：`write_ok` 比的是**解码后的字符串**（`OUT.read_text()` 带通用换行翻译），磁盘落成 CRLF 时「逐字相同」这道门会放行一份字节完全不同的留档 | 实测（临时副本）：把落盘改成 `text.replace("\n","\r\n")` 后 `write_out` 返回空串＝判成功，磁盘上 `CR=4`、字节≠意图，而 `read_text` 读回与原串**完全相同**；带 BOM 那一发只是碰巧被长度分支抓到（解码后多一个 `\ufeff`），并不是按字节判的 | `write_ok(intent, raw: bytes)` 收字节、`write_out` 改走 `OUT.read_bytes()`；四种坏形状各给专属原因（半成品 / CRLF / BOM / 截断字节数）。M 段在 `write_ok` 层点名 CRLF 与 BOM，并加一条端到端「**说谎的落盘**」：写调用不抛、但磁盘上落的是 CRLF 版 ⇒ 必须报红。这条是唯一能抓「根本不回读」的：把 `last = write_ok(text, read())` 换成 `last = ""` 时除它以外每一条都全绿（当时是「其余 19 条」，第十轮 10-1 起条数由 `check()` 现算、本表不再复制）——**这一发是我自己的反证电池跑出来的，不在它的报告里** |
| 11 | **MAJOR**：「最多试 5 次、每次之间等 0.3 秒」两句都没有判据；且 id 9 那句 `Errno 22` 的成因是猜的 | `ATTEMPTS = 5`→`1` ⇒ `--self-test` 仍 rc=0；`sleep(0.3)`→`sleep(0)` ⇒ 仍 rc=0（基线 1.63s、改后 0.44s/0.15s，说明确实在跑）。异常形状逐个实测：目标为目录 → `PermissionError [Errno 13]`；名字含 `*`（win32 保留字符）→ `OSError [Errno 22] Invalid argument`；父目录不存在 → `FileNotFoundError [Errno 2]`；**被普通读柄持有的文件覆盖写不抛**（CPython 在 win32 不设 deny 模式）⇒ 「瞬时占用」这一解释在本机不可达 | `write_out` 的 `write/read/sleep/attempts/pause` 改为可注入（生产全部走默认值），M 段加三条真用例：① 第 1、2 次抛、第 3 次写成 ⇒ 整体必须成功且恰好试 3 次（`ATTEMPTS` 改 1 立刻红）；② 一直失败 ⇒ 必须试满 `ATTEMPTS` 次且原因里带异常类名；③ 两次失败之间必须各等 `PAUSE` 且 `PAUSE ≥ 0.2`。覆盖面从此按**异常族**（`except OSError`）声明、不按 errno 号数声明 |
| 12 | MINOR：「11 条」里有一条不可假——半成品那条只判「原因非空」，`if PLACEHOLDER in text:` 改成 `if False:` 照样 PASS，因为通用分支顺手把话说完了 | 实测 rc=0（跑两遍）。`write_ok` 先判等、再判占位符，所以删掉分支只是换了句措辞 | `check()` 断言**原因文本**：「半成品」「CRLF」「BOM」「字节」四个关键词各归各支，删任一支即红 |
| 13 | MINOR：`replay_s213.py` 注释「指向目录本身：写入必抛 `IsADirectoryError`」——本机实测抛 `PermissionError [Errno 13]`，那句是没测过的猜测 | 见 id 11 的实测表 | 注释/docstring 改成实测形状；那条端到端判据只要求「报得出原因」，不硬点异常类（所有 `OSError` 走同一道门） |
| 14 | MINOR：头部 `{state}` 只数 `docs/06_validation` + `apps/api` 两条路径，却在句子读起来像「整棵树干净」。dcb1ffb 那次报「6 项」而那次提交动了 7 个文件（步卡在 `docs/任务规划V0.3.0/`，不在担保路径里）；写这一格那天本机再跑是「范围内 0 项 / 全局 3 项」，而同一批入库的留档第 2 行报的是 5 项 / 8 项——**两个都是当时的实时读数，本表把前一对抄成了常量**（这正是第十轮 10-5 抓到的东西），旧写法还会在工作树不干净时直接打印「工作树干净」 | `git status --porcelain` 全局若干行 vs 同一路径 spec 下若干行（两个数每次不同） | `state` 三分叉：范围内有 ⇒ 两个号数都报；范围内干净但全局有 ⇒ 明写「本留档不担保它们」；两者皆空才算「工作树干净（全局 `git status --porcelain` 为空）」。**第十轮处置**：本表与卡面一律不再复制这两个数，头部那行由驱动 `n_range()`/`git status` 现算 |
| 15 | MINOR：墙钟归一化只做了留档，**README 自己的「真实执行通道 A」里留了一条活读数** `# → 14 passed, 1 warning in 0.08s`——就在 `:31`「三条真实执行通道（都能在别人机器上一条命令复现）」这句话下面，正是 §4.10 id 1 所说「留一份不可复现的读数」那一类 | `grep -nE "[0-9]\.[0-9]+s" README.md` 命中该行（`out_s213.txt` 本体是干净的：3 条 `in <redacted>s`、零条 `in \d+\.\d+s`） | 该行改为 `in <redacted>s` 并在下面写清「复现命令没变，变的只是那句读数」；判据口径从此对 README 与留档一致 |
| 16 | MINOR：`j_attack_r7.py` J-13 打印「10 发攻击」，实际 `len(ATTACKS)=8` + `len(CRASHES)=2`——与 id 5 刚修掉的「J-0 写死条数」同一类缺陷；M 段那句「11 条」也是手抄的，涨到 20 条后必然对不上 | `grep -n '10 发' j_attack_r7.py`；把任一检查删一条，读数里的「11」不动 | J-13 由 `len(ATTACKS)/len(CRASHES)` 现算；M 段每条判据都经 `check()` 记账，末行打印 `len(ran)` 与分组小计（条数从此不可能与代码不一致） |
| 17 | MINOR：「判据/变异/样本对/等价 …（16/24/26/11；PI 侧 12/17/4）」——PI 侧四个字段只给三个数，靠「判据恰好等于变异＝12」蒙混过关 | 两份脚本各自打印：PI 主跑 `合计 PASS=12`、PI `--self-test` 「12 个实现变异体 + 17 个判据样本对 + 4 个等价重构」；BD 主跑 `PASS=16`、BD `--self-test` 「24 + 26 + 11」 | 本节末尾与卡面 D-12 尾巴都改成**逐字段带名**的写法，不再用斜杠串 |

复现不成立或需打折的一条：它说「L 段是同义反复，永远只会失败于手改文件」。**部分成立**——由驱动生成的
留档里 L 必然通过，这是事实；但它的价值恰恰是「读者拿到磁盘上这一份时把手齐不齐」，而把手不齐
在上一轮真的发生过（§4.9 S-2）。所以我不删 L，而是补 M 段把「取命令通道」本身的判定力做成可跑的反证，
并在 §4.9 代价 ④ 里明写 L 判不了「取错命令」。

四条计数**逐字段带名**（id 17：斜杠串会把四个字段的三个数糊在一起，PI 侧全靠「判据恰好等于变异＝12」蒙混）：
**BD 侧** 判据 16 条 / 实现变异 24 个 / 判据样本对 26 对 / 等价写法 11 个；
**PI 侧** 判据 12 条 / 实现变异 12 个 / 判据样本对 17 对 / 等价写法 4 个。
第八到第十一这四轮下来**这八个数字一律未变**，变的是自证层与留档格式；
`kb.py` 仍未被改动（`git diff c10b229 -- apps/api/app/services/kb.py` 复跑仍为空）。
要说清这八个为什么还留在正文里（上一条刚宣布「本节不复制号数」）：它们不是**读数**，而是这份证明的**规格**——
「用 24 个变异去堵 16 条判据」这组配比是设计时定下的、被 `check()`/`--self-test` 逐条兑现的目标形状，
而每一次兑现都由命令现算现打（BD 侧 `python docs/06_validation/evidence/EVD-V2-02/prove_biz_delegation.py --self-test`
的 PASS 行、PI 侧同名的 `--self-test`；这两份读数在留档里各有落点——BD 侧在 C 段与 K.1、PI 侧在 K.4，
`grep -n "SELF-TEST PASS" out_s213.txt` 一跑就能看到）。
两者一旦分叉，**以命令为准、本节即错**，读者用上面两条命令就能当场发现；这与「留档行数 / M 段条数」那类
纯读数抄件的区别在于：那类没有任何规格意义，抄下来只是我顺手把测量结果写进了正文。
M 段与 N 段的条数不在「未变」之列，而**本节从这一版起不复制它们的任何号数**：上一版这里抄了
「30 / 20 / 17 / 3」，第十一轮复审 10-2 报回的正因为是抄件——代码改了它不会跟着改，而读者无从分辨。
现读法只有一处真相：M 段条数与分组小计看
`python docs/06_validation/evidence/EVD-V2-02/replay_s213.py --self-test` 末行，
分组逐条清单看同一脚本的 `--list-checks`（每行 `组｜判据名`，它同时是 N 段算覆盖率的分母），
N 段发数、红绿小计与覆盖率看
`python docs/06_validation/evidence/EVD-V2-02/mutate_replay_r9.py` 末尾的 `N-覆` 与 `N-总` 两行；
这三处读数在留档里的落点是 M 段末行与 N 段末两行。

## 4.11 第十轮：复审报告 14 项逐条复现（ids 18–31）

ids 18–31 = 第十轮（对提交 `d80eeaf`），报告 **8 条 MINOR + 6 条 NIT、0 条 MAJOR**；按报告的 10-1…10-14 顺序记账，
18←10-1、19←10-2、20←10-3、21←10-4、22←10-5、23←10-6、24←10-7、25←10-8、26←10-9、27←10-10、28←10-11、
29←10-12、30←10-13、31←10-14）。14 条全部在本机复现成立，没有打折的一条。

定锚这件事本身在这一轮被复审抓到过（10-2 的同类：叙述跑在代码前面）——上一版把被审提交写成 `b45777a`，
而报告所引的那份留档在 `git show d80eeaf:docs/06_validation/evidence/EVD-V2-02/out_s213.txt` 是 469 行，与报告正文一致；
`git show b45777a:…/replay_s213.py` 直接 `fatal: … exists on disk, but not in 'b45777a'`（驱动是第七轮 `0161bcd` 才入库的），
且 `b45777a` 那份留档只有 159 行，对不上报告里的任何一个数，所以它不可能是被审的那一份。
现按「报告引用的留档行数在哪一个提交命中」定锚。锚点写错等于把这一轮的全部复现挂在一个拿不到的对象上；
追查过程中我自己还踩到一个可复现的坑，一并记在这里免得下轮重犯：**`git ls-tree -r --name-only <c> -- <路径>` 的
pathspec 相对于当前工作目录**，在 `EVD-V2-02/` 里跑它会对任何提交都返回空，看起来像「整个目录在那个提交不存在」——
那是一条**拿不到读数却被读成读数**的命令。要么 `cd` 到仓库根，要么用 `git show <c>:<全路径>` 这种绝对形式。

这一轮没有 MAJOR，但它的**主线正是第八、九两轮反复抓到的同一枚硬币**：文档与留档头部里的手抄数字。
复审明确写了「最重的是 10-1 + 10-2，同类问题连续第四轮」——所以本轮处置的重心不是再补几句措辞，
而是**把那几个数从「我抄进正文」改成「代码现算并打印」**，并给每条新判据配一发能打红的变异。

| id | 现象 | 复现 | 落点 |
|---|---|---|---|
| 18 | MINOR：留档头部仍是手抄。`replay_s213.py:444` 写死「判据条数：16 条——BD-1…BD-6 行为面、BD-7…BD-16 结构面」，`:448` 写死「重试要真的试满 5 次」；`:411` 那句「这 92 行」指 `j_attack_r7.py`，而它被报回那一次实测已是 141 行（本轮处置后又到 147）——**历史指涉不可判**，「92」这个号既不被任何命令产出、也就永远不会被推翻 | 删掉 harness 里任一 `check("BD-…")` 行，头部那句「16 条」不动；`wc -l j_attack_r7.py` ≠ 92 | 三条：① `bd_ids()` 用两条正则从 harness 的**标注现场**（`out.append(("BD-…` / `check("BD-…`）数出行为面与结构面，`bd_headline()` 现算头部那句，数不出来时在头部写 `FAIL` 而不是写一句好听的话；② 头部「试满 5 次 / 每次等 0.3 秒」由 f-string 插 `ATTEMPTS`/`PAUSE`，四种坏形状的原因名由 `head_causes` 现列；③ 「这 92 行」删掉，换成一句明写「那是当时未测量的历史数字，本节不再复制任何号数」。M 段新增第三组**头部现算** 3 条（区间连续 / 两组不相交 / **真删掉 `STR_LABEL` 那一行 ⇒ 清单必须正好少它一条**），电池 N-17 是它的反证 |
| 19 | MINOR：卡面 `:367` 写「（467 行，整份由驱动重放）」，而同一批的驱动实打 469 行——**留档行数由驱动打印，正文却抄了一份**（本行当时也抄了一份「磁盘上现在是几行」，第十一轮复审 10-2 报回的就是这一句：它现在又是别的数了。所以这一列不再写现时行数，现读只认 `python docs/06_validation/evidence/EVD-V2-02/replay_s213.py` 末行那句 `写出 …（N 行、M 段）｜回读逐字节相同`） | 卡面 467 vs 留档末行 469 vs 文档正文里第三个数，三者互不相等，而只有末行那个能重跑 | 卡面与 README 一律不再写留档行数，改为写**测量命令**（末行那句 `写出 …（N 行）｜回读逐字节相同`）。这条与 id 18 同因：能被打印的数就不该被抄写 |
| 20 | MINOR：`write_out` 的默认 `sleep=time.sleep` **从没被任何判据碰过**——M 段每一条重试判据都注入 `sleep=`，于是把默认值换成 `lambda _s: None` 时全部 20 条照样绿。生产路径等的是不是真时钟，留档里没有证据 | 把 `def write_out(..., sleep=time.sleep)` 改成 `sleep=lambda _s: None` ⇒ `--self-test` rc=0 | M 段「写入通道」加三条：`inspect.signature(write_out).parameters` 断言默认 `sleep is time.sleep`、默认 `attempts/pause` 就是模块级 `ATTEMPTS/PAUSE`；再加一条**只注入 write、不注入 sleep** 的计时用例——真试满 5 次且耗时 ≥ `(ATTEMPTS-1)*PAUSE*0.6`（=0.72s）。反证 N-15 |
| 21 | MINOR：**四种原因在生产写入点会塌成同一句「半成品」**。生产意图里本来就带着 `PLACEHOLDER`（L 段读数位待回填），而 `write_ok` 把占位符分支排在最前，于是盘上落的是 CRLF 时诊断说的是另一回事。复审实测 rc=1、盘上 `CR=269`、原因写「半成品」 | 按生产路径复现：意图含 `PLACEHOLDER` + 落盘换成 CRLF ⇒ 原因点名「半成品」而非 CRLF | 分支顺序改为 `raw == want` → CRLF → BOM → 半成品 → 通用，且半成品判据收紧成**两个条件**：`PLACEHOLDER in text and PLACEHOLDER not in intent`（意图自带占位符时它不是坏消息）。M 段加两条对应正例（意图自带占位符而坏在换行 ⇒ 仍须点名 CRLF；意图自带占位符而盘上只是截断 ⇒ 报字节差），反证 N-11/N-04 |
| 22 | MINOR：`replay_s213.py:424`、本节 id 14 行、卡面 D-13 ⑤ 三处都写着「范围内 0 项 / 全局 3 项」，而**同一提交**入库的留档第 2 行报的是 5 项 / 8 项——那两个数是 `git status` 的实时读数，被文档当常量抄了下来 | 同一台机器隔一次提交再跑，两个数都不同；留档头部与文档正文互相矛盾 | 头部那两个号数由驱动现算（`state` 三分叉，id 14 的处置）；文档侧本轮把三处都改为「不复制号数，只写测量命令」。见本节 id 14 行同步改写的部分 |
| 23 | MINOR：**电池只判 rc**。给驱动注入一条与变异无关的红，10 发「必须红」全部打印 OK——它证明的是「跑挂了」而不是「这条变异打中了该打红的判据」；`N-iso` 两行只是 print，没有任何形状能让它红；`first`（第一条 FAIL 行）打出来却从没被比较 | 注入无关红 ⇒ 全 OK；把 `REPO_OUT` 改成会残留 `_tmp_*` 的世界 ⇒ `N-iso` 照样打「无」 | 三条：① RED 档必须**同时**满足「有可读 FAIL 行」与「至少一条落在期望判据组」，`rc=2`（或 rc≠0 却一条可读裁决都没有）判 `RC_INCONCLUSIVE` 而不是判红——沿用本项目「崩栈不是裁决」；② `SHOTS` 扩成五元组带 `group`，末行按 `len(SHOTS)` 现算小计；③ `N-iso` 改成 `isolate_selfcheck()` **三世界自证**（字节被改 / `_tmp_*` 残留 / 干净），探测器和它要判的那句话一起被证明。另加 **N-00 基线**：先跑一份**没打变异**的副本，它不绿就整批 rc=2（否则后面每一发的「红」都可能来自副本本身） |
| 24 | MINOR：电池自己**没有编码 guard**。给驱动加一条含 `⇒` 的标签后裸跑，它在 `mutate_replay_r9.py:98` 以 `UnicodeEncodeError: 'gbk' codec can't encode character '\u21d2'` 死掉，一条裁决都没输出——本卡第七轮起专门消灭的那种「没有裁决」的第三态，回到了处置它的工具上 | 裸跑（不带 `PYTHONIOENCODING`）一份标签含 `⇒` 的电池 ⇒ traceback、零读数 | 电池加 `_ensure_utf8_stdout()`，并按 K 段那一档的形状给它配**编码三发**（裸跑必须出裁决 / 关掉 guard 必须复现崩 / 把靶字抽成 `->` 后不许假绿，且「靶没打上」「靶字没抽干净」各有专属原因）。踩到的坑记一笔：`write_text` 在 win32 会把暂存副本的换行写成 `\r\n`，第一版正则 `^_ensure_utf8_stdout\($` 因此永不命中——修成 `\r?$` 并要求命中，否则报「靶没打上」 |
| 25 | MINOR：**裸 `assert` 当闸门**。`replay_s213.py:230/405/414` 与 `j_attack_r7.py:34` 用 `assert` 兜「取不到就该停」，实得 rc=1 且 stdout 一句都没有；更坏的是 `python -O` 下 assert 被剥掉——复审实测：驱动写出一份**缺整段**的 240 行留档，还照样打印「回读逐字节相同」 | `python -O replay_s213.py` ⇒ 缺段的留档 + 绿色读数；`python j_attack_r7.py` 在取不到 `git show` 时 rc=1 无正文 | 项目纪律本来就有三档退出码与「崩栈不是裁决」，本轮把它用到驱动自己身上：`k_sections()` 改为**返回缺陷清单**而不是 assert；`main()` 收集 `defects`、把 `extract_cmd` 的 raise 转成裁决行、并用 `ARCHIVED`/`CODE` 两张注册表核对「本该有哪几段」，缺段打印 `FAIL …` 并 rc=1；`j_attack_r7.py` 模块级 assert 改为打印 FAIL 文案后 `SystemExit(1)` |
| 26 | NIT：截断那条判据断言的是**词**而不是数——`"字节" in reason` 对 CRLF、BOM 的原因同样成立，所以「删掉长度分支」未必红 | 把截断原因写成「长度不同」而不给号数，判据照样绿 | 改为断言**两个号数**：原因必须写「写 {len(好)} 字节，读回 {len(好)-4} 字节」，且 CRLF/BOM 的措辞不能冒充它。反证 N-12 |
| 27 | NIT：N 段标题写「M 段**每条**新判据都配一发」，实际缺两发——没有任何锚删过通用原因分支，也没有锚碰 `except OSError` 那道门 | 逐条比对 `SHOTS` 锚点与 M 段判据；标题那句话当时不成立 | 补 N-13（删掉通用分支）与 N-14（把 `except OSError` 换成别的类 ⇒ 异常逃出 `write_out`，红在「写入通道」组）。标题那句现在由 `len(SHOTS)` 与分组小计托住，不再是形容词 |
| 28 | NIT：docstring 说「CRLF 会让 `git diff` 整片变红」——本机 `core.autocrlf=true` 且 `.gitattributes` 只钉了 `*.sh eol=lf`，所以一份**只把换行改成 CRLF**的留档 `git diff --stat` 是**空的**。那句话把唯一能被 git 抓到的高估写进了文档 | 落 CRLF 后 `git diff --stat -- out_s213.txt` 无输出 | docstring 改写成实测形状：换行差异在 diff 层**看不见**，所以比对必须落在字节层（这正是 id 10/第九轮那条 MAJOR 的判据存在的理由） |
| 29 | NIT：电池里标「等价」的第 12 发**并不保等价**——它把 `read_bytes()` 换成「读文本再编码」，等于让文本模式掩掉一次 CRLF 落盘；它当时没假红只是因为**另一条** M 判据自己调了 `read_bytes()` | 单独看第 12 发：GREEN；但它其实弱化了被测面 | 拆成两处：真正的等价写法只留三条（CRLF 常量写成字面量 / 字节比较两边对调 / BOM 前缀用切片），期望 rc=0；「默认回读退回文本模式」是**改坏**，移进 RED 档成为 N-16——它恰好就是第九轮那条 MAJOR 的原样形状 |
| 30 | NIT：两处措辞与代码对不上——本节开头写「说谎的落盘是那批电池的**第 11 发**」（电池两度扩编，序号早已漂移；那一发今天是 N-07），卡面 D-13 ① 写「我用 **⑧** 的新电池跑出来的」（电池是在 ⑨ 入库的） | `--print-labels` 现读 vs 文档里的序号；卡面 ① 与 ⑨ 的先后 | 两处都改成**可现读的指涉**：正文不再复制序号，只写「N-07，序号以 `--print-labels` 或留档 N 段为准」。这条与 id 18/19 同因，只是发生在指涉而非计数上 |
| 31 | NIT：G 段的被检文件清单是**我抄进 `$ ` 行的七份**，同包内已入库的 `block_article_identity_plugin.py` 漏在外面，也没有任何判据核对「清单 vs 包里实际有什么」 | `ls EVD-V2-02/*.py` 与 `$ ` 行逐个比对 | `g_section()` 由 `sorted(EV.glob("*.py"))` 现算命令（外加 `apps/api/tests` 的两份用例），所以「几份」永远只在留档 G 段那条 `$ ` 命令与其输出里，本节不写号数。包里新增 `.py` 会自动进门禁，不再依赖我记得加它。第十一轮复审 MINOR② 报回的是另一处：卡面 D-14 把 glob 的**包内**份数说成「本包 8 份」，实为「包内 glob 若干 + 用例两份」相加，两个集合的口径已在卡面分开写 |

第十轮那批**同样不改 `kb.py`**：`git diff c10b229 -- apps/api/app/services/kb.py` 复跑仍为空（交付物本身没动，动的
是自证层与留档格式）。BD/PI 那八个计数字段照旧逐字未变（见 §4.10 末）；M 段、N 段与留档行号数**不在本节
出现**，原因见上一段——它们各自的现读命令写在 §4.10 末，而下一轮（第十一轮）的处置见 §4.12。

## 4.12 第十一轮：复审报告 14 项逐条复现（ids 32–42）

ids 32–42 = 第十一轮（对提交 `65f508b`，即 §4.11 那批处置入库后的状态；报告 **1 条 MAJOR + 6 条 MINOR + 4 条 NIT**，
外加它对本卡 10-1…10-14 的裁决「10 项闭合、4 项部分闭合」。锚点这次按「上一批处置落在哪个提交」定，
可现读：`git log --oneline -1 65f508b` 与 `git show 65f508b:docs/06_validation/evidence/EVD-V2-02/out_s213.txt`
的行数就是那份报告所引的留档）。

这一轮最重的一条**是我上一轮的处置自己引入的**，而且恰好落在本卡第七轮起最立意的地方——落盘层：
驱动把 L 段读数回填进留档时用了全局 `replace()`，而 `write_ok` 的半成品原因串里当时正好打印着那个占位标记，
于是标记在磁盘上出现了两处，整段 L 输出被塞进另一条判据的**读数中间**。字节回读比不出来，
因为写下去的意图本身就是污染后的串——「回读逐字节相同」这句话第一次在同一份留档上变成了真话兼假话。
本节的写法因此改了一条纪律：**凡是驱动会打印的号数，本节只写测量命令**（§4.10 末、§4.11 末与本节同）。

| id | 现象 | 复现 | 落点 |
|---|---|---|---|
| 32 | **MAJOR**：`main()` 里 `OUT.read_text(…).replace(PLACEHOLDER, lout)` 没有 `count=1`、没有定位 ⇒ 全局替换。标记在磁盘上有两处（一处是 L 段读数位，一处是 M 段某条判据打印了标记本身的值），回填把整段 L 输出注入**另一条判据的读数**里；在库那份 `out_s213.txt` 的 N-11 就是事故现场，连被引号围住的标记字面量都被吞掉（`grep -c` 归零），而回读比对**看不见**这次自我污染 | `grep -n -A2 "N-11" git show 65f508b:…/out_s213.txt` ⇒ 判据读数中间夹着整段 L；`grep -c "PLACEHOLDER_L_OUT"` = 0 | 两处一起堵，且都配了反证：① `write_ok` 的半成品原因改为**描述**占位符而不打印标记值（读数里不再可能出现第二个标记）；② 回填前先 `pending.count(PLACEHOLDER)`，不是恰好 1 就打印 FAIL 并 rc=1——多出来的那一处是某段读数把标记打印了出来，少出来的那一处是 L 段没落下去，两种都拒绝交出这份留档；③ 替换改为 `replace(…, 1)`。留档头部那句「除三类归一化，段体每个字符都是命令的真实输出」从这一版起才配得上「每个字符」 |
| 33 | MINOR：电池末句「M 段**每条**判据都有能把它打红的变异」当时是**形容词**——判据 30 条、能打红的变异只有 17 发，而 README §7 自己承认「取命令那组没有新变异」，驱动与留档却仍在替那句话背书。这与 §4.11 id 23/27 是同一枚硬币的第四次 | 逐条比对 `--list-checks` 清单与 `SHOTS` 实际红出来的判据名 ⇒ 有一批判据从来不变红 | 把它做成**数字**：电池先跑 `replay_s213.py --list-checks` 取「组｜判据名」全清单当分母（`norm()` 把标签里的数字归一为 `N`，所以合法重构新增判据不会把电池变成假红），每发变异解析**实际**红出来的 `[组] 判据名` 对回登记表，末尾 `N-覆` 报「覆盖 n / 共 m 条」并把没有变异的判据**点名列出**、少一条 rc≠0。四个判据组现在各有变异：取命令这组补了六发（把手不剥 / 切片硬剥 / heredoc 只取首行 / 三处 `raise` 分别改成 `return ""` 或 `pass`） |
| 34 | MINOR：卡面 D-14 末句写「静态自检本轮对**本包 8 份** `.py`」——包里 `ls -1 *.py` 只有 6 份，另外 2 份在 `apps/api/tests`，等于把 `G_TEST_FILES` 记到了 `EV.glob` 头上 | `ls -1 docs/06_validation/evidence/EVD-V2-02/*.py \| wc -l` = 6，而留档 G 段 `$ ` 行有 8 个路径 | 卡面 D-14 改为分开两个集合的口径（包内 glob 现算 + `apps/api/tests` 两份用例），且不写号数、只写「以留档 G 段 `$ ` 行与 `合计违规` 读数为准」；README §4.11 id 31 行同步 |
| 35 | MINOR：三处（README `:451`、卡面 `:296`、卡面 D-14）把第十轮复审的对象写成 `b45777a`，而驱动 `replay_s213.py` 在那个提交里还没入库（第七轮 `0161bcd` 才进），`b45777a` 那份留档也只有 159 行，对不上报告引用的任何数 ⇒ 锚点漂了，等于把这一轮全部复现挂在一个拿不到的对象上；而报告引用的「467 行」**在任何提交的留档里都不命中**——那是当年卡面抄错的数，同一批驱动实打 469 行（见 §4.11 id 19），所以能命中的锚只有 `d80eeaf`。**行数不抄进正文**，逐提交命中表请跑：`for c in c10b229 b45777a a15a55b 5288f1f 0161bcd dcb1ffb d80eeaf 65f508b 99506cf; do printf "%s " $c; git show $c:docs/06_validation/evidence/EVD-V2-02/out_s213.txt | wc -l; done`（本行上一版在这里写「467 行只在 d80eeaf 命中」，与同一行右边的实测列 469 自己打脸，是 id 35 这条 MINOR 的复踩，第十二轮复审 B5(c) 抓到） | `git show b45777a:…/replay_s213.py` ⇒ `fatal: … exists on disk, but not in 'b45777a'`；`git show b45777a:…/out_s213.txt \| wc -l` = 159 vs `d80eeaf` = 469 | 三处一并改为 `d80eeaf`，并把**定锚方法**写在句子里（报告引用的留档行数在哪个提交命中就锚哪个）；本轮新写的 §4.12 头部同样带命令，读者可复核我这次没写错。**处置过程中我自己复踩一个坑**，记在这里：在 `EVD-V2-02/` 目录里跑 `git ls-tree -r --name-only <c> -- <路径>` 恒返回空——pathspec 相对当前目录，不是相对仓库根——我一度据此写下「整个目录在那个提交不存在」，那是**把「命令没给读数」读成了读数**；换到仓库根再跑，`b45777a` 明明带着 README/两份 harness/`out_run.txt`/`out_s213.txt`。详见 §4.11 头部那段 |
| 36 | MINOR：README `:506` 写「现为 18 段」，而同一份 README `:478` 说「A–N 十九段」、留档 L 段读数报的是另一个数——三处互相打脸，且「现为」是**现时断言**，抄下那一刻起就错 | 三个号数并列即矛盾 | 该句删掉号数，改为「段集合现读只认 L 段 `$ ` 命令读数与驱动末行『N 行、M 段』」；§4.10/§4.11 里同类抄件（M 段条数、N 段发数、留档行数）一并换成测量命令 |
| 37 | MINOR：文档写「用 `ARCHIVED`/`CODE` 两张注册表核对」，AST 实得 `ARCHIVED` 有 Store 也有 Load，而 **`CODE` 只有 Store、从不被读**——第二张注册表是死常量，那句「两张」是 G-23 禁的那种永不失败的断言 | `python -c` 走 AST 数 `CODE` 的 Store/Load ⇒ Load = 0 | `main()` 在落盘后加**输出侧**判据：从写下去的那份文本里 `re.finditer(r"(?m)^########## ([A-Z]+)")` 现取段集合，与 `{*ARCHIVED, *CODE}` 比对，不符就打印 FAIL 并 rc=1。输入侧那句 `found != want` 只保证**旧留档**里归档段齐；这一条保证**交出去的这一份**归档段 + 现生成段一个都不少——`python -O` 那种「缺整段却报逐字节相同」的形状正落在它身上（`CODE` 从此承重，AST 上 Load 不再为零） |
| 38 | MINOR：编码三发全绿时一声不出（等于注销），锚点不命中也只在批级兜 ⇒ 「guard 承重」这一档在绿的时候不可证 | 全绿一趟跑，N 段编码部分零读数 | `encoding_probe()` 三发各自把**实得读数**打出来（裸跑 rc / 关 guard rc 与是否 traceback / 抽靶后 rc 与 stdout 行数），靶没打上、靶字没抽干净各有专属原因；落点在 `out_s213.txt` N 段编码那几行 |
| 39 | NIT：`g_section()` 的返回值只进 `rendered`，`defects` 不收它 ⇒ 实测往包里放一个带违规的 `.py`，G 段记 `rc=1`、「合计违规 1 条」，驱动照样 rc=0——静态门禁不承重 | 造一个违规文件进门禁 ⇒ G 段红而整趟绿 | `g_section()` 改为返回 `(文本, 缺陷清单)`，`main()` 把它并进 `defects`（`defects += g_defects` 之后是
`if defects: … return 1`）；**本轮实测的是 `g_section()` 那一半**，端到端那一半是代码路径而非读数——
没有为它单跑一趟整份重放（重放一趟要把探针留在包里，写完的留档就成了脏证据）。判据形状是三判：末行必须 `rc=0`、必须出现「合计违规 0 条」、表里 `===` 的份数必须等于命令列出的份数（少一份就是 glob 与命令脱节）。**本轮实测定了改后的形状**：往包里放一个探针 `zz_probe_bad.py`（一行未使用的 `import os` 加一行赋值后不读的局部变量，命中的是 g24 的 F401/F841 两条——注意探针必须挑**规则表里真实现了的**类别，第一版我用裸 `except:` 造「违规」，`g_section()` 返回的缺陷清单是空的，那是探针没造对而不是门禁不承重，实测读数就是「缺陷条数：0」），`g_section()` 返回**两条**缺陷（「没下绿裁决：末行 'rc=1'」与「报的不是『合计违规 0 条』」），而「命令列出的份数 = 表里 `===` 的份数」这一判不误报；`main()` 在 `defects` 非空时 `return 1`，探针用完即删、包里不留残留（复现脚本与读数条数不再抄在这里——跑一次上面那三步就能看到） |
| 40 | NIT：`prove_article_identity.py:125` 仍是闸门裸 `assert`（本卡 §4.11 id 25 刚把同类清完，这是漏网的那一条）——`python -O` 下被剥掉，spec 取不到时后面拿一个 `None` 继续跑 | `python -O` 跑 PI，或让 `IMPL` 指向不存在的文件 | 换成显式分支：`spec is None or spec.loader is None` 时打印 `INCONCLUSIVE 目标加载不了：…一条判据都没跑` 并 `SystemExit(2)`——「压根没跑」绝不伪装成红，也不伪装成绿 |
| 41 | NIT：§4.11 末句写「后两个数**也**只出现在驱动打印里，不出现在本节正文」，而它自己所在那一节正文里就抄着那两个数（`:462` 抄 493、`:474` 抄 8 份）——声明与执行相反；另 A5 那 7 行跨 worktree 差里含一个内存地址 `<function <lambda> at 0x…>`，属「每次必不同」的读数却没与墙钟同口径归一化 | 读 README 自己打自己；`diff` 临时 worktree 的留档 vs 在库 ⇒ 地址那一行必不同 | 抄件全部删除（见 id 33/36），新增第三类归一化 `MEMADDR = 0x[0-9a-fA-F]{5,}` → `0x<redacted>`，并在留档头部**就地声明**三类归一化各是什么；A5 复现的差集因此只剩时间戳/绝对路径两类，号数以留档为准 |
| 42 | 上一轮「部分闭合」四项的残余：10-1（只判行为面区间连续，结构面 `BD-7…BD-N` 的连续性没人判）、10-6（`got = "RED" if rc else "GREEN"` 把 rc=2 折进 RED，崩栈那发逐行仍印 OK，只靠批级 `bad` 兜）、10-12（「默认 `attempts/pause`」那条判据可红，但 `SHOTS` 里没有打它的那发）、10-8（同 id 40） | 逐项对代码：M 段当时无结构面连续性判据；`verdict` 只有两档；`SHOTS` 无默认 attempts/pause 那发 | ① M 段「头部现算」组新增判据「两个区间**首尾相接**、合起来是 `BD-1…BD-N`」，配一发变异（结构面回写成行为面 ⇒ 红在头部现算组）；② 电池 `verdict()` 三档 `GREEN/RED/INCONCLUSIVE`——`rc==1` **且**有可读 FAIL 才算 RED，`rc=2` 或 rc≠0 却零裁决一律 INCONCLUSIVE 并计入批级不合格，末行「n 发红 / 0 发 INCONCLUSIVE」现算；③ `SHOTS` 补 `attempts: int = 3, pause: float = 0.1` 这一发（红在写入通道组，正是 10-3 那类「注入通道全绿也骗过」的默认值形状）；④ 见 id 40 |

本轮**仍不改 `kb.py`**：`git diff c10b229 -- apps/api/app/services/kb.py` 为空（A5 复现里这一条是 D 组实测）。
自证层的变化一律以 `--self-test` / `--list-checks` / `mutate_replay_r9.py` 三处打印为准，本节不复制号数；
留档由驱动整份重放后再入库，重放命令就是留档 L 段那条 `$ ` 命令。

## 4.13 第十二轮：复审报告逐条复现（ids 43–49）+ 一次**证据被改写**的事故

锚点：本轮对象是提交 `99506cf`（§4.12 那批处置入库后的状态）。可现读：`git log --oneline -1 99506cf`
与 `git show 99506cf:docs/06_validation/evidence/EVD-V2-02/out_s213.txt | wc -l`。
本轮派了**两份**独立复核：A 组管机制与承重断言、B 组管读数与 git 取证——分开派是因为一份报告里既跑电池
又抄号数时，前者会把后者的调用预算吃光（第八/九轮的实测教训，见 id 49）。

B 组回报 **3 CONFIRMED + 2 MINOR**，两条 MINOR 逐条本机复现成立、无一条打折。**A 组始终没有回报**：
它把一份打了变异的驱动副本放进**本包内**直接跑，那一跑改写了在库留档（id 45），此后它没有再给出任何结论。
所以本节关于 A 组只有事故本身和我自己复现出来的读数——**一份没交回报告的复核不能替我背书，
但它造成的现场必须记账**。

这一轮的落点跟前面几轮不一样：归一化那句声明、段末裁决那张表、落盘权那一句，判的都是
**驱动交出去的东西**，而不是「驱动跑没跑」。抄进正文的号数照旧一个不留。

| id | 现象 | 复现 | 落点 |
|---|---|---|---|
| 43 | **MINOR（B 组 B3）｜归一化②是一句空声明**：留档头部写「段体里有**三类**读数不是命令的原样输出……都在 `run_cmd()` 里统一处理」，而那是个模板字面量——`99506cf` 那份留档里 `0x<redacted>` 出现 **1** 次，而那一次就是头部自己这句；段体（非 `#` 行）里 `0x[0-9a-fA-F]{5,}` 命中 **0**。于是「处理了」这句话**只能靠留档恰好撞出那个形状**才谈得上被证，撞不出来就永远假不了——G-23 禁的正是这种永不失败的断言 | `git show 99506cf:docs/06_validation/evidence/EVD-V2-02/out_s213.txt \| grep -n "0x<redacted>"` ⇒ 唯一一处落在头部声明行；再把匹配范围收到 `^[^#]` 上就是 0 | 三类归一化改成**登记表** `NORMALIZATIONS = (类名, 正则, 替换文本, 必须命中的样本, 必须不命中的样本)`：`apply_norm()` 逐段累加命中处数，`norm_ledger()` 再对**正文**把替换文本数一遍，**两条通道**不符就把缺陷并进交付判据；头部那句从字面量改为「读数归一化命中**现算**……」，**0 也照写**（这一趟没撞到 ≠ 登记表里没这条规则）。M 段新增「归一化」组：每条规则一对正/反靶子（反样本是 `in 5s` 缺小数、`0x12` 不足 5 位——把阈值放宽就当场红）、`rc=2` 补注与 `rc=0/1` 不许补注各判、一条 `inspect.getsource(run_cmd)` 锚核对「登记了却不调用」、账判据两侧世界（相符须静默 / 故意少算一处须点名）。N 段配齐能打红的变异：正则宽度 `{5,}`→`{20,}` 与 `{2,}`、`rc == 2`→`rc == 3` 与 `rc >= 0`、`NORM_HITS` 传成 `{}`、账判据改 `if True:`、缺陷原因里去掉类名、头部只点一类、以及一发 GREEN（等价累加写法不许假红） |
| 44 | **MINOR（B 组 B5c）｜§4.12 id 35 那一格自己打自己**：左边写「467 行只在 `d80eeaf` 命中」，同一行右边测量列写 `d80eeaf` = 469；467 在**任何**提交的留档里都不命中（那是当年卡面抄错的数，见 §4.11 id 19） | `for c in c10b229 b45777a a15a55b 5288f1f 0161bcd dcb1ffb d80eeaf 65f508b 99506cf; do printf "%s " $c; git show $c:docs/06_validation/evidence/EVD-V2-02/out_s213.txt \| wc -l; done` ⇒ 没有一份是 467 | id 35 那一格里删掉「只在 `d80eeaf` 命中」这句断言，**逐提交命中表交给自己重跑的循环**，并在同一格写明我在那里复踩了 id 33 的纪律（抄件从写下那一刻就过期）。这是 §7 抄件清剿的最后一处 |
| 45 | **事故｜包内的变异副本把在库留档重写了**（不在报告里，是我这边跑出来的现场）：复核时把打了变异的驱动副本放进本包跑——`EV` 由 `__file__` 推出、正指着仓库里的证据包 ⇒ `OUT` 就是**在库的** `out_s213.txt`，变异版把整份留档重写，N 段标题当场变成 M 段。而 `N-iso` 当时只 glob `_tmp_*`，那份 `_v12_a2d.py` 就待在包里、探测器一声不出：**「电池不碰仓库」这句声明在被真实破坏的时候是沉默的** | `git status` 里出现 `M …/out_s213.txt`（我并没有跑过在册那份）；`grep -c '^########## N' out_s213.txt` 归零而 M 段标题读起来像 N；`ls _*` 有复核遗留件 | 三处一起堵：① **落盘权** `stray_copy(here, ev)`——`main()` 第一件事就核「跑的是不是在册那一份」，不是就点名拒收并 rc=1（变异副本请拷进临时目录跑，`mutate_replay_r9.py` 的 `stage()` 本来就是这么做，所以它从不碰在库件）；② 残留探测从 `_tmp_*` 扩到**任何 `_` 前缀的文件**（目录不算：`__pycache__` 也是 `_` 开头），并把隔离探测器自己反证一遍——**字节变 / 留 `_tmp_*` / 留 `_v12_*` / 只有正常命名件与目录 / 都干净**，各档逐条列在这里而不写条数，走了几种世界由电池 `N-iso` 那行现算打印（现算的那个数就落在打印里，本节不抄）：只会在坏消息上吱一声、或永远沉默的都不算判据；③ 受损的留档先 `git restore` 回到 `99506cf`，再由**在册驱动**整份重放重新生成——本轮入库这份是跑出来的，不是抄回来的 |
| 46 | 顺带抓到的鲁棒缺口｜G 段被检清单是 `EV.glob("*.py")` 现算的（第十一轮 NIT② 刚从手抄改成 glob），于是 id 45 那份 `_v12_a2d.py` 被当场**吸收进被检清单** ⇒ 留档里那条 `$ ` 命令与 `===` 表跟着一起变：「读者看到的被检文件集」被一次复核动作改写，而没有任何一条判据说这不行 | 包内多一个 `.py` ⇒ G 段那行文件列表就多一个；留档 `$ ` 行与登记表不符时无人比对 | 清单改为**登记** `EV_PY`，配双向相符判据：包内出现**未登记**的 `.py` 判缺陷、登记了却**不在包里**也判缺陷（当场点名——既不静默扩清单，也不静默少检）；G 段标题写明「被检清单由在库登记表 `EV_PY` 给出」；新入库一份证明脚本 = 同时进这张表，改一处就够 |
| 47 | 自查（未等复审）｜G 段在第十一轮被修成「报了红就不交付」，而 **M（驱动自证）与 N（反证电池）报了红却照样落进留档、整趟 rc=0**：读者得自己从十九段读数里发现哪一段红了。更糟的是 A 段（**改前红重放**）本来就该红、D 段（本机无 structlog/sqlalchemy）本该是 **2**，这两种「预期中的非绿」和真故障在末行上长得一模一样，没有登记就没有区分 | 造一份 M 段含 FAIL 而整趟 rc=0 的留档 ⇒ 无人出声；`grep '^rc=' out_s213.txt` 给出的档位与「哪段该是什么档」当时没有任何登记 | 新增 `EXPECTED_RC`（A=1、D=2，其余段须 0）+ `rc_gate()`：逐段核末行 `rc=N` 与登记表、`rc=2` 那段必须带 ③ 那句标注、末行不是 `rc=N` 形状就报「这一段的裁决读不出来」。`main()` **落盘前**（读要交出去的段体）与**落盘后**（读写下去的那份，顺带核归一化计数在两遍之间没漂）各跑一遍，任何一处不符即拒绝交付。M 段为此新增「段末裁决」判据组（各档形状逐条见 `python docs/06_validation/evidence/EVD-V2-02/replay_s213.py --list-checks`，本节不抄条数），其中一条是「登记表的键都得在探针里出现过」（`set(EXPECTED_RC) <= set("ADB")`——空挂的登记等于没登记）；N 段配了预期档改错、不符不报、`rc=2` 丢标注被放过、末行形状坏了却静默、以及空挂登记那几发 |
| 48 | 电池自己的一处自相矛盾｜覆盖率那行报「49 / 50 条判据……——每条都配到了变异」：分母 50 是 `--list-checks` 的**行数**，而 `norm()` 把标签里的数字塌成 `N` 之后有**两行同名**（`rc=0` / `rc=1` 那两条），分子按去重后的判据集合算 ⇒ 一句话里两个基数不同，读起来像「有一条没人覆盖却声明全覆盖」，而那句结论本身是对的 | 直接跑电池读 `N-覆` 那一行 ⇒ 分子、分母、结论三者互不成立 | 分母也走同一套去重（`uniq = list(dict.fromkeys(baseline))`），并把「清单若干行、塌数后同名若干行」这个差**显式报出来**；`N-总` 用同一个 `len(uniq)`——两个基数从此只能是同一个。塌数本身不许取消（它正是「合法重构改了判据名里的数字不会把电池变成假红」那半边） |
| 49 | 派单方式（记律，不是缺陷）｜A 组那份报告我没等到，而**它的预算本身就是信息**：一份复核件既要跑电池、又要逐条抄号数取证时，报告回不来的那一次，我手里既没有结论也没有现场 | 本轮 A 组无回报、B 组在预算内交回 3+2 | 复核按**断言类型**分派（机制/承重断言 vs. 读数/git 取证）而不是按任务号分派；任何复核件的临时件一律落在**系统临时目录**——包内出现 `_` 前缀文件时，交付者现在会拒收（id 45 ①②），这条不再依赖我提醒复核者 |

本轮**仍不改 `kb.py`**：`git diff c10b229 -- apps/api/app/services/kb.py` 为空。M 段/N 段/留档行数/覆盖率
一律以 `--self-test` 末行、`--list-checks`、电池 `N-覆` 与 `N-总` 四处打印为准，本节不复制号数；
留档由在册驱动整份重放后入库，重放命令就是留档 L 段那条 `$ ` 命令。

## 4.14 第十三轮：S2.1.4/S2.1.5 落库——一次**驱动自己崩掉**、一次**指针指空**、两处锚随代码漂

锚点：本轮对象是第十二轮处置入库后的状态（`git log --oneline -3`）。这一轮**动了生产代码**
（`kb.py` 的 `_find_source_by_anchor`、`asset.py` 的 `get_by_url_fragment` 与模块级阈值），
与 §4.4…§4.13 那几轮「只改证明层」不同，所以 §6 那句「`asset.py` 零改动」同时作废。
本轮没有派复核件（复核对象还没入库，派早了就是复核一个还没交付的形状），
下表五条全部是**我自己跑出来的现场**——其中 id 50 与 id 52 都是缺陷被判据抓住的那一类。

| id | 现象 | 复现 | 落点 |
|---|---|---|---|
| 50 | **驱动以 traceback 收场**：AF 那台把判据集中在 `CHECKS` 表里登记，id 是**三段**形状 `AF-<面字母><号数>`，而 `af_ids()` 借用了 BD 台按两段取号的 `int(s.split("-")[1])` ⇒ 整份重放在 `o_section()` 里抛 `ValueError: invalid literal for int() with base 10: 'P0'`，末行既不是 OK 也不是 FAIL，一个裁决都没交出。本项目禁的正是这第三种形态，而这一次**犯的是取证工具自己**，不是被测件 | 本轮实测：`python docs/06_validation/evidence/EVD-V2-02/replay_s213.py` 的 stdout 末段是 traceback（修好后同一条命令就是留档 O.1/O.2/O.3 三段的原样读数） | 取号改由 `_af_num()`：形状不符返回 `None` 而**不抛**，红由判据下而不是由解释器下。M 段新增「锚定台现算」的形状档——`AF-P0` 不许被当数字、`AF-S2` 必须排在 `AF-S10` 前（按字符串排就反序，正是这发变形），N 段配「AF 清单按字符串排序」那发变异把它打红 |
| 51 | 「头部现算」这条纪律从前只担保 BD 一台：本轮新增 O 段与 `af_headline()` 之后，**删掉一条 AF 判据，头部那句与 O 段对账都不会跟着变**——同一类缺陷第五次欠账，只是换了台机器 | 把 `prove_anchor_fallback.py` 的 `CHECKS` 里任意一行删掉 ⇒ 改前头部照旧、`--list-checks` 的分母跟着掉而没人比对 | M 段发满这一组（面齐/区间连续、头部条数、**真删一行** ⇒ 清单与头部同步变小、形状档、`o_ledger()` 的八档探针：有判据红 / PASS 少于登记 / 登记数虚报 / 整句计数丢了 / O.2 电池没绿 / O.3 少一条又多一条（条数相等，那种读数最像绿的）/ 同一 id 列两行 / 登记表空了要说「没有分母」，再加 `inspect.getsource(o_section)` 锚核对「登记了却不调用」与锚定台在 `EV_PY` 在册）；N 段配 15 发 RED + 1 发 GREEN（等价：显式按 `(号数, id)` 排） |
| 52 | 「交真库跑」那句话点到的文件与用例**根本不存在**：卡面 S2.1.4.1 点名 `test_kb_multisource_anchor.py`，我最初把 P-4 用例写进了 `test_kb_longlink_ingest.py`。按卡面搬过去之后，harness 的 print、O 段注释、README §5 **三处指针同时陈旧**，而当时没有任何一条判据核对磁盘上确有其事——这类否定式/指针式声明正是本包一路在补的形状 | `git show` 本轮中间态：搬迁后 `grep -rn "test_kb_longlink_ingest.py::test_multi_source_no_crash"` 仍命中两处（一处 print、一处注释），文件里已经没有那个函数 | 名字集中登记为 `REAL_DB_TARGETS`（文件 + 顶层用例名），`db_pointer_defects()` 按 **AST** 核对——不是 grep：注释里的名字、`class` 里的同名方法都算不得「确有其事」，本轮为这两种形状各配一发探针与变异。G 段在**仓库根**上核对，不符就不交付；M 段只判这道核对的**语义**（静默档 + 漂移/缺文件/类方法三档探针 + 真表非空 + 表内文件同时进 G 段门禁 + `g_section` 真的调用）。为什么 M 段不直接判真表（本轮实测踩过、也是这条的落点的一部分）：反证电池把本包拷进系统临时目录跑，副本的 `ROOT` 上面没有 `apps/` ⇒ 五条指针全报「文件不存在」，基线不绿、整批 **INCONCLUSIVE**——判据把自己的电池弄成「没有裁决」是最糟的一种红，所以判据带 `root` 把手，M 段对着一棵临时造假的小树判 |
| 53 | 两处 harness 的**宿主尾部锚**随生产代码一起漂了：S2.1.4 删掉兜底之后，旧锚 `).scalar_one_or_none()\n        return row` 在磁盘上出现 0 次 ⇒ BD 台 `--self-test` 有两发直接失配报红，J 台 J-8 报的是「应红未红」——**那两种红的含义相反**（一个是判据不够严，一个是攻击压根没打出去），却共用同一句文案 | `python docs/06_validation/evidence/EVD-V2-02/prove_biz_delegation.py --self-test`（修前：两行 `FAIL 变异锚失配（出现 0 次）`）；`python …/j_attack_r7.py`（修前：`FAIL 攻击对照：J-8 … 应红未红 ['BD-14']`） | 锚跟着磁盘走（`_HOST_TAIL`、`TAIL` 两处）。J 台补**锚失配预检**：`CALL`/`TAIL` 在 `kb.py` 里出现次数 ≠ 1 就点名并退出，且每一发构造后的源码若与基准**一字不差**就报「replace 没命中锚，这一发压根没打出去」——锚漂了必须由电池自己说，跳过等于把这条反证悄悄注销（电池的老纪律①，这一轮轮到 J 台补上） |
| 54 | 卡面 S2.1.4.3「已有 biz 源时优先命中 biz 源」从前只在假会话侧证过（AF-B1），连库侧没有对应的常驻用例——本机证不了不等于卡面可以少一条 | 读 §4 S2.1.4.3 与本包 §5 J-6 的差集 | 连库侧补 `test_biz_anchor_wins_when_both_anchors_exist`：种两条源（`external_id` 分别等于 biz 与 `_article_key(LONG_A)`），断言返回的是 biz 那条——判的是**顺序**而不是「有没有结果」（SQL 不保证行的顺序，所以顺序必须写进判据）；开头 `assert key == "s"` 把前提钉住，哪天 `_article_key` 换口径，这一行先出声，免得那句话悄悄变成在测另一件事。J-6 交有依赖环境实跑 |

这一轮改了 `kb.py` 与 `asset.py`（§6 里那句「`git diff c10b229 -- kb.py` 为空」是第七轮之前的当时读数，
现已就地标注并给出两条现读命令）；
两份新连库用例本机不可跑 ⇒ §5 J-6/J-7。M 段/N 段/AF 台判据条数一律以
`replay_s213.py --list-checks`、`prove_anchor_fallback.py --list-checks`、电池 `N-覆`/`N-总`
与驱动末行为准，**本节不复制号数**；留档由在册驱动整份重放后入库，重放命令就是留档 L 段那条 `$ ` 命令。

## 4.15 第十三轮复审处置：两份独立复核（A 组机制/判定力、B 组读数/取证）逐条复现

对象是提交 `078dc30`（S2.1.4/S2.1.5 落库）与文档提交 `a9b194d`。**两份都交回了**，且这一轮的分派
按 §4.13 id 49 那条纪律走（A 组只管「自称能判的东西到底能不能判」，B 组只管读数与 git），
两边都在预算内回来——上一轮那种「A 组无声消失、只留下事故现场」没有重演。

A 组回报 **3 MAJOR + 8 MINOR + 3 NIT + 8 CONFIRMED**，B 组回报 **5 MAJOR + 5 MINOR + 2 NIT + 14 CONFIRMED**。
下面每一格都是**本机复跑过**的：现象与原样复现命令、实得读数、落点。
**号数的口径**（第十四轮 D 组 D-14-06 抓到上一版这句是假声明：本节当时抄了十几个可打印号数却没挂时点）：
本节抄的是**带时点的读数**，锚是 `078dc30`（S2.1.4/S2.1.5 落库）与 `a576bc2`（这一批处置），
不是无时点的常量；每个号数旁边都给出现读命令——`replay_s213.py --list-checks`（M 段清单行数）、
电池 `N-总`（发数）与 `N-覆`（覆盖到的判据数）、`prove_anchor_fallback.py --list-checks`（AF 判据条数）、
两份 `--self-test` 末行。现读与这里抄的数**本来就该不同**（这一批又往上加了一批靶子），
对不上不是这里抄错，而是节拍的时点差；对得上反而说明有人在原地复用上一次的读数。

| id | 来源 | 现象 | 复现 | 落点 |
|---|---|---|---|---|
| A1 | A-MA-1 | **AF-S6 只认字面形状**：col = Source.url 后 col.like(f"%{key}%")、以及 getattr(Source, "url").like(...) 两种写法都把兜底复活了，而 18 条判据 PASS=18 FAIL=0。这句话的射程本来是「这条 SQL 写法」，不是「这一串字符」 | 副本在临时目录、--kb= 覆盖：## 3 … rc=0｜合计 PASS=18 FAIL=0、## 3b … rc=0 | AF-S6 换成「整份 kb.py 里**任何接收者**的 .like( 调用」（_calls_any_like，别名与 getattr 两种形状天然在内）；两发新变异各点名 AF-S6 / AF-S1+AF-S6。**号数挂时点**：那两行的「18 条判据 PASS=18」是 `078dc30` 时点 AF 台的读数，现读走 `python docs/06_validation/evidence/EVD-V2-02/prove_anchor_fallback.py --list-checks \| wc -l`（本批加了 AF-B6 之后它不再是 18） |
| A2 | A-MA-2 | **AF-S5 只认属性赋值形态的重绑**：setattr(AssetRepository, "get_by_url_fragment", …) 换掉了活绑定而判据绿，只有 AssetRepository.get_by_url_fragment = … 那种写法才红。兄弟台 BD 早把这一族配齐（J-1…J-4），AF 台只配了一发——覆盖不对称 | 同一份探针脚本：## 4 … rc=0｜PASS=18｜红=无；对照 ## 4b … rc=1｜红=['AF-S5'] | _attr_rebinds 扩到 setattr/delattr 调用与下标赋值两种形状，各配一发变异；PEP 562 那一类**不在 AF 台判**（它的 exec 面不经过模块属性查找），边界进 §7 |
| A3 | A-MA-3 | **「真库指针不符就不交付」这句话没有靶子**：把 defects += g_defects 改成 pass、把 g_section 的返回改成 return text, []、把 if defects: 改成 if False and defects:（死门，永不成立），M 段当时的判据与电池全部照样绿——被覆盖的从来是「判据」，不是「判据所在的交付门」 | python C:\…\Temp\r13rp\rp_probe.py：三发都 rc=0｜可读裁决 0 条 | 新增 M 段「**交付门**」一组：按 AST 判 main 里 if defects:/if late: 是**直接把名字当条件**（不收 BoolOp 那种死门）、G/K 的缺陷都经 defects += 并入、o_defects 并入 late、两道拒收门都排在第一次 write_out( 之前（按行号）。电池配 6 发：两发死门、两发丢合并、一发丢 o_defects、一发把落盘挪到门之前。**读数挂时点**（第十四轮 D 组 D-14-05：这一格上一版写「M 段 74 条判据与电池 73/73 全部照样绿」，73/73 是 `N-覆` 的**判据覆盖分母**、不是发数，发数在 `N-总` 那一行＝76——现读命令：`python …/replay_s213.py --list-checks \| wc -l` 与电池末行 `N-总`/`N-覆` 两条，本批之后它们各自又涨了） |
| A4 | A-MI-1 | AF-S2 数的是**处数**不是链：q = select(Source).where(...)（不带 limit）+ 另起一句 _diag = q.limit(1)，两处 select/limit 仍相等 ⇒ S2 绿，而被执行的链没带 limit | 探针 shot 1：rc=1｜红=['AF-B1','AF-B4']，AF-S2 不在红集里 | 改成沿 AST 父链爬：每条 select(...) 的后继方法链里必须有字面 .limit(1)。踩点记录：select(X).where(…) 的树形是 Call ← Attribute ← Call，第一版漏爬中间那个 Attribute ⇒ **未变异的 kb.py 上就报红**（本轮实测），修完才与 EQUIVS 同时成立 |
| A5 | A-MI-2 | 守卫的**计数单位**可漂：len(fragment.encode("utf-8")) 全绿；而三份边界样本全是 ASCII，字符数与字节数分不开（3 个汉字 = 9 字节会被放行） | 探针 shot 2：rc=0｜PASS=18｜红=0 | _compare_ok 钉死 len() 的实参必须是形参 fragment 本体；AF-A3 加 热点热（3 字符 / 9 字节，必须挡）；变异一发按字节数；连库用例的参数化同加那一行 |
| A6 | A-MI-3 | WARNING 的**载荷**无人判：把 source_id=/fragment=/min_len= 三个 kw 全删掉照样绿——S2.1.5「显式放弃兜底并留痕」的「痕」只剩一个词 | 探针 shot 5：rc=0｜PASS=18 | AF-A1 判事件名 + 三个键，且 min_len 的值须等于磁盘上的阈值常量；变异一发「只留事件名」；连库那条用例同改（event, kw = recorder.warnings[0] 后逐键断言） |
| A7 | A-MI-4 | 「g_section 真的在**仓库根上**调 db_pointer_defects」是 inspect.getsource 子串匹配，**双向都错**：写成关键字形式（语义正确）被判红，实参根被换成 ROOT / "docs"（核对错了根）反而抓不到 | 探针 R3/R7：两发都 rc=1｜[真库指针] …，其中一发是假红 | 换成 AST 取那次调用的实参：表必须是 REAL_DB_TARGETS、root 省略或恰为 ROOT；电池配一发 root 漂移（RED）+ 一发关键字写法（GREEN，等价写法不许假红） |
| A8 | A-MI-5 | o_ledger() 两处只取首个匹配/只比字样：O.1 里出现两行合计而第二行才是真裁决时读绿；O.2 只要**回引**过一次 SELF-TEST PASS 字样也读绿 | 报告内那段 python - <<PY 直接调 mod.o_ledger(...)：两行都返回 [] | 合计行改 findall 并要求**恰好一行**（多行本身就是异常形状，点名）；O.2 改判**末行**；M 段八档探针相应扩到「多行合计」那一档 |
| A9 | A-MI-6 | 交接措辞把不需要库的那半也说成「真库」：test_asset_fragment_guard.py 用记账假会话，压根不连库——REAL_DB_TARGETS 只核「文件在 + 顶层 def 在」，核不到「确能证引擎侧」 | grep -n "db_session\\|scalar(\\|compile(" apps/api/tests/test_asset_fragment_guard.py → 无 db_session | harness 头部与 run() 的边界段改成两半分别交代（①连库＝J-6，②只需依赖不连库＝J-7）；README §5 J-7 那格同时改写 |
| A10 | A-MI-7 | 用例断言弱于它自己的 docstring：test_url_fragment_query_is_source_scoped_like 只判 "LIKE" in sql and "LIMIT" in sql ⇒ .limit(5)、删掉 source_id 谓词都判不动；而这条用例还**没登记**进指针表 | grep -n "LIKE\\" in sql" -B 12 … | 断言补三条：source_id = 'src-1'、LIMIT 1（带值）、模式含 %片段%；用例登记进 REAL_DB_TARGETS |
| A11 | A-MI-8 | **基线路径崩栈**：evaluate() 有 try 而 run() 没有——喂进「阈值常量被重复绑定」这类世界建不起来的副本时，行为面判据取空账本的 log[0] 抛 IndexError，rc=1、stdout 连「合计」行都没有；而三档自证里根本没有「exec 不了」这一档 | 报告内那段子进程复现：rc=1｜合计行=无｜IndexError: list index out of range | 两条路径共用 _judged()（判据崩按红记并把异常形状写进读数）；档位自证**补两档**（内存 + 子进程各一档「世界建不起来 ⇒ RC_FAIL 且无 traceback」） |
| A12 | A-NI-1 | j_attack 的锚是逐字符比对：宿主尾部那行只要加一句行内注释，整个 J 段就出「锚失配」而不给裁决（方向安全，fail-closed，但下次落库被迫改锚） | 报告内 S0/S1/S2 三档读数：S0 rc=0、S1/S2 rc=1｜stdout 1 行 | **判为刻意保留**：锚漂必须出声，且这次它给的是**指名道姓的一行原因**而不是崩栈（上一版这里是静默「应红未红」，见 §4.14 id 53）。改 AST 定位的代价与收益不匹配，记进本节而不是改代码 |
| A13 | A-NI-2 | 指针表只按文件级判：其中一份新文件四条顶层用例、表里只登记两条，「确有其事」判到文件就停了（另一份两条都登记着——上一版这里写成「两份各有四条」是抄错的，第十四轮 D 组 D-14-08 抓到） | 现读两条：`grep -cE "^async def test_" apps/api/tests/test_asset_fragment_guard.py` 与 `grep -cE "^async def test_" apps/api/tests/test_kb_multisource_anchor.py`，再与 `git show <c>:…/replay_s213.py` 里 `REAL_DB_TARGETS` 的条数比（078dc30 时点是 4 与 2、表里 5 条；本批补到 7 条） | 新增 db_pointer_missing()：STEP_NEW_TEST_FILES 里**每条顶层 test_*** 都须在表里，G 段并入交付缺陷；M 段配三条探针（缺一条目点名 / 齐备时静默 / 文件不在也要出声）+ 两发变异；REAL_DB_TARGETS 补全到与该口径一致 |
| A14 | A-NI-3 | g24_static_check.py 只吃仓库根相对路径：给它临时副本的绝对路径就在 relative_to 上抛 ValueError，rc=1 且是 traceback（A 组只能另造同构小树才跑得动） | python docs/06_validation/evidence/EVD-V2-00/g24_static_check.py "C:\…\Temp\r13af\kb.py" → rc=1 + traceback | 落点在 EVD-V2-00：仓库外路径改落 **INCONCLUSIVE=2** 档并点名那几个路径；本轮复跑 rc=2 无 traceback，仓库内路径仍 rc=0 |
| B1 | B-R13B-07 | 留档头部与 M 段注释都写着「**本轮**重放撞到过一次回填 OSError [Errno 22] 而驱动照过」——那是 dcb1ffb（第八轮）引进的**模板字面量**，每轮都自称本轮；而现行驱动在该形状上根本交不出货，「撞到过而驱动照过」不可能成立于任何一份已交付留档 | 在**仓库根**上跑全路径（git 的 pathspec 相对当前目录，在证据包目录里用长路径会**静默给空结果**——第十四轮 D 组 D-14-07 就是被这一条绊到的）：`git log --oneline -S"本轮重放就撞到过一次" -- docs/06_validation/evidence/EVD-V2-02/replay_s213.py` ⇒ 两条命中，**引入＝`dcb1ffb`（第八轮处置批）、删除＝`a576bc2`（第十三轮处置批）**；上一版这里写「唯一命中 dcb1ffb」是把 `-S` 当成了只报引入 | 两处措辞改成「第八轮当时实测」并指名轮次与账目所在小节；那一轮另撞的两次崩溃面（驱动 ValueError: 'P0'、AF 台基线 IndexError）在 §4.14 id 50 与本表 A11 各有自己的条目。**这一条上一批只落了一半**（第十四轮 D 组 D-14-02 复跑发现）：驱动注释里还剩三处同样的自指措辞（`:24`/`:277`/`:822`，都是第八轮那次 Errno 22），而 M 段一条判据的**名字**也把它印进了留档——现在整份重扫并由 M 段「轮次自指」那一组判，见 §4.16 D 组那一格 |
| B2 | B-R13B-11 | 我本轮在 V0.5.0 卡面新写的那条验收 grep 当场是红的：grep -n '\.like(' apps/api/app/services/kb.py 实得 1 处命中，命中的正是本轮为交代「为什么删」而写进 docstring 的那一行 | 直接跑那条命令 → 342: …旧版此处还有一条 \Source.url.like(...)\ 兜底 | 卡面改成：否定式声明由 **AST** 判（AF-S1 判体内、AF-S6 判全文件任何接收者），并**写下字面 grep 会命中哪一行**；hunk 级断言不再挂在 --stat 上（配 grep -c '^@@' 那条） |
| B3 | B-R13B-15 | V0.4.0 卡面 :113/:122 仍把 P-4 用例写成 test_kb_longlink_ingest.py::test_multi_source_no_crash，而 :122 是**验收命令代码块**（同文件 :103 的注记证明这类命令真被人按字面执行）；按字面在有依赖环境里得到 ERROR: not found；我从前留的「按 V0.5.0 README 的取代关系读」指向一个不存在的文件（V0.5.0 下是 00-README.md，且它没有逐条宣布取代 V0.4.0 的验收命令） | grep -n "^def test\\|^async def test" apps/api/tests/test_kb_longlink_ingest.py；再用一条确实不存在的用例暴露失败形状 → rc=4｜ERROR: not found | 判为「会误导执行」而非「历史账不必回改」：在那两处**就地插勘误注记**并把命令改成有效那条，历史结论本身不改写；§6 那句指向不存在取代关系的话同步更正 |
| B4 | B-R13B-17 | 证据包里躺着一份 __pycache__/_harness_probe.cpython-311.pyc，其源文件在整个仓库已不存在（第十二轮那起「变异副本留在包里」的同族残留停在原地）；而 EV.glob("*.py") 看不见 .pyc、stray_copy() 只管落盘权，M 段那句「本包里的变异副本没有落盘权」读起来像已经清了 | ls docs/06_validation/evidence/EVD-V2-02/__pycache__；find . -name "_harness_probe*"（只剩编译件）；git check-ignore -v …__pycache__ 命中 .gitignore:10 | 清掉那份孤儿件（**只判源文件不存在的**：正常新生成的编译件不咬，见什么的探测器等于没判）；新增 orphan_pycs() 进 G 段缺陷 + M 段一条判据 + 一发「见谁都咬」的变异（反证那条口径）；现读命令进 §7 |
| B5 | B-R13B-06 | 头部那句「范围内未提交 11 项｜全仓库未提交 16 项」没带命令，读者按 git status --porcelain -- … \| wc -l 现跑得到 0——因为那两个数取于**留档自身落盘之前**，恒不含 out_s213.txt 这一改 | 留档第 2 行 vs 现跑同一条命令的差 | 头部那句后面直接附口径与两条命令；不改采集时机（落盘前取数才是它该有的语义） |
| B6 | B-R13B-10/21/22/23 | 四处**手抄号数**：卡面「剩余原子任务 6」（实为 7，grep -cE "^- \*\*S" 减交付数）、README §1 的「14 条」「27/27=100%」、§7 的「26 条语料 / 11 条 EQUIVS」、§6 把 hunk 级断言挂在只给行数的 --stat 上 | 逐条按报告里那些命令现跑（读数都对，**问题在于它们不该被抄进正文**） | 四处全部改成「命令 + 现读」，正文只留命令；这也正是 06-执行记录 开头那条口径在证据包内的落地 |
| B7 | B-R13B-24/27 | 头部那句「十九段」是描述上一版的抄件（数值为真但没有命令口径），而 §7 给的现读 grep 会把头部声明行自己算进去（实得 4 行 vs 头部报「墙钟 2｜地址 0」），两条通道指向同一件事却互相打脸 | git show e29000c:…out_s213.txt \\| grep -c "^########## "；grep -n "in <redacted>s\\|0x<redacted>" out_s213.txt | §7 那条命令补 grep -v ':#'（正文 = 全文减头部声明行）并写明口径；「十九段」类措辞改为带命令的历史读数 |

A 组另有 8 条 CONFIRMED（AF 台 5 发独立变异确实变红、`--self-test` 全绿、电池 76 发跑完且 `N-iso` 报
仓库留档未改动（这一个是 `078dc30` 时点电池末行 `N-总` 的发数；现读同一条命令，本批之后它又变了）、
`_af_num()` 七种输入不抛、`af_ids` 对「埋在表外」的同形行会出声、J 台预检真能区分
两种红、`db_pointer_defects` 的 AST-vs-grep 有靶、生产语义与两份用例期望无实质矛盾）；
B 组 14 条 CONFIRMED 见其报告 R13B-01/02/03/04/05/08/09/13/14/16/18/19/20/25。
**本轮没有打折的条目**：两份报告里没有一条被我复现否证；唯一的「不照办」是 A12（J 台锚的脆性），
理由是它现在给的是指名道姓的裁决而不是崩栈，这条判断写在这里而不是藏在代码注释里。

本轮**动了生产代码**（`kb.py`/`asset.py` 的语义没再改，改的是证据与文档；S2.1.4/S2.1.5 的实现
在 `078dc30` 就已定型），也动了 `EVD-V2-00/g24_static_check.py` 一处（A14，退出码分档）。

## 4.16 第十四轮复审处置：两份独立复核（C 组机制/判定力、D 组读数/git 取证）逐条复现

对象是提交 `078dc30`＋`a576bc2` 那一批（§4.15 的处置本身）。两份都交回了：**C 组 4 MAJOR + 7 MINOR + 4 CONFIRMED**、
**D 组 4 MAJOR + 5 MINOR + 1 NIT + 3 CONFIRMED**。分派仍按 §4.13 id 49 那条纪律走。
下面每一格都在本机按报告里的命令原样复跑过；号数一律写成**现读命令**，唯一的例外是挂了时点（提交号）的历史读数。

| id | 来源 | 现象 | 复现（报告原命令，仓库根执行） | 落点 |
|---|---|---|---|---|
| C1 | C-14-01 | **AF-S1/S6 判的是「`.like(` 这个字形」**：`getattr(getattr(Source,"url"),"like")` 配一句 `if len(article_key) > 8:` 把兜底复活，当时 18 条判据里的静态两条全绿；而行为面 AF-B2 只喂过 `"s"` 这一种短键，**恰好是被那句长度门排除的一侧** | 临时目录副本 + `--kb=` 覆盖：AF 台 rc=0｜红集为空；同一副本的假会话账本里实打实出现 `url.like('%abcdefghij123456%')` | 新增行为判据 **AF-B6**：生产量级的 18 字符短链键也不许下发 URL 列的 like 条件，读的是**假会话收到的条件**而不是源码字形——任何拼法造出来的条件都算（`methodcaller` 那一发连 `like` 都不是被调用的属性名，天然在内）。两发变异各点名 AF-B6 |
| C2 | C-14-02 | **AF-S3 判的是「If 子树里存在 `return None`」**：把守卫尾部换成 `if fragment.isalpha(): return None`，三件（比较、告警、返回）都在子树里 ⇒ 静态绿；而 `1234567` 这类短**数字**片段既不空也不是字母，守卫放行、LIKE 照发 | `python -c` 直接调 `m.af_s3(...)`：`(True, ...)`；行为探针：frag=`1234567` 时 SQL 1 条 | af_s3 改成要求 `return None` 是守卫分支的**直接语句**（告警那一半刻意不要求直接——它本就该只在片段非空时响，AF-A2 判的就是这个差别）；AF-A3 的样本加 `1234567` 一行；连库用例 `test_url_fragment_boundary_is_exactly_min_len` 的参数化同加，并一发「嵌一层条件的 return」变异 |
| C3 | C-14-03 | **`_attr_rebinds` 认不出两种间接形状**：`type.__setattr__(AssetRepository, "get_by_url_fragment", …)` 与 `_T = setattr; _T(类, "方法名", …)`、以及第二实参写成常量名（`_N = "get_by_url_fragment"`）——AF-S5 是重绑的唯一防线，而它只认字面 `setattr` 与字面字符串 | 三发探针：前两发 `红集=[]`，第三发 `__code__` 形态被抓（`AF-S5`） | `_attr_rebinds` 补 `_alias_map`（名字→函数、名字→字符串常量两张表）：`setattr`/`delattr` 的别名调用、`type.__setattr__`/`object.__setattr__`/`X.__setattr__(…)` 的位参形状、常量名实参各认；三发变异同批配上。**这一格的「边界」那一半上一版写错了**：它当时说再深一层（循环里挑出来的可调用）「由 AF-B6/B2 那条**运行时条件**兜住」——第十五轮 E 组证伪：AF 台的行为面 exec 的只有目标 def 的文本，重绑发生在类体/模块级/另一个函数时**行为面根本看不见它**，那一格只能由静态面负责（`_calls_any_like` 全文扫 + 非字形拼法，见 §4.17 E-15-01③/E-15-03）。真正的边界是「静态面与行为面各有扫不到的形状，两面之间没有谁兜谁」 |
| C4 | C-14-04 | **交付门可以「形状保留、语义掏空」**：`defects += [d for d in g_defects if False]`、`late = … + [d for d in o_defects if False]`、以及门之前一句 `sys.exit(0)`——三发下 M 段当时全部判据照样 SELF-TEST PASS，且 `reached_write_out=true`（既不落盘也不拒收，磁盘上旧那份冒充本轮交付） | 把整包拷进 `mkdtemp` 逐发改副本跑 `--self-test`，再 monkeypatch 注入一条缺陷跑 `main()`：三发都 rc=0/`sys_exit_code=0`、无 `FAIL 交付` | 交付门那一组换成语义判法：`_merge_targets` 接受 `+=`、`= 名字 + 名字`、`list(...)+list(...)` 三种等价形状但**拒绝带 `if` 的推导式**；`_gate_lines` 把「恒假的与项」（`if False and defects:`）与「找不到门」分开点名；新增一发 `_escape_lines` 判 main 体内不许有 `sys.exit`/`exit`。四发变异（两发过滤推导式、一发 sys.exit、一发等价形状必须绿） |
| C5 | C-14-05 | 「门须排在第一次落盘之前」只认被调用者字面叫 `write_out`：门之前插一句 `OUT.write_text("坏留盘")` 完全合法——磁盘先被改坏、门之后才出声 | 同一套 monkeypatch 仿真：`jiaofumen_red=[]`、`disk_is_bad_ledger=true` | 那条判据改成比 **sink**：`_sink_line` 认 `write_out`/`_disk_write`/`X.write_text`/`X.write_bytes`/`open(..., "w")`；配一发 `OUT.write_text` 的变异（红）＋原有 `write_out("")` 那发（红） |
| C6 | C-14-06 | **AF-S2 沿父链爬对三种等价写法假红**：`q = select(…).where(…)` 之后 `q = q.limit(1)`、`sel = select` 别名、`sqlalchemy.select(…)` 属性形态——三者语义都带 LIMIT 1，旧爬法第一跳就断 | `af_atk.py` 的 `S2_shapes`：三发分别 `(False, "链上方法 ['where']——没有 limit")` 等 | `_select_chains` 把链读成**数据流上的链**：向上爬完再顺着「这条链被赋给了哪个变量」走一跳，把 `变量.<meth>(…)` 的后续调用接进同一条链；`is_origin` 认别名与属性形态。三发等价写法进 `EQUIVS`（等价不许假红），拆句**且真的没带 limit** 那一发仍在 `MUTANTS` 里 |
| C7 | C-14-07 | 交付门第 1/3 条对等价改写假红：`defects += g_defects` → `defects = defects + g_defects` 报「实接 [k_defects]」；`if defects:` → `if len(defects) > 0:` 报「找不到拒收门」 | 两发仿真都 rc=1 而 `main` 行为一字不差 | 见 C4 的 `_merge_targets`/`_gate_lines`；两发等价形状进电池做 **GREEN** 靶（`defects = defects + g_defects`、`if len(defects) > 0:`、`if not not late:`） |
| C8 | C-14-08 | 两张指针判据对**同一个形状给出相反答案**，而且那份手抄名单本身就是绕口：`class TestOffline: async def test_unregistered_class_case()` 与 `if True: def test_x()` 既登记不进表也不被要求登记（pytest 真收集它们），而 `db_pointer_defects` 反过来把类方法判成指空；另：第三份新用例文件不在 `STEP_NEW_TEST_FILES` 里 ⇒ 两条判据同时看不见它 | 临时造一棵 `apps/api/tests` 小树直接调两个函数：两次读数逐字相同，加第三份文件后仍相同 | `_collect_cases` 统一口径（顶层 `test*` + `Test*` 类里的方法，后者登记成 `类::用例`；**不以 Test 开头的类不算**，那是判据咬合法形状）；两张判据共用它，M 段配「只写裸用例名仍指空」「按 `类::用例` 登记时核对得到」「四条齐备时静默且非 Test 类那一条不许被要求登记」三档；新增 `registry_drift` + `new_test_files_from_git`（基线 `STEP_TEST_BASE`＝`65f508b`，`--diff-filter=A` 加未跟踪的 `test_*.py`），git 取不到读数时按「没跑成」记缺陷而不是交空集 |
| C9 | C-14-09 | `orphan_pycs` 只 glob `ev/__pycache__` 一层：`sub/__pycache__/deep_gone.cpython-311.pyc` 与包根的 `root_stray.cpython-311.pyc` 两类位置全都隐形。顺带把这一轮的可疑点**证伪**了：pytest 双后缀编译件的 stem 解析没错（源文件在册 ⇒ 不咬；源文件删掉 ⇒ 咬） | 临时小树：只报第一条，另两条静默 | 改 `rglob("*.pyc")` 并按编译件自己的位置找源文件（`__pycache__` 的上一层，否则就地）；M 段为此自己造一棵三种位置都有的小树——于是「见谁都咬」那一发在电池里**第一次有读数**（`stage()`  ignore 了 `__pycache__`，从前那种写法在副本世界里根本没有 `.pyc` 可咬） |
| C10 | C-14-10 | 两条指针核对的 `ast.parse` 没有保护：一份 `def test_ok(:` 的用例文件让 `g_section()` 抛 `SyntaxError`，一份带 `# -*- coding: gbk -*-` 的（CPython 认）抛 `UnicodeDecodeError`——整趟 `main()` 以 traceback 收场，既不是红档也不是 INCONCLUSIVE 档 | 同一棵小树上直接调两个函数：两条都「抛出异常类名（不是裁决）」 | 新增 `_parse_or_none`：解析不了就**点名成缺陷**（带文件与异常类名），两张判据共用；M 段各配语法坏 / GBK 两档探针＋一发「静默交出空模块」的变异（那种写法把「没跑成」读成「没有缺陷」，比崩更糟） |
| C11 | C-14-11 | AF 台 `main()` 里两次 `_read()` 没有 try：喂一份 GBK 的源文件 ⇒ rc=1 + traceback、stdout 连「合计」行都没有。另两发「崩法」（9 万层嵌套括号、4 万段 `.limit(1)` 链）都在档位内 ⇒ `_judged()` 那层确实承重 | 子进程 `prove_anchor_fallback.py --kb=<非 UTF-8 副本> --asset=… --quiet`：rc=1、有 traceback、无合计行 | 新增 `_read_pair`，`main()` 与 `self_test()` 都走它：读不动就打印 INCONCLUSIVE + 合计行并 `rc=2`；子进程档位自证**补一档**「kb 是 GBK 编码的合法源文件 ⇒ 须 2 且无 traceback」（现读：AF 台 `--self-test` 的「退出码自证」那行报的档数） |
| D1 | D-14-01 | §4.14 写着「那句『`git diff c10b229 -- kb.py` 为空』的读法见 §6 更新」——**空指针**：§6 那句一字未改，还带着「本轮复跑确认」 | `git diff --stat c10b229 -- apps/api/app/services/kb.py` ⇒ `28 +-`（非空） | §6 那一条就地标注成**当时口径**（第七轮之前为空），并给出两条现读命令（kb.py 与 asset.py 各一条）；§4.14 那句指针改成指向这条注记 |
| D2 | D-14-02 | §4.15 的 B1 落点只兑现了一半：驱动注释里还有三处把第八轮那次 `OSError [Errno 22]` 写成「跑到这一轮时撞到的」（`:24`/`:277`/`:822`），而 M 段一条判据的**名字**也带着同一类代词被逐字印进留档（在库那份的第 479 行就是现场，第 484 行的 N 段模板字面量另有一处） | `grep -n "本轮" …/replay_s213.py`（修前 21 行命中）与 `grep -n "本轮" …/out_s213.txt`（修前 5 行） | 驱动源码与**拼好的整份留档**都不许出现那种措辞：`SELF_REF_MARKS`＋`self_ref_defects()`，落盘前后各扫一遍（落盘前拦 `body`、落盘后连 L 的回填一起扫），不符就 `FAIL 交付` 并 rc=1；M 段为此新增「轮次自指」一组（源码档 + 混进文本必须点名行号 + 指名轮次/提交一律放行 + 登记表不许被清空），驱动注释里 21 处代词按 `git blame` 逐行改成指名轮次。**这一条不再靠下一轮再抓一次**：它现在是读数 |
| D3 | D-14-03 | 一条历史读数被就地改成不存在的值：`06-执行记录.md` 里 `spawn UNKNOWN` / `0xC0000142` 在 `a576bc2` 被写成 `0x00000142`，而 `grep -rln "0xC0000142" docs apps` 已零命中——那不是任何真实 NTSTATUS，等于把观测值抹掉 | `git show a576bc2 -- …/06-执行记录.md` 的 `+` 行 vs `git show a576bc2^:…`:73 原文 | 值按 `a576bc2^` 回滚，并在那一条后面加一行勘误说明**为什么这条根本不该动**：驱动的 `MEMADDR` 归一化只作用于 `out_s213.txt`，06 文档不经过它——要躲归一化改的是口径不是读数。同一批 V0.4.0 卡面用的是 blockquote 注记（见 D11），两处口径现在一致 |
| D4 | D-14-04 | 卡面「剩余原子任务」那条**替代命令本身是坏的**：`grep -cE "^- \*\*S"` 减 `grep -c "✅"` 两个基数不同源（后者把表头图例与交付门那句也数进去），按字面跑出 `9 - 10 = -1` | 仓库根：两个 `grep -c` 分别给 9 与 10 | 换成口径明确的一条：`grep -E '^- \*\*S' <本文件> \| grep -vc '✅'`（顶层未带 ✅ 的 S 项），子项另算不与本行混；卡面同时写下这一处「换命令换得并不比手抄更可核」的勘误 |
| D5 | D-14-05 | §4.15 同一节两个电池号数互相打脸，其中「电池 73/73」用错了通道：73/73 是 `N-覆` 的**判据覆盖分母**，发数在 `N-总`（当时 76） | `git show 078dc30:…out_s213.txt \| grep -E "^N-总\|^N-覆"` 两条并读 | A3 那格改成「判据条数走 `--list-checks`、发数走 `N-总`、覆盖走 `N-覆`」三条现读命令，并把 73/73 与 76 各归各位 |
| D6 | D-14-06 | §4.15 顶格声明「号数一律现读，本节不抄」，正文却抄了 ≥12 个可打印号数而没挂时点 | 逐条数：`18 条 PASS=18`（A1/A2）、`M 段 74`／`电池 73/73`（A3）、`26 发`（§7）、`76 发`（CONFIRMED 段）等 | 声明改成实话：**本节抄的是带时点的读数**（锚 `078dc30`/`a576bc2`），每个号数旁边给现读命令；并写明「现读与抄的数本来就该不同，对上反而说明有人原地复用上一次的读数」 |
| D7 | D-14-07 | B1 的复现命令 `git log -S` 现已给 2 条命中（表里写「唯一命中 dcb1ffb」）；而且短路径写法在子目录下**静默给空结果**（pathspec 相对 CWD） | 仓库根全路径跑那条命令 ⇒ `a576bc2` + `dcb1ffb` | 改成「引入＝`dcb1ffb`（第八轮处置批）、删除＝`a576bc2`（第十三轮处置批）」，并把「仓库根执行 + 写全路径，否则空结果是命令没给读数而不是没有」写进那一格（与 §4.11 头部那条同族的教训，第二次记） |
| D8 | D-14-08 | A13 那句「两份新文件各有四条顶层用例」与磁盘不符（一份 2 条、一份 4 条；当时表里 5 条） | `git show 078dc30:apps/api/tests/test_kb_multisource_anchor.py \| grep -cE "^async def test_"` = 2；同法另一份 = 4 | 措辞改成「其中一份四条只登记两条」，落点的「补全到四条」换成现读命令与本批的实际口径（用例级判据要求**每条被收集的**都登记） |
| D9 | D-14-09 | `a576bc2` 的提交说明没覆盖它实际改的 5 份文档中的 2 份（`04-剩余可执行大体系.md`、`06-执行记录.md`） | `git show --name-only a576bc2` 的文件表 vs 说明正文 | 记成流程账：**本批的提交说明逐条点名它动的每一份文件**（这条也在 §4.13 id 49 那条「派单方式记律」旁边，属于「我自己复踩」那一类） |
| D10 | D-14-10/11/12（CONFIRMED） | 复核件自己确认：留档各段末行 rc 与 `EXPECTED_RC` 全部相符（段数不抄在这里，现读 `grep -c '^########## ' out_s213.txt`）、归一化两条通道读数一致（且 §7 那条命令里的 `-n` 是**承重的**而不是装饰）、L 段命令原样重跑逐字相同、V0.4.0 勘误是注记而非改写、包内编译件都有在册源文件、`EV_PY` 与盘上双向相符、远端与本地 HEAD 一致、刻意未跟踪的那几件未动。**这一格上一版抄了三个可打印的数**（「25 段」「7 份 `.pyc`」「三件未跟踪」），第十五轮 F 组按 D6 同一条纪律把它换成命令 | 现读五条：`grep -c '^########## ' out_s213.txt`｜`find docs/06_validation/evidence/EVD-V2-02 -name '*.pyc' \| wc -l`（与 M 段那条孤儿核对同口径）｜`git status --porcelain --untracked-files=all -- docs/任务规划V0.4.0/evidence docs/任务规划V0.5.0/evidence`（未跟踪件按目录列，数量随别人的在飞件变，所以这里只给命令不给数）｜`git ls-remote origin main` vs `git rev-parse HEAD`｜归一化对账看留档末行 `N-覆`/`N-总` 与 M 段「账」那组 | 无需落点；把「`grep -n` 前缀是承重而不是装饰」这一条抄进 §7，免得下一轮有人把它去掉 |
| D11 | D-14-11 NIT | V0.4.0 卡面的**执行步骤 3** 被就地扩写成「转绿；另加…用例」——把后加的交付项写回历史计划卡的勾选项，与同一批在别处用的「只注记不改写」口径不一致 | `git show a576bc2 -- …V0.4.0/steps/STEP-02…md` 的 `+` 行 | 步骤 3 恢复成原文「转绿」，那条后加用例只留在上面已有的勘误 blockquote 里（它本来就写了） |

C 组那四发 MAJOR 全是同一族：**上一轮的靶补上了，同一族的下一个形状仍然判不动**（字形 vs 语义、
存在 vs 直接、字面名 vs 别名、形状保留 vs 语义掏空）。所以这一批的落点一律写成「判语义」而不是「再补一个字形」，
并且每一发都配了「等价不许假红」那一端——只配红端的判据，下一批一定会被同一类假红打回来。

`kb.py`/`asset.py` 的**语义这一批没再动**（动的只有 `apps/api/tests/test_asset_fragment_guard.py` 的参数化，
加的是 `1234567` 那一行样本；生产代码零改动，现读：`git show --stat <本批提交> -- apps/api/app` 为空——
**不要用 `git diff <提交> -- <路径>`**：它比的是**工作树**，共享工作树里那读的是别人的在飞件（第十六轮 C4b）。）
本机可跑的门：AF 台 `--self-test`、驱动 `--self-test`、电池 `mutate_replay_r9.py`、整份重放，
条数与发数一律看各自末行打印，本节不抄。

## 4.17 第十五轮复审处置：E 组（机制/判定力）与 F 组（读数/文档对账）逐条复现

对象是提交 `96e8f31`＋`de9866b` 那一批（§4.16 的处置本身）。下面每一格都按报告里的命令在本机原样复跑过，
复现不成的没有一格——E 组那七条全部成立。号数一律写成**现读命令**，本节不抄可打印的数：
判据条数 `python docs/06_validation/evidence/EVD-V2-02/replay_s213.py --list-checks | wc -l`、
电池发数与覆盖看末行 `N-总`/`N-覆`、AF 台条数 `… | python prove_anchor_fallback.py --list-checks | wc -l`。

| id | 现象 | 复现（本机读到的形状） | 落点 |
|---|---|---|---|
| E-15-01 | **AF-B6 自己也被同一族三个维度绕过**：① 兜底加一句长度门 `if len(article_key) > 19:` 复活——旧 AF-B6 只喂 18 字符的键，恰好被那扇门挡住；② 模糊匹配打到**别的列**（`ContentAsset.external_id`）上，旧写法读 `_url_conds`（只挑 `col=="url"`）看不见；③ 兜底整个挪进 kb.py 里另一个函数，行为面 `_call_anchor` 只 exec 目标 def 的文本 ⇒ 看不见，而静态面 AF-S6 当时仍只认 `.like(` 字形 | 临时副本 + `--kb=` 覆盖：三发都 `SELF-TEST PASS` | `af_b6` 的键长扩到四档 `(18,19,25,41)` 并改读 `_like_conds`（**任意列上的一个 like 条件**，不再挑列）；`_calls_any_like` 认 `.like` 属性、`getattr(x,"like")`/`attrgetter`、`methodcaller("like", …)` 三种拼法并扫**整份** kb.py；三发变异各点名对应的判据那一格 |
| E-15-02 | 守卫分支里再开一条「自己发一次查询再把 None 返回」的早退路径，AF-S3 看不见——它当时只要求「If 子树里存在 `return None`」 | `python -c` 直接调 `m.af_s3(...)`：`(True, ...)`，而守卫体内多了一条 `select` | `af_s3` 现在**禁止守卫分支里出现任何查询构造**（`select`/`execute`/`scalar(s)`/`like`），配一发变异。**顺带一处我自己先红的现场**：这一发的样本最初写成 `ab-1234`，它只有 7 个字符、被守卫正确地挡住 ⇒ 基线自己红；修的是样本长度那一侧（补 `ab-12345`/`p0-st_01` 两个 8 字符混合类），不是把期望从 1 改成 0。连库用例 `test_url_fragment_boundary_is_exactly_min_len` 的参数化同批补这三行 |
| E-15-03 | `_attr_rebinds` 仍漏六格：类体内 `get_by_url_fragment = lambda …` 的裸赋值、模块级裸赋值、`type("AssetRepository", …, {…})` 造同名类、目标名以**字符串字面量**出现在调用实参或字典键里、`setattr` 别名的第三种取法、`methodcaller` 挪到另一个函数 | 六发探针：旧实现里五发 `红集=[]`，第六发（另一个函数里的 methodcaller）连静态面都漏 | `_attr_rebinds` 补「裸 Name 重绑（类体/模块级都算）」与「任何等于目标名的字符串字面量」两条形状，`_alias_map` 扩到第三种别名；六发变异同批配上 |
| E-15-04 | 交付门还是能被「形状不动、语义掏空」：`defects += list(filter(lambda d: False, g_defects))`；而合并白名单 `_defect_names` 若数不到名字，那句「每个 `*_defects` 都并进了门」就又成形容词 | 电池注入：那一发下 `--self-test` rc=0 | `_merge_targets` 拒绝带 `if` 的推导式与任何 `lambda` 实参、拒绝 `filter`/`filterfalse`/`compress`/`dropwhile`；`_defect_names` 从 main 的代码现取（排掉被调用的函数名——第一版把 `self_ref_defects` 也算成清单，正常代码上假红）。电池补四发：filter 掏空（红）、`_defect_names` 数不到（红）、`_defect_names` 反向吃进一切名字（红）、`defects = list(defects) + list(g_defects)`（必须绿） |
| E-15-05 | 自指扫描**只扫驱动一册**，而兄弟台的判据名会被逐字印进留档——「驱动干净」这句话的射程当时只到它自己；登记表也只有三种代词写法。**这一条还带出一个新的形状**：把扫描面缩成 `[here]` 时，只判「有没有措辞」的那条照样绿（兄弟台此刻是干净的），实测 `rc=0` | 电池那一发跑出 GREEN ⇒ 反证不成立，改成对账扫描面本身 | 扫描面 = 驱动 + `EV_PY` 全部在册件，**另立一条判据核扫描面自己**：应扫集合从在册登记表现取（不是从 `face` 现取——拿 `face` 对账 `face`，缩面时两边一起变小而永远绿），与实扫集合比对，读不到的册子单独点名；登记表扩到七个词。电池四发：缩面（红）、应扫集合掏空（红）、实扫不记录（红）、只留三个词（红） |
| E-15-06 | `_collect_cases` 两处口径不齐：嵌套 `Test*` 类的前缀不累加（读出来是 `TestInner::test_c`，既不是能跑的 node id 也不是「不收集」）、`try` 的 handler/else/finally 与 `with` 体不遍历（pytest 真收集那些位置里的用例） | 临时小树：嵌套类那条两边读数都错；`try` 体里那条既登不进表也没人要求登记 | 前缀**累加**成 `外层::内层::用例`、四类语句体都遍历；M 段补「嵌套 Test 类要登记成 `外层::内层::用例`」探针与绿档（不以 Test 开头的类不许被要求登记——口径过头那一发也在电池里）；电池两发回归（去掉累加、`ast.Try and False`） |
| E-15-07 | `g_section` 的被检清单退回只 glob 一层时，子目录里那册未登记的 `.py` 与它的 `.pyc` 互相打掩护（第十四轮已把实现改成 `rglob`，缺的是**判据**那一发） | 报告里那棵小树：只 glob 一层的写法两条都静默 | 电池补一发 `EV.glob("*.py")` 回归（必须红），与第十四轮那发「孤儿编译件两类位置」配对 |
| F-A | **卡面把不可证的完成态标成已完成**：STEP-02 卡的 **S2.3.2**（「P-3/P-4 复跑达修复后期望；全量双环境 0 failed；ruff/mypy/CI 双绿」）写着 ✅，而这三个分句没有一条能在本机证——前两分句要 venv 与 CI，第三条要连库。**上一版这一格把落点写成「S2.1.4/S2.1.5 那一格」，那是错的**：S2.1.4/S2.1.5 是本步真交付的两条，被降级的是 S2.3.2；第十六轮 C5 抓到，而我给的那条复现命令 `grep -n "S2.1.4"` 根本指向不到落点——**一条指错的复现命令比没有复现命令更糟**，它会让下一个人在对的地方读出「没问题」 | 现读三条：`grep -n "S2.3.2" docs/任务规划V0.5.0/steps/STEP-02-文章身份规范键与锚定去LIKE.md`（该行现为 `🔴⏳`，下一行是勘误）、`grep -n "S2.3.2" docs/任务规划V0.5.0/04-剩余可执行大纲体系.md`（同口径）、不可证性本身：`ruff --version`/`mypy --version`/`gitleaks --version` ⇒ `command not found`（见 §4.18），连库面见 §5 J-4/J-6/J-7 | 卡面与大纲同批降级为 🔴⏳ 并就地写勘误（「把不可证的完成态标成已完成，比不标更糟：它会让 §4 的『现算剩余』命令跟着少算一格」） |
| F-B | 大纲与各卡里的 ✅ **既被当类型又被当交付**：STEP-02 卡「带 ✅」＝已交付，STEP-00C 卡图例里「✅」＝验证类任务，同一条 `grep` 套到两张卡上给出的是两回事 | 两卡各跑一次那条计数命令，读数互不相容 | 在 §4 头部与两张卡的「剩余原子任务」行各自写明本卡口径，并注明统一它属 STEP-12 文档对账；不假装一条命令通吃 |
| F-C | 大纲 §4.2 的「剩余」列合计与叶子行的 ✅ 数**不互洽**：那一列是各卡写卡时点的抄件，没有随交付递减；上一版还把「剩余 109、已完成 11」写死在行文里，而它自己文件里的勾选现读已是 17 | `awk -F'\|' '$5 ~ /^ *[0-9]+ *$/{a+=$5;p+=$6} END{print a,p}' <本文件>` 与两条 `grep -c` 并读 | 写死的数换成三条现算命令，并把这处不互洽**写在头部而不是藏起来**（合计与逐格之和不符这件事由那三条命令当场给出） |
| F-D | 提交说明里的号数与当日读数不符：`96e8f31` 的正文写「97 发」，当日本机电池末行是另一数 | `git log -1 --format=%B 96e8f31` vs 电池 `N-总` 那行 | **登记不改**：提交说明是不可变的历史账，只能在文档侧交代「发数只认电池末行 `N-总`，提交说明里的号数是当时点」。这一条与 §4.16 D6 是同族（抄来的数与现读的数本来就该不同） |

三条**跨步骤的环境事实**（不是本批的缺陷，但会影响下一轮读这些命令的人，所以记在这里）：

1. **本包的门禁读的是磁盘状态，而工作树是共享的。** 本轮跑留档重放时，另两个会话正在同一工作树里改
   `apps/api/app/services/kb.py`（STEP-R0 加的第三条锚：`ContentAsset.external_id` 等值反查 +
   `len(article_key) >= MIN_FRAGMENT_LEN` 守卫）、给 `apps/api/tests/test_kb_multisource_anchor.py`
   加了两条连库用例、并新建了未跟踪的 `apps/api/tests/test_alerting_default.py`（STEP-16）。
   实测两档读数（同一份 AF 台、两个磁盘状态）：脏工作树上
   `FAIL 基准（未变异）就有红判据：['AF-B6', 'AF-S7']——self-test 结论不可用`；
   在 `da4095a` 的干净视图上同一台 `SELF-TEST PASS`。**留档因此不是在脏工作树上打的**：
   用 `git worktree add --detach <tmp> da4095a` 取一份干净树，再把本批改动的五份文件叠上去重放，
   生成的 `out_s213.txt` 按字节拷回本包。命令见 §2 末「在干净视图上重放」那一条。
   这不是「绕过门禁」——门禁判的是**本批交付那一版的代码**，把别人未提交的在飞件读成我的缺陷，
   才是真正会交出假红的一扇门。
   **但这件事在本批之后变了**（写在这里免得下一轮读到的是旧状态）：STEP-R0 与 STEP-16 已于
   `b2d0b66` 入库，所以现在把 main 干净检出再跑同一台，读到的仍然是
   `FAIL 基准（未变异）就有红判据：['AF-B6', 'AF-S7']——self-test 结论不可用`
   （实测于 `61358c3` 的 `git worktree add --detach` 视图，命令见 §2b 第 1／3 步）。
   也就是说：**这不再是「工作树脏」的读数问题，而是两个已入库契约互相冲突的真红**——
   任何人按 §2 的命令在当前 main 上跑 AF 台都会看到它。本包的留档证明的是
   「`1a7e37e` + 本批叠件」那一版磁盘状态（配方见 §2b），它**不**声明当前 main 的 AF 台是绿的；
   把这句话写在这里而不是藏进「留档全绿」的读数里。冲突的裁决走 §5 J-8。
2. **STEP-R0 那条第三条锚与 S2.1.4/S2.1.5 的契约有实质交叠，本机不裁决。** AF-B6 现在的断言是
   「16..45 逐档键长都返回 `None` 且 0 条 like 条件」，而 R0 的等值反查在 ≥8 字符的键上**会**返回一行源
   （它不是模糊匹配，与 §3 删掉的那条 `Source.url.like("%s%")` 不是一件事）。两种读法都成立：
   要么 AF-B6 的射程应从「返回 None」收窄到「不下发模糊匹配」，要么 R0 需要在 S2.2 的规范键落地后
   再谈第三条锚。本机既不改判据去迁就未提交的他人代码，也不替对方步骤判定它越界——
   交 STEP-R0 的负责人与 D-V2-01/S2.2 一起拍板，登记为 §5 的 J-8。
   **这一条的措辞也要跟着事实 1 改**（第十六轮复核 C3）：原文写「本机既不改判据去迁就**未提交的**
   他人代码」——R0 已随 `b2d0b66` 入库，「未提交」这个前提不复存在；立场不变，但理由从
   「不迁就在飞件」换成「不替已入库的另一个契约单方面改自己的判据」。
3. **「本步新增」这四个字在多方并发入库之后已经不成立**，而且这件事现在是**已入库状态**而不是在飞件。
   原写法是「`git ls-files --others` 把别人未跟踪的 `test_*.py` 也算进本步新增，所以在脏工作树上会误点名」——
   STEP-16 那份文件随 `b2d0b66` 入库之后，它变成了 `git diff 65f508b..HEAD --diff-filter=A` 的**真新增**，
   于是这条误点名在干净检出的当前 main 上也照样出现。实测（`61358c3` 的 detached worktree，直接调本包两张判据）：
   - `registry_drift(...)` ⇒ `本步新增了 apps/api/tests/test_alerting_default.py 却没登记进 STEP_NEW_TEST_FILES`
     ——它不是本步的文件（STEP-16 的告警默认姿态用例，不碰本步任何一个被证对象）；
   - `db_pointer_missing(...)` ⇒ 2 条未登记，都在**本步那份文件**里：
     `test_kb_multisource_anchor.py::test_short_key_does_not_trigger_asset_reverse_lookup` 与
     `::test_asset_reverse_lookup_recovers_biz_keyed_source`（STEP-R0 加的两条连库用例）。
   这两条红**都不是本批的缺陷**，但也**不能靠改判据名把它糊过去**。留下的口径是：
   ①本包的留档按 §2b 在「本批那一版磁盘状态」上打，这是它声明的范围；
   ②当前 main 上跑本包会红的那两条，是**跨步骤所有权**问题——把自己的指针表当成全仓库用例登记表，
   等于替别人的步骤认领「去哪儿跑」；把别人的用例排除在表外，又正好是这条门禁当初要防的「不登记就绕开」。
   两个方向都不对，需要的是一次显式裁决（谁的用例进谁的表、并表的那条命令是什么），已登记为 §5 的 J-9。


`kb.py`/`asset.py` 的语义本批**未动**（动的是证明层与连库用例的参数化）：现读
`git show --stat <本批提交> -- apps/api/app` 为空（`git diff <提交> -- <路径>` 在这里会给假读数，见 §7 那条）。本机可跑的门：AF 台 `--self-test`、
BD 台 `--self-test`、驱动 `--self-test`、电池 `mutate_replay_r9.py`、整份重放——条数与发数一律看各自末行打印。

## 4.18 提交前自查（未等复审）——本机那张静态表的 E501 **单位**错了

第十六轮两份复核还在跑，这一格是本机自查先抓到的，性质与 §4.9 同族（不等别人来打）。
对象是 G 段门禁依赖的 `EVD-V2-00/g24_static_check.py`，它是本包「合计违规 0 条」这句话的唯一来源。

| 项 | 现象 | 复现（仓库根，现读） | 落点 |
|---|---|---|---|
| 单位 | 本表 E501 按 `len(line)`（**字符数**）判，而 ruff 的 120 是**列宽**：East Asian Width 为 `W`/`F` 的字符占 2 列。于是 CJK 撑爆的行在本表里一律假绿——本仓的注释与判据名大量是中文，这不是边角 | `python -X utf8 -c "import subprocess,unicodedata;t=subprocess.run(['git','show','65f508b:apps/api/tests/test_env_isolation.py'],capture_output=True).stdout.decode('utf-8');l=t.splitlines()[67];print(len(l), sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in l))"` （**锚 `65f508b` 才读得到 112/134**：那一行后来被折成三行，今天同一行号读出来是 `38 38`、全文件最大列宽 102——那是修法生效的痕迹，不是锚点错了。第十六轮复核 C4 抓的是「命令指向改后的文件、句子宣称的却是改前的读数」，与 06 条 17「指错的复现命令比没有更糟」同一族） ⇒ 折行前 `112 134`；`evidence/65f508b/ruff_65f508b.txt` 那一行报的正是 `134 > 120`（两个数只有后者与 ruff 可比） | 新增 `_width()` 按列宽计，报错文案同时给两个数（`E501 行宽 134 > 120（112 个字符）`）；docstring 把「两处方向性差异」写全：pragma 那一侧本表**更严**，单位这一侧本表**曾更宽**（已修），两个「0 违规」不是同一个数 |
| 假绿的量 | 换单位后：CI 射程 `apps/api` 内新抓到 2 行、本证据包内新抓到 7 行 | `python docs/06_validation/evidence/EVD-V2-00/g24_static_check.py <那九份文件>` 折行前逐条点名 | 九行同批折行（`test_asset_fragment_guard.py:122`、`test_env_isolation.py:68`、`replay_s213.py` 四处、`prove_anchor_fallback.py`/`prove_article_identity.py`/`prove_biz_delegation.py` 各一处）；折完同一条命令报「合计违规 0 条」 |
| 自证两端 | 旧的 E501 反样本 `("E501", "x = 1  # " + "长" * 110 + "\n", False)`（119 个字符 / **229 列**）在新单位下**必须报**，却被登记成「绿档不许咬」——按字符数写的那对样本本身就带着同一个单位错误。实测（把改好的表拷到临时目录、直接调它的 `check()`）：`sample_old_green.py:1 E501 行宽 229 > 120（119 个字符）` | `cd /tmp/g24old && python -c "…importlib 载入 g.py…; print(m.check(f))"`（形状见左列；不落进任何在册包，`_selftest_*.py` 会写在自己那层） | 样本换成五发两单位：130 个长（两单位都该报）、60 个长（69 字符 / 129 列，**只有按列宽才报**，就是这一格从前假绿的形状）、55 个长（64 字符 / 119 列，两单位都静默）、ASCII 116/117（钉 120/121 的边界）。条数看末行「N/N 项判据两端都对」的 N，本行不抄 |
| 连带 | 这一处与本包的关系不是凑数：G 段的绿裁决、STEP-00C 卡上那句「现读该行 112 列 ≤120」、以及「`e6f7de5` 之前就已满足」那条推断，全部建立在同一张表上。**判据的读数是绿色的，不等于判据读的是同一件事** | 见 §4.17 F 组那一族的同一形状：本批改的是「字形 vs 语义」，这一格是「字符 vs 列宽」——同一族的第二个实例 | STEP-00C 卡 S0C.1.2 从 ✅ 降级并写明真相、S0C.1.3/S0C.2.3/S0C.3.1/S0C.5.1 四条**来源标错**（把有依赖环境采集的入库件写成本地读数）一并更正；大纲同五行同步 |

留档 `out_s213.txt` 因这九处折行与本表改动而**整份重打**（干净视图，配方见 §2b）：G 段那一条 `$ ` 命令不变，
被检清单也不变，变的是头部 `HEAD=` 与未提交计数那一行、以及驱动源码自身被 G 段读过的事实。

## 4.19 第十六轮复核处置：机制组（F-17-01…09）逐条复现——又是「名单差一个名字」那一族

对象是提交 `1a7e37e`（§4.17 的处置本身）＋其后的 `41b789d`。两份报告都交回了：
**机制组 4 MAJOR + 1 MINOR + 2 CONFIRMED**，**读数组 2 MAJOR + 5 MINOR**（读数组那一半落在 §4.18 与 §2b）。
下面每一格都在本机复现过；号数一律现读（判据/变异/等价三个基数看 AF 台 `--self-test` 末行，
发数与覆盖看电池 `N-总`/`N-覆`）。

| id | 现象 | 复现（实得读数，本机跑的） | 落点 |
|---|---|---|---|
| F-17-01 | **模糊匹配走 `.op(变量)`**：`_OP = "like"` 之后 `Source.url.op(_OP)(f"%{key}%")`，外面再套一层 `article_key == <22 字符魔数>` 的门——`_calls_any_like` 认的是 `.like` 字形与 getattr/attrgetter/methodcaller 三种拼法，这个形状一样不沾；而 AF-B6 的行为面**永远喂不到那个魔数** | 临时副本注入后整台跑：`致红 ['AF-S1', 'AF-S6']`（行为面不红，这是**实测**而不是推断——把期望写成三条就是凭想象读数） | `_calls_any_like` 加第五认：`.op(模式串)`——字面量按内容判，**拼不出来（变量/表达式）按可疑算**（fail-closed）。一发变异，期望集合只写实测到的那两条 |
| F-17-02 | **同族谓词 `.contains(...)`**：既不产生 `like` 字形也不是 `op` 拼法，旧名单里没有它 | `致红 ['AF-B5', 'AF-B6', 'AF-S1', 'AF-S6']` | 同一处补 `_FUZZY_ATTRS`（like/ilike/notlike/contains/startswith/endswith 一族，按**会渲染成 LIKE 的谓词**这一语义列）；行为面这一发也红（键长门 `>8` 被 16..45 的扫描撞到，见下一行） |
| F-17-03 | **守卫体内走 legacy ORM**：`self._session.query(…).filter(….contains(…)).first()`——第十五轮那版「守卫体内不许有查询构造」是**黑名单**（select/execute/scalar/scalars/like），这一族一个都不沾 | 变异整台跑：`致红 ['AF-A3', 'AF-S3']`；改判据之前同一发是全绿 | 从「列黑名单」翻成**列白名单**：守卫体内除了 `len/str/repr/bool/int/isinstance/hash` 与后缀 `warn`/`warning` 的调用，**任何 Call 都算第二条兜底**。行为面补一条 `a--b` 样本（短、带 `-`），legacy 那条分支一开就被 A3 抓住。配一发等价：`min_len=MIN_FRAGMENT_LEN` → `min_len=len("12345678")`（同一个整数 8，白名单认的是语义不是字面） |
| F-17-04 | **原生 SQL 兜底**：`text("SELECT … WHERE url LIKE '%{key}%'")`——完全没有 Attribute，五种拼法全看不见 | `致红 ['AF-B6', 'AF-S1', 'AF-S6']` | `_calls_any_like` 第六认：`text(...)` 整句 unparse 后含 `like` 字样就算（原生 SQL 的**引擎语义**这台机器读不到，那条留给 J-6/J-7，这里判的是「有人把模糊匹配写回了 SQL 字符串」这件事本身） |
| F-17-05 | **交付门：多 for 的推导式**——`defects += [d for d in g_defects for _ in ()]`，名字在场、门在场、值恒空；旧写法只拒「带 if 的推导式」 | 电池那一发 `应 RED 实 RED`（改判据之前报告里那发是 rc=0） | `_merge_targets` 的 harvest 加两条：`len(generators) > 1` 算可疑、遍历**空字面量**也算可疑 |
| F-17-06／07 | **sink 的两种新形态**：`fh = OUT.open("w")`（属性形态的开句柄）与 `print("坏留档", file=…)`——`_sink_line` 只认裸 `open(...)` 的名字形态，于是「门排在第一次落盘之前」那条顺序判据把这两发读成「门在前」 | 两发各 `应 RED 实 RED`（红在『交付门』组） | `_sink_line` 补 Attribute 形态的 `.open(mode)` 与带 `file=` 的 `print`；两条各配一发变异 |
| F-17-08 | **收集面还差三块**：`class UTHelper(unittest.TestCase)` 里的 `test_*`（pytest 对 TestCase 子类**不看类名**照收）、`for` 循环体里的 `def`、`match/case` 体里的 `def`；反面是 `class TestHasInit` 带 `__init__`（pytest **不收**有构造器的类）却被要求登记 | 改判据之前那两条绿档判据不存在；之后现读 `python docs/06_validation/evidence/EVD-V2-02/replay_s213.py --self-test` 末行那句「N 条反证全过」的 N（本批加了一条绿档核对，N 随之变——条数不抄在这里，抄一次就旧一次） | `_collect_cases`：认 `bases` 里以 `TestCase` 结尾的类、遍历 `For`/`While`（含 `orelse`）与 `Match` 的各 `case` 体；同时补「`Test*` 且有 `__init__` ⇒ 不收」这一侧的**绿档**判据。M 段为此把探针树扩到这三种形状并新增一条绿档核对；电池配五发（口径过头、丢 `__init__` 例外、
    丢 TestCase 例外、丢 `for/while` 遍历、丢 `match/case` 遍历）+ 一发等价 |
| F-17-09（MINOR） | **拼出来的名字**仍是盲区：`exec(f"async def get_by_url{SUF}(…)")`、`nm = "".join([...])` 再当字典键——上一版把这件事写在 §7 让读者自己推，判据名里却没有 | 报告里那两条探针：`f-string → hits: []`、`split-join + 变量键 → hits: []` | **不改判据**（真要在扫描器里还原拼名，就得执行任意字符串，那是把门禁变成攻击面）。改的是**声明**：AF-S5 的判据名里现在直接写着「**明认盲区**：拼出来的名字不在射程内，那一族要么 exec 时炸成 INCONCLUSIVE，要么交 J-6/CI」 |
| CONFIRMED-1 | E-15-05 那条「对账扫描面本身」是**可假且不自证**的：应扫集合从 `EV_PY` 现取，缩面与掏空两侧各有变异打中，`EV_PY` 自己又被 N-43 与 G 段的目录双向核对钉住 | 报告原样跑的电池：`N-97 应 RED 实 RED …｜应红在『轮次自指』组`、`N-43`/`N-99` 同款 OK | 无需改动。**这一格顺带把上一版的说法证死了**：拿 `face` 对账 `face` 确实会两边一起变小 |
| CONFIRMED-2 | 电池与四道门的完整性：126 发全落在期望档、覆盖按 `--list-checks` 现算、无「锚点漂了」注销行 | 报告末行逐字 + 本机复跑一致 | 无需改动；但 F-17-01～05 说明「这一批的靶全中」与「下一族的形状在门外」两件事同时成立 |

AF-B6 的取样口径这一批也换了：**四档手挑键长（18/19/25/41）换成 16..45 逐档扫**。
手挑那一版的问题不是挑得少，而是**样本集合在替判据说话**——`== 22 字符` 那一档恰好不在里面。
剩下的格子写进 §7，不假装关掉了：①内容等值门（`if key == <魔数>`）只有喂进那个魔数才会在行为面出声，
样本无法穷举 ⇒ 该形状只能由静态面兜，而静态面认到「谓词族 + 可疑 `.op`」为止；
②守卫白名单是**故意**fail-closed 的（把 `logger` 改名成 `_LOG` 会红，因为 exec 的世界里没那个名字，
也因为白名单不认没见过的名字），代价是将来守卫里真要用别的无害函数时必须显式改这份口径——
与 BD-12 同一处理，读成「宁严勿宽的显式契约」而不是「合法形状的完备刻画」。

## 4.20 第十七轮自查（未等复审）——一条恒红的用例，和一条当时不存在的判据

两份第十六轮复核还在跑的时候，本机先抓到自己交付里的一条真缺陷，而它**不在**任何一份复核的范围里：

| 项 | 现象 | 复现（现读） | 落点 |
|---|---|---|---|
| 恒红用例 | S2.1.5 交付的 `apps/api/tests/test_asset_fragment_guard.py` 里「机器门③」断言的是 `str(stmt.compile())` 渲染文本中的**字面值**（`source_id = 'src-1'`、`LIMIT 1`、`%aaaa1111%`），而 SQLAlchemy 默认方言把值渲染成绑定参数（`:source_id_1`、`:param_1`）⇒ 在任何环境都红 | 红证是别人采的：`docs/任务规划V0.8.0/evidence/61358c3/pytest_local_noPG.txt` 里逐字 `tests/test_asset_fragment_guard.py:143: AssertionError`，同份合计 `1 failed, 640 passed, 421 skipped`。本机无 sqlalchemy/pytest-venv，跑不了这条用例（这正是 §5 J-7 交接的那一半） | 修法照 V0.8.0 STEP-00C 卡 S0C.1.2：假会话改 `str(stmt.compile(compile_kwargs={"literal_binds": True}))`（值内联进文本，三条断言才谈得上可满足）。**终判在对方卡上**（其 S0C.1.1 先复现、S0C.3.2 全量回归、S0C.3.3 推送后看 CI），本包不替别人宣布转绿 |
| 判据不存在 | 为什么十六轮都没抓到：所有反证都在问「已有判据能不能红」，没有人问「这一**类**形状有没有被判过」。而且 pytest 停在第一条失败 assert，所以 `:144`、`:145` 两条同类问题连露面的机会都没有——**一条恒红的断言会遮住它下面的同类错误** | 用新判据回打改前那一份（`git show 0e870d1:apps/api/tests/test_asset_fragment_guard.py`）：三条全部点名（`old.py:143/144/145 对 compile 渲染文本断言字面值 …`）；对修好的那一份：零条 | 新增 `sql_render_defects()`（AST 污点分析）：①假会话里 `self.calls.append(str(stmt.compile()))` 这种**源头**也要认（第一版只认 `def scalar` 不认 `async def scalar`，整条链从源头就断了）；②污点沿赋值与「在受污名字上调方法」两跳传播（只认第一跳 = 没判）；③字面量含 `=`/引号/`%…%`/**任何数字**即算断言的是值（纯关键字如 `LIKE` 不含数字，分得开）；④带 `literal_binds` 的渲染**豁免**——否则判据会把自己给的修法判成缺陷（这是假红方向，同样配了靶）。它接进 G 段交付门；M 段渲染探针条数与电池发数**一律现读**
（现读两条：`python docs/06_validation/evidence/EVD-V2-02/replay_s213.py --list-checks | grep -c 渲染文本判据/`
与留档 N 段末行 `N-总`；第十八轮 R18-09 抓到本节上一版把这两个数写成了「四档 / 六发」，实测当时已是
5 档 / 7 发——自查自己的计数也会抄错。**第十九轮记账组又把这条命令本身判红了**：一是路径写成裸的
`python replay_s213.py`，在仓库根跑不动；二是 `grep -c 渲染` 数的是 prose 里出现的「渲染」二字，
与检核条数无关。所以这一族的检核名从第十九轮起统一带 `渲染文本判据/` 前缀，计数命令换成上面那条） |
| 归属重叠 | 这条文件同时是 V0.8.0 STEP-00C 卡「允许修改」集里的唯一文件（`steps/STEP-00C-CI后端回绿-测试断言可满足化.md:12`），即**两个步骤对同一份文件都有主张** | 现读：`grep -n "允许修改" docs/任务规划V0.8.0/steps/STEP-00C-*.md` | 本包只做「按对方卡面 S0C.1.2 那一行的形状落地 + 补类级判据」，不改断言风格、不动别的用例，避免与对方步骤的修法打架；谁收口 CI 读数仍归 V0.8.0 那张卡 |

一句 generalization 抄进 `06-执行记录.md` 第 21 条：**判据的覆盖面等于上一轮想到的形状**；
凡是「这条用例本机跑不了」的交接，都要同时回答「它断言的东西有没有一条静态判据在看着」。

## 4.21 第十八轮复核处置：R18-06…10（新判据自己的两端）

对象是提交 `f97ae53`（§4.20 那条自查本身）。复核交回 **5 CONFIRMED + 4 MINOR + 1 静态核**，
逐条本机复现后成立 4 条、确认 2 条。判据加进去的那一轮往往就是它自己最弱的一轮——
下面四格全是「新判据的豁免面/传播面写宽或写窄」。

| id | 现象 | 复现（本机跑的） | 落点 |
|---|---|---|---|
| R18-06 | 值形状那一格含「任何数字」，于是 `assert ":param_1" in sql`、`"sha256" in sql`、`"api_v2" in sql` 这些**在默认方言下其实正确**的断言也被点名 | 三段源码直调 `sql_render_defects`：各 `1 defect` | **不放宽**，按「宁严勿宽的显式契约」记：docstring 里现在写着这三类会被多问、放行它们属改契约（与 BD-12 同一处理）。放宽与收紧的差别是有没有把它写成读数——旧版只写了「纯关键字不含数字，分得开」，那是不完全的声明 |
| R18-07 | 豁免面宽于声称：旧写法看「任一关键字的值里含 `literal_binds` 字样」，于是 `compile(**{"literal_binds": True})` 与 `compile(dialect="literal_binds")` 也被放过——**这两种写法根本不内联值**，放过就是放过恒红 | 两发直调：各 `0 defects`（旧版）；改后各 `1 defect` | 豁免改为只认 `compile_kwargs` 这一个通道（关键字或位置第二实参）。M 段加一条「假豁免必须点名两发」探针；电池两发：把豁免退回旧口径（红）、把豁免整格拿掉（红，防它把修法判成缺陷）、位置实参判定换写法（必须绿）。**两处勘误（第十九轮）**：①「电池两发」下面列了三发，实际本批发的是 5 发（4 红 / 1 绿），而「注解放宽」那发属于 `f710ce9` 而不是本批——现读用 `git diff --stat f97ae53 0e870d1 -- docs/06_validation/evidence/EVD-V2-02/mutate_replay_r9.py` 与电池末行 `N-总`，别再抄发数；②**位置第二实参那一格已从「豁免」改成「不豁免」**（机制组 M3：本机不装依赖，核实不了 SQLAlchemy 2.0 的形参槽位，「核实不了的写法一律放行」等于自己拆门禁），所以那条 GREEN 现在测的是别的等价写法 |
| R18-08 | 污点只认 `=` 赋值：`if (sql := str(q.compile())):`、`for sql in [str(q.compile())]:` 之后那条断言就隐身；助手函数返回渲染文本、f-string 作左值也漏 | 四发直调全 `0 defects`；内联海象与推导式里的赋值则 `1 defect` | 补 `ast.NamedExpr` 与 `ast.For`/`AsyncFor` 两种绑定（各配一发变异 + 一条 M 段探针）；**跨文件辅助函数与 f-string 左值明认为边界**——那要全仓过程间分析，代价与收益不匹配，docstring 里写着留给 J-6/J-7 与 CI。这一格还揪出**探针自己的分辨力缺陷**：判据按名字记污点、不分作用域，两段探针都叫 `sql` 时关掉任一分支缺陷数仍是 2（两发变异都测不出差别，本机实测 2/2/2）；分名 `sql_w`/`sql_f` 之后才是 2/1/1。同一个性质的另一面就是**过判**：跨函数同名会把干净的引用一起点名，这条也写进了 docstring |
| R18-09 | §4.20 那格写「M 段四档探针、电池六发」，实测当时是 5 档探针 / 7 发——**自查自己的计数也抄错了** | `python docs/06_validation/evidence/EVD-V2-02/replay_s213.py --list-checks \| grep -c 渲染文本判据/`、留档 N 段末行 `N-总`（第十九轮勘误：上一版这里给的是裸路径 `python replay_s213.py` 加 `grep -c 渲染`，前者在仓库根跑不动、后者数的是 prose 里的两个字，都不构成读数） | 本节与 §4.20 里这两处计数一律换成命令；判据条数、发数、覆盖三个数都不再出现在正文 |
| R18-10 | 锚点承重静态核：7 个新锚在驱动里各命中 1 次、期望值形状合法；漂移不会静默（`mutate_replay_r9.py` 的 `锚点漂了，这条反证已注销` 那一档） | 报告直调 + 本机复跑 `SHOTS` 全量锚计数：145 发里仅 2 个锚出现 2 次，且**都是历史那两发**（`stage()` 取首个匹配，行为确定） | 无需改动；这一格记下来是为了让下一轮知道「锚计数」这件事是可查的，而不是「锚都在」的一句声明 |

四格的共同形状与 §4.19 同源：**新写的判据默认会把自己没想到的一端留空**（豁免太宽、传播太窄、
契约太严却没声明）。所以本批每条落点都带一发「退回旧口径」的变异——判据的强度由它能被怎样削弱来定义。

## 4.22 第十九轮复核处置：机制组四格 + 记账组四格（同一条判据的两种撒谎方式）

对象是提交 `2315cda`。两路独立复核各交回一份，**同一轮的同一族**：机制组量的是
「判据说自己管这一族，实际只管了一个字形」，记账组量的是「文档说自己是机器生成的，实际没有任何
一条命令能证伪这句话」。前者的四条我在本机直调复现（探针在临时目录，不动在库件），后者的四条
用命令复现——两边都成立，所以两边都改了实现而不只是改了措辞。

| id | 现象 | 复现（现读） | 落点 |
|---|---|---|---|
| R19-M1 | 渲染判据只认 `Assert ∧ In ∧ 左操作数是常量`。同样恒红的 `sql == "… = 'src-1'"`、`re.search("= 'x'", sql)`、`sql.find(…)`、`if "x = '1'" in sql: raise` 全部隐身；而 `assert "…" not in sql` 更坏——它**恒绿**，只会好看 | 八段源码直调 `sql_render_defects`：加固前全 `0 defects` | 判据按**语义**重写：比较整族（`in/not in/==/!=/` 四个大小比较，见 `_CMP_HOW`）、取段方法族（`_READ_TEXT_METHODS`）、`re` 的匹配族、且不再要求外面套 `assert`；字面量写在哪一侧同判 |
| R19-M2 | 污点只认函数内的 `=` 赋值：`self.sql = str(q.compile())`、推导式目标、以及**同模块辅助函数把形参拿去比字面值**（调用点传渲染文本）都漏；假会话那条链还要求方法名**恰好叫 `scalar`**，夹具改名整条链失效 | 同上直调：属性目标 / 异名形参 / `def execute` 三发各 `0 defects` | 属性目标与推导式目标进绑定面；append 的识别改认「把渲染文本塞进某个属性列表」这件事本身，与宿主方法名无关；同模块跨函数用 `guarded` 名单接上。绑定改为**先扫到不动点**——第十八轮那条「探针必须换变量名」的教训本来就是这一格的副作用，顺序从此不影响读数（M 段有一发专测正序=倒装） |
| R19-M3 | 豁免按**子串**判：`compile_kwargs={"literal_binds": False}` 被放过（False 就是默认方言，那句断言恒红），位置第二实参也被放过（本机不装依赖，核实不了 2.0 的形参槽位） | 直调两发各 `0 defects` | `_exempt` 改成读**字典字面量的值**且只认 `literal_binds=True`；位置槽那一格按 fail-closed 删掉（它现在是缺陷，装依赖的连库面 J-6 可以把它证伪）。docstring 把这两条写成边界而不是沉默 |
| R19-M4 | 扫描面 = 本步登记的三份文件。`apps/api/tests/test_hot_scorer_batch.py:44` 同样在假会话里 `str(stmt.compile())`，却在面外——**没人检查过它是不是缺陷**，而 §4.20 那句「这一类封死了」听着像封了全仓 | 现读 `python …replay_s213.py --self-test` 里「文档面/扫描面」那一档的读数；全仓现扫 `grep -rln '\.compile(' apps/api/tests/` | 新增 `sql_scan_face()`：面 = `apps/api/tests/*.py` ∪ 真库目标 ∪ 本步新文件（份数由门自己现读，不抄）。当前全仓命中为零——这是**读数**，不是推断：`test_hot_scorer_batch.py` 只判结构关键字（`startswith("UPDATE")`，不带值形状），M 段专门配了一发绿档钉住「不许咬它」 |
| R19-A1 | `判据迁移清单.md` 表头带时间戳 ⇒ `--write` **永远不可能**字节幂等，于是「这张表是机器生成的」不可证伪；同一批发还量出 92 行的 `行` 列记的是提交前的中间态 | 报告在内存里重跑 `--write` 并与盘上那份比（差异 = 1 行时间戳 + 92 行 `行` 列） | 产物改成**当前树的纯函数**（时钟拿掉），并新增 `extract_checks.py --check`：重跑提取、与盘上那份逐字节对账，不一致 rc=1 点名哪几行。`行` 列的口径写在表头（「生成本表那一次的行号」），过期从一句提醒变成一个读数。**本轮内又红了两次**——每改一次 harness，锚就漂一次，所以最终那份是全部代码改动落地之后重新 `--write` 的 |
| R19-A2 | `06-执行记录.md` 里 `f710ce9` 那行的两条验收命令读的是 `git show <sha> --format=%B -s`（**提交说明**），而它要证的结论在**文件**里；两条都读出 0，等于把「已补回」写在一条不会红的命令上 | 报告实跑：两条 `grep -c` 对提交说明 = 0/0，对该文件 = 1/1 | 命令换成 `git show <sha>:<路径>`，并在账上就地记「上一版读错对象」（历史结论不改写，只把尺子换对） |
| R19-A3 | `2315cda` 已入库并已推送，账上那一行却还是「（本行之后）… 待提交」——占位行没转换，等于账比仓库慢 | 现读 `grep -n '待提交' docs/任务规划V0.5.0/06-执行记录.md` 与 `git log --oneline -1` | 占位行转成锚定行，验收列只给可重跑命令（号数不抄） |
| R19-A4 | `S0T.1.1` 这个编号在 V0.6.0/V0.7.0/V0.8.0 三册里**同号不同义**：V0.8.0 的 STEP-00T 卡把它定义成「列出全部判据函数」，状态 ⚪ 未开始，归属执行 Agent，且它的「允许修改」集**不含**本目录 | 现读 `grep -n 'S0T.1.1' docs/任务规划V0.8.0/steps/STEP-00T-*.md` 与各册同名行 | 本卡把「已交付」限定在 **V0.5.0 的编号空间**，并在卡面写明跨册同号不同义这件事（谁收口 S0T 仍归对方卡）——不替别人宣布、也不让别人替我宣布。这一条同时进 §5 的 J 表 |

一句 generalization 抄进 `06-执行记录.md`：**判据认字形不认语义，文档认声明不认产物**——
同一轮里机制组与记账组抓到的是同一件事的两面：一条命令/一句话如果不能被一个具体的坏形状判红，
它就还没有被写下来。所以本批每条落点都同时配「退回旧口径」的变异与「不许咬正当写法」的绿档。

### 4.22.1 两件发生在处置过程中的事，按原样记

**其一：交付门本轮拦住了落盘，`out_s213.txt` 因此不是本批的读数。**
本批评据与文档落完后，在 `2315cda` 的干净视图上重放（`git worktree add --detach … 2315cda` +
只覆盖本批那九份文件），驱动在第一道交付门就拒绝落盘，三条 `FAIL 交付` 全部点名 `b2d0b66`
（STEP-R0/STEP-16）带进来的用例：两条在我自己那份 `apps/api/tests/test_kb_multisource_anchor.py` 里
（`test_short_key_does_not_trigger_asset_reverse_lookup`、`test_asset_reverse_lookup_recovers_biz_keyed_source`，
它们确实引用本步符号 `_find_source_by_anchor` 与 `MIN_FRAGMENT_LEN`），一条是
`apps/api/tests/test_alerting_default.py` 整份未登记。这正是 §5 **J-9 那条待裁决**的条件本身：
本包既不把别人的用例写进自己的指针表（那等于替它们认领去向），也不把表 scoped 到刚好绿
（那等于注销这条门禁当初要防的「不在表里就没人判」）。于是：
- 盘上那份留档的**自报基准**是 `head -2 docs/06_validation/evidence/EVD-V2-02/out_s213.txt | tail -1`
  里那个 `HEAD=`（本轮读到的是 `1a7e37e`，即 R0 并入**之前**的视图）；§2b 那句「第七轮起整份重放」
  本轮第一次不成立，**不成立的原因是门禁拦住落盘，不是我把判据改成刚好通过**。
- 本批的判定力只有两条现读通道（都要在干净视图上跑，脏视图会让基准自带红，见 §2b 与 §4.17 环境事实 1｜2）：
  M 段 `python docs/06_validation/evidence/EVD-V2-02/replay_s213.py --self-test` 末行那句「N 条反证全过」，
  N 段 `python docs/06_validation/evidence/EVD-V2-02/mutate_replay_r9.py` 末行 `N-总`。条数与发数不抄在这里。
- 解除阻塞的动作不在本包手里：J-9 拍板之后才会落新盘，同一拍板连带 `REAL_DB_TARGETS` 与 R0 那两条用例的
  口径对齐（J-8）。

**其二：我这轮新写的探针自己把电池跑崩了一次，判据没坏、探针坏了。**
第一版文档面探针用 `shutil.copytree(PLAN_DIR, …)` 复制**真实规划树**再注入坏形状，而电池把 harness
暂存进一个只含本包内容的目录——那里没有 `docs/任务规划V0.5.0/`，`copytree` 直接抛
`FileNotFoundError`，整趟 `--self-test` 变成 traceback，N-00 于是按纪律报
`INCONCLUSIVE 基线副本不绿（rc=1）：一条可读裁决都没有` 并让整批不作数（而不是把 145 发的「红」收下）。
改成**自带一棵最小合成树**（大纲三份行 + 两张卡，含一张 `STEP-00C` 用来钉前缀映射）之后同一批探针
在任何树上都判得成。**这一格与 §7 那条「扫描面按目录取、不按登记名单取」是同一件事的另一面**：
取证工具能跑在哪里，是它的契约的一部分，不是环境巧合。顺带还留了一条更硬的操作教训——
本轮一次替换脚本把起始锚写成了一句会被别处匹配到的短前缀，静默吃掉了约 1100 行；
恢复用的是干净视图里那份覆盖前的副本（哈希比对后回抄），此后所有整文件替换一律加两条断言：
**被替换区间的行数落在预期窗口内**、**结果总行数不偏离基线太远**，两条不成立就不写盘。

## 5. 交人工 / 有依赖环境的项目

| # | 项 | 为什么本机不能做 | 命令 |
|---|---|---|---|
| J-1 | 卡面原验收命令（带覆盖率门禁） | 无 `uv`、无 `pytest-cov` | `cd apps/api && uv run pytest tests/test_article_identity.py -q --cov=app.services.article_identity --cov-fail-under=100` |
| J-2 | ruff I001 终判 | 无 `ruff`（本机只有 `g24_static_check.py` 的等价静态检查报 I001） | `cd apps/api && uv run ruff check app tests` |
| J-3 | `idx=%20`、参数名大小写、`/S/` 大写路径三条口径 | 需微信真实抓取样本，本机不抓取（不启服务） | 对现有 `Source.url` 样本跑 `parse_wechat_url` 分布，交 STEP-06/07 |
| J-4 | 全量连库回归（S2.3） | 需隔离 PG16@5547 | 见 STEP-00R §4 H-2 的 `test-env.sh env` 链 |
| J-5 | `tests/test_kb_longlink_ingest.py` 的 pytest 实跑（S2.1.3 的用例面） | `kb.py:22-25` 模块级 import structlog+sqlalchemy，本机收集期即失败（实测 `out_s213.txt` D 段）；本机侧只由通道 C 承担 | `cd apps/api && uv run pytest tests/test_kb_longlink_ingest.py tests/test_article_identity.py -q -k biz` |
| J-6 | `tests/test_kb_multisource_anchor.py` 的 pytest **连库**实跑（S2.1.4：P-4 转正 + 锚定顺序） | 同一原因（收集期即失败）+ 需要隔离 PG；本机侧由 O 段那台假会话承担，它只证「生产代码向 DB 要了什么」，不证 SQL 引擎侧真跑 | `eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_kb_multisource_anchor.py -q` |
| J-7 | `tests/test_asset_fragment_guard.py` 的 pytest 实跑（S2.1.5 的用例面，**不连库**） | 与 J-6 不同一件事：这四条用假会话记录「有没有把 SQL 发出去」，判据是收集期就要 `structlog`+`sqlalchemy`（本机连收集都过不去），但它**不证** SQL 引擎侧真实执行——那半在 J-6/J-4。本机侧形状由 O 段 AF-A1…A5 承担 | `cd apps/api && uv run pytest tests -q -k url_fragment` |
| J-8 | **STEP-R0（V0.7.0）那条第三条锚与本步契约谁让谁**：R0 在 `_find_source_by_anchor` 里加了 `ContentAsset.external_id == article_key` 的等值反查（带 `len(article_key) >= MIN_FRAGMENT_LEN` 守卫与 `status=="READY"` 谓词），而本包 AF-B6 断言的是「四档键长都返回 `None` 且 0 条 like 条件」——等值反查不是模糊匹配，但它**会**返回一行源，于是 AF-B6 在含 R0 改动的那份磁盘上判红 | 本机既不替别人的步骤判定它越界，也不把自己的判据改成刚好通过未提交的他人代码（那等于拿别人的在飞状态给自己背书）。两档读数见 §4.17 环境事实 1｜2：干净视图 `SELF-TEST PASS`、脏工作树 `FAIL 基准（未变异）就有红判据：['AF-B6','AF-S7']` | 交 STEP-R0 负责人与 D-V2-01/S2.2 一起拍板。① 若第三条锚属 S2.1.4 契约的**合法扩展**，AF-B6 的断言应收窄成「不下发任何模糊匹配（like）」，§1 那句「兜底已删」的措辞同步改；② 若规范键（S2.2）才是这条路的正解，R0 那一半应等 S2.2。两种拍板都要求先把 `apps/api/tests/test_kb_multisource_anchor.py` 里那两条 R0 用例与本包 `REAL_DB_TARGETS` 的登记口径对齐。**状态更新（同批收尾时）**：R0 与 STEP-16 已于 `b2d0b66` 入库，那两条用例现在是**已提交**的磁盘事实——本包的用例级门禁（`db_pointer_missing`）因此会在含 R0 的树上点名它们未登记。这不是要我把别人的用例塞进我的指针表（那张表登记的是**本步交付**的去向，把别人的用例写进去等于替它们认领去向），而是 J-8 拍板之后必须一起做的一次对账 |
| J-9 | **跨步骤的用例所有权：别人的用例进不进本步的指针表**（第十六轮批次收尾时新增，由 §4.17 环境事实 3 那两条实测红引出） | 本机两个方向都不肯自己拍：把 STEP-R0/STEP-16 的用例登记进 `REAL_DB_TARGETS`／`STEP_NEW_TEST_FILES`，等于本步替它们认领「去哪儿跑」，而它们一旦改名或回退，本包的门禁会替别人的步骤红；把它们排除在表外，又正好复刻这条门禁当初要防的那件事——「不在表里就没人判」。现读（`61358c3` 的 detached worktree，直接调本包两张判据）：`db_pointer_missing` 报 2 条未登记（都在本步那份 `test_kb_multisource_anchor.py` 里），`registry_drift` 报 `test_alerting_default.py` 未登记 | 需要一次显式裁决。建议方案：①按**被证对象**划范围——只有引用本步符号（`_find_source_by_anchor`／`get_by_url_fragment`／`MIN_FRAGMENT_LEN`／`parse_wechat_url` 等）的用例文件才算「本步新增」，其余作为**读数**打出来而不算缺陷；②或给别的步骤开一张**代管表**，登记但注明所有权在对方。裁决归 D-V2-01／S2.2 那一层与 J-8 一起做；本批先在 §2b 的干净视图上交付，不用改判据来消除这条红 |

| J-10 | **编号跨册同号不同义：`S0T.1.1` 在 V0.5.0 与 V0.6.0/V0.7.0/V0.8.0 里是两件事**（第十九轮记账组 A4 抓到，本批在 `docs/任务规划V0.5.0/steps/STEP-00T-*.md` 卡面记了边界，但不替对方判定） | V0.5.0 的 `S0T.1.1.1` 已交付＝「用 AST 从在库证明件提取判据清单、且产物与当前树可逐字节对账」；V0.8.0 的 STEP-00T 卡把 `S0T.1.1` 定义成「列出全部判据函数」，状态 ⚪、归属执行 Agent，且其「允许修改」集**不含** `docs/任务规划V0.5.0/evidence/S0T/**`。两册各自收口会给出不一致的「S0T 做完了没」，而这件事本机无权裁决（谁 owns S0T 是规划方的分配，不是取证） | 现读：`grep -n 'S0T\.1\.1' docs/任务规划V0.8.0/steps/STEP-00T-*.md` 与 `grep -rn 'S0T\.1\.1' docs/任务规划V0.6.0 docs/任务规划V0.7.0`。需要一次归一：①或把本计划里的这段改名（例如 `S0T-V5.1.1`）并在两侧卡面互指；②或 V0.8.0 那张卡显式声明它采信本包产物并接手人工两列。在归一之前，本包只在**V0.5.0 的编号空间**内声明交付，卡面那句话就是这么写的 |

## 6. 范围与偏离声明

- 本包交付 **S2.1.1 + S2.1.2 + S2.1.3 + S2.1.4 + S2.1.5**（第十三轮起）。改动面与读数都现读，
  本节不抄号数：
  `git diff --stat 78e3378 078dc30 -- apps/api/app/services/kb.py apps/api/app/repositories/asset.py`
  给出生产侧两份文件的两段账（**两端都要写**：单端形式 `git diff <提交> -- <路径>` 比的是**工作树**，
  第十六轮复核实测它在有别人在飞件的树上给 `75 ++ / 25 --`，而双端形式给 `37 ++ / 20 --`——
  差的那一节正是别人未提交的第三条锚，见 §4.17 环境事实 1）。S2.1.3 那一 hunk 只碰 `_biz_from_url`，
  S2.1.4 那一 hunk 只碰 `_find_source_by_anchor`，S2.1.5 在 `asset.py` 的 `get_by_url_fragment`
  与模块级阈值常量；
  `_article_key`（`kb.py:554`）与规范键 **未动**，那属 S2.2（阻塞于 ADR-0011 / D-V2-01）。
  从前这里写过「S2.1.4/S2.1.5 未做（`asset.py` 零改动，复审 G 段独立确认）」——那句话在第十三轮
  之前是真的，现在由上面那条命令取代；两点读数口径的老教训仍然成立：①「一个 hunk」只在
  **默认上下文**下成立，`-U0` 会因 docstring/导入块与 return 行之间的空行拆成 2 个 hunk；
  ②`grep -c '^-'` 会多算 `--- a/…` 文件头那一行，以 numstat 为准。
- S2.1.4 的「P-4 转正」用例落在 **`test_kb_multisource_anchor.py`**（卡面 S2.1.4.1 点名的文件名），
  不是 `test_kb_longlink_ingest.py`。这处搬迁把两份文档的指针带歪了，已就地更正并**变成判据**：
  `replay_s213.py` 的 `REAL_DB_TARGETS` 登记「文件 + 用例名」，G 段在仓库根上按 AST 逐条核对
  确有其事，并额外判**用例级完整性**——口径在第十四轮改过一次（C 组 C-14-08）：从「顶层 `test_*`」
  改成「**pytest 真会收集的那些**」（顶层的 + `Test*` 类里的，后者登记成 `类::用例`），
  而且这份名单本身不再手抄维持：`registry_drift()` 拿 git 现取的本步新增集合与之双向对账。详见 §4.14 id 52、
  §4.15 R13A-2 与 §4.16 C8。
  **V0.4.0 的 STEP-02 卡面**（`docs/任务规划V0.4.0/steps/STEP-02-文章身份与锚定修复.md` 的
  S2.1.4 那一节）从前写着「按 V0.5.0 README 的取代关系读」——那句话指向一个不存在的取代关系
  （V0.5.0 目录下是 `00-README.md`，且它没有逐条宣布取代 V0.4.0 卡面的验收命令），
  而 `:122` 那条**验收命令**按字面跑会得到 `ERROR: not found`（B 组 R13B-15 判定为「会误导执行」
  而不是「历史账不必回改」）。现已在那两处就地插勘误注记并给出正确的命令，历史结论本身不改写。
- **四轮处置批（§4.4/§4.5 的第二轮、§4.6 的第五轮、§4.7 的第六轮、§4.8 的第七轮）都没有再动
  `kb.py`**，§4.9 的**提交前自查批**同样没动（它是证明层与运行层的改动）——那句
  `git diff c10b229 -- apps/api/app/services/kb.py` 为空是**那几批当时**的读数（第十四轮 D 组 D-14-01
  抓到本节把它写成了现在时，还带一句「本轮复跑确认」——那条命令按单端写法比的是工作树，
  第十四轮当时读到非空，而**它读到的数会随别人的在飞件变**（第十六轮 C4b 同一处给 `75 ++`），
  要复现那句历史读数请跑双端形式并锚到当时的两端：`git diff --stat c10b229 078dc30 -- apps/api/app/services/kb.py`。
  现在要说这两件事，读这两条（同样两端都写）：
  `git diff --stat c10b229 078dc30 -- apps/api/app/services/kb.py`（S2.1.4 改了它）与
  `git diff --stat c10b229 078dc30 -- apps/api/app/repositories/asset.py`（S2.1.5 新增守卫），
  取代关系写在 §4.14 开头那一句里，不在这里重复抄数。
  改动面只有 `prove_biz_delegation.py`/`prove_article_identity.py`（判据、档位、通道自守、编码自守）、
  `test_kb_longlink_ingest.py`
  （用例的第二条锚 + import 段序，第二轮改）、本 README 与 `out_s213.txt`
  （**第七轮起整份重放**，段集合不写在本节——上一版这里写死「现为 18 段：A–J 十段 + K.1–K.6 + M + L」，
  而第十一轮复审 10-5 报回它与自己同一份文档里的另一句互相打脸；现读只认留档 L 段那条
  `$ ` 命令的读数（`grep -c '^########## ' out_s213.txt` 与段字母清单），以及驱动末行的「N 行、M 段」。
  H 段是第五轮三条空过的闭合实测，
  I 段是第六轮 D1/D2/D4/D5 的，J 段是第七轮 N1…N5 的两版 harness 对照，K 段是 §4.9/§4.10 的编码崩溃面
  （K.1/K.4 裸跑、K.2/K.5 注掉 guard、K.3/K.6 抽掉靶字），M 段机检「取命令」这条通道本身，
  L 段机检每段有没有把手。之所以不「只在末尾追加一段」：判据从 15 条变 16 条之后（那对数也是 `0161bcd` 时点，现读 BD 台末行或 `--list-checks`），
  A/B/C/F/H/I 的读数本身会变——实测例是 I-2 由 `['BD-13']` 变 `['BD-13', 'BD-16']`、
  A 段由 `PASS=5 FAIL=10` 变 `PASS=6 FAIL=10`——**这两对是第七轮那批当时的读数**（锚 `0161bcd`/`d80eeaf`），现读走留档 A 段那行的 `合计 PASS=… FAIL=…`；
  而这条纪律上一轮**实际是漏的**（驱动按 `$ ` 前缀找命令、又在输出时剥掉前缀），见 §4.9 S-2）。
  harness 新增的 `--kb=<路径>` 只服务于 self-test 的子进程退出码自证，
  **默认路径仍是 `apps/api/app/services/kb.py`**，验收命令不变；第六轮起
  `--self-test` 也认这个开关（改前它恒读真实 `kb.py`，「在临时副本上自证」名不副实）。
- 新增文件都在卡面「允许修改」或「证据路径」内：`tests/test_kb_longlink_ingest.py` 是卡面
  允许路径；`prove_biz_delegation.py`、`prove_article_identity.py`、`out_s213.txt`、
  `block_article_identity_plugin.py`、`j_attack_r7.py`（J 段驱动）、`replay_s213.py`（留档重放器）与本
  README 落在证据路径 `docs/06_validation/evidence/EVD-V2-02/`。后两件是本轮由 `_workspace/` 提进来的，
  提进来才算交付，留在临时目录里只算我说过。
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
- 第十三轮那台（`prove_anchor_fallback.py`，O 段）的边界同一条，而且要说得比「它证了什么」更狠：
  它证的是**生产代码向 DB 要了什么**（假会话如实实现 `limit(1)` 截断与多行抛错），
  **不证** SQL 引擎侧真实执行、不证 commit、也不证存量库里到底有几行会撞上同一个锚——那三件事
  分别交 J-6/J-7 与 J-4。
- **一处刻意的不对称**（读者会问，先写在这里）：S2.1.5 拒绝「用 `.limit(1)` 猜一行」（短片段直接放弃
  兜底），而 S2.1.4 的两条锚查询却**正是**用 `.limit(1)` 收尾。区别在锚的**身份含量**：
  `.limit(1)` 在这里处理的是「同一 external_id 因脏数据有多行」（同身份，取哪条都对，AF-B4 判的就是
  摘掉它要抛 `MultipleResultsFound`）；而 `%s%` 匹配到的是**不同身份**的若干行（取哪条都错）。
  这个区分成立的前提是 biz 锚先命中——S2.1.3 之后长链都能解出 `__biz`，退化锚 `s` 只在
  「URL 里确实没有 `__biz`」时才轮到它。前提一旦被拆（比如有人把锚元组顺序换了、或解析层又退化），
  本包能出声的是 AF-B1/AF-S7（锚序与委托接线），而**「库里到底有多少行 external_id='s'」本机无从知道**：
  那是 J-4 的存量面，也是 STEP-07 存量审计该量的东西。
- **AF 台不判 PEP 562 那一族**（A 组 MA-2 的边界声明）：`del 模块.目标名` 之后再 def 一个
  `__getattr__` 凭空造出假实现，这类攻击在 BD 台是 J-3、有实测红；AF 台是把函数**单独 exec 进
  一个假世界**，不经过模块属性查找，所以那种手法在这台机器上根本不构成绕过。别把
  「AF-S5 现在认得 `setattr`/下标形态」读成「AF 台覆盖了所有活绑定攻击面」。
- **「交付门」那一组判的是 `main` 的形状与顺序，不是「门真的拦得住」**：它按 AST 认
  `if defects:` / `if late:` 是不是以那个名字为条件（`if len(defects) > 0:` 同权，恒假的与项单独点名）、
  G/K/O 的缺陷有没有被**无条件**并进去（带 `if` 的推导式不收）、两道门是否都排在第一次 **sink** 之前，
  以及 main 体内有没有 `sys.exit` 式的提前逃逸。「把合并语句改成 `pass`」「门之前先 `OUT.write_text`」
  这种破坏现在会被判红（电池各配一发），但**门在真实交付路径上拦不拦得住**，仍只能靠 `main()` 跑完之后
  那份 `FAIL 交付：…` 读数——第十三轮那次「C/J/N 三段红了却差点交付」就是它自己拦下来的
  （§4.14 头部与那一份三份 `RC=` 读数）。
- **「轮次自指」那一组只管驱动源码与它生成的留档，不管本 README**：留档是每轮**整份重打**的，
  代词那句每重印一次就换一个所指，所以那里禁得掉；而本文件每个 §4.x 小节的标题就写着它属于第几轮，
  小节里的「本轮」由标题解析，扫它只会逼人把历史账改成现在时（那才是真的失真）。
  登记表 `SELF_REF_MARKS` 用拼接定义（`"本" + "轮"`）不是打字游戏：这个扫描要扫**驱动自己的源码**，
  写成字面量就永久命中定义那一行。现读：`grep -c` 那条别在这里抄——跑一次驱动的 `--self-test`
  看「轮次自指」那一组的小计就行。
- **AF-B6 读的是假会话收到的条件，不是 SQL 字符串**：任何经 `select()/where()` 造出来的 like 条件都算，
  包括拼法怪异的（`getattr` 嵌套、`operator.methodcaller`）。但 `text("SELECT … LIKE …")` 那种**原生 SQL
  字符串**不经过这里的假 `select` 通道，这台机器读不到它——那条留给 J-6 的连库用例与 CI。
- **AF-S3 的守卫白名单是 fail-closed 的契约，不是合法形状的完备刻画**（第十六轮 F-17-03）：守卫体内只允许 `len/str/repr/bool/int/isinstance/hash` 与后缀 `warn`/`warning` 的调用，其余任何 Call 都算「第二条兜底」。代价写在判据名里：将来守卫里真要用没见过的函数（哪怕无害）必须**先改这份口径**再改代码——与 BD-12 同一种「宁严勿宽」。反面那一发等价样本（`min_len=len("12345678")`）钉的是「认的是语义而不是字面」；把 logger 改名会红，这一条本机不假装已经放行。
- **`.op(模式串)` 拼不出来时按可疑算**：`_calls_any_like` 对 `.op(<字面量>)` 按内容判、对 `.op(<变量/表达式>)` 一律点名。这是有意的过判（false positive 方向），因为模糊匹配这一族「漏一格」的代价是回归本体，而「多问一处」的代价只是改一次判据名。
- **AF 台的两面之间没有「谁兜谁」**（第十五轮 E 组把上一版那句「再深一层由运行时条件兜住」证伪了）：
  行为面 `_call_anchor`/`_call_frag` 只 exec **目标 def 自己的文本**，所以重绑发生在类体、模块级或
  另一个函数里时，行为面看不见它；反过来静态面只认得**写得出来的形状**，运行期从数据里挑出来的可调用
  它认不出。两面各自的盲区由对方补不了，剩下的那一格只能交 J-6/J-4 的连库面。
  读 §4.16 那张表时按这条读，别把任何一句「由某某兜住」当成闭合。
- **轮次自指那条「扫描面对账」只担保在册件都被读过，不担保在册登记表本身齐全**：应扫集合是从
  `EV_PY` 现取的，而 `EV_PY` 与盘上 `.py` 的双向核对是 G 段另一条判据的职责
  （第十五轮 E-15-05 实测的另一半：往包里加一册却不登记，G 段会点名它，自指那一组不会）。
  还有第三条：`EV_PY` 之外的**文档**（本 README、卡面）不在扫描面里——那里每节标题自带轮次，
  扫它只会逼人把历史账改成现在时。
- **`_collect_cases` 的口径就是 pytest 的默认收集口径**（顶层 `test*` + 名字以 `Test` 开头的类里的方法），
  所以 `class Helper: def test_x()` 那种**没人收集**的函数不会被要求登记——把它算进去就是判据咬合法形状。
  这一条的前提是仓库没改 `python_classes`：现读 `grep -rn "python_classes" pyproject.toml pytest.ini setup.cfg`
  （为空才成立）。类里的用例登记名是 `类::用例`，因为那句交代得写成 `file::类::用例` 才真的跑得动。
  第十五轮 E-15-06 补的是两处**收集面**（嵌套 `Test*` 类的前缀累加、`try` 的 handler/else/finally 与
  `with` 体），但**没**扩到装饰器动态生成的用例与 `conftest` 注入的参数化——那种形状本机既收集不到
  也登记不了，出现时应改的是这份口径说明而不是硬造登记名。
- **「本步新增」这四个字的前提是「这段时间里只有这一步在动这些文件」**——而并发入库会把它打掉。
  `registry_drift` 的两条来源是 `git diff <基线> HEAD --diff-filter=A` 与 `git ls-files --others`：
  前者把**别人已入库**的新用例文件也算进来，后者把**别人未跟踪**的算进来。第十六轮批次收尾时
  STEP-R0/STEP-16 随 `b2d0b66` 入库，本包在 `61358c3` 的干净检出上实测两条红
  （`registry_drift` 点名 `test_alerting_default.py`；`db_pointer_missing` 点名同一份文件里 R0 加的两条），
  读数抄在 §4.17 环境事实 3。判据**没有为此改动**（改了它就再也抓不到「我自己新写第三份却不登记」），
  交付走 §2b 的干净视图；剩下的那一半是跨步骤所有权问题，登记为 §5 J-9 等裁决，
  不在这里用「把别人的用例写进我的表」或「把表scoped到刚好绿」来消掉一条红。
- **取证命令一律写双端**：`git diff <提交> -- <路径>` 拿那个提交与**工作树**比，共享工作树里它读的是别人的在飞件，单机独占时也随时间漂移。本包这类声明（改动面、hunk 数、「生产代码零改动」）现在只写成 `git diff A B -- <路径>` 或 `git show --stat <提交> -- <路径>`。实测对照（第十六轮 C4b）：`git diff --stat 78e3378 078dc30 -- kb.py asset.py` 给 `37 ++ / 20 --`，同一份路径集合用单端写法在今天给 `75 ++ / 25 --`。写下来的数只有配上「哪两端」才叫读数。
- **`registry_drift` 的基线 `STEP_TEST_BASE` 是写死的**（现为 V0.5.0 建卡时的 `65f508b`）：本步收口、
  下一步另起基线时**必须前移它**，否则「登记表里那份已经不是本步新增」那一判会长期红。
  那不是判据坏了，是它在提醒这张表陈旧——照着 §4.11 id 34 那条口径办：改判据的同时改口径说明。
- **留档头部那句归一化计数的现读命令里，`grep -n` 前缀是承重的而不是装饰**（第十四轮 D 组复核实测）：
  那条 `grep -n "in <redacted>s\|0x<redacted>" out_s213.txt \| grep -v ':#'` 的过滤器靠的是「声明行自带 `:#`」，
  去掉 `-n` 之后裸文件行里没有 `:#`，过滤器失效 ⇒ 读数比头部那句多几处，两条通道看起来互相打脸。
- **覆盖自证的阈值从这一批起反转**（写清楚免得被读成放水）：旧规则要求「≥2 发变异抽不得」，
  而第十三轮补齐 provider 之后 26 发变异**全都抽得**（抽不得的那一档是 0）——因为当时那 18 条判据
  每条都有了 ≥2 发独立变异（两个数都是 `078dc30` 时点的 AF 台末行读数；现读走 `--self-test` 末行）
  旧阈值把冗余当缺陷、电池越结实越要报 FAIL，方向是反的。现在的门禁是「每条判据 provider ≥2」，
  它两端都可假：少配一发就点名那一判据（实测过），多一发冗余也不会变成假红。
  「有多少发抽不得」降级为读数（0 才是满分）。现读：`prove_anchor_fallback.py --self-test` 的
  `覆盖自证` 那一行，以及驱动侧的 `mutate_replay_r9.py` 的 `N-覆`。
- **字面 grep 判不动否定式声明**（B 组 R13B-11 的教训，写在这里而不是只改卡面）：
  「`Source.url.like(...)` 已经删干净」这件事，`grep -n "\.like(" apps/api/app/services/kb.py`
  现在**必然**命中一行——命中在解释「为什么删」的 docstring 里。否定式声明一律走 AST
  （AF-S1 判锚定方法体、AF-S6 判整份文件任何接收者的 `.like(` 调用），
  现读 `python docs/06_validation/evidence/EVD-V2-02/prove_anchor_fallback.py | grep AF-S`。
- **本包里的编译件**：`ls docs/06_validation/evidence/EVD-V2-02/__pycache__`——G 段判的是
  「源文件已不存在的孤儿 `.pyc`」（B 组 R13B-17 抓到过一份 `_harness_probe` 的），
  正常新生成的编译件不在此列（见什么都咬的探测器等于没判，第十二轮那条口径同一形状）。
- 覆盖率是**语句覆盖**（`sys.settrace`），不是分支覆盖——复审 Q-16 另用自写弧采集核对了唯一
  那条 If 的两条弧，但那不是本脚本的门禁项，别把它读成「分支覆盖 100%」。
- 三条反证通道各自的方向：变异体证明「改坏会红」，样本对证明「判据能假」，等价重构证明
  「换写法不假红」。缺任意一条，另两条的结论都不完全可信。
- 读 `out_s213.txt` 的 rc 要分档：`0` 全绿 / `1` 有判据红（真红基线）/ `2` **INCONCLUSIVE**
  （目标函数不在文件里，**或整份文件解析不了**——判据压根没跑）。把 2 当成 1 读，就是把
  「没测到」读成「测出红」。本轮起这一映射**测两层且加了两发对照**：`run()` 返回值 + 临时副本
  子进程的真实退出码（C 段次行），副本清单含「带 BOM 的基准」与「解析不了的副本」，
  并且任何一档的 stderr 里出现 traceback 都判 FAIL（第七轮 N5：改前那两发是崩溃不是裁决）。
  同一判据现在有**第三层**：`--self-test` 在 cp936 输出流下重跑自己（编码自证），因为「没有裁决」
  这一类失效不止来自被测文件，也来自脚本自己的 print——这一层测的是脚本本身。**三层都在 BD 侧**；
  PI 侧只有编码那一层（它没有档位/退出码那两档），别把两份脚本读成三道闸门。
  第三层自己也曾是**假绿**（§4.10 id 3）：子进程被 `BD_NO_NEST`/`PI_NO_NEST` 挡着不递归，所以它压根
  不打印这一档的 OK 行；而父进程只验 rc 与 traceback，从没验过「stdout 里还有没有靶字」。现在它要求
  `rc=0`、无 traceback，**且**子进程 stdout 里确实出现过 `⇒`（判据把靶字写成转义形式 `"\u21d2"`，
  否则 `sed 's/⇒/->/g'` 会连判据一起改掉、检查自我失效——第一版就踩在这上面）。K.3/K.6 是这一条的实测红。
- 「这份留档是被重放过了一遍」也是同类的**不可自证声明**，上一轮就虚了一次（§4.9 S-2）：驱动按
  `$ ` 前缀找命令、输出时又剥掉前缀，前缀一丢就不跑而直接抄旧输出，且抄得不报错。现在的兜底分三段：
  **L 段**机检「每段都留得下一条 `$ ` 命令」，缺段点名并让驱动 rc≠0；**M 段**机检驱动自己的两条通道
  （`replay_s213.py --self-test`：条数与分组小计由 `check()` 记账现算并打印，逐条清单由同一脚本的
  `--list-checks` 现出，**本节一个号数都不抄**——§4.10 id 16 起、§4.11 id 18/19 报回的都是抄件。四个判据组是
  「取命令」（把手缺失 / 整段无命令 / heredoc 配对断了 / 第一条非注释行是读数等，坏输入一律要求 raise 或取到
  同一条）、「写入判据」（**按字节**逐位相同才算成、半成品与 CRLF 与 BOM 与截断各有各的原因，其中半成品
  要「盘上有占位符**且**意图里没有」两个条件才成立、截断必须报出**两个字节号**）、「写入通道」（真磁盘写成、
  目标是目录要报原因、第 3 次才成功要救回来、恰好试满 `ATTEMPTS` 次、两次失败之间真的等 `PAUSE`、落盘与意图
  不逐位相同时报红、`OSError`/`PermissionError` 各试满并点出类名，以及第十轮补的**默认值三条**：`inspect` 断言
  默认 `sleep is time.sleep`、默认 `attempts/pause` 就是 `ATTEMPTS/PAUSE`，再来一条只注入 write 的计时用例——
  生产路径等的是真时钟，不是被换成空函数）、「头部现算」（留档头部那句「判据条数」由 `bd_ids()` 从标注现场数出来，
  真删一行 BD 判据它必须少一条；两个区间还须首尾相接、合起来是 `BD-1…BD-N`）——绝不返回旧
  文本，也绝不把半成品当成品，见 §4.10 id 9–11 与 §4.11 id 18–21）；**N 段**是 M 段的反证电池
  （`mutate_replay_r9.py`：「改坏必须红、且红在该红的那一组」与「等价写法不许假红」两档，发数由 `len(SHOTS)`
  现算），前面还有 N-00 基线：一份**没打变异**的副本必须先绿，否则整批判 INCONCLUSIVE（rc=2）而不是判红；
  M 段自己涨条数却没人校验它的判定力，就是第九轮那两条 MAJOR 的形状。
  三段各有**局限**：L 只保证每段有把手，
  不保证把手后面是命令、更不保证读数与当前代码相符——M 补的是「取错/取不到」与「落不落得进磁盘」这一半，
  仍补不了「代码变了而留档没重跑」那一半（那一半只能靠下面那条重跑纪律）；N 补的是「M 的判定力本身」，
  而这句话从第十一轮起**不再是形容词**：电池先跑 `replay_s213.py --list-checks` 取判据全清单当分母，
  再按每一发变异**实际**红出来的 `[组] 判据名` 记账（标签里的数字被归一化成 `N`，所以合法重构新增判据不会
  把电池变成假红），末尾 `N-覆` 报「覆盖 n / 共 m 条」并把**没有变异的判据点名列出**，少一条就 rc≠0——
  上一版这里写的「它只覆盖写入与头部那几组，取命令旧几条没有新变异」当场作废；组名与每组条数都不再抄进本节
  （现读 `--list-checks`）。第十二轮新加的归一化 / 段末裁决 / 落盘权几组**同样各有能打红的变异**，
  而这句话不再由本节担保——它由 `N-覆` 那行的现算读数担保：少一条，整个电池 rc≠0 并把判据名字点出来。
  所以改 harness 之后必须重跑
  `python docs/06_validation/evidence/EVD-V2-02/replay_s213.py`（在库件，与 `j_attack_r7.py` 一起交付；
  上一版驱动躺在不入库的 `_workspace/` 里，这条纪律当时只存在于那句话中）。
- 留档里**只有三类**读数不是命令的原样输出，三类都在文件头就地声明（不是这一节的叙述）：
  ① pytest 墙钟 `in <数字>.<数字>s` → `in <redacted>s`；② 解释器对象表示里的内存地址 `0x…` →
  `0x<redacted>`——第十一轮复审 NIT④ 报回的是上一版只声明了①：同一份留档里「默认 `sleep` 到底是什么」那条
  读数当时打印的是 `<function <lambda> at 0x000001D8…>`，它在 A5 的跨 worktree 复现里每次必不同，
  却没和墙钟同口径归一化，于是「整份可复现」被这一个地址打了个洞；③ 任何一档 `rc=2` 时末行补一句
  `**INCONCLUSIVE**` 标注——那是「压根没测到」，不能让人读成真红。
  现测各类出现在哪、各有几处，一律以文件头那句现算读数为基准；要用 grep 复核就得**把头部声明行排除**
  （B 组 R13B-27：从前这里给的 `grep -n "in <redacted>s\|0x<redacted>" out_s213.txt` 会把头部那两行
  自己的命中算进去，实得 4 行而头部报「墙钟 2 处｜地址 0 处」，两条通道指向同一件事却差头部那几行，
  读者按旧命令会判头部虚报）：
  `grep -n "in <redacted>s\|0x<redacted>" out_s213.txt | grep -v ':#'`——正文 = 全文减去头部声明行。
  本节不复制号数（上一版这里抄了「共 3 处 = D 段 1 +
  E 段 1 + 头部 1」，而按 `in [0-9]\.[0-9]+s` 匹配的原样墙钟必须为 0 处——那个 0 才是判据，3 只是当时的读数）。
  **这句话从第十二轮起才有判定力**：上一版头部那句「段体里有三类读数」是模板字面量，而 ② 那一类在留档里
  一处都没有（§4.13 id 43）——「处理了」只能靠形状恰好撞上。现在三类住在登记表 `NORMALIZATIONS` 里、
  各自带着「必须命中 / 必须不命中」两档靶子，命中处数由 `apply_norm()` 累加后再对正文数一遍替换文本，
  两条通道不符就不交付；计数为 0 也照样写进头部（这一趟没撞到 ≠ 登记表里没这条规则）。
  除这三类，段体每个字符都是命令的真实输出；
  文件头也带着 HEAD、工作树状态、Python 版本与运行时刻，状态那一项由 `git status --porcelain` 现取，不是模板里写死的。
- BD-9 的名字名单（`parse_qs`/`urlparse`/`urllib`）是**必要不充分**条件：第五轮复审用
  `str.split("?")` 手搓解析就绕过了它，也绕过了「把 `"biz"` 拆成 `"bi" + "z"`」的 BD-11。
  充分性现在靠 BD-12（形状白名单，含「除文档串与导入路径外不许出现任何字符串字面量」）
  加 BD-3 的差分语料。**仍然不是全域等价性证明**：语料是有限的（条数与 EQUIVS 的条数都以
  `python docs/06_validation/evidence/EVD-V2-02/prove_biz_delegation.py --self-test` 末行那句
  「N 个判据样本对敏感 + M 个等价写法不假红」为准，本节不抄——B 组 R13B-23 抓的就是这里从前抄的
  「26 条 / 11 条」）。白名单是按**当前那批 EQUIVS** 校准的：真要改形状，先加 EQUIV 再加实现——
  顺序反了就是假红门禁。
  另注意 BD-9 的口径**只管 `_biz_from_url` 自己**：调用点里另起一份解析器它看不见，那是
  BD-14 数据流的职责（§4.8 N3），别把 BD-9 读成「kb 全文件无第二份解析」。
- BD-12 白名单**欠接纳**（会误伤合法重构）的实数，第六轮量了（§4.7 D6）：7 发「仍然委托、
  只是换个写法」的形态里 **5 发会红**（前置 `if not url:` 守卫、加一行日志、`str(...)` 包一层、
  `biz_of_url(url)` 门面、把解析层挪进子包），只有「先取 `parts`/`biz` 局部变量」这 2 发绿。
  读 BD-12 时按「宁严勿宽的显式契约」理解，别当「合法形状的完备刻画」；误伤了就照上一条补 EQUIV。
- BD-13 判的是**活绑定**：模块作用域里唯一动过 `_biz_from_url` 这个名字的语句，就是被 exec 的
  那份 def。它因此能抓住 lambda 赋值、`globals()[...] =`、顶层 `if` 里的 def、`del`（§4.7 D1），
  以及第七轮的**属性形态**——`sys.modules[__name__]._biz_from_url = …`、`del` 同一形态、
  模块级 `def __getattr__` 里点名目标名、`from x import *`（§4.8 N1/N2）。
  两个残余盲区要写明白：①**动态 exec 类花招**仍只靠「目标名与 `exec`/`setattr` 等**同一条语句**
  内同现」的启发式记账，构造得刻意就能绕开（第七轮把共现单位从「整条顶层语句」收窄到「单条语句」，
  是为了不再误伤 `setattr(rec, "url", …)`，不是为了变强）；②嵌在别的函数里的同名 `_biz_from_url`
  不是模块属性，`from app.services.kb import _biz_from_url` 拿不到它，那种形态由 `has_target()`
  直接落进 INCONCLUSIVE（rc=2），不会伪装成红基线。
- BD-16 是**契约**不是**判据**：它把「本文件不许用命名空间改写设施」写成一条人为规定，
  命中即红，哪怕那一处今天确实无害（模块级 `__getattr__` 即使与目标名无关也会红）。
  这么做的代价是**将来正当使用这些设施时必须改契约**，收益是攻击面从「Python 名字查找的全部形态」
  收缩成一个可枚举的名单。它扫的是整份文件，与 BD-13 的模块作用域扫描互补而不是重复：
  BD-13 问「有没有换掉绑定」，BD-16 问「这个文件有没有能力换掉绑定」。
- BD-14 只往函数边界外走**一跳**，且只做**名字传播**（≤3 跳）：宿主 `_find_source_by_anchor`
  里委托调用的结果必须经由局部变量（含别名）进到 `Source.external_id` 那一侧。本轮已把「共现」
  换成「数据流」，但四个方向仍然漏：①锚点先存进 `self.xxx`/`dict`/闭包再比较；②宿主改名或
  拆成两个方法；③URL 形参改名成不含 `url` 的字样（会**假红**，属契约变更而非缺陷）；
  ④kb 的其余调用方（`_ensure_source` 等）不在射程内——那属于 J-5/J-4 的连库面。
  宿主同名重复定义现在直接红（`_caller_anchor_fns` 按行号取末位 = Python 的活绑定语义），
  所以「证明一段没人调用的代码」这一类被堵住了，代价是合法的「先写一版再覆盖」也被一并禁掉。
- BD-15 是**崩栈护栏**，不是行为判据：它只保证「目标函数能被单独 exec」，exec 不成时把六条行为
  判据各记一次红并给出可读原因，而不是让 `run()` 带着 traceback 退出（改前那种「既不是绿也不是红」
  的第三态会被当噪音关掉，见 §4.7 D5）。
- F 段的 F-3/F-4 是**判定力模拟**：用 `lambda u: ""` 顶替实现来问「这条锚会不会空过」，
  不是对磁盘代码的执行——对磁盘代码的真实执行只有 F-1/F-2 与 B 段。两者的结论不可互换。
- **渲染文本判据（`sql_render_defects`）的扫描面现在按目录取，不按登记名单取**（第十九轮机制组 M4）：
  `sql_scan_face()` = `apps/api/tests/*.py` ∪ 真库目标 ∪ 本步新文件。这一条**只担保覆盖面**，
  不担保判据认全：它认的是「比较/取段/正则这几种谓词落在渲染文本上」，
  不认 f-string 左值、不认**跨文件**的辅助函数（同模块认）、不认 `getattr` 动态取的属性名。
  面内命中为零是一句读数，不是「这一族在全仓封死了」——后一句要从判据的语义面读，而语义面永远
  只到「本轮想到的形状」为止（§4.20 那条 generalization 对它自己同样成立）。
- **两处 fail-closed 的代价明写在契约上**：①`compile(<位置第二实参>)` 不再算豁免——本机按约定
  不装依赖，核实不了 SQLAlchemy 2.0 的形参槽位，「核实不了的写法一律放行」等于自己拆门禁；
  ②值形状含「任何数字」，所以 `":param_1" in sql`、`"sha256" in sql` 这类**其实正确**的断言也会被
  多问一处。两种代价都留给装了依赖的连库面（J-6）去证伪，放行它们属改契约，与 BD-12 同一处理。
- **文档面那道门（`doc_face_defects`）判的是两面行集与产物新鲜度，不判文档写得好不好**：
  大纲与任务卡的 S 编号行集必须相等（只进一面都点名），S0T 迁移清单要与当前树逐字节相同
  （`--check`）。它**不担保**行集之外的东西——行内的状态符号、措辞、号数是否现算，仍由 §4.x 那些
  逐格勘误与记账组复核管。还有一条要说清：它读的是 `docs/任务规划V0.5.0/`，那是**本计划的树**；
  别的会话若在共享工作树里同时改这册，这里可能读到别人的中间态——那种红按 §2b 的干净视图处理，
  不把判据改成刚好通过别人未提交的代码（与 J-8/J-9 同一口径）。
- **`--write` 与 `--check` 必须走同一个取数函数**（第十九轮记账组当场抓到我自己埋的那发）：
  第一版 `--write` 把占位行渲进表、`--check` 没加，于是刚生成的清单立刻被自己的核对报过期
  （506 行 vs 508 行）。产出物与对账工具各算各的，是「两条通道不是同一批判据」那一族的新实例。

