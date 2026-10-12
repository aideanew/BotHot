#!/usr/bin/env python
"""STEP-02 S2.1.3 机器证明：`kb._biz_from_url` 真的委托了 `parse_wechat_url`。

为什么不能直接 pytest：`app.services.kb` 在模块级 import `structlog` 与 `sqlalchemy`
（`kb.py:22-25`，本机两者皆无——实测收集期 `ModuleNotFoundError: No module named 'structlog'`），
连 import 都过不去。这里用的是 EVD-V2-00 已确立、EVD-V2-00R 沿用的机制——
**从磁盘上的 kb.py 里按 AST 取出 `_biz_from_url` 这一个函数节点，单独 compile + exec**。
函数体里的依赖全是局部导入（`from app.services.article_identity import …`），
所以不需要执行整个模块，也就绕开了 sqlalchemy。被执行的是文件里的当前代码，不是抄本：
改了函数体，这里的结论就会变。

判据分三面：
- 行为面 BD-1…BD-6：长链出号主、与解析侧恒等、伪 biz 向后兼容、百分号等价、脏类型不抛；
- 结构面 BD-7…BD-9：函数体里必须真的出现对 `parse_wechat_url` 的调用、导入源必须是
  `app.services.article_identity`、且不得再有第二份解析（`parse_qs`/`urlparse` 归零）；
- 反面 BD-10：委托点不许用 `except` 兜底伪造返回值（把异常吞成非空串 = 数据黑洞+静默）。

`--self-test` 三条反证通道（与 prove_article_identity.py 同一方法论）：
① `MUTANTS` 把函数体改成「看起来还在但已失效」的形态（含**退回旧实现**），逐条要求指定判据红；
② `TEXT_PROBES` 对内存样本跑同一判定函数，要求真实样本判真、坏样本判假；
③ `EQUIV_REFACTORINGS` 方向相反——语义等价的写法（关键字实参、`模块.函数` 形式）必须不假红。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[4]
API = REPO / "apps" / "api"
KB = API / "app" / "services" / "kb.py"
TESTS = API / "tests"

_p = str(API)
_t = str(TESTS)
if _p not in sys.path:
    sys.path.insert(0, _p)
if _t not in sys.path:
    sys.path.insert(0, _t)

passed: list[str] = []
failed: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> None:
    (passed if ok else failed).append(label)
    print(f"{'PASS' if ok else 'FAIL'} {label}" + ("" if ok else f" :: {detail!r}"))


def get_fn_node(src: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == "_biz_from_url":
            return node
    raise AssertionError("kb.py 里没有 _biz_from_url——本步的委托目标已不存在，必须显式复核")


def load_biz(src: str):  # noqa: ANN201 - 返回被 exec 出来的函数对象
    """只 exec 这一个函数节点，得到**文件里当前实现**的真实可调用对象。"""
    fn = get_fn_node(src)
    mod = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    ns: dict[str, object] = {"__name__": "kb_sliced"}
    exec(compile(mod, str(KB), "exec"), ns)  # noqa: S102 - 执行仓库内受审代码
    return ns["_biz_from_url"]


# ── 结构判据（返回 (ok, detail)，供 main 与反证样本共用）─────────────────────

DELEGATE_SRC = "app.services.article_identity"


def j_calls_delegate(src: str) -> tuple[bool, object]:
    """函数体内必须出现对 `parse_wechat_url` 的**调用**（裸名或 `模块.函数` 两种形态都算）。"""
    calls = [
        n
        for n in ast.walk(get_fn_node(src))
        if isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Name) and n.func.id == "parse_wechat_url")
            or (isinstance(n.func, ast.Attribute) and n.func.attr == "parse_wechat_url")
        )
    ]
    return bool(calls), f"调用点 {len(calls)} 处"


def j_import_source(src: str) -> tuple[bool, object]:
    """委托目标必须来自 `app.services.article_identity`，不能是本地另写的同名函数。

    三种等价写法都要认：`from X import f`、`import X`、`from pkg import X`（后者按
    `pkg.X` 拼接比对）——只认第一种会把合法重构判成缺陷，正是反证③要防的假红。"""
    mods = set()
    for n in ast.walk(get_fn_node(src)):
        if isinstance(n, ast.ImportFrom):
            if n.module:
                mods.add(n.module)
                mods.update(f"{n.module}.{a.name}" for a in n.names)
        elif isinstance(n, ast.Import):
            mods.update(a.name for a in n.names)
    return DELEGATE_SRC in mods, sorted(mods)


def j_no_second_parser(src: str) -> tuple[bool, object]:
    """口径单点：kb 侧不得再出现第二份 URL 解析（`parse_qs`/`urlparse` 的任何形态）。"""
    bad = sorted(
        {
            (n.func.id if isinstance(n.func, ast.Name) else n.func.attr)
            for n in ast.walk(get_fn_node(src))
            if isinstance(n, ast.Call)
            and (
                (isinstance(n.func, ast.Name) and n.func.id in {"parse_qs", "urlparse", "parse_qsl"})
                or (isinstance(n.func, ast.Attribute) and n.func.attr in {"parse_qs", "urlparse", "parse_qsl"})
            )
        }
    ) + sorted(
        {
            f"import:{m}"
            for m in [
                (n.module or "") if isinstance(n, ast.ImportFrom) else ",".join(a.name for a in n.names)
                for n in ast.walk(get_fn_node(src))
                if isinstance(n, (ast.Import, ast.ImportFrom))
            ]
            if "urllib" in m
        }
    )
    return not bad, bad


def j_no_swallow(src: str) -> tuple[bool, object]:
    """不许用 except 把异常兜成返回值：那会把「解析失败」变成「解析出一个假身份」。"""
    handlers = [n for n in ast.walk(get_fn_node(src)) if isinstance(n, ast.ExceptHandler)]
    return not handlers, f"except 分支 {len(handlers)} 处"


def j_reads_both(src: str) -> tuple[bool, object]:
    """函数体里不该再出现字面量参数名——读参逻辑必须整体交给解析层（防半委托）。"""
    literals = sorted(
        {
            n.value
            for n in ast.walk(get_fn_node(src))
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in {"biz", "__biz", "mid", "sn"}
        }
    )
    return not literals, literals


# ── 行为面 ────────────────────────────────────────────────────────────────


def behavior_probes(biz) -> list[tuple[str, bool, object]]:
    from app.services.article_identity import parse_wechat_url
    from fixtures.wechat_urls import (
        BIZ_A,
        LONG_A,
        LONG_A_TRACKING,
        LONG_B,
        OFFSITE,
        SHORT_1,
        SHORT_WITH_FAKE_BIZ_PARAM,
    )

    out = []
    got_a = biz(LONG_A)
    out.append(("BD-1 长链解出号主 biz（改前红：旧实现返回空串）", got_a == BIZ_A, f"_biz_from_url(LONG_A)={got_a!r}"))
    got_b = biz(LONG_B)
    out.append(("BD-2 同 biz 不同 mid 的两篇都能解出同一号主", got_b == BIZ_A, f"={got_b!r}"))
    pairs = [LONG_A, LONG_A_TRACKING, LONG_B, OFFSITE, SHORT_1, SHORT_WITH_FAKE_BIZ_PARAM]
    diff = [(u[:48], biz(u), parse_wechat_url(u).biz) for u in pairs if biz(u) != parse_wechat_url(u).biz]
    out.append(("BD-3 与 parse_wechat_url(...).biz 恒等（口径单点，6 个样本）", not diff, diff))
    short = biz(SHORT_WITH_FAKE_BIZ_PARAM)
    out.append(("BD-4 短链伪 biz= 向后兼容（旧实现能解，委托后不许退化）", short == BIZ_A, f"={short!r}"))
    from urllib.parse import quote

    enc = LONG_A.replace(BIZ_A, quote(BIZ_A, safe=""))
    out.append(("BD-5 `%3D%3D` 与 `==` 同值（前提：样本确有差异，否则失去判定力）",
                enc != LONG_A and biz(enc) == biz(LONG_A) == BIZ_A, f"enc→{biz(enc)!r} raw→{biz(LONG_A)!r}"))
    raised = []
    nonempty = []
    for bad in (None, b"https://mp.weixin.qq.com/s?__biz=AAA", 42):
        try:
            if biz(bad) != "":
                nonempty.append((repr(bad), biz(bad)))
        except BaseException as exc:  # noqa: BLE001
            raised.append((repr(bad), f"{type(exc).__name__}: {exc}"))
    out.append(("BD-6 脏类型归零且不抛（None/bytes/int；旧实现只对 int 抛 AttributeError，"
                "对 None 与 bytes 静默返回空串——实测，非推断）",
                not raised and not nonempty, f"抛={raised} 非空={nonempty}"))
    return out


def main() -> int:
    if not KB.exists():
        print(f"FAIL kb.py 不存在：{KB}")
        return 1
    src = KB.read_text(encoding="utf-8")
    print(f"目标：{KB.relative_to(REPO).as_posix()} 的 _biz_from_url（按 AST 取出后真实 exec）\n")
    biz = load_biz(src)
    for label, ok, detail in behavior_probes(biz):
        check(label, ok, detail)
    check("BD-7 函数体内确有对 parse_wechat_url 的调用", *j_calls_delegate(src))
    check(f"BD-8 委托源必须是 {DELEGATE_SRC}", *j_import_source(src))
    check("BD-9 kb 侧无第二份 URL 解析（parse_qs/urlparse/urllib 导入归零）", *j_no_second_parser(src))
    check("BD-10 无 except 兜底（不许把失败伪造成身份）", *j_no_swallow(src))
    check("BD-11 无残留参数字面量（不许半委托）", *j_reads_both(src))
    print(f"\n合计 PASS={len(passed)} FAIL={len(failed)}")
    for lbl in failed:
        print(f"  FAIL {lbl}")
    print(
        "边界：本脚本只证明委托接线与解析口径；`test_kb_longlink_ingest.py` 的 pytest 实跑需 "
        "structlog+sqlalchemy（kb.py:22-25 模块级导入，本机皆无，实测收集期 ModuleNotFoundError），"
        "交 EVD-V2-02 §5 J-1/J-5。"
    )
    return 1 if failed else 0


# ── 反证①：函数体变异必须让指定判据红 ──────────────────────────────────────

OLD_BODY = (
    '    """URL 中的 biz 参数（短链/长链 query 携带）；无则空串。"""\n'
    "    from urllib.parse import parse_qs, urlparse\n\n"
    "    qs = parse_qs(urlparse(url).query)\n"
    '    val = qs.get("biz", [""])\n'
    "    return val[0] if val else \"\"\n"
)
NEW_BODY = (
    '    """URL 中的号主标识；口径单点取自 article_identity。"""\n'
    "    from app.services.article_identity import parse_wechat_url\n\n"
    "    return parse_wechat_url(url).biz\n"
)

MUTANTS: list[tuple[str, str, str, set[str]]] = [
    ("退回旧实现：只读 biz（D-01b 本体复活）", NEW_BODY, OLD_BODY,
     {"BD-1", "BD-2", "BD-3", "BD-6", "BD-7", "BD-8", "BD-9", "BD-11"}),
    ("取错字段：返回 mid", "return parse_wechat_url(url).biz", "return parse_wechat_url(url).mid",
     {"BD-1", "BD-2", "BD-3"}),
    ("篡改返回值：把 base64 尾巴削掉", "return parse_wechat_url(url).biz",
     'return parse_wechat_url(url).biz.rstrip("=")', {"BD-1", "BD-3", "BD-5"}),
    # 多行替换体一律用**带缩进的锚**（锚含 4 空格），否则替换后首行变 8 空格 ⇒
    # 变异体根本解析不了，结构判据会以 IndentationError 冒充「致红」，反证通道失效。
    ("半委托：委托但空串时回退到本地再解析一次", "    return parse_wechat_url(url).biz",
     "    result = parse_wechat_url(url).biz\n"
     "    if result:\n        return result\n"
     "    from urllib.parse import parse_qs, urlparse\n\n"
     '    return parse_qs(urlparse(url).query).get("biz", [""])[0]\n',
     {"BD-9", "BD-11"}),
    ("except 兜底伪造身份（失败静默变假数据）", "    return parse_wechat_url(url).biz",
     "    try:\n        return parse_wechat_url(url).biz\n"
     '    except Exception:\n        return "MjM5MjgwNTQ1MQ=="\n',
     {"BD-10"}),
]

# ── 反证②：结构判据的坏样本必须判假 ────────────────────────────────────────

_WRAP = 'def _biz_from_url(url: str) -> str:\n'

PROBES: list[tuple[str, object, str, str]] = [
    ("BD-7 调用被删（只剩导入）", j_calls_delegate,
     _WRAP + "    from app.services.article_identity import parse_wechat_url\n    return ''\n", NEW_BODY),
    ("BD-8 委托到别的模块", j_import_source,
     _WRAP + "    from app.services.kb_legacy import parse_wechat_url\n\n    return parse_wechat_url(url).biz\n",
     NEW_BODY),
    ("BD-9 第二份解析回潮", j_no_second_parser,
     _WRAP + "    from urllib.parse import urlparse\n\n    return urlparse(url).path\n", NEW_BODY),
    ("BD-10 except 兜底回潮", j_no_swallow,
     "    try:\n        from app.services.article_identity import parse_wechat_url\n\n"
     "        return parse_wechat_url(url).biz\n    except Exception:\n        return ''\n", NEW_BODY),
    ("BD-11 参数字面量回潮", j_reads_both,
     _WRAP + '    from app.services.article_identity import parse_wechat_url\n\n'
     '    return parse_wechat_url(url).biz or "biz"\n', NEW_BODY),
]

# ── 反证③：等价写法必须不假红 ──────────────────────────────────────────────

EQUIVS: list[tuple[str, str, str]] = [
    ("关键字实参形式", "return parse_wechat_url(url).biz", "return parse_wechat_url(url=url).biz"),
    ("模块属性调用形式", "    from app.services.article_identity import parse_wechat_url\n\n"
     "    return parse_wechat_url(url).biz",
     "    from app.services import article_identity\n\n    return article_identity.parse_wechat_url(url).biz"),
    ("先取局部变量再返回", "    return parse_wechat_url(url).biz",
     "    parts = parse_wechat_url(url)\n    return parts.biz"),
]


def _parses(src: str) -> bool:
    """反证通道自身的守门：变异体必须能解析。解析不了的变异体会让结构判据以
    SyntaxError 的形式「变红」，看起来像缺陷被抓住，实际是锚写错了——必须单独判 FAIL。"""
    try:
        ast.parse(src)
        return True
    except SyntaxError:
        return False


def self_test() -> int:
    rc = 0
    src = KB.read_text(encoding="utf-8")
    if NEW_BODY not in src:
        print(f"FAIL 基准异常：kb.py 里找不到委托后的函数体锚点，MUTANTS/PROBES 的基准无从构造\n{NEW_BODY!r}")
        return 1
    base = evaluate(src)
    if base:
        print(f"FAIL 基准（未变异）就有红判据：{sorted(base)}——self-test 结论不可用")
        rc = 1
    else:
        print("OK   基准：未变形的 kb.py 判据全绿")

    for label, old, new, must_red in MUTANTS:
        if src.count(old) != 1:
            print(f"FAIL 变异锚失配（出现 {src.count(old)} 次）：{label}")
            rc = 1
            continue
        mutated = src.replace(old, new)
        if not _parses(mutated):
            print(f"FAIL 变异体无法解析（锚缩进错）：{label}")
            rc = 1
            continue
        red = evaluate(mutated)
        miss = {k for k in must_red if k not in red}
        if miss:
            print(f"FAIL {label}｜应红未红：{sorted(miss)}｜实际红：{sorted(red)}")
            rc = 1
        else:
            print(f"OK   {label} → 致红 {sorted(red)}")

    for label, judge, bad_body, good_body in PROBES:
        bad_src = _wrap_body(bad_body)
        good_src = _wrap_body(good_body)
        ok_bad = judge(bad_src)[0]
        ok_good = judge(good_src)[0]
        if ok_bad:
            print(f"FAIL {label}：坏样本仍判真（判据不可失败）")
            rc = 1
        elif not ok_good:
            print(f"FAIL {label}：好样本判假，基准选错")
            rc = 1
        else:
            print(f"OK   {label}：好样本判真 / 坏样本判假")

    for label, old, new in EQUIVS:
        mutated = src.replace(old, new)
        if src.count(old) != 1:
            print(f"FAIL 等价重构锚失配：{label}")
            rc = 1
            continue
        if not _parses(mutated):
            print(f"FAIL 等价重构体无法解析（锚缩进错）：{label}")
            rc = 1
            continue
        red = evaluate(mutated)
        if red:
            print(f"FAIL 等价重构被判成缺陷：{label}｜假红={sorted(red)}")
            rc = 1
        else:
            print(f"OK   等价重构 {label} → 判据全绿")

    print(
        f"\nSELF-TEST {'PASS' if rc == 0 else 'FAIL'}："
        f"{len(MUTANTS)} 个函数体变异各自让指定判据变红 + {len(PROBES)} 个判据样本对敏感"
        f" + {len(EQUIVS)} 个等价写法不假红"
    )
    return rc


def _wrap_body(body: str) -> str:
    head = body if body.startswith("def ") else _WRAP + body
    return head + "\n"


def evaluate(src: str) -> set[str]:
    """返回变红的判据 id 集合（结构面 + 行为面，行为面异常按「该判据红」处理）。"""
    red: set[str] = set()
    structural = {
        "BD-7": j_calls_delegate,
        "BD-8": j_import_source,
        "BD-9": j_no_second_parser,
        "BD-10": j_no_swallow,
        "BD-11": j_reads_both,
    }
    for bid, judge in structural.items():
        try:
            if not judge(src)[0]:
                red.add(bid)
        except (AssertionError, SyntaxError) as exc:
            red.add(f"{bid}(异常 {type(exc).__name__})")
    try:
        biz = load_biz(src)
    except BaseException as exc:  # noqa: BLE001 - 变异体可能连函数都构造不出来
        return red | {f"EXEC({type(exc).__name__})"}
    for label, ok, _detail in behavior_probes(biz):
        if not ok:
            red.add(label.split()[0])
    return red


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else main())
