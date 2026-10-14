#!/usr/bin/env python
"""STEP-02 S2.1.4 + S2.1.5 机器证明：锚定兜底的 `LIKE` 真的删了，片段守卫真的挡在发 SQL 之前。

被证明的两个对象都在**磁盘上的当前代码**里，本脚本不抄它们：
- `apps/api/app/services/kb.py::KnowledgeBaseService._find_source_by_anchor`（S2.1.4）
- `apps/api/app/repositories/asset.py::AssetRepository.get_by_url_fragment`（S2.1.5）

为什么不能直接 pytest：`kb.py:22-25` 与 `asset.py:11-15` 都在模块级 import `structlog`/`sqlalchemy`，
本机两者皆无（实测收集期 `ModuleNotFoundError: No module named 'structlog'`，rc=2）⇒
连 import 都过不去。机制沿用 `prove_biz_delegation.py`：**按 AST 取出目标函数节点，
`ast.unparse` 之后单独 compile + exec**，再给它装配一个**记账用的假会话**。
被执行的是文件里那份代码，改了函数体这里的结论就会变。

假会话不是「随便一个 mock」，它把生产代码对数据库提的三个要求如实实现出来：
① `where` 的条件按列如实匹配（`eq` 比值、`like` 按子串，`%` 是通配）；
② `limit(n)` 截断在**返回之前**发生（所以「摘掉 limit 会不会拿到多行」是可判的）；
③ `scalar_one_or_none()` 在多行时抛 `MultipleResultsFound`——这正是 P-4 当年崩的那一类。
边界要说清：这里证的是「生产代码向 DB 要了什么、拿到结果怎么处理」，**不是** SQL 引擎怎么执行。
交出去的那两半口径不同，别混读（A 组 MI-6：从前这里把两份用例都写成「真库那条」，而
`test_asset_fragment_guard.py` 用的是记账假会话，压根不连库）——
① `test_kb_multisource_anchor.py` 的两条**连库**（`db_session`，真 PG 上跑 SELECT 与 commit）；
② `test_asset_fragment_guard.py` 的四条**只需依赖不需库**（判据是「有没有把 SQL 发出去」）。
两半的本机障碍都是模块级 `import structlog`/`sqlalchemy` 导致收集期就失败（README §5 J-6/J-7），
但「本机跑不了」不等于「跑了就证同一件事」。文件名与用例名登记在 `replay_s213.py` 的
`REAL_DB_TARGETS`，由 G 段逐条核对确有其事。

判据分三面（`--list-checks` 打全清单，条数一律现算不手抄）：
- 前提 AF-P0：两个目标都能被单独 exec（exec 不了就没有裁决，只有 traceback）；
- 行为面 AF-B1…B6 / AF-A1…A5：biz 锚命中、两锚皆空不许落到 URL 兜底、多源含 `s` 不崩、
  `limit(1)` 真的挡住同 `external_id` 的脏数据、短链的空 biz 被跳过、
  生产量级的 18 字符键也不下发 URL 列的 like 条件（B6 读的是**假会话收到的条件**，
  所以 `getattr(getattr(...),"like")` 与 `methodcaller("like", …)` 两种拼法都在射程里）；
  短片段不发 SQL 且留 WARNING、空串不告警、阈值边界卡在 7/8（含 `1234567` 那一发，
  它钉的是「守卫的 `return None` 必须是分支的直接语句」）、放行路径形态仍是
  (source_id eq + url like %片段% + limit 1)、LIKE 携带的真是 `%片段%`；
- 结构面 AF-S1…S7：函数体内没有 `.like(`、体内每条 select 链都带字面 `.limit(1)`、
  守卫分支的形状（比较 + `return None` + `logger.warning`）齐备、磁盘上的 `MIN_FRAGMENT_LEN`
  确实是 8 且只绑一次、两个目标各自活绑定唯一（无重复 def / 无属性形态重绑 / 无装饰器）、
  kb **全文** AST 层不再出现对 `Source.url` 的 like 调用（只在方法里删干净不算数）、
  锚仍然来自 `_biz_from_url` 的结果（改这段时不许把 S2.1.3 的接线顺手拆掉）。

三档裁决与 `prove_biz_delegation.py` 同规：`0` 全绿 / `1` 有判据红 / `2` INCONCLUSIVE
（目标函数压根不在文件里，或整份文件解析不了——判据无从判定，不能冒充红基线，也不许以崩栈收场）。

`--self-test` 三条反证通道：
① `MUTANTS`：把磁盘源码在内存里改坏（含**退回旧实现**：把 `Source.url.like(f"%{article_key}%")`
   兜底原样放回、把守卫换回 `if not fragment:`），逐条要求指定判据红；
   并且要求**每一条判据都至少被一发变异打红过**——覆盖表由 `CHECKS` 与 `MUTANTS` 现算，
   少一条就 FAIL（没配变异的判据等于悄悄注销）；这条覆盖判据自己也被反证一次（抽掉一发变异必须报缺）；
② `EQUIVS`：语义等价的写法必须不假红（`.where()` 与 `.limit()` 换序、生成式换列表推导、
   比较两侧换边、select 先存局部变量、锚元组先存局部变量）——假红的代价是门禁被当噪音关掉；
③ 档位自证：三档在**内存里**和**真实子进程退出码**上各核一遍，子进程刻意在 win32 默认的
   cp936 输出流下跑，且任何一档都不许以 traceback 收场。
"""

from __future__ import annotations

import ast
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
API = REPO / "apps" / "api"
KB = API / "app" / "services" / "kb.py"
ASSET = API / "app" / "repositories" / "asset.py"
TESTS = API / "tests"

#: 两个目标的名字。模块作用域/类作用域里凡是动过这两个名字的绑定都算「换了实现」。
KB_TARGET = "_find_source_by_anchor"
AS_TARGET = "get_by_url_fragment"
#: 守卫阈值（卡面口径 8）；这里只当**判据的期望**，代码里的实际值由 `_module_const` 从磁盘读。
CARD_MIN_LEN = 8

_p, _t = str(API), str(TESTS)
for _d in (_p, _t):
    if _d not in sys.path:
        sys.path.insert(0, _d)

RC_GREEN, RC_FAIL, RC_INCONCLUSIVE = 0, 1, 2

passed: list[str] = []
failed: list[str] = []
#: 完全静默：self-test 的内存档位层只关心 `run()` 返回哪一档，逐行输出是噪音。
_quiet = False
#: 精简：子进程档位层用它。逐条判据与说明都不打印，**但裁决行照打**——「绝不抑制裁决本身」。
_terse = False


