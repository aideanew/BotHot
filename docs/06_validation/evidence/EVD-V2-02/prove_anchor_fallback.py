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
边界要说清：这里证的是「生产代码向 DB 要了什么、拿到结果怎么处理」，**不是** SQL 引擎怎么执行
（真库那条走 `test_kb_multisource_anchor.py` 与 `test_asset_fragment_guard.py`，
文件名与用例名登记在 `replay_s213.py` 的 `REAL_DB_TARGETS` 里、由 G 段逐条核对确有其事；
见 EVD-V2-02 README §5 J-1/J-5）。

判据分三面（`--list-checks` 打全清单，条数一律现算不手抄）：
- 前提 AF-P0：两个目标都能被单独 exec（exec 不了就没有裁决，只有 traceback）；
- 行为面 AF-B1…B5 / AF-A1…A5：biz 锚命中、两锚皆空不许落到 URL 兜底、多源含 `s` 不崩、
  `limit(1)` 真的挡住同 `external_id` 的脏数据、短链的空 biz 被跳过；
  短片段不发 SQL 且留 WARNING、空串不告警、阈值边界卡在 7/8、放行路径形态仍是
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


def _attr_rebinds(src: str, name: str) -> list[int]:
    """`X.<name> = …` / `del X.<name>` 这类属性形态重绑（def 还在，活绑定已换）。"""
    hits = []
    for n in ast.walk(ast.parse(src)):
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
    return hits


def _call_like(fn: ast.AST, model_attr: str, col: str) -> list[ast.AST]:
    """函数/文件里对 `<model_attr>.<col>.like(...)` 的调用点。"""
    out = []
    for n in ast.walk(fn):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "like"
                and isinstance(n.func.value, ast.Attribute) and n.func.value.attr == col
                and isinstance(n.func.value.value, ast.Name) and n.func.value.value.id == model_attr):
            out.append(n)
    return out


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


def af_b5(kb: str, asset: str) -> tuple[bool, object]:
    """短链：`_biz_from_url(SHORT_1)` 是空串，锚元组里的 `if a` 必须把它跳过，只用 article_key 锚。"""
    _biz, _long, short_1, short_key = _samples()
    got, log, exc = _call_anchor(kb, asset, short_key, short_1, [_row(short_key, short_1)])
    vals = [c.val for _t, conds, _l in log for c in conds if c.op == "eq" and c.col == "external_id"]
    ok = got is not None and not exc and len(log) == 1 and vals and all(v != "" for v in vals)
    return bool(ok), f"结果 {got!r}、异常 {exc!r}、external_id 取值 {vals}、账本 {log}"


def af_a1(kb: str, asset: str) -> tuple[bool, object]:
    got, log, rec, exc = _call_frag(kb, asset, "s", [_arow("https://mp.weixin.qq.com/s/other0")])
    ok = (got is None and not exc and log == [] and [w[0] for w in rec.warnings]
          == ["asset_url_fragment_too_short"])
    return bool(ok), f"结果 {got!r}、异常 {exc!r}、SQL {len(log)} 条、告警 {rec.warnings!r}"


def af_a2(kb: str, asset: str) -> tuple[bool, object]:
    """空串维持「不查」，但不许刷 WARNING——空串是调用方没给值，不是命中风险。"""
    got, log, rec, exc = _call_frag(kb, asset, "", [])
    return bool(got is None and not exc and log == [] and rec.warnings == []), (
        f"结果 {got!r}、异常 {exc!r}、SQL {len(log)} 条、告警 {rec.warnings!r}")


def af_a3(kb: str, asset: str) -> tuple[bool, object]:
    """阈值边界卡在 8：7 个字符挡、8 个字符放。数字漂移（改成 1 或 12）这条当场红。"""
    seen = {}
    for frag in ("abcdefg", "abcdefgh"):
        _g, log, _r, exc = _call_frag(kb, asset, frag, [_arow(f"https://x/{frag}")])
        seen[len(frag)] = (len(log), exc)
    ok = seen.get(7) == (0, "") and seen.get(8) == (1, "")
    return ok, f"长度→(SQL 条数, 异常) {seen}"


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


