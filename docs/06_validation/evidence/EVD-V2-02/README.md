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
| S2.1.3 `kb._biz_from_url` 委托 | ✅ 改前红可重放 + 改后 16 判据全绿 + 三条反证通道（24 变异 / 26 样本对 / 11 等价写法）+ 档位/退出码/编码三层自证（仅 BD 侧三层，PI 侧只有编码那一层） | §2 通道 C（`prove_biz_delegation.py`）、`out_s213.txt` A–M（十八段） |
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
| D3 | README 两处陈旧计数（`:27` 的「11 判据 / A–E」、`:67` 的「BD-1…BD-11」） | 复现成立（本轮之前一次改判据没同步过 §1/§2 的表） | 当时改为 `15 判据 / A–I`、`BD-1…BD-15`；**第七轮之后又变两次**（现 `16 判据 / A–M`（十八段）、`BD-1…BD-16`，见 §4.8/§4.9/§4.10）——这条正好证明「每轮改判据必须回头扫 §1 §2 §6 §7」不是套话：第八轮复审 id 2 抓到的就是**我自己**没扫这一格，处置见下一段，而 §4.10 那张表写下「改为 A–M」时这一格其实还是旧的，本轮才真的补上 |
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
| S-2 | 上一版重放驱动 `_workspace/gen_s213_r7.py` 按 `^$ ` 前缀找命令，且**取走前缀再输出**（`cmd_lines[0][2:]`）⇒ 每重生成一次就丢一批把手，而把手一丢，下一趟就**不跑而直接抄旧输出**，且不报错。第八轮复审 id 3 拿这条去对仓库里的文件，发现我记错了对象：**已提交的那几份一直是完好的**（`git show b45777a:…out_s213.txt` 实测 7 段 / 7 条 `$ `，`de78125` 版 9 段 / 9 条），丢把手只发生在 `_workspace/` 里那份没入库的草稿上。所以「第七轮那份只剩 J 段有」这句话说的是**不可复核的东西** | 原先写的反证是 `grep -c cp936 _workspace/out_s213_new.txt` 得 0——那条依赖一个不入库的草稿，会话结束就没人能再跑（第八轮复审判它不可采信，判得对）。现在换成在库、逐字可跑的一条：`python docs/06_validation/evidence/EVD-V2-02/replay_s213.py --self-test`（留档 M 段），它对「把手缺失 / 整段无命令 / heredoc 配对断了 / 第一条非注释行是读数」四种输入分别要求 raise 或取到同一条命令，取不到就停下而绝不返回旧读数 | 新驱动 **`replay_s213.py` 落在本包内**（不再放 `_workspace/`，理由见下一段）：按段落版式取命令（标题后第一条非 `#` 非空行，heredoc 取到配对的 `PY`），输出时**统一补上 `$ ` 前缀**（不再自我剥除）；取不到命令一律 `raise ValueError`；**L 段机检**「每一段都留得下一条 `$ ` 命令」，缺一段就点名段号并让驱动 rc≠0；**M 段机检**取命令这条通道本身（L 只数把手，判不了把手后面是不是命令）。J 段的攻击驱动也从「内嵌 92 行到留档里」改成在库件 `j_attack_r7.py`。本文件 18 段（A–J、K.1–K.6、M、L）全部是这次真跑出来的 |

两件驱动**入库**这一步不是整理癖：`_workspace/` 不入库，那么「每次改 harness 都要重跑重放器」这条纪律
在仓库里就只剩 README 的一句话，会话一结束就没人执行；`j_attack.py` 那 92 行此前是**抄进**留档的，
在库版本与留档里的副本各一份、必然漂移。现在两者都是本包的文件，命令指向它们本身。