def _ensure_utf8_stdout() -> None:
    """把输出流钉在 UTF-8：win32 控制台/管道默认 cp936，编不出本文件的 `⇒`。

    崩溃不是裁决（项目纪律），而这一类崩溃与判据无关，纯环境噪音——噪音门禁会被关掉，所以在此自愈。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


_ensure_utf8_stdout()


def check(label: str, ok: bool, detail: object = "") -> None:
    (passed if ok else failed).append(label)
    if not (_quiet or _terse):
        print(f"{'PASS' if ok else 'FAIL'} {label}" + ("" if ok else f" :: {detail!r}"))


def say(text: str) -> None:
    """裁决与计数行：只有完全静默才抑制。"""
    if not _quiet:
        print(text)


def note(text: str) -> None:
    """说明性抬头/边界段：不是裁决，两种静默都抑制。"""
    if not (_quiet or _terse):
        print(text)


# ── 记账假会话：把「生产代码向 DB 要了什么」如实记下来 ─────────────────────────


class MultipleResultsFound(Exception):
    """名字与 `sqlalchemy.exc.MultipleResultsFound` 一致——P-4 当年崩的就是这一类。"""


class _Cond:
    __slots__ = ("col", "op", "val")

    def __init__(self, col: str, op: str, val: object) -> None:
        self.col, self.op, self.val = col, op, val

    def __repr__(self) -> str:
        return f"{self.col}.{self.op}({self.val!r})"


class _Col:
    """假列：`==` 与 `.like()` 只记成条件，不生成 SQL。"""

    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: object) -> object:
        return _Cond(self.name, "eq", other)

    def __ne__(self, other: object) -> object:
        return _Cond(self.name, "ne", other)

    def __hash__(self) -> int:
        return hash(self.name)

    def like(self, pattern: str) -> object:
        return _Cond(self.name, "like", pattern)


class _Model:
    """假 ORM 类：`key` 用来在假表里取行，其余按需暴露列。"""

    def __init__(self, key: str, *cols: str) -> None:
        self._key = key
        for c in cols:
            setattr(self, c, _Col(c))


class _Query:
    def __init__(self, key: str) -> None:
        self.key, self.conds, self.limit_n = key, [], None

    def where(self, *conds: object) -> _Query:
        self.conds += [c for c in conds if isinstance(c, _Cond)]
        return self

    def limit(self, n: int) -> _Query:
        self.limit_n = n
        return self


class _Result:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def scalar_one_or_none(self) -> dict | None:
        if len(self.rows) > 1:
            raise MultipleResultsFound(f"命中 {len(self.rows)} 行，要求一行或零行")
        return self.rows[0] if self.rows else None


def _match(rows: list[dict], conds: list[_Cond], limit: int | None) -> list[dict]:
    out = []
    for row in rows:
        keep = True
        for c in conds:
            if c.op == "eq":
                keep = row.get(c.col) == c.val
            elif c.op == "like":
                keep = str(c.val).strip("%") in str(row.get(c.col, ""))
            if not keep:
                break
        if keep:
            out.append(row)
    return out[:limit] if limit is not None else out


class _StubSession:
    """`execute`/`scalar` 都记一条账：(表, 条件, limit)。真库语义里的截断与多行都如实发生。"""

    def __init__(self, tables: dict[str, list[dict]]) -> None:
        self._tables = tables
        self.log: list[tuple[str, list[_Cond], int | None]] = []

    def _run(self, q: _Query) -> _Result:
        self.log.append((q.key, list(q.conds), q.limit_n))
        return _Result(_match(self._tables.get(q.key, []), q.conds, q.limit_n))

    async def execute(self, q: _Query) -> _Result:
        return self._run(q)

    async def scalar(self, q: _Query) -> dict | None:
        rows = self._run(q).rows
        return rows[0] if rows else None


class _Recorder:
    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict]] = []

    def warning(self, event: str, **kw: object) -> None:
        self.warnings.append((event, kw))

    def info(self, event: str, **kw: object) -> None:
        pass

    def debug(self, event: str, **kw: object) -> None:
        pass

    def error(self, event: str, **kw: object) -> None:
        pass


SOURCE = _Model("Source", "type", "external_id", "url")
ASSET_M = _Model("ContentAsset", "source_id", "external_id", "url")


# ── AST 取件 ─────────────────────────────────────────────────────────────


def parse_err(src: str) -> str | None:
    try:
        ast.parse(src)
    except SyntaxError as exc:
        return f"{type(exc).__name__}@第 {exc.lineno} 行：{exc.msg}"
    return None


def _parses(src: str) -> bool:
    return parse_err(src) is None


def _fn_nodes(src: str, name: str) -> list[ast.AST]:
    """文件里所有叫这个名字的 def（含类内方法），按行号排；末位才是活绑定。"""
    found = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    return sorted(found, key=lambda n: n.lineno)


def _module_const(src: str, name: str) -> tuple[object, int, str | None]:
    """模块级 `NAME = <字面量>`：返回 (值, 出现次数, 失败原因)。"""
    vals: list[object] = []
    for st in ast.parse(src).body:
        if isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in st.targets):
            try:
                vals.append(ast.literal_eval(st.value))
            except ValueError:
                return None, len(vals), f"{name} 的右值不是字面量：{ast.unparse(st.value)}"
    if not vals:
        return None, 0, f"模块级没有 {name} 的赋值"
    if len(set(map(repr, vals))) > 1:
        return None, len(vals), f"{name} 被赋了不止一个值：{vals!r}"
    return vals[-1], len(vals), None


def _alias_map(tree: ast.AST) -> tuple[dict[str, str], dict[str, str]]:
    """两小张别名表：`名字 → 它被绑到的函数名`、`名字 → 它被绑到的字符串常量`。

    第十四轮 C 组 C-14-03 报的形状：`_R14T = setattr` 之后 `_R14T(AssetRepository, "get_by_url_fragment", …)`
    与 `NAME = "get_by_url_fragment"; setattr(Repo, NAME, …)` 都换掉了活绑定而判据绿——
    旧扫描只认字面 `setattr` 与字面第二实参。别名不需要图完备：这里只认**直接赋值给一个名字**这一跳，
    再深一层（`for` 循环里挑出来的）就由 AF-B5 那条行为面兜住，边界写在 README §7。
    """
    funcs: dict[str, str] = {}
    strs: dict[str, str] = {}
    for n in ast.walk(tree):
        if not isinstance(n, ast.Assign) or len(n.targets) != 1 or not isinstance(n.targets[0], ast.Name):
            continue
        v = n.value
        who = n.targets[0].id
        if isinstance(v, ast.Name):
            funcs[who] = v.id
        elif isinstance(v, ast.Attribute):
            funcs[who] = v.attr
        sv = _str_of(v)
        if sv is not None:
            strs[who] = sv
    return funcs, strs


def _name_of_arg(node: ast.AST, strs: dict[str, str]) -> str | None:
    """第二个实参到底是不是那个名字：字面量、或**绑定到该字面量的常量名**。"""
    sv = _str_of(node)
    if sv is not None:
        return sv
    if isinstance(node, ast.Name) and node.id in strs:
        return strs[node.id]
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _attr_rebinds(src: str, name: str) -> list[int]:
    """换掉活绑定的形状：`X.<name> = …`/`del X.<name>`、`setattr`/`delattr`（含别名与常量名实参）、
    `type(X).__setattr__(…)`、下标赋值。

    第十三轮 A 组实测：只有第一类会被抓到——`setattr(AssetRepository, "get_by_url_fragment", _legacy)`
    把方法换掉了而这条判据绿（`getattr` 反例 `AssetRepository.get_by_url_fragment = _legacy2` 才红）。
    BD 那台早就把这一族配齐（`j_attack_r7.py` 的 J-1…J-4），AF 台只配了一发，是覆盖不对称。
    第十四轮 C 组 C-14-03 又推进两发：`type.__setattr__` 与「别名 + 常量名」的 setattr 照样绿——
    这一族的规矩是**认语义不认字形**：谁调的不重要，重要的是那个名字被换掉了。
    名字查不到时还能由模块级 `__getattr__`（PEP 562）凭空造一份——那在 BD 台是 J-3，
    本台的 exec 面不经过模块属性查找，所以不在这里判，边界写在 README §7。
    """
    tree = ast.parse(src)
    funcs, strs = _alias_map(tree)
    hits = []
    for n in ast.walk(tree):
        tg: list[ast.expr] = []
        if isinstance(n, ast.Assign):
            tg = list(n.targets)
        elif isinstance(n, (ast.AnnAssign, ast.AugAssign)):
            tg = [n.target]
        elif isinstance(n, ast.Delete):
            tg = list(n.targets)
        for t in tg:
            if any(isinstance(s, ast.Attribute) and s.attr == name for s in ast.walk(t)):
                hits.append(getattr(n, "lineno", 0))
            # `vars(AssetRepository)["get_by_url_fragment"] = …` / `d["…"] = …`：下标形态同样换绑定
            if any(isinstance(s, ast.Subscript) and _str_of(s.slice) == name for s in ast.walk(t)):
                hits.append(getattr(n, "lineno", 0))
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        callee = ""
        if isinstance(f, ast.Name):
            callee = funcs.get(f.id, f.id)
        elif isinstance(f, ast.Attribute):
            callee = f.attr
        # `setattr(obj, "name", v)` / `delattr(obj, "name")` / `_T = setattr; _T(obj, "name", v)`
        if callee in {"setattr", "delattr"} and len(n.args) >= 2:
            idx = 1
            if _name_of_arg(n.args[idx], strs) == name:
                hits.append(n.lineno)
        # `type(X).__setattr__(X, "name", v)` / `object.__setattr__(…)` / `X.__setattr__("name", v)`
        elif isinstance(f, ast.Attribute) and f.attr in {"__setattr__", "__delattr__"}:
            for idx in (0, 1):
                if len(n.args) > idx and _name_of_arg(n.args[idx], strs) == name:
                    hits.append(n.lineno)
                    break
    return sorted(set(hits))


def _str_of(node: ast.AST) -> str | None:
    """节点若是字符串常量就取值，否则 None（`ast.Index` 包装在 3.11 里已被去掉）。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _calls_any_like(fn: ast.AST) -> list[ast.AST]:
    return [n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "like"]


def _select_calls(fn: ast.AST) -> list[ast.Call]:
    """体内的 `select(...)` 处数——AF-S2 的分母。"""
    return [n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "select"]


def _limit_calls(fn: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "limit"]


def _exec_fn(code: str, path: str, ns: dict) -> None:
    """单独 exec 一个函数节点，并强制 `from __future__ import annotations` 语义。

    两个目标的签名都带 ORM 类型注解（`-> Source | None`、`-> ContentAsset | None`），而这里的
    `Source`/`ContentAsset` 是假对象：不加这个编译标志，注解会在 def 求值时报
    `TypeError: unsupported operand type(s)` —— 那不是判据红，是取证工具自己坏了。
    磁盘上的真模块顶部本来就有 `from __future__ import annotations`，加标志才是同口径。

    `import __future__` 放在函数里而不是文件头：它是一条**普通** import，却会被 I001 按
    「同段内先 import 后 from」排在 `from __future__ import annotations` 之前——而那条
    future 语句必须是模块里第一条**future** 语句，前面不能有别的东西（`import __future__`
    不算 future 语句）。局部导入绕开这个死结，也让标志的来源在调用点就近可读。
    """
    import __future__

    exec(  # noqa: S102 - 执行仓库内受审代码
        compile(code, path, "exec", __future__.annotations.compiler_flag), ns
    )


def _world(kb_src: str, asset_src: str, source_rows: list[dict], asset_rows: list[dict],
           ) -> tuple[object, object, _StubSession, _Recorder, str | None]:
    """把两份磁盘源码里的目标函数 exec 进同一个假世界；返回 (锚函数, 片段函数, 会话, logger, 失败原因)。"""
    kb_fns = _fn_nodes(kb_src, KB_TARGET)
    as_fns = _fn_nodes(asset_src, AS_TARGET)
    if not kb_fns or not as_fns:
        return None, None, _StubSession({}), _Recorder(), "目标 def 不存在"
    session = _StubSession({"Source": list(source_rows), "ContentAsset": list(asset_rows)})
    rec = _Recorder()
    ns: dict[str, object] = {
        "select": lambda m: _Query(m._key),
        "Source": SOURCE,
        "ContentAsset": ASSET_M,
        "logger": rec,
        "__name__": "anchor_sliced",
    }
    try:
        biz = _fn_nodes(kb_src, "_biz_from_url")
        if biz:
            _exec_fn(ast.unparse(biz[-1]), str(KB), ns)
        const, _n, cerr = _module_const(asset_src, "MIN_FRAGMENT_LEN")
        if cerr:
            raise AssertionError(cerr)
        ns["MIN_FRAGMENT_LEN"] = const
        _exec_fn(ast.unparse(kb_fns[-1]), str(KB), ns)
        _exec_fn(ast.unparse(as_fns[-1]), str(ASSET), ns)
    except BaseException as exc:  # noqa: BLE001 - 变异体的破坏方式不受我们控制
        return None, None, session, rec, f"{type(exc).__name__}: {exc}"

    class _Host:
        def __init__(self, sess: _StubSession) -> None:
            self._session = sess

    anchor = ns[KB_TARGET]
    frag = ns[AS_TARGET]
    return (lambda ak, u: asyncio.run(anchor(_Host(session), ak, u)),
            lambda sid, f: asyncio.run(frag(_Host(session), sid, f)), session, rec, None)


def _call_anchor(kb_src: str, asset_src: str, article_key: str, url: str, source_rows: list[dict]):
    """跑一次锚定查询，返回 (结果, 会话账本, 异常名或空串)。"""
    anchor, _frag, sess, _rec, err = _world(kb_src, asset_src, source_rows, [])
    if err:
        return None, [], err
    try:
        return anchor(article_key, url), sess.log, ""
    except BaseException as exc:  # noqa: BLE001 - 「崩了」本身就是 P-4 的判据
        return None, sess.log, type(exc).__name__


def _call_frag(kb_src: str, asset_src: str, fragment: str, asset_rows: list[dict]):
    _anchor, frag, sess, rec, err = _world(kb_src, asset_src, [], asset_rows)
    if err:
        return None, [], rec, err
    try:
        return frag("src-1", fragment), sess.log, rec, ""
    except BaseException as exc:  # noqa: BLE001
        return None, sess.log, rec, type(exc).__name__


# ── 样本：一律取自夹具，脚本里不再抄第二份 URL ──────────────────────────────


def _samples() -> tuple[str, str, str, str]:
    from fixtures.wechat_urls import BIZ_A, LONG_A, SHORT_1, SHORT_TOKEN_1

    return BIZ_A, LONG_A, SHORT_1, SHORT_TOKEN_1


def _row(external_id: str, url: str) -> dict:
    return {"id": external_id, "type": "wechat_oa", "external_id": external_id, "url": url}


def _arow(url: str) -> dict:
    return {"id": "a1", "source_id": "src-1", "external_id": "k1", "url": url}


def _like_conds(log: list) -> list:
    return [c for _t, conds, _l in log for c in conds if c.op == "like"]


