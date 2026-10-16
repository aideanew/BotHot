"""STEP-02 竞态修复的本机证明件：`kb._save_short_link` 的后发者必须被 savepoint 吸收。

为什么需要本机件：这条洞只在**两个事务交错**时出现，连库用例在 `@ci` 上靠时序
（run 38908795127 红在 `test_concurrent_same_url_converges`，同一条在 38899498196 上是绿的），
而本机没有 PG 也没有 docker。靠 flaky 的绿当证据，等于把判定力交给调度器。
本件用 AST 取出**磁盘上 kb.py 的当前函数体**真实执行（不是抄本），配一台
可脚本化抛 IntegrityError 的假 session，四条判据都是确定的行为断言。

判据：
- SR-B1 正常写入：查不到既有行 ⇒ 走一次 add + 一次 flush，不抛；
- SR-B2 竞态冲突：查不到既有行、flush 抛 IntegrityError、重查查到对手的行 ⇒ **不抛**
  （这就是修复本体；旧实现没有 savepoint，异常会一路冒到 HTTP 面）；
- SR-B3 非唯一冲突：flush 抛 IntegrityError 而重查仍查不到 ⇒ **必须上抛**
  （兜底只认唯一冲突这一种；无条件吞掉就是把别的数据问题藏起来）；
- SR-B4 已存在：查得到既有行 ⇒ 早退，一次 add/flush 都不下发（省一次无谓写）；
- SR-S1 结构面：插入必须在 `begin_nested()` 里，且体内有 `except IntegrityError`
  ——行为面 B2 已抓住大部分，结构面抓「换个写法把 savepoint 摘掉」。

反证（`--self-test`）：摘 savepoint / 把重查后的 raise 改成无条件放过 / 把早退条件改成永假，
每发都必须让对应判据红。

跑法（仓库根）：`apps/api/.venv/Scripts/python.exe -X utf8 docs/06_validation/evidence/EVD-V2-02/prove_shortlink_race.py [--self-test]`
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import sys
import textwrap
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[4]
API = REPO / "apps" / "api"
KB = API / "app" / "services" / "kb.py"
TARGET = "_save_short_link"

sys.path.insert(0, str(API))

from sqlalchemy.exc import IntegrityError  # noqa: E402  (要真异常类，假造会让 isinstance 判空)


class _Result:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _Nested:
    """`begin_nested()` 的假替身：进入时打点，体内异常时模拟 savepoint 回滚（丢弃 add）。"""

    def __init__(self, sess: "_FakeSession") -> None:
        self._sess = sess

    async def __aenter__(self) -> "_Nested":
        self._sess.nested_entered += 1
        self._sess.snapshot = len(self._sess.added)
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        if exc_type is not None:
            del self._sess.added[self._sess.snapshot :]
            self._sess.rolled_back += 1
        return False


class _FakeSession:
    def __init__(self, select_results: list[Any], flush_raises: bool) -> None:
        self._select_results = list(select_results)
        self._flush_raises = flush_raises
        self.added: list[Any] = []
        self.flushes = 0
        self.selects = 0
        self.nested_entered = 0
        self.rolled_back = 0
        self.snapshot = 0

    async def execute(self, _stmt: Any) -> _Result:
        self.selects += 1
        return _Result(self._select_results.pop(0) if self._select_results else None)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushes += 1
        if self._flush_raises:
            raise IntegrityError("INSERT INTO short_link_maps", {}, Exception("uq_shortlink_key"))

    def begin_nested(self) -> _Nested:
        return _Nested(self)


class _Host:
    def __init__(self, sess: _FakeSession) -> None:
        self._session = sess


def _fn_src(kb_text: str) -> str:
    tree = ast.parse(kb_text)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == TARGET:
            return ast.unparse(node)
    raise AssertionError(f"kb.py 里找不到 {TARGET}")


def _run(kb_text: str, sess: _FakeSession, *, short_key: str = "sk-1", article_key: str = "s:long-1") -> Any:
    # 被 exec 的函数体引用模块级 `select` / `IntegrityError`，假世界必须提供同名真物，
    # 否则 NameError 会让每条判据都「红在工具上」（本仓库反复踩过的那一族）。
    from sqlalchemy import select as _select

    ns: dict[str, Any] = {"select": _select, "IntegrityError": IntegrityError}
    exec(compile(_fn_src(kb_text), str(KB), "exec"), ns)  # noqa: S102  被检函数必须来自磁盘当前内容
    fn = ns[TARGET]
    return asyncio.run(fn(_Host(sess), short_key, article_key, "biz-1"))


def sr_b1(kb: str) -> tuple[bool, object]:
    sess = _FakeSession([None], flush_raises=False)
    err = None
    try:
        _run(kb, sess)
    except BaseException as exc:  # noqa: BLE001
        err = exc
    ok = err is None and len(sess.added) == 1 and sess.flushes == 1 and sess.nested_entered == 1
    return ok, f"异常={err!r}、add={len(sess.added)}、flush={sess.flushes}、savepoint={sess.nested_entered}"


def sr_b2(kb: str) -> tuple[bool, object]:
    """竞态主判据：先查收空、flush 抛唯一冲突、重查拿到对手的行 ⇒ 不许抛。"""
    sess = _FakeSession([None, "row-from-other-tx"], flush_raises=True)
    err = None
    try:
        _run(kb, sess)
    except BaseException as exc:  # noqa: BLE001
        err = exc
    ok = err is None and sess.rolled_back == 1 and sess.selects == 2
    return ok, f"异常={err!r}、回滚={sess.rolled_back}、select 次数={sess.selects}"


def sr_b3(kb: str) -> tuple[bool, object]:
    """非唯一冲突必须上抛：兜底只认「对手已写入」那一种。"""
    sess = _FakeSession([None, None], flush_raises=True)
    err = None
    try:
        _run(kb, sess)
    except IntegrityError as exc:
        err = exc
    except BaseException as exc:  # noqa: BLE001
        err = exc
    ok = isinstance(err, IntegrityError)
    return ok, f"抛出的异常={err!r}（期望 IntegrityError 原样上抛）"


def sr_b4(kb: str) -> tuple[bool, object]:
    """已存在则早退：一次写下发都是多余。"""
    sess = _FakeSession(["existing-row"], flush_raises=False)
    err = None
    try:
        _run(kb, sess)
    except BaseException as exc:  # noqa: BLE001
        err = exc
    ok = err is None and len(sess.added) == 0 and sess.flushes == 0
    return ok, f"异常={err!r}、add={len(sess.added)}、flush={sess.flushes}"


def sr_s1(kb: str) -> tuple[bool, object]:
    """结构面按 AST 判，不按字形判：savepoint 必须**包住那次 add**，且体内有 IntegrityError 处理。

    只查「出现过 begin_nested 字样」会被两种写法绕开：把 add 放到 savepoint 外面，
    或者把捕获换成 `except Exception`（那会把非唯一冲突一起吞掉，B3 也保不住）。
    """
    fn = ast.parse(_fn_src(kb)).body[0]
    nested = [n for n in ast.walk(fn) if isinstance(n, ast.AsyncWith)]
    has_nested = any(
        isinstance(item.context_expr, ast.Call)
        and isinstance(item.context_expr.func, ast.Attribute)
        and item.context_expr.func.attr == "begin_nested"
        for n in nested
        for item in n.items
    )
    caught = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.ExceptHandler) and isinstance(n.type, ast.Name) and n.type.id == "IntegrityError"
    ]
    add_inside = any(
        isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "add"
        for item in nested
        for sub in ast.walk(item)
    )
    ok = has_nested and add_inside and len(caught) == 1
    return ok, f"savepoint={has_nested}、add 在其内={add_inside}、IntegrityError 处理={len(caught)} 处"


CHECKS = (
    ("SR-B1", "正常写入：一次 add + 一次 flush，且在 savepoint 内，不抛", sr_b1),
    ("SR-B2", "竞态冲突：flush 抛唯一冲突而重查拿到对手行 ⇒ 不抛（修复本体）", sr_b2),
    ("SR-B3", "非唯一冲突：重查仍为空 ⇒ IntegrityError 必须原样上抛（不掩盖）", sr_b3),
    ("SR-B4", "已存在：早退，不下发任何写", sr_b4),
    ("SR-S1", "结构：插入在 begin_nested 内且体内捕获 IntegrityError", sr_s1),
)

# (标签, 旧锚, 新代码, 必须变红的判据)
MUTANTS = [
    ("摘掉 savepoint（回到修复前的裸 add+flush 形状）",
     "            async with self._session.begin_nested():", "            if True:", {"SR-B2", "SR-S1"}),
    ("兜底里不再重查判定，一律放过（把非唯一冲突也吞掉）",
     "            if won is None:\n                raise", "            if False:\n                raise", {"SR-B3"}),
    ("早退条件写反（已存在也再插一次）",
     "        if exists is not None:", "        if exists is None:", {"SR-B4"}),
    ("早退条件永真（永远不写映射，静默丢键）",
     "        if exists is not None:", "        if True:", {"SR-B1"}),
]


def _target_span(text: str) -> tuple[int, int]:
    """目标函数在源文件里的行区间（1 起，闭区间）。"""
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == TARGET:
            return node.lineno, node.end_lineno or node.lineno
    raise AssertionError(f"{TARGET} 不在源里")


def _apply(text: str, old: str, new: str) -> tuple[str, str]:
    """变异只作用在**目标函数体内**：kb.py 里 `async with self._session.begin_nested():` 有 3 处
    （_ensure_source / _persist_document / 本函数），整文件计数会把别处的同名行也算进来——
    既会误判「锚不唯一」，也会把不相关的代码改掉冒充成这一发的结论。
    """
    lo, hi = _target_span(text)
    lines = text.splitlines(keepends=True)
    body = "".join(lines[lo - 1 : hi])
    n = body.count(old)
    if n != 1:
        return text, f"锚在 {TARGET} 体内出现 {n} 次（应为 1）"
    mutated = body.replace(old, new)
    try:
        # 切片自带 class 里的公共缩进，直接 parse 会报 unexpected indent ⇒ 先 dedent 再校验
        ast.parse(textwrap.dedent(mutated))
    except SyntaxError as exc:
        return text, f"改后无法解析：{exc}"
    return "".join(lines[: lo - 1]) + mutated + "".join(lines[hi:]), ""


def run(kb_text: str) -> tuple[int, int, list[str]]:
    passed, failed, names = 0, 0, []
    for cid, label, judge in CHECKS:
        try:
            ok, why = judge(kb_text)
        except BaseException as exc:  # noqa: BLE001
            ok, why = False, f"判据崩了 {type(exc).__name__}: {exc}"
        if ok:
            passed += 1
            print(f"PASS {cid} {label}")
        else:
            failed += 1
            names.append(cid)
            print(f"FAIL {cid} {label} :: {why}")
    return passed, failed, names


def self_test(kb_text: str) -> int:
    print("== 基线 ==")
    passed, failed, _ = run(kb_text)
    if failed:
        print(f"基线不绿（{failed} 条红），self-test 结论不可用")
        return 1
    covered: set[str] = set()
    rc = 0
    for label, old, new, must_red in MUTANTS:
        mutated, why = _apply(kb_text, old, new)
        if why:
            print(f"FAIL 变异取消：{label} :: {why}")
            rc = 1
            continue
        _, _, red = run(mutated)
        red_set = set(red)
        missing = sorted(must_red - red_set)
        if missing:
            print(f"FAIL 变异「{label}」期望红 {sorted(must_red)}，实得 {sorted(red_set)}")
            rc = 1
        else:
            covered |= red_set
            print(f"OK   变异「{label}」→ 致红 {sorted(red_set)}")
    uncovered = sorted({c for c, _, _ in CHECKS} - covered)
    if uncovered:
        print(f"FAIL 覆盖：这些判据没有任何变异打红 {uncovered}")
        rc = 1
    else:
        print(f"OK   覆盖：{len(CHECKS)} 条判据 each 至少被一发变异实测打红")
    print(f"\nSELF-TEST {'PASS' if rc == 0 else 'FAIL'}：判据 {len(CHECKS)} 条 + 变异 {len(MUTANTS)} 发")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--kb", default="")
    args = ap.parse_args()
    path = Path(args.kb) if args.kb else KB
    text = path.read_text(encoding="utf-8-sig")
    print(f"读源 {path}")
    if args.self_test:
        return self_test(text)
    _, failed, _ = run(text)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
