#!/usr/bin/env python
"""STEP-02 S2.1.1/S2.1.2 机器证明：`parse_wechat_url` 的真实执行、覆盖率与反证。

与 EVD-V2-00/prove_dsn_policy.py 的区别：本步实现是**纯 stdlib 零 IO 函数**，所以不需要
AST 剔除三方 import 再 exec——直接按真实路径加载真实模块、调用真实测试函数。被执行的是
`apps/api/app/services/article_identity.py` 与 `apps/api/tests/test_article_identity.py`
两个文件里的当前代码；改坏它们，这里的结论就会变。

为什么还要一个 stdlib runner：本机**装有** pytest 9.1.1（实测 `python -c "import pytest"` → OK；
第一轮复审据此推翻了我原先「本机没有 pytest」的说法），但**没有** sqlalchemy / httpx /
pytest-asyncio / coverage（同法实测 ModuleNotFoundError）⇒ 卡面的
`uv run pytest --cov=... --cov-fail-under=100` 在本机仍不可复现，且默认收集会因
`conftest.py` 导入 sqlalchemy 而失败。两条通道因此并存且各有用处：
- 真实 pytest：`cd apps/api && PYTHONPATH=. python -m pytest tests/test_article_identity.py -q --noconftest`
  → `14 passed`（`--noconftest` 是绕开 sqlalchemy，本文件不消费任何 conftest 夹具）；
- 本脚本：builtins 逐个调用真实测试函数 + `sys.settrace` 自计语句覆盖（本机无 coverage），
  并额外做下面三条反证通道——这部分是 pytest 给不了的。

`--self-test` 的三条通道（条数全部由 `len(...)` 动态打印，不在文档里手抄）：
① `MUTANTS`——把**实现**改成「看起来还在但已失效」的形态，逐条确认指定用例**变红**；
② `_JUDGES`——每条结构判据同时喂「真实样本（必须判真）」与「坏样本（必须判假）」，
   堵掉「判据永远为真」这一类空洞断言；`PI-7` 另做「逐个删除用例名」的敏感性检查；
③ `EQUIV_REFACTORINGS`——方向相反：**语义等价的改写必须不假红**（内联常量、换切片写法、
   用例改用中间变量断言）。缺这条时我自己的 PI-6 就会把 `or "1"` 这种合法写法判红（复审 Q-20），
   而脆性判据的真实代价是门禁被当噪声放宽，等于没有门禁。
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

# ruff: noqa: E501

REPO = Path(__file__).resolve().parents[4]
API = REPO / "apps" / "api"
TESTS = API / "tests"
IMPL = API / "app" / "services" / "article_identity.py"
TEST = TESTS / "test_article_identity.py"
MODNAME = "app.services.article_identity"

#: 卡面 S2.1.1 交付口径 → 必须存在的用例名（机器核对，防空洞）。
#: 末条是本步补充（非卡面要求），它兜住「host 大小写折叠」这条实现分支，见 MUT_HOST_NO_LOWER。
DELIVERABLES: dict[str, tuple[str, ...]] = {
    "LONG_A/LONG_B 同 biz 不同 mid": ("test_long_links_share_biz_but_differ_mid",),
    "__biz URL 编码可解": ("test_encoded_biz_param_decodes_to_same_value",),
    "LONG_A_TRACKING 与 LONG_A 同 (biz,mid,idx)": ("test_tracking_params_do_not_change_identity",),
    "SHORT_1 得 token": ("test_short_link_yields_token",),
    "SHORT_WITH_FAKE_BIZ_PARAM 仍解析出 biz": ("test_short_link_with_fake_biz_param_still_yields_biz",),
    "MALFORMED_LONG 的 mid 为空": ("test_malformed_long_link_has_empty_mid",),
    "OFFSITE 返回 host≠微信": ("test_offsite_url_is_not_wechat",),
    "idx 缺省 '1'（卡面 S2.1.2）": ("test_idx_defaults_to_one_when_absent",),
    "__biz 优先于 biz": ("test_biz_takes_precedence_over_short_biz_param",),
    "host 折叠后仍认短链（本步补充）": ("test_host_case_folding_keeps_short_token",),
    "返回值为冻结值对象（本步补充）": ("test_parse_returns_frozen_parts",),
    "裸 `+` 与 `%2B` 解出同一 biz（本步补充，防一篇裂两条）": (
        "test_plus_sign_in_biz_is_literal_not_space",
    ),
    "非 str 入参归零返回（本步补充，Source.url 可为 NULL）": (
        "test_non_string_input_yields_empty_parts_without_raising",
    ),
    "解析与 host 解耦的当前口径被钉住（本步补充，S2.2 待定项）": (
        "test_wechat_params_on_foreign_host_are_still_parsed",
    ),
}

ALLOWED_IMPORTS = {"__future__", "dataclasses", "urllib.parse"}
#: 裸名（Load 语境出现即算 IO）
IO_NAMES = {"open", "input", "session", "requests", "httpx", "socket", "urlopen", "asyncio"}
#: 挂在任意对象上的方法名——`s.execute()` 与 `session.execute()` 是同一个漏洞的两种写法，
#: 只按变量名匹配会漏检（本项由 --self-test 的第二个 PI-2 样本实测抓出）。
IO_ATTRS = {"execute", "commit", "flush", "scalar", "scalars", "urlopen", "add", "request"}
#: 动态求值族：静态黑名单的绕行通道（`__import__("os").popen(...)` 里既没有 `import os`
#: 也没有 `os.` 前缀，PI-1/PI-2 原形都探不到——由复审 Q-19 实测构造，判据据此补上）。
#: 解析一个 URL 用不到这四个名字，出现即视为逃逸而非等价写法，故允许判得严。
DYNAMIC_NAMES = {"__import__", "eval", "exec", "compile"}
EXPECTED_FIELDS = ["biz", "mid", "idx", "sn", "short_token", "host"]

_passed: list[str] = []
_failed: list[str] = []


def _ensure_utf8_stdout() -> None:
    """把输出流钉在 UTF-8 上，让「少带一个环境变量」不成为崩溃源。

    win32 控制台与重定向管道默认 cp936，编不出本文件里的 `⇒`：裸跑
    `python prove_article_identity.py --self-test`（不带 `PYTHONIOENCODING=utf-8`）原先在
    print 处 `UnicodeEncodeError` 崩掉。按本项目规矩**崩掉不等于裁决**，这条崩溃与判据、
    与三档退出码都无关，纯粹是环境噪音——噪音门禁会被关掉，所以在此自愈。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