def _url_conds(log: list) -> list:
    return [c for _t, conds, _l in log for c in conds if c.col == "url"]


# ── 判据 ────────────────────────────────────────────────────────────────


def af_p0(kb: str, asset: str) -> tuple[bool, object]:
    _a, _f, _s, _r, err = _world(kb, asset, [], [])
    return err is None, err


def af_b1(kb: str, asset: str) -> tuple[bool, object]:
    biz, long_a = _samples()[0], _samples()[1]
    got, log, exc = _call_anchor(kb, asset, "s", long_a, [_row(biz, long_a)])
    ok = got is not None and not exc and len(log) == 1 and log[0][2] == 1
    eqs = [c for c in log[0][1] if c.op == "eq"]
    ok = ok and any(c.col == "external_id" and c.val == biz for c in eqs)
    return ok, f"结果 {got!r}、异常 {exc!r}、账本 {log}"


def af_b2(kb: str, asset: str) -> tuple[bool, object]:
    """两锚都不命中时必须返回 None，且**一条 URL 列条件都不许下发**——LIKE 兜底复活的形状就在这条上。"""
    long_a = _samples()[1]
    got, log, exc = _call_anchor(kb, asset, "s", long_a, [_row("MzOther0", "https://mp.weixin.qq.com/s/other0")])
    return (got is None and not exc and not _url_conds(log)), f"结果 {got!r}、异常 {exc!r}、URL 条件 {_url_conds(log)}"


def af_b3(kb: str, asset: str) -> tuple[bool, object]:
    """P-4 的形状：库里已有 ≥2 个 source（url 都含 `s`）时入库长链不得抛 MultipleResultsFound。"""
    long_a = _samples()[1]
    rows = [_row("MzOther0", "https://mp.weixin.qq.com/s/other0"),
            _row("MzOther1", "https://mp.weixin.qq.com/s/other1")]
    got, log, exc = _call_anchor(kb, asset, "s", long_a, rows)
    return got is None and exc == "", f"异常 {exc!r}（改前实测这一发就是 MultipleResultsFound）、账本 {log}"


def af_b4(kb: str, asset: str) -> tuple[bool, object]:
    """同一 external_id 有脏数据两行时，`limit(1)` 必须真的截断——摘掉它这条就抛。"""
    biz, long_a = _samples()[0], _samples()[1]
    rows = [_row(biz, long_a), _row(biz, long_a + "&mid=9")]
    got, log, exc = _call_anchor(kb, asset, "s", long_a, rows)
    limits = [l for _t, _c, l in log]
    return got is not None and exc == "" and limits == [1], f"结果 {got!r}、异常 {exc!r}、limit 列 {limits}"


def af_b6(kb: str, asset: str) -> tuple[bool, object]:
    """生产量级的短链键（18 字符）也不许下发任何 URL 列的 like 条件——按**条件**判，不按源码里的写法判。

    第十四轮 C 组 C-14-01 报的就是这一格：AF-B2 用的键是 `"s"`，而那一发攻击把兜底写成
    `if len(article_key) > 8: … getattr(getattr(Source, "url"), "like")(…)`——
    短键不发、长键才发，于是「兜底有没有复活」取决于探针喂了多长的键；而 `operator.methodcaller("like", …)`
    那一发连 AST 里的 `.like(` 字面形状都不留（AF-S1/S6 抓不到）。
    「URL LIKE 复活」在 SQL 层是一个**条件**，所以这里读的是假会话收到的条件集：任何拼法造出来的都算。
    """
    key = "RwMKZ3pT7qLdXe1bQs"
    url = f"https://mp.weixin.qq.com/s/{key}"
    rows = [_row("MzNotThisOne", url)]
    got, log, exc = _call_anchor(kb, asset, key, url, rows)
    likes = [c for c in _url_conds(log) if c.op == "like"]
    return (got is None and not exc and not likes), (
        f"结果 {got!r}、异常 {exc!r}、URL 上的 like 条件 {likes}（键长 {len(key)} 字符，短链 article_key 的真实量级）")


def af_b5(kb: str, asset: str) -> tuple[bool, object]:
    """短链：`_biz_from_url(SHORT_1)` 是空串，锚元组里的 `if a` 必须把它跳过，只用 article_key 锚。"""
    _biz, _long, short_1, short_key = _samples()
    got, log, exc = _call_anchor(kb, asset, short_key, short_1, [_row(short_key, short_1)])
    vals = [c.val for _t, conds, _l in log for c in conds if c.op == "eq" and c.col == "external_id"]
    ok = got is not None and not exc and len(log) == 1 and vals and all(v != "" for v in vals)
    return bool(ok), f"结果 {got!r}、异常 {exc!r}、external_id 取值 {vals}、账本 {log}"


def af_a1(kb: str, asset: str) -> tuple[bool, object]:
    """短片段：返回 None、零条 SQL、**恰一条** WARNING，且告警载荷齐三个键。

    第十三轮 A 组实测：把 `source_id=…/fragment=…/min_len=…` 三个 kw 全删掉，本条曾照样绿——
    那时无声放弃与留痕放弃长得一样，S2.1.5「显式放弃兜底并留痕」这句话的「痕」是空的。
    现在 `min_len` 的值还须等于磁盘上的阈值常量（阈值漂了告警也在撒谎）。
    """
    got, log, rec, exc = _call_frag(kb, asset, "s", [_arow("https://mp.weixin.qq.com/s/other0")])
    const, _n, cerr = _module_const(asset, "MIN_FRAGMENT_LEN")
    events = [w[0] for w in rec.warnings]
    kws = rec.warnings[0][1] if rec.warnings else {}
    bad = []
    if got is not None:
        bad.append(f"返回了资产 {got!r}")
    if exc:
        bad.append(f"抛了 {exc!r}")
    if log:
        bad.append(f"下发了 {len(log)} 条 SQL")
    if events != ["asset_url_fragment_too_short"]:
        bad.append(f"告警事件名 {events!r}（应为恰一条 asset_url_fragment_too_short）")
    if kws.get("source_id") != "src-1" or kws.get("fragment") != "s":
        bad.append(f"告警载荷缺 source_id/fragment：{kws!r}")
    if kws.get("min_len") != const:
        bad.append(f"告警里的 min_len={kws.get('min_len')!r} 与磁盘阈值 {const!r} 不符")
    return not bad, bad or [f"None、0 条 SQL、告警 {events}＋载荷 {sorted(kws)!r}"]


def af_a2(kb: str, asset: str) -> tuple[bool, object]:
    """空串维持「不查」，但不许刷 WARNING——空串是调用方没给值，不是命中风险。"""
    got, log, rec, exc = _call_frag(kb, asset, "", [])
    return bool(got is None and not exc and log == [] and rec.warnings == []), (
        f"结果 {got!r}、异常 {exc!r}、SQL {len(log)} 条、告警 {rec.warnings!r}")


def af_a3(kb: str, asset: str) -> tuple[bool, object]:
    """阈值边界卡在 8 个**字符**：7 挡、8 放，且非 ASCII 与非字母那两侧同口径。

    数字漂移（改成 1 或 12）当场红；把守卫换成按字节数（`len(fragment.encode("utf-8"))`）也会红——
    这一发是第十三轮 A 组报回的：三个样本全是 ASCII 时，字符数与字节数谁也分不开（MI-2）。
    `1234567` 是第十四轮 C 组 C-14-02 补的第四发：只测字母样本时，
    `if not fragment or fragment.isalpha(): return None` 那种「嵌一层条件的返回」在行为面上看不出来，
    而短数字片段（缓存键、纯数字 mid）正是被它放过去的那一类。
    """
    want = {"abcdefg": 0, "abcdefgh": 1, "热点热": 0, "1234567": 0}
    seen: dict[str, tuple[int, str]] = {}
    for frag, _ in want.items():
        _g, log, _r, exc = _call_frag(kb, asset, frag, [_arow(f"https://x/{frag}")])
        seen[frag] = (len(log), exc or "")
    ok = all(seen[f] == (n, "") for f, n in want.items())
    return ok, f"片段→(SQL 条数, 异常) {seen}（`热点热` 3 字符 / 9 字节，按字节数就会放行；`1234567` 7 字符必须挡）"


def af_a4(kb: str, asset: str) -> tuple[bool, object]:
    """放行的片段仍按 (source_id eq + url like + limit 1) 下发并返回匹配行：守卫不等于关掉兜底。

    取两个长度各测一遍：`aaaa1111` 卡在阈值下沿（阈值漂到 12 时它会被误挡），
    18 字符那发是真实 article_key 的量级（比较方向被写成 `>` 时它会被误挡）。
    只测一个长度就会漏掉一类漂移——第十二轮复审前本判据只测 8，`>` 变异体全绿。
    """
    seen = {}
    for frag in ("aaaa1111", "aaaa1111bbbb2222cc"):
        rows = [_arow(f"https://mp.weixin.qq.com/s?sn={frag}")]
        got, log, _rec, exc = _call_frag(kb, asset, frag, rows)
        if not log:
            seen[frag] = "一条 SQL 都没下发"
            continue
        _key, conds, limit = log[0]
        seen[frag] = (got is not None and not exc and limit == 1
                      and any(c.op == "eq" and c.col == "source_id" for c in conds)
                      and any(c.op == "like" and c.col == "url" for c in conds))
    return all(v is True for v in seen.values()), f"片段→放行形状 {seen}"


def af_a5(kb: str, asset: str) -> tuple[bool, object]:
    frag = "aaaa1111"
    _g, log, _r, exc = _call_frag(kb, asset, frag, [_arow(f"https://x/{frag}")])
    pats = [c.val for c in _like_conds(log)]
    return pats == [f"%{frag}%"], f"LIKE 实参 {pats}、异常 {exc!r}"


def af_s1(kb: str, _asset: str) -> tuple[bool, object]:
    fn = _fn_nodes(kb, KB_TARGET)
    if not fn:
        return False, f"kb.py 里没有 {KB_TARGET}"
    return not _calls_any_like(fn[-1]), f"体内 like 调用 {len(_calls_any_like(fn[-1]))} 处"