S-2 的边界要说清，别顺势夸大，也别把已入库的账本一起抹掉：仓库里 `b45777a`/`de78125` 两份留档的把手
**实测一条不缺**（7/7、9/9），所以我先前写在格子里的「已提交的那份也丢过把手」是错的，已更正。
我**同样没有**证据说第七轮那份草稿里的读数是假的（H-0 写着 16 条全绿、I-2 写着 `['BD-13','BD-16']`，
都对得上那一版 harness）。能被一条命令钉住的只有**机制**：那个驱动取不到命令时不 raise 而返回旧文本，
于是「没跑到」可以冒充「跑到了」，且抄得不报错。现在这件事由 M 段每天判一次（取命令的四种坏输入各自要求
raise 或取到同一条，另有写入回读的判据三条与端到端两档，共 11 条，见 §4.10 id 9），驱动里也真的改成了 raise-first。
所以「本文件全部段落都在同一版 harness 上重放」这句话，此前靠的是叙述，现在靠两段：L 段数把手、
M 段判驱动自己的两条通道（取命令 + 落盘回读）；而且 L 读的是**交付出去的这一份**（驱动先落文件、再跑 L、
最后回填 L 的输出，回填后还要把整份读回来核对逐字相同），不是运行前那一刻的半成品。
本项目反复踩的是同一个坑：一句不能被一条命令反驳的声明，等于没有声明。

代价（写进 §7）：① `_ensure_utf8_stdout()` 改的是**进程级** stdout/stderr，被别的脚本 import 时会连带
生效；② 编码自证档会让 `--self-test` 的耗时翻倍（子进程把全套变异再跑一遍）；③ 子进程真是崩在 print 上时，
它的 stdout 缓冲区随异常退出一起丢掉，traceback 文本自己也含 `⇒`、写 stderr 时二次失败，所以 FAIL 分支
只能落一句兜底文案而不是抄出异常原文（K.2/K.5 的读数就是那句兜底）；④ 命令是按**版式**识别的（标题后第一条非 `#` 行），不是按显式标记；`$ ` 前缀现在只出现在输出侧。
将来若有人在标题和命令之间插一条以 `python`/`cd` 开头的话，取到的命令就错了——L 段能抓到「某段没有
`$ ` 命令」，抓不到「某段取错了命令」。真要钉死，得把每段命令抽成驱动里的清单，那是下一步的账。

## 4.10 第八轮：独立验证子智能体的报告（对提交 `0161bcd`）——4 条 MAJOR + 5 条 MINOR 逐条复现

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
| 9 | **本批收尾自己撞出来的**（不在它的报告里）：重放器整份跑完，最后一次回填 `out_s213.txt` 抛 `OSError [Errno 22]`（win32 上文件被瞬时占用），驱动就此终止，而磁盘上留下的是 **L 读数位还空着的半成品**——`write_text` 之后没有任何回读，「写出 431 行」只是驱动自己的一句 print | 同一条命令立刻重跑就成功（431→432 行、18 段），说明是竞态不是逻辑错；把 `OUT` 指到一个目录上跑 `write_out`，实测得到 `落盘或回读抛异常：PermissionError: [Errno 13]…` 而不是异常穿透 | 新增 `write_ok(intent, readback)`（**回读逐字相同**才算成；仍留着占位符 = 半成品冒充成品；其余 = 字数不一致）与 `write_out`（写→回读比对，最多 5 次；失败**返回原因而不 raise**——本项目「崩栈不是裁决」），`main()` 两处写入都走它，失败打印 `FAIL 交付…` 并 rc=1。M 段于是从 6 条涨到 **11 条**（取命令 6 + 写入判据 3：逐字相同才算成 / 半成品不算 / 字数不一致不算 + 写入端到端 2：临时目录里真写成且磁盘上就是这一份 / 目标是目录写不进时必须报原因而不是让异常穿透）。顺带把一条**依赖**写进 docstring：A–I 的命令取自上一版留档，删掉 `out_s213.txt` 就断自举（本轮实测：删掉后驱动以 `FileNotFoundError` traceback 收场）——现在落一句 `FAIL 交付：… 先 git checkout -- <该文件>` 并 rc=1 |

复现不成立或需打折的一条：它说「L 段是同义反复，永远只会失败于手改文件」。**部分成立**——由驱动生成的
留档里 L 必然通过，这是事实；但它的价值恰恰是「读者拿到磁盘上这一份时把手齐不齐」，而把手不齐
在上一轮真的发生过（§4.9 S-2）。所以我不删 L，而是补 M 段把「取命令通道」本身的判定力做成可跑的反证，
并在 §4.9 代价 ④ 里明写 L 判不了「取错命令」。