_ensure_utf8_stdout()


def check(label: str, ok: bool, detail: object = "") -> None:
    (_passed if ok else _failed).append(label)
    print(f"{'OK  ' if ok else 'BAD '} {label}" + ("" if ok else f"\n       └ 判据输入：{detail!r}"))


# ── 真实加载与执行 ─────────────────────────────────────────────────────────


def load_impl(source: str | None = None) -> ModuleType:
    """加载实现并挂成 `app.services.article_identity`，供测试文件的真实 import 语句绑定。

    先注册进 `sys.modules` 再执行：`@dataclass` 在构造类时会按 `cls.__module__` 回查
    `sys.modules`（`dataclasses._is_type`），顺序颠倒会 AttributeError。
    """
    import app.services  # 真实包（`app/services/__init__.py` 为空文件）

    if source is None:
        spec = importlib.util.spec_from_file_location(MODNAME, IMPL)
        if spec is None or spec.loader is None:
            # 这句原先是一行裸 `assert`（第十一轮复审 NIT②，也是 10-8 的残余）：`python -O` 下整行
            # 被剥掉，接着以 `TypeError: module() takes at most 2 arguments` 收场——零裁决。
            # 而这一档的真实后果是「判据压根没跑」，按本项目退出码映射该走 2（INCONCLUSIVE），
            # 不能读成 1（测出不合格），更不能读成崩栈。
            print(f"INCONCLUSIVE 目标加载不了：`spec_from_file_location({MODNAME}, {IMPL})` "
                  f"给不出可执行的 spec——一条判据都没跑")
            raise SystemExit(2)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[MODNAME] = mod
        setattr(app.services, "article_identity", mod)
        spec.loader.exec_module(mod)
    else:
        mod = ModuleType(MODNAME)
        mod.__file__ = str(IMPL)
        sys.modules[MODNAME] = mod
        setattr(app.services, "article_identity", mod)
        exec(compile(source, str(IMPL), "exec"), mod.__dict__)
    return mod