def _select_chains(fn: ast.AST) -> list[tuple[list[ast.Call], int]]:
    """每条 `select(...)` 的**方法链**（自下而上爬，再把分句的那几跳接回来）。

    只数处数判不了「limit 挂在哪条链上」——第十三轮 A 组的绕过是
    `q = select(Source).where(...)`（无 limit）+ 另起一句 `_diag = q.limit(1)`：
    体内 select 与 limit 的个数仍然相等，AF-S2 那版「数处数」就绿了，而真正被执行的链没带 limit。

    反过来，第十四轮 C 组 C-14-06 报的是**假红**那一侧：`q = select(…).where(…)` 之后
    `q = q.limit(1)` 这种拆句写法、`sel = select` 的别名、`sqlalchemy.select(…)` 的属性形态，
    三种都语义正确地带着 LIMIT 1，旧爬法第一跳就断。所以这里把链读成**数据流上的链**：
    向上爬完之后，顺着「这条链被赋给了哪个变量」再走一跳，把 `q.<meth>(…)` 的后续调用也算进同一条链。
    """
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(fn):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    funcs, _strs = _alias_map(fn)
    # 右端 → 被赋给的那个变量名（用来把 `q = select(…)` / `q = q.limit(1)` 这种断链接回去）
    rvalue_vars: dict[int, list[str]] = {}
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    rvalue_vars.setdefault(id(n.value), []).append(t.id)

    def is_origin(n: ast.AST) -> bool:
        if not isinstance(n, ast.Call):
            return False
        f = n.func
        if isinstance(f, ast.Name):
            return funcs.get(f.id, f.id) == "select"
        return isinstance(f, ast.Attribute) and f.attr == "select"

    out: list[tuple[list[ast.Call], int]] = []
    for n in ast.walk(fn):
        if not is_origin(n):
            continue
        chain: list[ast.Call] = []
        cur: ast.AST = n
        while True:
            up = parent.get(cur)
            # `select(X).where(...)` 的树形是 Call ← Attribute ← Call：中间那个 Attribute 必须先爬过去，
            # 否则第一跳就断，链永远读成空（第十三轮处置批实测错过这一跳，AF-S2 在**未变异**的 kb.py 上报红）。
            if isinstance(up, ast.Attribute) and up.value is cur:
                cur = up
                continue
            if isinstance(up, ast.Call) and up.func is cur:
                chain.append(up)
                cur = up
                continue
            break
        # 分句那一跳：链尾被赋给了某个变量，就把 `变量.<meth>(…)` 的后续调用接进同一条链
        seen_vars: set[str] = set()
        work = list(rvalue_vars.get(id(cur), []))
        while work:
            var = work.pop()
            if var in seen_vars:
                continue
            seen_vars.add(var)
            for m in ast.walk(fn):
                if (isinstance(m, ast.Call) and isinstance(m.func, ast.Attribute)
                        and isinstance(m.func.value, ast.Name) and m.func.value.id == var):
                    if m not in chain:
                        chain.append(m)
                    work += rvalue_vars.get(id(m), [])
        out.append((chain, n.lineno))
    return out


def _literal_one(call: ast.Call) -> bool:
    return len(call.args) == 1 and isinstance(call.args[0], ast.Constant) and call.args[0].value == 1


def af_s2(kb: str, _asset: str) -> tuple[bool, object]:
    """**每条被执行的选择链**都带字面 `.limit(1)`——不是「体内 limit 的个数刚好等于 select 的个数」。

    判据说的是链，所以分母取自 `_select_chains`（沿 `select(…).where(…).limit(1)` 这类链式调用爬），
    旁路上另挂一个 `.limit(1)` 不顶数。`.where` 与 `.limit` 换序仍算等价（两种顺序都在同一条链上）。
    """
    fn = _fn_nodes(kb, KB_TARGET)
    if not fn:
        return False, f"kb.py 里没有 {KB_TARGET}"
    chains = _select_chains(fn[-1])
    bad = []
    for chain, line in chains:
        limits = [c for c in chain if isinstance(c.func, ast.Attribute) and c.func.attr == "limit"]
        if not limits:
            bad.append(f"@{line}: 链上方法 {[c.func.attr for c in chain if isinstance(c.func, ast.Attribute)]}"
                       "——没有 limit")
        elif not all(_literal_one(c) for c in limits):
            bad.append(f"@{line}: 链上有 limit 但不是字面 1：{[ast.unparse(c) for c in limits]}")
    return bool(chains) and not bad, bad or [f"{len(chains)} 条选择链都带字面 .limit(1)"]


def _guard_if(asset: str) -> tuple[ast.AST | None, str]:
    fns = _fn_nodes(asset, AS_TARGET)
    if not fns:
        return None, f"asset.py 里没有 {AS_TARGET}"
    for st in fns[-1].body:
        if isinstance(st, ast.If):
            return st, ""
    return None, "函数体里没有一个 `if` 守卫分支"


def _compare_ok(test: ast.AST, const_val: object) -> tuple[bool, str]:
    """守卫条件必须是「`len(fragment)` 与阈值的单一比较」（两侧换边的 `>` 写法同样接受）。

    第十三轮 A 组实测的漂移：`if len(fragment.encode("utf-8")) < MIN_FRAGMENT_LEN:` 在旧判据下全绿
    ——旧写法只问「哪一侧以 `len(` 开头」，不问 `len()` 数的是**什么**。按字节数长度是行为差
    （3 个汉字 = 9 字节会被放行，而卡面口径是「片段长度 <8」的字符数），所以这里钉死实参照回形参本体，
    并让 AF-A3 带一发多字节样本（`热点热`：3 字符必须挡）。
    """
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False, f"守卫条件不是单一比较：{ast.unparse(test)}"
    op = type(test.ops[0]).__name__
    left, right = test.left, test.comparators[0]

    def _is_len_of_fragment(e: ast.AST) -> bool:
        return (isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and e.func.id == "len"
                and len(e.args) == 1 and isinstance(e.args[0], ast.Name) and e.args[0].id == "fragment")

    lenish = next((e for e in (left, right) if _is_len_of_fragment(e)), None)
    thresh = next((e for e in (left, right)
                   if ast.unparse(e) == "MIN_FRAGMENT_LEN" or _const_of(e) == const_val), None)
    if lenish is None or thresh is None:
        return False, (f"两侧不是「len(fragment) 与阈值」：{ast.unparse(test)}"
                       "（`len()` 的实参必须是形参 `fragment` 本体，数别的都不是卡面那条长度）")
    same_side = (lenish is left)
    want = "Lt" if same_side else "Gt"
    if op != want:
        return False, f"比较方向是 {op}，应当是 {want}（方向反了就把长短判反）"
    return True, ""


def _const_of(node: ast.AST) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    return None


def af_s3(kb: str, asset: str) -> tuple[bool, object]:
    """守卫分支形状：`if` 的条件是 len 与阈值的比较，分支体里既有 `logger.warning` 也**直接** `return None`。

    合并成 `if fragment and len(...) < MIN:` 这种写法会被本条抓住（条件成了 BoolOp），
    因为它对空串不再返回 None——那是行为差，不是等价的换写法（见 MUTANTS 里那一发）。

    「直接」这一限定是第十四轮 C 组 C-14-02 补的：把尾部换成
    `if not fragment or fragment.isalpha(): return None` 之后，旧写法在整棵 If 子树里 `ast.walk`
    找一个 `return None` 照样找得到 ⇒ 18 条判据全绿，而短**数字**片段（`1234567`）既不为空也不是字母，
    守卫直接放行、LIKE 照发。守卫的语义是「进了这个分支就不许再往下查」，
    所以那个 return 必须是分支体的成员，而不是嵌在下面某一层条件里——
    告警那一半刻意不要求直接：它本来就该只在片段非空时响（AF-A2 判的就是这个差别）。
    """
    node, why = _guard_if(asset)
    if node is None:
        return False, why
    const, _n, cerr = _module_const(asset, "MIN_FRAGMENT_LEN")
    if cerr:
        return False, cerr
    ok, why = _compare_ok(node.test, const)
    if not ok:
        return False, why
    body = ast.unparse(node)
    bad = []
    if "logger.warning(" not in body and ".warning(" not in body:
        bad.append("分支里没有 logger.warning")
    direct = [st for st in node.body
              if isinstance(st, ast.Return) and isinstance(st.value, ast.Constant)
              and st.value.value is None]
    if not direct:
        nested = [n.lineno for n in ast.walk(node)
                  if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)
                  and n.value.value is None]
        bad.append(f"分支体里没有**直接**的 `return None`（嵌在下一层条件的第 {nested} 行不算："
                   f"那一层的条件不成立时，短片段照样往下发 LIKE）")
    return not bad, bad


def af_s4(kb: str, asset: str) -> tuple[bool, object]:
    const, n_bind, err = _module_const(asset, "MIN_FRAGMENT_LEN")
    if err:
        return False, err
    return n_bind == 1 and const == CARD_MIN_LEN, f"磁盘上的值 {const!r}（赋值 {n_bind} 处），卡面口径 {CARD_MIN_LEN}"


def af_s5(kb: str, asset: str) -> tuple[bool, object]:
    """两个目标各自全文件只有一份 def、没有被属性形态重绑、也没有装饰器（被 exec 的就是活绑定）。"""
    bad = []
    for src, name, path in ((kb, KB_TARGET, KB), (asset, AS_TARGET, ASSET)):
        fns = _fn_nodes(src, name)
        if len(fns) != 1:
            bad.append(f"{name} 的 def 有 {len(fns)} 处 @{[n.lineno for n in fns]}（{path.name}）")
            continue
        hits = _attr_rebinds(src, name)
        if hits:
            bad.append(f"{name} 被属性形态重绑/解绑 @{hits}")
        if getattr(fns[0], "decorator_list", []):
            bad.append(f"{name} 带装饰器 @{fns[0].lineno}——单独 exec 的那份与 import 拿到的那份不是同一个")
    return not bad, bad


def af_s6(kb: str, _asset: str) -> tuple[bool, object]:
    """整份 kb.py 的 AST 里**一个 `.like(` 调用都不许有**——不只认 `Source.url.like(...)` 那一种写法。

    第十三轮 A 组实测的绕过：`col = Source.url` 之后 `col.like(f"%{key}%")`，以及
    `getattr(Source, "url").like(...)`——两发都把兜底复活了而按字面形状匹配的这条判据全绿
    （当时 18 条判据 `PASS=18 FAIL=0`）。兜底被删掉这件事的射程是「这条 SQL 写法」而不是
    「这一串字符」，所以判据跟着换成「任何接收者上的 `.like(` 调用」；别名与 `getattr` 两种形状
    各配一发变异。
    留档里 kb.py 的注释仍会提到这条兜底（历史说明，不是代码），走 AST 而不是 grep 文本正因为如此。
    """
    hits = _calls_any_like(ast.parse(kb))
    return not hits, [f"@{n.lineno}: {ast.unparse(n)}" for n in hits]


def _assigned_values(fn: ast.AST) -> dict[str, list[ast.expr]]:
    """局部赋值表：名字 → 它被赋过的那些值表达式（沿「先存进变量再用」那一跳走时要查）。"""
    out: dict[str, list[ast.expr]] = {}
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out.setdefault(t.id, []).append(n.value)
    return out


def _reaches(expr: ast.expr, want: str, binds: dict[str, list[ast.expr]],
             seen: frozenset[str]) -> bool:
    """`expr` 的可达式里是否出现 `want(...)` 调用：直接写在内层算，绕道局部变量也算（走到不动点）。"""
    if any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == want
           for c in ast.walk(expr)):
        return True
    for n in ast.walk(expr):
        if isinstance(n, ast.Name) and n.id not in seen and n.id in binds:
            if any(_reaches(v, want, binds, seen | {n.id}) for v in binds[n.id]):
                return True
    return False