判据条数、变异体数、样本对数、等价写法数**本批一律未变**（16 / 24 / 26 / 11；PI 侧 12 / 17 / 4），
`kb.py` 仍未被改动（`git diff c10b229 -- apps/api/app/services/kb.py` 复跑仍为空）。变的是自证层与留档格式。

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
- **四轮处置批（§4.4/§4.5 的第二轮、§4.6 的第五轮、§4.7 的第六轮、§4.8 的第七轮）都没有再动
  `kb.py`**，§4.9 的**提交前自查批**同样没动（它是证明层与运行层的改动）：
  `git diff c10b229 -- apps/api/app/services/kb.py` 为空（本轮复跑确认）。
  改动面只有 `prove_biz_delegation.py`/`prove_article_identity.py`（判据、档位、通道自守、编码自守）、
  `test_kb_longlink_ingest.py`
  （用例的第二条锚 + import 段序，第二轮改）、本 README 与 `out_s213.txt`
  （**第七轮起整份重放**，现为 18 段：A–J 十段 + K.1–K.6 + M + L。H 段是第五轮三条空过的闭合实测，
  I 段是第六轮 D1/D2/D4/D5 的，J 段是第七轮 N1…N5 的两版 harness 对照，K 段是 §4.9/§4.10 的编码崩溃面
  （K.1/K.4 裸跑、K.2/K.5 注掉 guard、K.3/K.6 抽掉靶字），M 段机检「取命令」这条通道本身，
  L 段机检每段有没有把手。之所以不「只在末尾追加一段」：判据从 15 条变 16 条之后，
  A/B/C/F/H/I 的读数本身会变——实测例是 I-2 由 `['BD-13']` 变 `['BD-13', 'BD-16']`、
  A 段由 `PASS=5 FAIL=10` 变 `PASS=6 FAIL=10`，留旧读数就是留一份和当前代码不符的证据；
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
  `$ ` 前缀找命令、输出时又剥掉前缀，前缀一丢就不跑而直接抄旧输出，且抄得不报错。现在的兜底分两段：
  **L 段**机检「每段都留得下一条 `$ ` 命令」，缺段点名并让驱动 rc≠0；**M 段**机检驱动自己的两条通道
  （`replay_s213.py --self-test`，11 条反证：取命令的「把手缺失 / 整段无命令 / heredoc 配对断了 /
  第一条非注释行是读数」等 6 条要求 raise 或取到同一条，写入回读的 5 条要求「逐字相同才算成、半成品与
  截断都不算、写不进磁盘必须报原因而不是让异常穿透」——绝不返回旧文本，也绝不把半成品当成品，见 §4.10 id 9）。
  两段各有**局限**：L 只保证每段有把手，
  不保证把手后面是命令、更不保证读数与当前代码相符——M 补的是「取错/取不到」这一半，仍补不了「代码变了而
  留档没重跑」那一半。所以改 harness 之后必须重跑
  `python docs/06_validation/evidence/EVD-V2-02/replay_s213.py`（在库件，与 `j_attack_r7.py` 一起交付；
  上一版驱动躺在不入库的 `_workspace/` 里，这条纪律当时只存在于那句话中）。
- 留档里**只有**一处读数不是命令的原样输出：pytest 的墙钟被驱动归一化成 `in <redacted>s`（D/E 段两处，
  §4.10 id 1）。它每次重跑必不同，原值留着就是留一份不可复现的读数。除这一处，段体每个字符都是命令的真实输出；
  文件头也带着 HEAD、工作树状态、Python 版本与运行时刻，状态那一项由 `git status --porcelain` 现取，不是模板里写死的。
- BD-9 的名字名单（`parse_qs`/`urlparse`/`urllib`）是**必要不充分**条件：第五轮复审用
  `str.split("?")` 手搓解析就绕过了它，也绕过了「把 `"biz"` 拆成 `"bi" + "z"`」的 BD-11。
  充分性现在靠 BD-12（形状白名单，含「除文档串与导入路径外不许出现任何字符串字面量」）
  加 BD-3 的 26 条差分语料。**仍然不是全域等价性证明**：语料是有限的 26 条，白名单是按
  当前 11 条 EQUIVS 校准的。真要改形状，先加 EQUIV 再加实现——顺序反了就是假红门禁。
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