def load_tests() -> ModuleType:
    sys.modules.pop("test_article_identity", None)
    return importlib.import_module("test_article_identity")


def load_tests_from_source(source: str) -> ModuleType:
    """在内存里执行「改写后的用例源码」并返回模块（等价重构通道用，绝不写盘）。"""
    sys.modules.pop("test_article_identity", None)
    mod = ModuleType("test_article_identity")
    mod.__file__ = str(TEST)
    sys.modules["test_article_identity"] = mod
    exec(compile(source, str(TEST), "exec"), mod.__dict__)  # noqa: S102 — 执行的是仓库里的用例
    return mod


def load_tests_after_impl(impl_source: str) -> ModuleType:
    load_impl(impl_source)
    return load_tests()


def run_test_functions(mod: ModuleType) -> tuple[list[str], list[tuple[str, str]]]:
    passed, failed = [], []
    for name in sorted(n for n in vars(mod) if n.startswith("test_")):
        fn = vars(mod)[name]
        if not callable(fn) or getattr(fn, "__module__", None) != mod.__name__:
            continue
        try:
            fn()
            passed.append(name)
        except BaseException as exc:  # noqa: BLE001 — 变异体可能抛任何形态
            failed.append((name, f"{type(exc).__name__}: {exc}"))
    return passed, failed


# ── 结构判据：统一返回 (ok, 判据输入)，供 main 与 JUDGE_PROBES 共用 ─────────


def j_stdlib_only(src: str) -> tuple[bool, object]:
    extra = imports_of(src) - ALLOWED_IMPORTS
    return not extra, sorted(extra)


def j_zero_io(src: str) -> tuple[bool, object]:
    hits = [
        f"{n.value.id}.{n.attr}:{n.lineno}"
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in IO_NAMES
    ] + [
        # 任意对象上的 IO 方法名（抓 `s.execute(...)` 这一类换名写法）
        f"*.{n.attr}:{n.lineno}"
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Attribute) and n.attr in IO_ATTRS
    ] + [
        f"{n.id}:{n.lineno}"
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Name) and n.id in IO_NAMES and isinstance(n.ctx, ast.Load)
    ] + [
        # 动态求值族：绕过 PI-1 导入白名单与 PI-2 名字黑名单的那条路
        f"dyn:{n.id}:{n.lineno}"
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Name) and n.id in DYNAMIC_NAMES and isinstance(n.ctx, ast.Load)
    ]
    return not hits, sorted(hits)


def j_no_mutation(src: str) -> tuple[bool, object]:
    """纯函数前提：不写 global、不写属性 ⇒ 可并发复用、无隐藏状态。"""
    bad = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Global):
            bad.append(f"global:{n.lineno}")
        elif isinstance(n, (ast.Assign, ast.AugAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            bad.extend(f"attr-write:{t.lineno}" for t in targets if isinstance(t, ast.Attribute))
    return not bad, sorted(bad)


def j_field_order(src: str) -> tuple[bool, object]:
    order: list[str] = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ClassDef) and node.name == "WechatUrlParts":
            order = [
                st.target.id
                for st in node.body
                if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name)
            ]
    return order == EXPECTED_FIELDS, order


def j_frozen(src: str) -> tuple[bool, object]:
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ClassDef) and node.name == "WechatUrlParts":
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call):
                    got = any(
                        kw.arg == "frozen" and isinstance(kw.value, ast.Constant) and kw.value.value is True
                        for kw in dec.keywords
                    )
                    return got, [ast.unparse(dec)]
    return False, "WechatUrlParts 上找不到带参数的装饰器"