def af_s7(kb: str, _asset: str) -> tuple[bool, object]:
    """锚必须**真的来自**委托结果——不是「体内既有 `_biz_from_url` 调用、又有 external_id 比较」那种共现。

    第十三轮 A 组的覆盖读数里，AF-S7 是唯一只有 1 发 provider 的判据，因为它是共现判据：
    四件事可以同时成立却互不相关（第六轮复审在 BD 台上报过同一类，当时改成数据流才堵住）。
    现在顺着流走——找到把值比给 `Source.external_id` 的那条循环，要求它迭代表的可达式里含委托调用；
    `_b = _biz_from_url(url)` 存进局部变量再进锚元组那种等价写法仍然算数（EQUIVS 里就有那一发）。
    """
    fns = _fn_nodes(kb, KB_TARGET)
    if not fns:
        return False, f"kb.py 里没有 {KB_TARGET}"
    body = fns[-1]
    loops = {n.target.id: n.iter for n in ast.walk(body)
             if isinstance(n, (ast.For, ast.AsyncFor)) and isinstance(n.target, ast.Name)}
    binds = _assigned_values(body)
    bad: list[str] = []
    n_cmp = 0
    for n in ast.walk(body):
        if not (isinstance(n, ast.Compare)
                and any(isinstance(x, ast.Attribute) and x.attr == "external_id" for x in ast.walk(n))):
            continue
        n_cmp += 1
        names = [x.id for x in ast.walk(n) if isinstance(x, ast.Name) and x.id in loops]
        if not names:
            bad.append(f"@{n.lineno}: 与 `external_id` 比的不是任何循环锚变量：{ast.unparse(n)}")
        for name in names:
            if not _reaches(loops[name], "_biz_from_url", binds, frozenset()):
                bad.append(f"@{n.lineno}: `{name}` 的锚来源里没有委托调用：{ast.unparse(loops[name])}")
    if n_cmp == 0:
        return False, "体内没有任何与 `Source.external_id` 的比较（锚查询被换掉了）"
    return not bad, bad or [f"{n_cmp} 处 external_id 比较所用的锚，其来源都可达 `_biz_from_url`"]


CHECKS: tuple[tuple[str, str, object], ...] = (
    ("AF-P0", "两个目标都能被单独 exec（行为面判据的前提）", af_p0),
    ("AF-B1", "biz 锚命中：一条查询、external_id 比到 biz、带 limit(1)", af_b1),
    ("AF-B2", "两锚皆空返回 None，且一条 URL 列条件都不下发", af_b2),
    ("AF-B3", "P-4 形状：库内 ≥2 个含 s 的 source 时不抛 MultipleResultsFound", af_b3),
    ("AF-B4", "同 external_id 的脏数据两行被 limit(1) 截断（摘掉就抛）", af_b4),
    ("AF-B5", "短链：空 biz 被 `if a` 跳过，只用 article_key 锚", af_b5),
    ("AF-B6", "生产量级的 18 字符键也不下发 URL 列 like 条件（按条件判，不按 `.like(` 字形判）", af_b6),
    ("AF-A1", "片段 's'：返回 None、零条 SQL、恰一条 WARNING（事件名点名）", af_a1),
    ("AF-A2", "空片段：返回 None、零条 SQL、不刷 WARNING", af_a2),
    ("AF-A3", "阈值边界卡在 8（7 挡、8 放）", af_a3),
    ("AF-A4", "放行路径形态仍是 source_id eq + url like + limit(1) 并返回匹配行", af_a4),
    ("AF-A5", "LIKE 实参确实是 %片段%", af_a5),
    ("AF-S1", f"{KB_TARGET} 体内没有 .like( 调用", af_s1),
    ("AF-S2", f"{KB_TARGET} 体内每条 select 链都带字面 .limit(1)", af_s2),
    ("AF-S3", f"{AS_TARGET} 守卫分支形状齐备（比较 + return None + warning）", af_s3),
    ("AF-S4", f"磁盘上 MIN_FRAGMENT_LEN 唯一绑定且等于 {CARD_MIN_LEN}", af_s4),
    ("AF-S5", "两个目标各自活绑定唯一（无重复 def / 无属性重绑 / 无装饰器）", af_s5),
    ("AF-S6", "kb 全文 AST 层不再出现 Source.url.like(...)", af_s6),
    ("AF-S7", "锚仍来自 _biz_from_url 的结果（不许顺手拆掉 S2.1.3）", af_s7),
)


def _judged(judge: object, kb: str, asset: str) -> tuple[bool, object]:
    """跑一条判据，**崩了也下裁决**：`evaluate()` 一直有这层 try，`run()`（基线路径）从前没有。

    第十三轮 A 组实测（MI-8）：把 `MIN_FRAGMENT_LEN` 再赋一次这类变异喂进基线路径时，AF-B1 在
    空账本上取 `log[0]` 抛 `IndexError` ⇒ 整脚本 rc=1、stderr 是 traceback、stdout 连「合计」行都没有，
    三档退出码的自证里又没有「exec 不了」这一档——那正是本项目禁的「崩栈冒充裁决」。
    现在两条路径共用这一层：崩按红记，并把异常形状原样写进读数里。
    """
    try:
        ok, detail = judge(kb, asset)  # type: ignore[operator]
        return bool(ok), detail
    except BaseException as exc:  # noqa: BLE001 - 判据自己崩了也是裁决的一种，但必须出声
        return False, f"判据抛出 {type(exc).__name__}: {exc}"


def evaluate(kb: str, asset: str) -> set[str]:
    red: set[str] = set()
    for cid, _label, judge in CHECKS:
        ok = _judged(judge, kb, asset)[0]
        if not ok:
            red.add(cid)
    return red


def run(kb: str, asset: str, label: str = "") -> int:
    passed.clear()
    failed.clear()
    for path, src in ((KB, kb), (ASSET, asset)):
        err = parse_err(src)
        if err is not None:
            say(f"INCONCLUSIVE {path.name} 解析不了：{err}\n"
                "              结构面要 AST、行为面要 exec，两者都无从判定；"
                "打印成 FAIL 清单会冒充红基线，让它 traceback 上去则违反「崩栈不是裁决」。")
            say(f"合计 未判定 PASS=0 FAIL=0（INCONCLUSIVE，rc={RC_INCONCLUSIVE}）")
            return RC_INCONCLUSIVE
    if not _fn_nodes(kb, KB_TARGET) or not _fn_nodes(asset, AS_TARGET):
        say("INCONCLUSIVE 目标函数至少有一个不在文件里（S2.1.4/S2.1.5 未落地或被改名）——"
            "此时任何判据都无从判定，故与「有判据红」分档返回，不打印 FAIL 清单冒充红基线。")
        say(f"合计 未判定 PASS=0 FAIL=0（INCONCLUSIVE，rc={RC_INCONCLUSIVE}）")
        return RC_INCONCLUSIVE
    note(f"目标：{label or '磁盘上的 kb.py + asset.py'}"
         f"（AST 取 {KB_TARGET} / {AS_TARGET} 的活绑定那份 def，真实 exec + 记账假会话后再下裁决）\n")
    note(f"夹具样本来自 {TESTS.relative_to(REPO).as_posix()}/fixtures/wechat_urls.py，本脚本不抄第二份 URL\n")
    for cid, label_txt, judge in CHECKS:
        ok, detail = _judged(judge, kb, asset)
        check(f"{cid} {label_txt}", ok, detail)
    say(f"\n合计 PASS={len(passed)} FAIL={len(failed)}｜判据登记 {len(CHECKS)} 条")
    for lbl in failed:
        say(f"  FAIL {lbl}")
    note(
        "边界：本脚本用记账假会话证明「生产代码向 DB 要了什么」；SQL 引擎侧的真实执行与 commit 只交"
        "`test_kb_multisource_anchor.py` 那两条**连库**用例（J-6），"
        "`test_asset_fragment_guard.py` 的四条走的是记账假会话、不连库，它补的是**用例面**而非引擎面（J-7）"
        "——两份都需要 structlog+sqlalchemy 才能收集，但别把两份读成同一件事。"
        "文件名/用例名登记在 `replay_s213.py` 的 `REAL_DB_TARGETS`，由 G 段逐条按 AST 核对 ⇒ README §5。"
    )
    return RC_FAIL if failed else RC_GREEN


# ── 变异锚：全部取自磁盘上的当前代码，失配必须由 count!=1 报出来 ──────────────

KB_LOOP = "        for anchor in (a for a in (_biz_from_url(url), article_key) if a):"
KB_TAIL = ("                    .limit(1)\n                )\n            ).scalar_one_or_none()\n"
           "            if row is not None:\n                return row\n        return None\n")
KB_TAIL_OLD = ("                    .limit(1)\n                )\n            ).scalar_one_or_none()\n"
               "            if row is not None:\n                return row\n"
               "        row = (\n            await self._session.execute(\n"
               "                select(Source).where(\n"
               "                    Source.type == \"wechat_oa\",\n"
               "                    Source.url.like(f\"%{article_key}%\"),\n"
               "                )\n            )\n        ).scalar_one_or_none()\n        return row\n")
KB_NO_LIMIT = "                    .limit(1)\n                )\n            ).scalar_one_or_none()"
AS_GUARD = ("        if len(fragment) < MIN_FRAGMENT_LEN:\n"
            "            if fragment:\n"
            "                logger.warning(\n"
            '                    "asset_url_fragment_too_short",\n'
            "                    source_id=source_id,\n"
            "                    fragment=fragment,\n"
            "                    min_len=MIN_FRAGMENT_LEN,\n"
            "                )\n"
            "            return None\n")
AS_OLD = '        if not fragment:\n            return None\n'
AS_TAIL = '            return None\n        return await self._session.scalar(\n'
AS_LIKE = '                ContentAsset.url.like(f"%{fragment}%"),\n            )\n            .limit(1)\n'
#: 类内下一个方法的 def 行（全文件唯一）。重复定义的变异锚在这里而不是文件末尾：
#: 方法名活在 `AssetRepository` 的命名空间里，往**模块**级再 def 一个同名函数并不换掉它，
#: 那是无害代码不是攻击；只有类内的后一份 def 才会把活绑定换掉（实测缩进错到模块级 ⇒ 变异体自己解析不了）。
AS_NEXT_DEF = "    async def upsert_content("