def af_s2(kb: str, _asset: str) -> tuple[bool, object]:
    fn = _fn_nodes(kb, KB_TARGET)
    if not fn:
        return False, f"kb.py 里没有 {KB_TARGET}"
    body = fn[-1]
    n_select = len(_select_calls(body))
    limits = _limit_calls(body)
    ones = [n for n in limits if len(n.args) == 1 and isinstance(n.args[0], ast.Constant) and n.args[0].value == 1]
    return n_select > 0 and len(limits) == n_select and len(ones) == n_select, (
        f"体内 select {n_select} 处、limit 调用 {len(limits)} 处（其中字面 1 的 {len(ones)} 处）")


def _guard_if(asset: str) -> tuple[ast.AST | None, str]:
    fns = _fn_nodes(asset, AS_TARGET)
    if not fns:
        return None, f"asset.py 里没有 {AS_TARGET}"
    for st in fns[-1].body:
        if isinstance(st, ast.If):
            return st, ""
    return None, "函数体里没有一个 `if` 守卫分支"


def _compare_ok(test: ast.AST, const_val: object) -> tuple[bool, str]:
    """守卫条件必须是「len(fragment) 与阈值的 `<` 比较」（两侧换边的 `>` 写法同样接受）。"""
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False, f"守卫条件不是单一比较：{ast.unparse(test)}"
    op = type(test.ops[0]).__name__
    left, right = test.left, test.comparators[0]
    lenish = next((e for e in (left, right) if ast.unparse(e).startswith("len(")), None)
    thresh = next((e for e in (left, right)
                   if ast.unparse(e) == "MIN_FRAGMENT_LEN" or _const_of(e) == const_val), None)
    if lenish is None or thresh is None:
        return False, f"两侧不是「len(...) 与阈值」：{ast.unparse(test)}"
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
    """守卫分支形状：`if` 的条件是 len 与阈值的比较，分支体里既有 `logger.warning` 也 `return None`。

    合并成 `if fragment and len(...) < MIN:` 这种写法会被本条抓住（条件成了 BoolOp），
    因为它对空串不再返回 None——那是行为差，不是等价的换写法（见 MUTANTS 里那一发）。
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
    if not any(isinstance(n, ast.Return) and isinstance(n.value, ast.Constant) and n.value.value is None
               for n in ast.walk(node)):
        bad.append("分支里没有 return None")
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
    """整份 kb.py 的 AST 里不许再有 `Source.url.like(...)`——只在锚定方法里删干净不算数。

    留档里 kb.py 的注释仍然提到这条兜底（那是历史说明，不是代码），所以本条走 AST 而不是 grep 文本。
    """
    hits = _call_like(ast.parse(kb), "Source", "url")
    return not hits, [f"@{n.lineno}: {ast.unparse(n)}" for n in hits]


def af_s7(kb: str, _asset: str) -> tuple[bool, object]:
    """改这段时不许顺手把 S2.1.3 的接线拆掉：体内既调 `_biz_from_url`，也比 `Source.external_id`。"""
    fns = _fn_nodes(kb, KB_TARGET)
    if not fns:
        return False, f"kb.py 里没有 {KB_TARGET}"
    body = fns[-1]
    calls = [n for n in ast.walk(body)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_biz_from_url"]
    cmps = [n for n in ast.walk(body) if isinstance(n, ast.Compare) and "external_id" in ast.unparse(n)]
    return bool(calls) and bool(cmps), f"_biz_from_url 调用 {len(calls)} 处、external_id 比较 {len(cmps)} 处"


CHECKS: tuple[tuple[str, str, object], ...] = (
    ("AF-P0", "两个目标都能被单独 exec（行为面判据的前提）", af_p0),
    ("AF-B1", "biz 锚命中：一条查询、external_id 比到 biz、带 limit(1)", af_b1),
    ("AF-B2", "两锚皆空返回 None，且一条 URL 列条件都不下发", af_b2),
    ("AF-B3", "P-4 形状：库内 ≥2 个含 s 的 source 时不抛 MultipleResultsFound", af_b3),
    ("AF-B4", "同 external_id 的脏数据两行被 limit(1) 截断（摘掉就抛）", af_b4),
    ("AF-B5", "短链：空 biz 被 `if a` 跳过，只用 article_key 锚", af_b5),
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


def evaluate(kb: str, asset: str) -> set[str]:
    red: set[str] = set()
    for cid, _label, judge in CHECKS:
        try:
            ok = judge(kb, asset)[0]
        except BaseException as exc:  # noqa: BLE001 - 判据自己崩了也按红记，但注明是异常
            ok = False
            if not (_quiet or _terse):
                print(f"     （{cid} 判据抛出 {type(exc).__name__}: {exc}）")
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
        ok, detail = judge(kb, asset)
        check(f"{cid} {label_txt}", ok, detail)
    say(f"\n合计 PASS={len(passed)} FAIL={len(failed)}｜判据登记 {len(CHECKS)} 条")
    for lbl in failed:
        say(f"  FAIL {lbl}")
    note(
        "边界：本脚本用记账假会话证明「生产代码向 DB 要了什么」；SQL 引擎侧的真实执行与 commit 交"
        "`test_kb_multisource_anchor.py::test_multi_source_no_crash` 与 `test_asset_fragment_guard.py`"
        "（需 structlog+sqlalchemy，本机皆无；两份的文件名/用例名登记在 `replay_s213.py` 的 "
        "`REAL_DB_TARGETS`，由 G 段逐条核对磁盘上确有其事）⇒ README §5 J-1/J-5。"
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


def _strip_fn(src: str, name: str) -> str:
    """按行删掉目标 def（含其装饰器，只在内存里，不动工作树），用于档位自证。"""
    node = _fn_nodes(src, name)[-1]
    lines = src.splitlines(keepends=True)
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])]) - 1
    return "".join(lines[:start] + lines[node.end_lineno:])


def self_test() -> int:
    rc = 0
    kb = _read(_ovr("--kb=") or KB)
    asset = _read(_ovr("--asset=") or ASSET)
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
            ("基准", kb, asset, RC_GREEN),
            ("基准带 BOM", "\ufeff" + kb, asset, RC_GREEN),
            ("删掉锚定方法", _strip_fn(kb, KB_TARGET), asset, RC_INCONCLUSIVE),
            ("删掉片段方法", kb, _strip_fn(asset, AS_TARGET), RC_INCONCLUSIVE),
            ("退回旧实现", m0[0], m0[1], RC_FAIL),
            ("kb 解析不了", kb + "\ndef _probe_broken(:\n    pass\n", asset, RC_INCONCLUSIVE),
        ]
        for name, kb_body, asset_body, want in cases:
            ck, ca = tmp / "kb.py", tmp / "asset.py"
            ck.write_text(kb_body, encoding="utf-8")
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
    # 这条覆盖判据自己也要能假：逐发抽掉它，看覆盖是否立刻出现缺口——一发都抽不得的电池才是真电池。
    essential = [i for i in range(len(observed)) if coverage(observed[:i] + observed[i + 1:])]
    if len(essential) < 2:
        print(f"FAIL 覆盖自证：{len(observed)} 发实测变异里只有 {len(essential)} 发不可省略（下标 {essential}）——"
              f"任意抽掉一发都仍全覆盖，说明「覆盖」靠的是别处，这条通道不可假")
        rc = 1
    else:
        k = essential[0]
        print(f"OK   覆盖自证：{len(essential)}/{len(observed)} 发变异不可省略；抽掉第 {k} 发"
              f"（{MUTANTS[k][0]}）即露出缺口 {coverage(observed[:k] + observed[k + 1:])}")

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
    return run(_read(kb_path), _read(asset_path), label)


if __name__ == "__main__":
    if "--list-checks" in sys.argv:
        sys.exit(listing())
    sys.exit(self_test() if "--self-test" in sys.argv else main())