def j_default_idx(src: str) -> tuple[bool, object]:
    """`idx` 的缺省值必须是 `'1'`——但**不锁定它写成常量还是内联字面量**。

    第一版只认「模块级 `_DEFAULT_IDX = "1"`」，于是把常量内联成 `or "1"` 这种完全等价的
    重构会被判红（复审 Q-20）。判据过严的后果不是误报一次，而是门禁被人当噪声放宽，
    所以这里接受两种形态、只拒绝「缺省值不是 1 / 根本没有缺省」。
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_DEFAULT_IDX" for t in node.targets
        ):
            val = node.value.value if isinstance(node.value, ast.Constant) else None
            return val == "1", f"模块常量 _DEFAULT_IDX={val!r}"
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "idx" and isinstance(node.value, ast.BoolOp):
            last = node.value.values[-1]
            if isinstance(last, ast.Constant) and last.value == "1":
                return True, f"内联缺省 idx or \"1\"（{node.value!r} 的末项）"
            return False, f"内联缺省值不是 '1'：{ast.unparse(last)!r}"
    return False, "既无 _DEFAULT_IDX 常量，也无 idx=... or \"1\" 的内联缺省"


def j_cases_have_asserts(test_src: str) -> tuple[bool, object]:
    """每条用例体内至少有一个 assert 或 raise（复审 Q-17：掏空用例体时其余判据仍全绿）。

    「用例数对得上交付项」只证明名字存在，不证明它们判定任何东西——那正是 G-23 禁止的形态。
    """
    hollow = []
    for node in ast.walk(ast.parse(test_src)):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            has = any(
                isinstance(sub, (ast.Assert,)) or (
                    isinstance(sub, ast.Raise)
                )
                for sub in ast.walk(node)
            )
            if not has:
                hollow.append(node.name)
    return not hollow, sorted(hollow)


def j_deliverables(names: set[str]) -> tuple[bool, object]:
    gaps = {k: [t for t in v if t not in names] for k, v in DELIVERABLES.items()}
    gaps = {k: v for k, v in gaps.items() if v}
    return not gaps, gaps


def j_no_pytest_import(test_src: str) -> tuple[bool, object]:
    got = "pytest" in imports_of(test_src)
    return not got, sorted(imports_of(test_src))


def j_fixtures_resolved(test_src: str) -> tuple[bool, object]:
    """夹具走 PEP 420 命名空间包（`tests/fixtures/` 无 `__init__.py`），必须真实取到常量。

    判的是「用例 import 的每个名字都真的存在」，不是「夹具里有几个常量」——后者是数量下界，
    删掉一个未被本文件引用的常量也照样绿（复审 Q-21），既没锁住口径又假装锁住了。
    """
    imported = fixtures_imported_names(test_src)
    if not imported:
        return False, "用例文件没有 from fixtures.wechat_urls import"
    try:
        import fixtures.wechat_urls as f
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    missing = sorted(n for n in imported if not hasattr(f, n))
    return not missing, f"import {len(imported)} 个｜夹具缺失 {missing}"


def fixtures_imported_names(test_src: str) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(test_src)):
        if isinstance(node, ast.ImportFrom) and node.module == "fixtures.wechat_urls":
            out.update(a.name for a in node.names)
    return out


def imports_of(src: str) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
    return out


def test_function_names(src: str) -> set[str]:
    return {n.name for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}


def statement_lines(src: str) -> set[int]:
    """可执行语句行（docstring 表达式与装饰器行不计）。"""
    out: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.stmt):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        out.add(node.lineno)
    return out


# ── 语句覆盖（stdlib sys.settrace，不依赖 coverage/pytest-cov）──────────────


class LineTracer:
    def __init__(self, target: str) -> None:
        self.target = target
        self.seen: set[int] = set()

    def __enter__(self) -> LineTracer:
        self._prev = sys.gettrace()
        sys.settrace(self._global)
        return self

    def __exit__(self, *exc: object) -> None:
        sys.settrace(self._prev)
        return None

    def _global(self, frame, event: str, _arg: object):
        if frame.f_code.co_filename != self.target or event != "call":
            return None
        return self._local

    def _local(self, frame, event: str, _arg: object):
        if event == "line":
            self.seen.add(frame.f_lineno)
        return self._local


def measure_coverage(src: str) -> tuple[set[int], set[int], set[int]]:
    """重新加载实现并跑全部用例，返回（语句行全集, 覆盖到, 未覆盖）。

    跨行语句（多行 return 调用）允许命中其区间内任一行即视为执行——`settrace` 的行事件
    在 3.11 上按指令粒度给出，不保证正好是语句首行。
    """
    tracer = LineTracer(str(IMPL))
    with tracer:
        load_impl(src)
        run_test_functions(load_tests())
    lines = statement_lines(src)
    spans = {
        n.lineno: (n.lineno, getattr(n, "end_lineno", n.lineno) or n.lineno)
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.stmt)
    }
    covered = {ln for ln in lines if any(x in tracer.seen for x in range(spans[ln][0], spans[ln][1] + 1))}
    return lines, covered, lines - covered


# ── 主流程 ────────────────────────────────────────────────────────────────


def main() -> int:
    if not IMPL.exists():
        print(f"BAD 实现文件不存在：{IMPL}（S2.1.1 先红阶段，此时预期 ModuleNotFoundError）")
        return 1
    impl_src = IMPL.read_text(encoding="utf-8")
    test_src = TEST.read_text(encoding="utf-8")

    print(f"目标实现：{IMPL.relative_to(REPO).as_posix()}")
    print(f"目标用例：{TEST.relative_to(REPO).as_posix()}\n")

    check("PI-1 实现只依赖白名单标准库（无三方、无 IO 库）", *j_stdlib_only(impl_src))
    check("PI-2 实现体零 IO（无 open/session/execute/httpx 等名字）", *j_zero_io(impl_src))
    check("PI-3 实现无 global 写、无属性写（纯函数可并发复用）", *j_no_mutation(impl_src))
    check("PI-4 WechatUrlParts 字段序 = (biz, mid, idx, sn, short_token, host)", *j_field_order(impl_src))
    check("PI-5 WechatUrlParts 冻结（身份不可就地篡改）", *j_frozen(impl_src))
    check("PI-6 idx 的缺省值为 '1'（常量或内联字面量两种写法都接受）", *j_default_idx(impl_src))
    check(
        f"PI-7 交付口径逐条落到真实用例名（卡面 S2.1.1/S2.1.2 + 本步补充，共 {len(DELIVERABLES)} 条）",
        *j_deliverables(test_function_names(test_src)),
    )
    check("PI-8 用例文件不 import pytest（本机无依赖也能跑）", *j_no_pytest_import(test_src))
    check("PI-9 夹具经 PEP 420 命名空间包真实解析（tests/fixtures 无 __init__.py）", *j_fixtures_resolved(test_src))

    load_impl(impl_src)
    passed, failed = run_test_functions(load_tests())
    check(f"PI-10 真实执行 {len(passed) + len(failed)} 个用例全部通过", not failed, [f"{n}: {m}" for n, m in failed])
    print(f"       用例明细：{len(passed)} passed / {len(failed)} failed")

    lines, covered, uncovered = measure_coverage(impl_src)
    pct = 100.0 * len(covered) / len(lines) if lines else 0.0
    check(
        f"PI-11 实现语句覆盖 {len(covered)}/{len(lines)} = {pct:.1f}%（卡面 S2.1.2 要求 100%）",
        not uncovered,
        sorted(uncovered),
    )

    check(
        f"PI-12 每条用例体内都含 assert/raise（防空壳用例，共 {len(test_function_names(test_src))} 条）",
        *j_cases_have_asserts(test_src),
    )

    print(f"\n合计 PASS={len(_passed)} FAIL={len(_failed)}")
    for lbl in _failed:
        print(f"  BAD {lbl}")
    return 1 if _failed else 0


# ── 反证①：实现变异体必须让指定用例变红 ────────────────────────────────────

MUTANTS: list[tuple[str, str, str, set[str]]] = [
    (
        "退化成 kb.py 旧行为：只读 biz、不读 __biz（D-01b 本体）",
        '_first(query, "__biz") or _first(query, "biz")',
        '_first(query, "biz")',
        {
            "test_long_links_share_biz_but_differ_mid",
            "test_biz_takes_precedence_over_short_biz_param",
            "test_malformed_long_link_has_empty_mid",
        },
    ),
    (
        "biz 优先级倒置（两种都读，但伪 biz 抢先）",
        '_first(query, "__biz") or _first(query, "biz")',
        '_first(query, "biz") or _first(query, "__biz")',
        {"test_biz_takes_precedence_over_short_biz_param"},
    ),
    (
        "query 改裸切分（不再百分号解码）",
        'query = parse_qs(parsed.query.replace("+", "%2B"))',
        "query = {k: [v] for p in parsed.query.split('&') if '=' in p for k, _, v in [p.partition('=')]}",
        {"test_encoded_biz_param_decodes_to_same_value"},
    ),
    (
        "`+` 退回表单口径（裸 + 被还原成空格）",
        'query = parse_qs(parsed.query.replace("+", "%2B"))',
        "query = parse_qs(parsed.query)",
        {"test_plus_sign_in_biz_is_literal_not_space"},
    ),
    (
        "非 str 守卫被删（bytes 直送 urlparse ⇒ b'' 型 host）",
        "    if not isinstance(url, str):\n        return WechatUrlParts()\n",
        "",
        {"test_non_string_input_yields_empty_parts_without_raising"},
    ),
    (
        "擅自给解析加 host 闸门（非微信源的 biz 全变空串，越界改动）",
        "    parsed = urlparse(url)\n    host = parsed.netloc.lower()",
        "    parsed = urlparse(url)\n    host = parsed.netloc.lower()\n"
        "    if host != WECHAT_HOST:\n        return WechatUrlParts(host=host)",
        {"test_wechat_params_on_foreign_host_are_still_parsed"},
    ),
    (
        "idx 缺省值被清空",
        '_DEFAULT_IDX = "1"',
        '_DEFAULT_IDX = ""',
        {"test_idx_defaults_to_one_when_absent"},
    ),
    (
        "mid 读成 id（长链畸形态的真实诱因）",
        'mid=_first(query, "mid")',
        'mid=_first(query, "id")',
        {"test_long_links_share_biz_but_differ_mid", "test_malformed_long_link_has_empty_mid"},
    ),
    (
        "短链 token 分支被旁路",
        "if host == WECHAT_HOST and parsed.path.startswith(_SHORT_PATH_PREFIX):",
        "if False and parsed.path.startswith(_SHORT_PATH_PREFIX):",
        {"test_short_link_yields_token", "test_short_link_with_fake_biz_param_still_yields_biz"},
    ),
    (
        "值对象不再冻结",
        "@dataclass(frozen=True)",
        "@dataclass",
        {"test_parse_returns_frozen_parts"},
    ),
    (
        "host 不做大小写折叠",
        "host = parsed.netloc.lower()",
        "host = parsed.netloc",
        {"test_host_case_folding_keeps_short_token"},
    ),
    (
        "sn 恒为空串（身份组成部分被吞）",
        'sn=_first(query, "sn")',
        'sn=""',
        {"test_long_links_share_biz_but_differ_mid", "test_tracking_params_do_not_change_identity"},
    ),
]

# ── 反证②：每条结构判据都要「真实样本判真 + 坏样本判假」────────────────────

_JUDGES: list[tuple[str, object, str, str]] = [
    # (标签, 判据, 坏样本源码, 好样本取哪个真实文件)
    ("PI-1 白名单依赖", j_stdlib_only, "import httpx\n", "impl"),
    ("PI-2 零 IO（open）", j_zero_io, "def f(u):\n    return open(u)\n", "impl"),
    ("PI-2 零 IO（session.execute）", j_zero_io, "async def f(s, u):\n    return await s.execute(u)\n", "impl"),
    # 复审 Q-19 实测：`__import__("os").popen("ver")` 既没有 `import os` 也没有 `os.` 前缀，
    # PI-1/PI-2 原形全绿，起子进程的实现仍被称「零 IO 纯函数」⇒ 补动态求值族。
    ("PI-2 零 IO（__import__ 动态逃逸）", j_zero_io, "def f(u):\n    return __import__('os').popen(u).read()\n", "impl"),
    ("PI-2 零 IO（eval 动态逃逸）", j_zero_io, "def f(u):\n    return eval(u)\n", "impl"),
    ("PI-3 纯函数（global 写）", j_no_mutation, "def f(u):\n    global C\n    C = 1\n    return u\n", "impl"),
    ("PI-3 纯函数（属性写）", j_no_mutation, "def f(o):\n    o.mid = '1'\n    return o\n", "impl"),
    ("PI-4 字段序", j_field_order, "class WechatUrlParts:\n    mid: str = ''\n    biz: str = ''\n", "impl"),
    ("PI-4 缺类", j_field_order, "class Other:\n    biz: str = ''\n", "impl"),
    ("PI-5 冻结", j_frozen, "from dataclasses import dataclass\n@dataclass(frozen=False)\n"
     "class WechatUrlParts:\n    biz: str = ''\n", "impl"),
    ("PI-6 缺省值漂移", j_default_idx, '_DEFAULT_IDX = ""\n', "impl"),
    ("PI-6 常量被删", j_default_idx, "x = 1\n", "impl"),
    ("PI-8 用例 import pytest", j_no_pytest_import, "import pytest\n", "test"),
    ("PI-9 夹具名写错", j_fixtures_resolved, "from fixtures.wrong_name import X\n", "test"),
    # 复审 Q-21：旧 PI-9 判的是「夹具里常量个数 ≥9」，删掉一个未被引用的常量照样绿。
    # 现改为「用例 import 的每个名字都要真存在」，坏样本就是引用一个不存在的名字。
    ("PI-9 引用了夹具里不存在的名字", j_fixtures_resolved, "from fixtures.wechat_urls import NO_SUCH_NAME\n", "test"),
    # 复审 Q-17：把 11 条用例体全部掏空后，PI-7/PI-10 都仍判真——补一条结构判据。
    ("PI-12 用例体被掏空（无 assert/raise）", j_cases_have_asserts, "def test_a():\n    return None\n", "test"),
]

# ── 反证③：等价重构必须保持全绿（方向与①②相反，第四轮 STEP-00R 的方法论移植）──────
#
# 判据若把语义等价的写法也判红，后果不是误报一次而是门禁被当噪声放宽。
# 每条要求：改完后 PI-* 判据仍真、且 14 条用例仍全绿。
EQUIV_REFACTORINGS: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "PI-6 允许把 _DEFAULT_IDX 内联成字面量（常量删除 + 用法改写，两步一起才等价）",
        "impl",
        [('_DEFAULT_IDX = "1"\n\n', ""), ('or _DEFAULT_IDX,', 'or "1",')],
    ),
    (
        "PI-2 允许把短链切片写成 removeprefix",
        "impl",
        [
            ('short_token = parsed.path[len(_SHORT_PATH_PREFIX) :].strip("/")',
             'short_token = parsed.path.removeprefix(_SHORT_PATH_PREFIX).strip("/")'),
        ],
    ),
    (
        "PI-4 允许字段注写成带引号的等价形式（顺序不动）",
        "impl",
        [('    biz: str = ""', "    biz: 'str' = \"\"")],
    ),
    (
        "PI-7/PI-12 允许用例改用中间变量再断言（判定不动）",
        "test",
        [
            ('    p = parse_wechat_url(MALFORMED_LONG)\n'
             '    assert p.biz == BIZ_A and p.mid == "", f"畸形长链应 biz 有值、mid 空：{p!r}"',
             '    p = parse_wechat_url(MALFORMED_LONG)\n'
             '    got = (p.biz, p.mid)\n'
             '    assert got == (BIZ_A, ""), f"畸形长链应 biz 有值、mid 空：{got!r}"'),
        ],
    ),
]


def self_test() -> int:
    rc = 0
    if not IMPL.exists() or not TEST.exists():
        print("BAD 实现或用例文件不存在，无法做变异反证")
        return 1
    base_src = IMPL.read_text(encoding="utf-8")
    test_src = TEST.read_text(encoding="utf-8")
    print(f"反证：{len(MUTANTS)} 个实现变异体 + {len(_JUDGES) + 1} 个判据样本对\n")

    # 基准门：未变异必须先全绿，否则「变红」的结论没有意义
    load_impl(base_src)
    base_passed, base_failed = run_test_functions(load_tests())
    if base_failed:
        print(f"BAD 基准（未变异实现）就有红用例：{[n for n, _ in base_failed]}——先修 main()")
        rc = 1
    else:
        print(f"OK   基准：{len(base_passed)} 个用例全绿")

    for label, old, new, must_red in MUTANTS:
        if base_src.count(old) != 1:
            print(f"BAD 变异锚失配（出现 {base_src.count(old)} 次）：{label}")
            rc = 1
            continue
        load_impl(base_src.replace(old, new))
        _p, failed = run_test_functions(load_tests())
        red = {n for n, _ in failed}
        if must_red - red:
            print(f"BAD 变异体未致红：{label}｜应红却绿：{sorted(must_red - red)}｜实际红：{sorted(red)}")
            rc = 1
        else:
            print(f"OK   {label} → 致红 {sorted(red)}")

    # 判据样本对：真实文件为「好样本」必须判真，构造样本必须判假
    good_src = {"impl": base_src, "test": test_src}
    for label, fn, bad_src, good_key in _JUDGES:
        ok_bad = fn(bad_src)[0]
        ok_good = fn(good_src[good_key])[0]
        if ok_bad:
            print(f"BAD {label}：坏样本仍判真（判据不可失败）")
            rc = 1
        elif not ok_good:
            print(f"BAD {label}：真实样本（{good_key}）判假，好样本选错了源")
            rc = 1
        else:
            print(f"OK   {label}：真实样本判真 / 坏样本判假")

    # PI-7 的用例集反证：删掉任一必需用例名，判据必须转假
    full = test_function_names(test_src)
    ok_full, _ = j_deliverables(full)
    holes = [name for name in sorted(full) if j_deliverables(full - {name})[0]]
    if not ok_full or holes:
        print(f"BAD PI-7：删用例仍判真的缺口={holes}（基准 ok={ok_full}）")
        rc = 1
    else:
        print(f"OK   PI-7：逐个删除 {len(full)} 个用例名，判据每次都转假")

    load_impl(base_src)  # 还原，避免后续 import 拿到变异体

    # 通道③：等价重构必须「判据仍真 + 用例仍绿」——方向与上面两条相反。
    # 没有这条通道时，我写的 PI-6 会把 `or "1"` 这种完全等价的内联写法判红（复审 Q-20 实测），
    # 而脆性判据的真实代价是门禁被当成噪声放宽，等于没有门禁。
    impl_judges = (j_stdlib_only, j_zero_io, j_no_mutation, j_field_order, j_frozen, j_default_idx)
    test_judges = (j_no_pytest_import, j_fixtures_resolved, j_cases_have_asserts)
    for label, which, pairs in EQUIV_REFACTORINGS:
        base = base_src if which == "impl" else test_src
        off_anchor = [old for old, _n in pairs if base.count(old) != 1]
        if off_anchor:
            print(f"BAD 等价重构锚失配：{label}｜锚={[a[:40] for a in off_anchor]}")
            rc = 1
            continue
        mutated = base
        for old, new in pairs:
            mutated = mutated.replace(old, new)
        false_red = [f.__name__ for f in (impl_judges if which == "impl" else test_judges) if not f(mutated)[0]]
        if which == "test" and not j_deliverables(test_function_names(mutated))[0]:
            false_red.append("j_deliverables")
        if which == "impl":
            run_mod = load_tests_after_impl(mutated)
        else:
            load_impl(base_src)
            run_mod = load_tests_from_source(mutated)
        _p, failed = run_test_functions(run_mod)
        if false_red or failed:
            print(f"BAD 等价重构被判成缺陷：{label}｜假红判据={false_red}｜红用例={[n for n, _ in failed]}")
            rc = 1
        else:
            print(f"OK   等价重构 {label} → 判据全真、用例全绿")

    # 本脚本只有这一档自证（档位/退出码两档在 prove_biz_delegation.py 侧），别读成三道闸门。
    # `PI_NO_NEST` 防递归；子进程因此不打印本档自己的 OK 行（也含 ⇒），那一行由 K.4 裸跑覆盖。
    # 额外要求子进程 stdout 里出现过 ⇒：靶字被抽掉时这一档不许假装绿（K.6 就是这一发）。
    if not os.environ.get("PI_NO_NEST"):
        r = subprocess.run(  # noqa: S603 - 只跑本文件自己
            [sys.executable, str(Path(__file__).resolve()), "--self-test"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "cp936", "PI_NO_NEST": "1"}, check=False,
        )
        crashed = "Traceback (most recent call last)" in (r.stderr or "")
        # 靶字写成转义形式，否则 K.6 那条 `s/⇒/->/g` 会连判据一起改掉、检查自我失效
        no_target = "\u21d2" not in (r.stdout or "")
        if crashed or r.returncode != 0:
            # 崩在 print 里时子进程的 stdout/stderr 缓冲区会随解释器异常退出一起丢掉——
            # traceback 文本本身也含 `⇒`，写 stderr 时二次失败，所以这里必须留兜底
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

    print(
        f"\nSELF-TEST {'PASS' if rc == 0 else 'FAIL'}："
        f"{len(MUTANTS)} 个实现变异体各自让指定用例变红 + {len(_JUDGES) + 1} 个判据样本对敏感"
        f" + {len(EQUIV_REFACTORINGS)} 个等价重构不假红"
    )
    return rc


if __name__ == "__main__":
    sys.path[:0] = [str(API), str(TESTS)]
    sys.exit(self_test() if "--self-test" in sys.argv else main())