#: (标签, 改哪份文件, 旧锚, 新代码, 必须变红的判据)
MUTANTS: list[tuple[str, str, str, str, set[str]]] = [
    ("退回 S2.1.4 改前：把 `Source.url.like('%article_key%')` 兜底原样放回", "kb", KB_TAIL, KB_TAIL_OLD,
     {"AF-S1", "AF-S6", "AF-B2", "AF-B3"}),
    ("摘掉锚查询的 .limit(1)（同 external_id 的脏数据会抛）", "kb", KB_NO_LIMIT,
     "                )\n            ).scalar_one_or_none()", {"AF-S2", "AF-B4"}),
    ("锚元组里不用委托结果（S2.1.3 的接线被顺手拆掉）", "kb", KB_LOOP,
     "        for anchor in (a for a in (article_key,) if a):", {"AF-S7", "AF-B1", "AF-B4"}),
    ("去掉 `if a` 过滤：空 biz 也去查一次锚", "kb", KB_LOOP,
     "        for anchor in (_biz_from_url(url), article_key):", {"AF-B5"}),
    ("锚命中了也不返回（`if row is not None` 改成永假）", "kb",
     "            if row is not None:\n                return row",
     "            if False:\n                return row", {"AF-B1", "AF-B4", "AF-B5"}),
    ("给锚定方法加一个引用未定义名字的装饰器（被 exec 的那份与活绑定不是同一个）", "kb",
     "    async def _find_source_by_anchor(", "    @_probe_cache\n    async def _find_source_by_anchor(",
     {"AF-P0", "AF-S5"}),
    ("退回 S2.1.5 改前：守卫换回 `if not fragment:`", "asset", AS_GUARD, AS_OLD,
     {"AF-S3", "AF-A1", "AF-A3"}),
    ("阈值漂到 1（守卫形同虚设）", "asset", "MIN_FRAGMENT_LEN = 8", "MIN_FRAGMENT_LEN = 1",
     {"AF-S4", "AF-A1", "AF-A3"}),
    ("阈值漂到 12（把存量兼容路径也挡了）", "asset", "MIN_FRAGMENT_LEN = 8", "MIN_FRAGMENT_LEN = 12",
     {"AF-S4", "AF-A3", "AF-A4"}),
    ("去掉 WARNING（静默放弃兜底）", "asset", AS_GUARD,
     "        if len(fragment) < MIN_FRAGMENT_LEN:\n            return None\n", {"AF-S3", "AF-A1"}),
    ("空串也刷 WARNING（把「调用方没给值」当成命中风险）", "asset",
     "        if len(fragment) < MIN_FRAGMENT_LEN:\n            if fragment:\n",
     "        if len(fragment) < MIN_FRAGMENT_LEN:\n            if True:\n", {"AF-A2"}),
    ("比较方向写成 `>`（长短判反）", "asset", "        if len(fragment) < MIN_FRAGMENT_LEN:",
     "        if len(fragment) > MIN_FRAGMENT_LEN:", {"AF-S3", "AF-A1", "AF-A4"}),
    ("守卫分支只剩告警、不 return（继续发 SQL）", "asset", AS_TAIL,
     "        return await self._session.scalar(\n", {"AF-A1", "AF-A3", "AF-S3"}),
    ("合并成 `if fragment and len(...) < MIN:`（空串不再返回 None，是行为差）", "asset", AS_GUARD,
     "        if fragment and len(fragment) < MIN_FRAGMENT_LEN:\n"
     '            logger.warning("asset_url_fragment_too_short")\n'
     "            return None\n", {"AF-A2", "AF-S3"}),
    ("摘掉片段查询的 .limit(1)", "asset", AS_LIKE,
     '                ContentAsset.url.like(f"%{fragment}%"),\n            )\n', {"AF-A4"}),
    ("LIKE 模式丢掉通配符（片段变成整串相等）", "asset", 'ContentAsset.url.like(f"%{fragment}%"),',
     "ContentAsset.url.like(fragment),", {"AF-A5"}),
    ("类内再 def 一份同名方法（活绑定换成后面那份，且它永返 None）", "asset",
     AS_NEXT_DEF,
     "    async def get_by_url_fragment(self, source_id: str, fragment: str) -> ContentAsset | None:\n"
     "        return None\n\n" + AS_NEXT_DEF, {"AF-S5", "AF-A4"}),
    ("模块级把 MIN_FRAGMENT_LEN 再赋一次（阈值被后面的赋值覆盖）", "asset",
     "MIN_FRAGMENT_LEN = 8", "MIN_FRAGMENT_LEN = 8\nMIN_FRAGMENT_LEN = 3\n", {"AF-S4"}),
    # ↓ 第十三轮 A 组报回的四种绕过 + 两类可漂移的形状。每一发都要求**新的**判据变红：
    #   旧版 AF-S6 只认 `Source.url.like(...)` 字面形状、AF-S5 只认属性赋值、AF-S2 只数处数、
    #   AF-S3 只问「哪一侧以 len( 开头」、AF-A1 只比事件名——这五发在旧版上全部是绿的。
    ("别名复活兜底：`col = Source.url` 后 `col.like(...)`（模块级新函数，不碰锚定方法）", "kb",
     "def _article_key(url: str) -> str:",
     "def _r13_legacy_fallback(key: str):\n"
     "    col = Source.url\n"
     '    return select(Source).where(col.like(f"%{key}%"))\n\n\n'
     "def _article_key(url: str) -> str:",
     {"AF-S6"}),
    ("getattr 形态的兜底：`getattr(Source, \"url\").like(...)` 写在锚定方法体内", "kb",
     KB_LOOP,
     KB_LOOP + '\n            _r13 = getattr(Source, "url").like(f"%{article_key}%")',
     {"AF-S1", "AF-S6"}),
    ("setattr 换掉活绑定（def 还在、名字也没动，被 exec 的却是新实现）", "asset",
     AS_NEXT_DEF,
     '    setattr(AssetRepository, "get_by_url_fragment", lambda self, sid, frag: None)\n\n'
     + AS_NEXT_DEF,
     {"AF-S5"}),
    ("下标形态换绑定（`registry[\"方法名\"] = …`，属性赋值那套扫描看不见）", "asset",
     AS_NEXT_DEF,
     "    _r13_registry: dict = {}\n"
     '    _r13_registry["get_by_url_fragment"] = None\n\n'
     + AS_NEXT_DEF,
     {"AF-S5"}),
    ("limit 挂到旁路上、被执行的链没带（select 与 limit 的**处数**仍然相等）", "kb",
     KB_TAIL,
     "                )\n            ).scalar_one_or_none()\n"
     "            if row is not None:\n                return row\n"
     '        _r13 = select(Source).where(Source.type == "wechat_oa").limit(1)\n'
     "        return None\n",
     {"AF-S2"}),
    ("守卫按**字节**数长度（3 个汉字 9 字节被放行，卡面说的是长度 <8 个字符）", "asset",
     AS_GUARD,
     AS_GUARD.replace("if len(fragment) < MIN_FRAGMENT_LEN:",
                      'if len(fragment.encode("utf-8")) < MIN_FRAGMENT_LEN:'),
     {"AF-S3", "AF-A3"}),
    ("告警只留事件名、载荷全删（无声放弃与留痕放弃长得一样）", "asset",
     AS_GUARD,
     "        if len(fragment) < MIN_FRAGMENT_LEN:\n"
     "            if fragment:\n"
     '                logger.warning("asset_url_fragment_too_short")\n'
     "            return None\n",
     {"AF-A1"}),
    ("委托调用还在、结果却被丢弃（共现判据抓不到，AF-S7 改数据流之后才有第二发 provider）", "kb",
     KB_LOOP,
     "        _biz_from_url(url)\n"
     "        for anchor in (a for a in (article_key,) if a):",
     {"AF-S7"}),
    # ↓ 第十四轮 C 组报回的四发：上一批补的是**字形**（`.like(`、`setattr(`、属性赋值），
    #   这四发都是同一族里换个字形的形状——静态扫描看不见，行为面或语义扫描才看得见。
    ("嵌套 getattr 复活兜底、且只对长键生效：AF-S1/S6 读不到 `.like(` 字形，AF-B2 用的又是短键 ⇒ 全绿",
     "kb", KB_LOOP,
     KB_LOOP + "\n            if len(article_key) > 8:\n"
     "                _r14 = select(Source).where(\n"
     '                    getattr(getattr(Source, "url"), "like")(f"%{article_key}%")).limit(1)\n'
     "                return (await self._session.execute(_r14)).scalar_one_or_none()",
     {"AF-B6"}),
    ("methodcaller 复活兜底：连 `like` 都不是被调用的那个属性名（AST 找 attr==\"like\" 也读不到）", "kb",
     KB_LOOP,
     KB_LOOP + "\n            import operator as _r14op\n"
     "            _r14 = select(Source).where(\n"
     '                _r14op.methodcaller("like", f"%{article_key}%")(Source.url)).limit(1)\n'
     "            return (await self._session.execute(_r14)).scalar_one_or_none()",
     {"AF-B6"}),
    ("守卫的 return 嵌进另一层条件：静态三件（比较、告警、返回）都在，短数字片段却照样往下发 LIKE", "asset",
     AS_GUARD,
     AS_GUARD.replace("            return None\n",
                      "            if fragment.isalpha():\n                return None\n"),
     {"AF-S3", "AF-A3"}),
    ("`type.__setattr__(类, \"方法名\", …)`：既不是属性赋值也不是裸 setattr", "asset", AS_NEXT_DEF,
     '    type.__setattr__(AssetRepository, "get_by_url_fragment", lambda self, sid, frag: None)\n\n'
     + AS_NEXT_DEF, {"AF-S5"}),
    ("setattr 先被绑到一个别名上，再由别名调用（旧扫描只认 `setattr` 这个名字）", "asset", AS_NEXT_DEF,
     '    _r14_t = setattr\n'
     '    _r14_t(AssetRepository, "get_by_url_fragment", lambda self, sid, frag: None)\n\n'
     + AS_NEXT_DEF, {"AF-S5"}),
    ("setattr 的第二实参是常量名而不是字面量（旧扫描只比 `_str_of(args[1])`）", "asset", AS_NEXT_DEF,
     '    _r14_name = "get_by_url_fragment"\n'
     "    setattr(AssetRepository, _r14_name, lambda self, sid, frag: None)\n\n"
     + AS_NEXT_DEF, {"AF-S5"}),
]

#: select 链的原文（`.where` 在前、`.limit` 在后）与其等价换序版：AF-S2 数的是处数，不是顺序。
KB_SELECT_BLOCK = (
    "                    select(Source)\n"
    "                    .where(\n"
    '                        Source.type == "wechat_oa",\n'
    "                        Source.external_id == anchor,\n"
    "                    )\n"
    "                    .limit(1)\n"
)
KB_SELECT_SWAPPED = (
    "                    select(Source)\n"
    "                    .limit(1)\n"
    "                    .where(\n"
    '                        Source.type == "wechat_oa",\n'
    "                        Source.external_id == anchor,\n"
    "                    )\n"
)
#: 整条 `row = (...)` 语句的原文：下面三发等价重构都以它为锚（第十四轮 C 组 C-14-06 报的三种形状，
#: 每一种都真的带 LIMIT 1，旧 `_select_chains` 却把它们判成红——那是假红，不是抓到绕过）。
KB_ROW_BLOCK = (
    "            row = (\n"
    "                await self._session.execute(\n"
    "                    select(Source)\n"
    "                    .where(\n"
    '                        Source.type == "wechat_oa",\n'
    "                        Source.external_id == anchor,\n"
    "                    )\n"
    "                    .limit(1)\n"
    "                )\n"
    "            ).scalar_one_or_none()\n"
)
#: 拆成三句：链被切成 `q = select(…)` / `q = q.where(…)` / `q = q.limit(1)`，被执行的还是同一个对象。
KB_ROW_SPLIT = (
    "            _r14_q = select(Source)\n"
    "            _r14_q = _r14_q.where(\n"
    '                Source.type == "wechat_oa",\n'
    "                Source.external_id == anchor,\n"
    "            )\n"
    "            _r14_q = _r14_q.limit(1)\n"
    "            row = (await self._session.execute(_r14_q)).scalar_one_or_none()\n"
)
#: 别名：`sel = select` 之后 `sel(Source)…`，select 这个名字根本不出现。
KB_ROW_ALIAS = (
    "            _r14_sel = select\n"
    "            row = (\n"
    "                await self._session.execute(\n"
    "                    _r14_sel(Source)\n"
    "                    .where(\n"
    '                        Source.type == "wechat_oa",\n'
    "                        Source.external_id == anchor,\n"
    "                    )\n"
    "                    .limit(1)\n"
    "                )\n"
    "            ).scalar_one_or_none()\n"
)
#: 模块限定：`ns.select(Source)…`——被调用者是属性而不是裸名字。
KB_ROW_QUALIFIED = (
    "            import types as _r14_types\n"
    "            _r14_ns = _r14_types.SimpleNamespace(select=select)\n"
    "            row = (\n"
    "                await self._session.execute(\n"
    "                    _r14_ns.select(Source)\n"
    "                    .where(\n"
    '                        Source.type == "wechat_oa",\n'
    "                        Source.external_id == anchor,\n"
    "                    )\n"
    "                    .limit(1)\n"
    "                )\n"
    "            ).scalar_one_or_none()\n"
)
#: 片段查询的原文与「先存局部变量」版：行为完全一致，只考验判据是否依赖链式写法。
AS_QUERY_BLOCK = (
    "        return await self._session.scalar(\n"
    "            select(ContentAsset)\n"
    "            .where(\n"
    "                ContentAsset.source_id == source_id,\n"
    '                ContentAsset.url.like(f"%{fragment}%"),\n'
    "            )\n"
    "            .limit(1)\n"
    "        )\n"
)
AS_QUERY_LOCAL = (
    "        q = select(ContentAsset).where(\n"
    "            ContentAsset.source_id == source_id,\n"
    '            ContentAsset.url.like(f"%{fragment}%"),\n'
    "        ).limit(1)\n"
    "        return await self._session.scalar(q)\n"
)

#: (标签, 改哪份文件, 旧锚, 等价新写法)
EQUIVS: list[tuple[str, str, str, str]] = [
    ("select 链里 .where 与 .limit 换序", "kb", KB_SELECT_BLOCK, KB_SELECT_SWAPPED),
    ("链拆成三句（`q = select(…)` / `q = q.where(…)` / `q = q.limit(1)`）——语义带着 LIMIT 1，"
     "旧爬法第一跳就断（第十四轮 C 组 MI-1 的假红）", "kb", KB_ROW_BLOCK, KB_ROW_SPLIT),
    ("select 被起了个别名（`_sel = select` 之后 `_sel(Source)…`）", "kb", KB_ROW_BLOCK, KB_ROW_ALIAS),
    ("select 走模块属性（`ns.select(Source)…`，被调用者是 Attribute 而不是裸名字）", "kb",
     KB_ROW_BLOCK, KB_ROW_QUALIFIED),
    ("锚元组的生成式换成列表推导", "kb", KB_LOOP,
     "        for anchor in [a for a in (_biz_from_url(url), article_key) if a]:"),
    ("委托结果先存局部变量再进锚元组", "kb", KB_LOOP,
     "        biz_anchor = _biz_from_url(url)\n"
     "        for anchor in (a for a in (biz_anchor, article_key) if a):"),
    ("阈值显式写成字面 8（行为等价，常量本身由 AF-S4 盯）", "asset",
     "        if len(fragment) < MIN_FRAGMENT_LEN:", "        if len(fragment) < 8:"),
    ("比较两侧换边：MIN_FRAGMENT_LEN > len(fragment)", "asset", "        if len(fragment) < MIN_FRAGMENT_LEN:",
     "        if MIN_FRAGMENT_LEN > len(fragment):"),
    ("select 先存局部变量再 scalar", "asset", AS_QUERY_BLOCK, AS_QUERY_LOCAL),
]


def _mutate(entry, kb: str, asset: str) -> tuple[str, str, str]:
    """按锚做一次字符串替换，返回平铺的 (新 kb, 新 asset, 失败原因)。

    三项必须平铺：早先写成 `(out, asset) if … else (kb, out), "", ""` 会被 Python 解析成
    「嵌套元组 + 两个空串」，调用方 `kb2, asset2, why = _mutate(…)` 拿到的 kb2 是个 tuple、
    asset2 是空串——self-test 的档位层把它炸成了 `TypeError: compile() arg 1 must be a string`。
    """
    label, which, old, new = entry[0], entry[1], entry[2], entry[3]
    base = kb if which == "kb" else asset
    n = base.count(old)
    if n != 1:
        return kb, asset, f"锚在 {which} 里出现 {n} 次（应为 1 次）：{label}"
    out = base.replace(old, new)
    if not _parses(out):
        return kb, asset, f"改后无法解析（锚缩进错）：{label}｜{parse_err(out)}"
    return (out, asset, "") if which == "kb" else (kb, out, "")


def coverage(observed: list[set[str]]) -> list[str]:
    """没有任何一发变异**实测**打红的判据 id。

    分母是 `CHECKS`、分子是各发变异跑出来的真实红集——不是 `MUTANTS` 里声明的 must_red：
    声明可以写错（锚失效时那一发根本没跑成），实测不能。号数一律现算，不抄读数。
    """
    hit: set[str] = set()
    for red in observed:
        hit |= red
    return sorted(cid for cid, _l, _j in CHECKS if cid not in hit)


def _ovr(flag: str) -> Path | None:
    for arg in sys.argv:
        if arg.startswith(flag):
            return Path(arg.split("=", 1)[1])
    return None


def _read(path: Path) -> str:
    """按 utf-8-sig 读：CPython 允许源文件带 BOM，判据不许因为 BOM 而崩。"""
    return path.read_text(encoding="utf-8-sig")


def _read_pair(kb_path: Path, asset_path: Path) -> tuple[str, str, str]:
    """把两份源文件读进来；读不动时返回原因而不是让 UnicodeDecodeError 往上抛。

    第十四轮 C 组 C-14-11：`_judged()` 那层管住了**判据**崩，`run()` 开头也核对了「解析不了」，
    但 `main()` 里的两次 `_read()` 一直裸着——喂一份 `# -*- coding: gbk -*-` 的副本（CPython 认它）
    就 rc=1 + traceback，stdout 连「合计」行都没有。那是第三种形态（压根没读到东西），
    按本项目的纪律必须落 INCONCLUSIVE 档，而不是混进「有判据红」。
    """
    out = []
    for p in (kb_path, asset_path):
        try:
            out.append(_read(p))
        except (UnicodeDecodeError, OSError) as exc:
            return "", "", f"{p.name} 读不出来：{type(exc).__name__}: {exc}"
    return out[0], out[1], ""


def _strip_fn(src: str, name: str) -> str:
    """按行删掉目标 def（含其装饰器，只在内存里，不动工作树），用于档位自证。"""
    node = _fn_nodes(src, name)[-1]
    lines = src.splitlines(keepends=True)
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])]) - 1
    return "".join(lines[:start] + lines[node.end_lineno:])


def self_test() -> int:
    rc = 0
    kb, asset, why = _read_pair(_ovr("--kb=") or KB, _ovr("--asset=") or ASSET)
    if why:
        print(f"INCONCLUSIVE self-test 的基准读不出来：{why}——变异与等价两条通道都没有锚")
        return RC_INCONCLUSIVE
    if not _fn_nodes(kb, KB_TARGET) or not _fn_nodes(asset, AS_TARGET):
        print(f"INCONCLUSIVE 目标至少缺一个（kb.{KB_TARGET} / asset.{AS_TARGET}）——"
              f"基准都无从构造，变异与等价两条通道的锚没有落点")
        return RC_INCONCLUSIVE
    base_red = evaluate(kb, asset)
    if base_red:
        print(f"FAIL 基准（未变异）就有红判据：{sorted(base_red)}——self-test 结论不可用")
        return RC_FAIL
    print(f"OK   基准：磁盘上的 kb.py + asset.py 判据全绿（{len(CHECKS)} 条）")

    # 档位自证（内存层）：三档必须互不相同，否则「没测到」会被读成「测出红」。
    global _quiet
    _quiet = True
    m0 = _mutate(MUTANTS[0], kb, asset)
    tiers = [
        ("基准（未变形）", run(kb, asset), RC_GREEN),
        (f"删掉 {KB_TARGET}", run(_strip_fn(kb, KB_TARGET), asset), RC_INCONCLUSIVE),
        (f"删掉 {AS_TARGET}", run(kb, _strip_fn(asset, AS_TARGET)), RC_INCONCLUSIVE),
        ("退回旧实现（LIKE 兜底复活）", run(m0[0], m0[1]), RC_FAIL),
        ("kb 解析不了", run(kb + "\ndef _probe_broken(:\n    pass\n", asset), RC_INCONCLUSIVE),
        ("asset 解析不了", run(kb, asset + "\nclass _X(:\n    pass\n"), RC_INCONCLUSIVE),
        # 第十三轮 A 组 MI-8：这一发让 `_world()` 建不起来（阈值常量被重复绑定 ⇒ exec 前置校验抛），
        # 从前行为面判据照旧去取空账本的 `log[0]` ⇒ IndexError、stdout 连「合计」行都没有。
        # 现在它必须落在「有判据红」这一档，并且照常打印合计行——崩栈不是裁决，档位自证原来缺这一档。
        ("阈值常量被重复绑定（exec 用的世界建不起来）",
         run(kb, asset.replace("MIN_FRAGMENT_LEN = 8\n", "MIN_FRAGMENT_LEN = 8\nMIN_FRAGMENT_LEN = 3\n", 1)),
         RC_FAIL),
    ]
    _quiet = False
    tier_offenders = [f"{name} 应 rc={want}，实得 rc={got}"
                      for name, got, want in tiers if got != want]
    if tier_offenders:
        print("FAIL 档位自证：" + "；".join(tier_offenders))
        rc = 1
    else:
        print(f"OK   档位自证（内存层）：绿 {RC_GREEN} / 目标缺失 {RC_INCONCLUSIVE} / 有判据红 {RC_FAIL} / "
              f"解析不了也按 {RC_INCONCLUSIVE} 档报（{len(tiers)} 档各测一面，逐档核过）")

    # 退出码自证（子进程层）：三档必须真的映射到进程退出码，且在 win32 默认的 cp936 输出流下
    # 不许以 traceback 收场——只测 `run()` 的返回值等于没测到 `sys.exit` 那一步。
    tmp = Path(tempfile.mkdtemp(prefix="afb_tiers_"))
    offenders: list[str] = []
    try:
        cases = [
            ("基准", kb, asset, RC_GREEN, "utf-8"),
            ("基准带 BOM", "﻿" + kb, asset, RC_GREEN, "utf-8"),
            ("删掉锚定方法", _strip_fn(kb, KB_TARGET), asset, RC_INCONCLUSIVE, "utf-8"),
            ("删掉片段方法", kb, _strip_fn(asset, AS_TARGET), RC_INCONCLUSIVE, "utf-8"),
            ("退回旧实现", m0[0], m0[1], RC_FAIL, "utf-8"),
            ("kb 解析不了", kb + "\ndef _probe_broken(:\n    pass\n", asset, RC_INCONCLUSIVE, "utf-8"),
            # MI-8 的第二层：同一发世界建不起来的情况走真实进程退出码，并且不许留 traceback。
            ("阈值重复绑定（世界建不起来）", kb,
             asset.replace("MIN_FRAGMENT_LEN = 8\n",
                           "MIN_FRAGMENT_LEN = 8\nMIN_FRAGMENT_LEN = 3\n", 1), RC_FAIL, "utf-8"),
            # 第十四轮 C 组 C-14-11：`main()` 里那两次读文件当时没有 try——喂一份 GBK 的副本
            # （CPython 认 `# -*- coding: gbk -*-`，那是**合法源文件**而不是坏输入）就 rc=1 + traceback，
            # stdout 连「合计」行都没有。现在它必须落 INCONCLUSIVE 档，与「有判据红」分开。
            ("kb 是 GBK 编码的合法源文件", "# -*- coding: gbk -*-\n" + kb, asset, RC_INCONCLUSIVE, "gbk"),
        ]
        for name, kb_body, asset_body, want, enc in cases:
            ck, ca = tmp / "kb.py", tmp / "asset.py"
            ck.write_text(kb_body, encoding=enc, errors="replace")
            ca.write_text(asset_body, encoding="utf-8")
            r = subprocess.run(  # noqa: S603 - 只跑本文件自己
                [sys.executable, str(Path(__file__).resolve()), f"--kb={ck}", f"--asset={ca}", "--quiet"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "cp936"}, check=False,
            )
            if r.returncode != want:
                offenders.append(f"{name} 应 rc={want}，子进程实得 rc={r.returncode}")
            if "Traceback (most recent call last)" in (r.stderr or ""):
                offenders.append(f"{name} 以 traceback 收场，而不是给出裁决")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if offenders:
        print("FAIL 退出码自证：" + "；".join(offenders))
        rc = 1
    else:
        print(f"OK   退出码自证：子进程真实退出码分得开，且无一把它崩成 traceback"
              f"（{len(cases)} 档全在 cp936 输出流下跑，含 BOM 与两份文件各自的缺失/崩溃形状）")

    # 编码自证（与 BD/PI 两台 harness 同一档，K 段据此判 `_ensure_utf8_stdout()` 是否承重）：
    # 把**父进程自己**放进被测面——`--self-test` 末尾那句总结里带 `⇒`，GBK/cp936 编不出它。
    # 只让子进程跑一次 `--self-test`，guard 一旦被关掉这一档就会崩在 print 处（既不是绿也不是红）。
    # `AF_NO_NEST` 防无限递归自调：嵌套那一层不再开第三层，但它照样要打印带 ⇒ 的那句总结。
    # 「子进程全绿」也可能是**假绿**（靶字被抽掉时这一档没东西可判），所以额外要求子进程 stdout
    # 里确实打印过 ⇒——K.3 那一发就是把文件里所有 ⇒ 换成 `->`，那一发必须让这里变红。
    if os.environ.get("AF_NO_NEST") != "1":
        r = subprocess.run(  # noqa: S603 - 只跑本文件自己
            [sys.executable, str(Path(__file__).resolve()), "--self-test"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "cp936", "AF_NO_NEST": "1"}, check=False,
        )
        crashed = "Traceback (most recent call last)" in (r.stderr or "")
        # 靶字写成转义形式：K.3 的复现是把文件里所有 ⇒ 换成 `->`，这里若也写字面 ⇒，
        # 那条 sed 会连判据一起改掉、检查就自我失效了（BD 台第一次试跑真的踩到这一点）。
        no_target = "\u21d2" not in (r.stdout or "")
        if crashed or r.returncode != 0:
            lines = (r.stderr or "").strip().splitlines() or (r.stdout or "").strip().splitlines()
            why = lines[-1] if lines else "子进程输出随崩溃丢失（裸跑该命令可看到 UnicodeEncodeError）"
            print(f"FAIL 编码自证：--self-test 在 cp936 输出流下 rc={r.returncode}"
                  + ("，收场异常：" if crashed else "，末行：") + why)
            rc = 1
        elif no_target:
            print(f"FAIL 编码自证：子进程 rc={r.returncode} 且无 traceback，但它 stdout 里一个靶字"
                  "（U+21D2）都没有——靶字被抽掉了，这一档没东西可判（假绿比红更糟）")
            rc = 1
        else:
            print("OK   编码自证：--self-test 全程在编不出 `⇒` 的 cp936 输出流下跑完，rc=0 无 traceback"
                  "，且子进程 stdout 里确实打印过 ⇒（靶子在场）")

    observed: list[set[str]] = []
    for entry in MUTANTS:
        label = entry[0]
        mutated_kb, mutated_asset, why = _mutate(entry, kb, asset)
        if why:
            print(f"FAIL {why}")
            rc = 1
            continue
        red = evaluate(mutated_kb, mutated_asset)
        observed.append(red)
        miss = {k for k in entry[4] if k not in red}
        if miss:
            print(f"FAIL {label}｜应红未红：{sorted(miss)}｜实际红：{sorted(red)}")
            rc = 1
        else:
            print(f"OK   {label} → 致红 {sorted(red)}")

    for entry in EQUIVS:
        label = entry[0]
        mutated_kb, mutated_asset, why = _mutate((*entry, set()), kb, asset)
        if why:
            print(f"FAIL 等价重构：{why}")
            rc = 1
            continue
        red = evaluate(mutated_kb, mutated_asset)
        if red:
            print(f"FAIL 等价写法被判成缺陷：{label}｜假红={sorted(red)}")
            rc = 1
        else:
            print(f"OK   等价重构 {label} → 判据全绿")

    # 覆盖表：每一条判据都要有一发变异能把它**实测**打红（没有实测变异的判据等于悄悄注销）。
    gaps = coverage(observed)
    if gaps:
        print(f"FAIL 覆盖：{len(gaps)} 条判据没有任何一发变异能把它打红：{gaps}")
        rc = 1
    else:
        print(f"OK   覆盖：{len(CHECKS)} 条判据 each 至少被一发变异实测打红（变异 {len(observed)}/{len(MUTANTS)} 发跑成）")
    # 这条覆盖判据自己也要能假。阈值在这一批**反过来定**（第十三轮处置批自查，理由必须留在这里）：
    # 前一版要求「≥2 发变异抽不得」，而第十三轮补进 8 发同族变异之后 26 发**全都抽得**——因为 18 条判据
    # 每条都有了 ≥2 发 provider。旧阈值把冗余当成缺陷：电池越结实它越要报 FAIL，方向是反的。
    # 现在门禁判「每条判据至少有两发独立变异能把它打红」（provider<2 即红，0 发也在这条里），
    # 「有多少发抽不得」降级为读数——0 才说明没有单点依赖。这条改动是可假的两端：
    # 少配一发 provider，`low` 立刻点名那一判据（上一版则会出现「加发变异反而变红」的荒谬读数）。
    providers = {cid: sum(1 for red in observed if cid in red) for cid, _l, _j in CHECKS}
    low = sorted(f"{cid}({n} 发)" for cid, n in providers.items() if n < 2)
    essential = [i for i in range(len(observed)) if coverage(observed[:i] + observed[i + 1:])]
    if low:
        print(f"FAIL 覆盖自证：{len(low)} 条判据的 provider 不足两发：{low}——"
              f"「每条判据都配了变异」这句话在这些条上还是形容词")
        rc = 1
    else:
        print(f"OK   覆盖自证：{len(CHECKS)} 条判据每条都有 ≥2 发变异实测打红"
              f"（最少 {min(providers.values())} 发、最多 {max(providers.values())} 发；"
              f"变异 {len(observed)}/{len(MUTANTS)} 发跑成；「抽掉一发就露缺口」的抽不得发 {len(essential)} 发"
              f"——0 才是这条链的满分，它从这一批起不再是门禁）")

    print(f"\nSELF-TEST {'PASS' if rc == 0 else 'FAIL'}：判据 {len(CHECKS)} 条 + 变异 {len(MUTANTS)} 发"
          f" + 等价 {len(EQUIVS)} 个 + 档位 {len(tiers)} 档（内存）/{len(cases)} 档（子进程）"
          f" ⇒ 三档分得开、崩栈不是裁决（这句本身也是编码自证的靶字，见上档）")
    return rc


def listing() -> int:
    for cid, label, _judge in CHECKS:
        print(f"{cid}｜{label}")
    return 0


def main() -> int:
    global _terse
    if "--quiet" in sys.argv:
        _terse = True
    kb_path = _ovr("--kb=") or KB
    asset_path = _ovr("--asset=") or ASSET
    if not kb_path.exists():
        print(f"FAIL kb.py 不存在：{kb_path}")
        return RC_FAIL
    if not asset_path.exists():
        print(f"FAIL asset.py 不存在：{asset_path}")
        return RC_FAIL
    label = "｜".join(p.relative_to(REPO).as_posix() if p.is_relative_to(REPO) else str(p)
                      for p in (kb_path, asset_path))
    kb_src, asset_src, why = _read_pair(kb_path, asset_path)
    if why:
        print(f"INCONCLUSIVE {why}——结构面要 AST、行为面要 exec，两条通道都无从判定；"
              "把它打成 FAIL 会冒充「有判据红」，让它 traceback 上去则违反「崩栈不是裁决」。")
        print(f"合计 未判定 PASS=0 FAIL=0（INCONCLUSIVE，rc={RC_INCONCLUSIVE}）")
        return RC_INCONCLUSIVE
    return run(kb_src, asset_src, label)


if __name__ == "__main__":
    if "--list-checks" in sys.argv:
        sys.exit(listing())
    sys.exit(self_test() if "--self-test" in sys.argv else main())
