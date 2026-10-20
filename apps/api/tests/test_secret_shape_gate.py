"""STEP-00P 敏感形机械门的判据用例（S00P.1.1 / S00P.1.2 / S00P.2.1 / S00P.2.2 / S00P.3.1）。

三条来自本轮现读的立项理由，写在最前面，免得后人以为这堆用例是形式主义：

1. **卡面指定的调用方式会造一个永远绿的门**。`docs/任务规划V0.5.0/evidence/65f508b/secret_shape_scan.py`
   的扫描集是 `rglob("*")`，把**单个文件**当参数喂给它返回空集 ⇒ 「文件数 0 / HIGH 0 / rc=0」
   （同一个 patch 文件按目录扫到 5 条、按文件扫到 0 条）。所以判据实体在 `scripts/guards.py`，
   并由 §D 的用例与那条脚本源码里的字面量**逐条对账**，防止副本漂移。
2. **门差点咬死自己**。第一版 `scripts/guards.py` 的注释里内联了凭据形状，自扫即 HIGH 命中——
   这正是本卡 S00P.2.1 立的规矩要防的事，而违规者是实现该规矩的文件本身。§G 末条把它钉成常设判据。
3. **夹具不许留形，否则检测器的测试会把门禁扫红**。本仓既有纪律是「去形」（S00S 已把 HEAD 内
   最后一处凭据形去形）。所以本文件所有形状都由**跨字符串边界拼接**产生：运行期拼出的串命中，
   源码文本里的行不命中。§A 与 §G 末条成对证明这件事——缺任何一侧，另一侧就是空话。

假阳性口径说明：§E 钉住的是**现状**（已登记待规划方裁），不是背书。执行方不自行收窄安全判据。
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_ROOTS = [
    up for up in Path(__file__).resolve().parents
    if (up / "scripts" / "guards.py").is_file() and (up / "Makefile").is_file()
]
assert _ROOTS, "向上找不到同时含 scripts/guards.py 与 Makefile 的仓库根"
_ROOT = _ROOTS[0]
_GUARDS_PATH = _ROOT / "scripts" / "guards.py"
# 规则的唯一权威副本（历史证据件，本卡禁止修改，只用于对账）
_TOOL_PATH = _ROOT / "docs" / "任务规划V0.5.0" / "evidence" / "65f508b" / "secret_shape_scan.py"

_spec = importlib.util.spec_from_file_location("bothot_secret_guards_under_test", _GUARDS_PATH)
assert _spec is not None and _spec.loader is not None
guards: Any = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guards)

# ── 夹具：形状一律拼接，源码文本里不留完整形状（见文件头理由 3）────────────────
PW = "S3cr3t" + "TailValue"
AKIA = "AKIA" + "1234567890ABCDEF"
GH = "ghp_" + "a" * 25
PAT = "github_pat_" + "b" * 25
SLACK = "xox" + "b-" + "c" * 12
SK = "sk-" + "d" * 24
GOOG = "AIza" + "e" * 32
PEM = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
VENDOR = "tikhub_api_key" + " = " + "g" * 12


def _dsn(pw: str = PW, user: str = "svc_acct", host: str = "db.example.invalid") -> str:
    return "post" + "gres://" + user + ":" + pw + "@" + host + ":5432/app"


def _kv(key: str, val: str) -> str:
    return key + ' = "' + val + '"'


# ═══════════════════════════ A. 判据敏感性：每条规则都要能红

_SHAPES = [
    ("dsn-embedded-password", _dsn()),
    ("aws-akia", AKIA),
    ("github-token", GH),
    ("github-fine-grained", PAT),
    ("slack-token", SLACK),
    ("openai-key", SK),
    ("google-api-key", GOOG),
    ("private-key-block", PEM),
    ("anthropic-key", "sk-ant-" + "f" * 22),
    ("vendor-key-assign", VENDOR),
    ("assign", _kv("password", PW)),
]


@pytest.mark.parametrize("rule, text", _SHAPES)
def test_every_rule_fires_on_its_own_shape(rule: str, text: str) -> None:
    """一条规则永远不会红 ⇒ 这一维等于不存在。逐条要求它至少命中自己那条形状。"""
    hits, allowed = guards.secret_scan(text)
    assert [h[0] for h in hits] == [rule], f"{rule} 没有报出来：{hits} / allowed={allowed}"


def test_rule_set_has_ten_entries_plus_the_assign_shape() -> None:
    """规则条数由常量产生，不手填：门少一条规则就等于少一维召回。"""
    assert len(guards.SECRET_RULES) == 10
    assert len([n for n, _ in _SHAPES if n != "assign"]) == len(guards.SECRET_RULES)


def test_multi_hit_text_counts_each_hit_separately() -> None:
    """同一行两条形状 ⇒ 两条命中：计数合并会把「一处还是三处」这件事糊掉。"""
    hits, _ = guards.secret_scan(_dsn() + " 以及 " + AKIA)
    assert len(hits) == 2, hits


# ═══════════════════════════ B. 放行侧：ALLOW 有效，但不是万能放行

@pytest.mark.parametrize(
    "text",
    [
        _dsn(pw="${PGPASS}"),
        _dsn(pw="$PGPASS"),
        _dsn(pw="<pw>"),
        _dsn(pw="%s"),
        _dsn(pw="bothot_dev"),
        _dsn(pw="not_a_secret"),
    ],
    ids=["美元花括号", "美元变量", "尖括号模板", "格式化占位", "本地固定占位", "明示非秘密"],
)
def test_placeholder_forms_are_allowed_not_high(text: str) -> None:
    hits, allowed = guards.secret_scan(text)
    assert hits == [], f"占位值被判成 HIGH：{hits}"
    assert allowed == 1, f"占位值没有被 ALLOW 认领（allowed={allowed}）——放行与漏检在读数上无法区分"


def test_allow_is_not_a_blanket_pass() -> None:
    """极性反证：同一个构造器只把口令段换成不像占位的值 ⇒ 必须红。

    没有这条，B 组「全是 0 命中」既可能是白名单在起作用，也可能是判据整体失效。
    """
    assert guards.secret_scan(_dsn(pw="${PGPASS}"))[0] == []
    assert len(guards.secret_scan(_dsn(pw=PW))[0]) == 1


def test_allow_cannot_be_borrowed_from_another_shape_on_the_same_line() -> None:
    """复核抓出的漏检：原脚本按**整行**判 ALLOW，同一行一处无关占位就能带走真凭据。

    现改为只对匹配段判——这也与 gitleaks 的 allowlist 语义一致（它作用在 match 上）。
    改前这条行读成 ALLOWED=1 / HIGH=0，即「凭据被同行另一条占位形签走」。
    """
    hits, allowed = guards.secret_scan(_dsn() + "  模板另见 url/%s@tenant")
    assert [h[0] for h in hits] == ["dsn-embedded-password"], hits
    assert allowed == 0, "占位形出现在**另一条形状**里，不该替真凭据放行"


def test_a_comment_mentioning_the_rule_builder_does_not_exempt_a_real_assignment() -> None:
    """复核抓出的第二条漏检：`re.compile` 的行级豁免太宽——注释里提一句就免检。

    收窄成「值本身以 re.compile 开头」（真正的规则定义行形状）。
    """
    hits, _ = guards.secret_scan("token" + ' = "hunter2secret99"' + "  # 这行与 re.compile 无关")
    assert [h[0] for h in hits] == ["assign"], hits


def test_rule_definition_lines_do_not_report_themselves() -> None:
    """`X = re.compile(…)` 这类规则定义行不算命中，否则召回器举报自己（原脚本同规矩）。"""
    guarded = 'token = re.compile("[a-z]{20}")'
    assert guards.secret_scan(guarded)[0] == []
    # 极性：摘掉 re.compile，同一行就是普通的口令赋值 ⇒ 必须红。
    # 没有这一句，上面那条「0 命中」可能是豁免在起作用，也可能是判据根本没跑。
    assert [h[0] for h in guards.secret_scan("token" + " = my-app-secret-value")[0]] == ["assign"]


# ═══════════════════════════ C. 输出只报形状，不报正文（安全铁律第 1 条）

# (规则名, 形状文本, 绝不许出现在输出里的那一段)
_MASK_CASES = [
    ("dsn-embedded-password", _dsn(), PW),
    ("aws-akia", AKIA, "1234567890ABCDEF"),
    ("github-token", GH, "a" * 20),
    ("github-fine-grained", PAT, "b" * 20),
    ("slack-token", SLACK, "c" * 10),
    ("openai-key", SK, "d" * 20),
    ("google-api-key", GOOG, "e" * 30),
    ("private-key-block", PEM, "OPENSSH"),
    ("anthropic-key", "sk-ant-" + "f" * 22, "f" * 20),
    ("vendor-key-assign", VENDOR, "g" * 12),
    ("assign", _kv("password", PW), PW),
]


@pytest.mark.parametrize("rule, text, secret_seg", _MASK_CASES)
def test_reported_shape_never_carries_the_secret_value(rule: str, text: str, secret_seg: str) -> None:
    """命中文本里不得出现被匹配的敏感段——门自己的输出就是最常见的泄漏渠道。

    打码逻辑与 `_MASK_CASES` 成对：改了判据却忘了改打码，这里立刻红。
    """
    hits, _ = guards.secret_scan(text)
    assert [h[0] for h in hits] == [rule], hits
    shape = hits[0][2]
    assert secret_seg not in shape, f"{rule} 的输出带了正文片段：{shape!r}"
    assert len(shape) < len(text), f"{rule} 的片段几乎等于正文：{shape!r}"


def test_dsn_mask_keeps_the_diagnostic_and_drops_the_credential() -> None:
    """打码后仍要能判断是哪一族、哪一行：规则名 + 文件:行号负责定位，片段只留 scheme 与前 4 字符。

    匹配串止于 at 符号 ⇒ 主机段本来就不在片段里（这不是漏，是形状定义）。
    """
    shape = guards.secret_scan(_dsn())[0][0][2]
    assert "postgres" in shape and "***" in shape
    assert PW not in shape and "svc_acct" not in shape


def test_credentials_sitting_in_the_userinfo_slot_are_masked_too() -> None:
    """复核抓出的第三条泄漏：有些形状里**用户名位本身就是凭据**（token 放 user 位、口令位填个 x）。

    只隐口令段的打码等于把这条凭据整条留在输出里——本用例的形状就是那个形状。
    它同时命中 token 族（那条 token 本身就该被抓），两条命中都要打码。
    """
    line = _dsn(user="ghp_" + "A" * 30, pw="x")
    hits, _ = guards.secret_scan(line)
    assert sorted(h[0] for h in hits) == ["dsn-embedded-password", "github-token"], hits
    for _rule, _no, shape in hits:
        assert "A" * 20 not in shape, shape


def test_the_masked_fragment_is_still_a_shape_do_not_quote_gate_output_into_docs() -> None:
    """打码保证「值不可复原」，**不**保证「形状消失」：星号本身满足那两段的字符类。

    后果（写进 conventions §9.1 与 EVD-V4-00P §10）：门的输出行留在终端/CI 日志是安全的，
    但原样抄进待提交文档 ⇒ 会被这道门自己再扫出来判红。本轮写 EVD 时实测踩到一次。
    """
    shape = guards.secret_scan(_dsn())[0][0][2]
    assert PW not in shape
    assert [h[0] for h in guards.secret_scan(shape)[0]] == ["dsn-embedded-password"]


# ═══════════════════════════ D. 与卡面指定脚本逐条对账（防副本漂移）


def _tool_patterns() -> dict[str, list[str]]:
    """从那条脚本的源码里抽 `re.compile` 字面量，不 exec 它（它是脚本、import 即扫描并 sys.exit）。

    三个都得处理：模式既可能直接写在 `re.compile(...)` 里，也可能引用上面定义过的名字
    （DSN 就是引用），折行写法则是相邻字符串相加（vendor 规则）。任一种取不到都要报错，
    **不能悄悄跳过**——悄悄跳过的对账等于没对账。
    """
    tree = ast.parse(_TOOL_PATH.read_text(encoding="utf-8"), filename=str(_TOOL_PATH))
    out: dict[str, list[str]] = {"RULES": [], "ALLOW": [], "ASSIGN": [], "FAKE": []}
    named: dict[str, str] = {}

    def compiled(node: ast.expr) -> str | None:
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "compile" and node.args):
            return None
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
        if isinstance(first, ast.BinOp):  # 相邻字符串折行
            parts: list[str] = []
            cur: ast.expr | None = first
            while isinstance(cur, ast.BinOp):
                if isinstance(cur.right, ast.Constant) and isinstance(cur.right.value, str):
                    parts.append(cur.right.value)
                cur = cur.left
            if isinstance(cur, ast.Constant) and isinstance(cur.value, str):
                parts.append(cur.value)
            if len(parts) >= 2:
                return "".join(reversed(parts))
        return None

    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Name):
            continue
        tgt = node.targets[0]
        pat = compiled(node.value)
        if pat is not None and tgt.id not in out:
            named[tgt.id] = pat
        if tgt.id not in out:
            continue
        value = node.value
        if isinstance(value, ast.List):
            for elt in value.elts:
                if isinstance(elt, ast.Tuple) and len(elt.elts) == 2:
                    name, src = elt.elts[0], elt.elts[1]
                    got = compiled(src)
                    if got is None and isinstance(src, ast.Name):
                        got = named.get(src.id)
                    assert got is not None, f"对账基准取不到：{tgt.id} 里的 {name.value!r}"
                    out[tgt.id].append(f"{name.value}:{got}")
                elif isinstance(elt, ast.Call):
                    got = compiled(elt)
                    assert got is not None, f"对账基准取不到：{tgt.id} 的列表元素"
                    out[tgt.id].append(got)
        else:
            got = pat
            if got is None and isinstance(value, ast.Name):
                got = named.get(value.id)
            assert got is not None, f"对账基准取不到：{tgt.id}"
            out[tgt.id].append(got)
    return out


def test_ported_rules_equal_the_card_named_script() -> None:
    """搬过来的规则必须与那条脚本里的字面量**逐字符相同**（含规则名与顺序）。"""
    tool = _tool_patterns()
    mine = [f"{name}:{rx.pattern}" for name, rx in guards.SECRET_RULES]
    assert tool["RULES"], "对账基准取不到 ⇒ 这条用例本身就成了空断言"
    assert mine == tool["RULES"], "规则与卡面指定脚本出现漂移"


def test_ported_allow_and_assign_shapes_equal_the_card_named_script() -> None:
    tool = _tool_patterns()
    assert [rx.pattern for rx in guards.SECRET_ALLOW] == tool["ALLOW"]
    assert guards.SECRET_ASSIGN.pattern == tool["ASSIGN"][0]
    assert guards.SECRET_FAKE.pattern == tool["FAKE"][0]


def test_both_sides_keep_the_compile_flags_inside_the_pattern() -> None:
    """对账比的是**模式串**；谁在规则常量上改用 `re.compile` 的第二/三参数传 flags，比较就漏掉它。

    复核的变异三正是这条：只加 `re.IGNORECASE` 而不动串 ⇒ 对账仍绿 = 悄悄放行。
    所以这里把前提钉死——两侧的规则常量区里，每条模式都只允许一个位置参数、零关键字参数。
    范围刻意只圈规则常量：`guards.py` 别处（轮次门的 `_ROUND_RE`）用 flags 是正常的，
    把它一起禁掉就是拿新用例去改别人的判据。
    """
    regions = {
        _TOOL_PATH: ("RULES", "ALLOW", "ASSIGN", "FAKE", "DSN"),
        _GUARDS_PATH: ("SECRET_RULES", "SECRET_ALLOW", "SECRET_ASSIGN", "SECRET_FAKE",
                       "_SECRET_ASSIGN_SKIP"),
    }
    # DSN 那条要单独列：工具里它是先编译再被 RULES 以名字引用，不列就有一处模式落在这个前提之外
    checked = {_TOOL_PATH.name: 0, _GUARDS_PATH.name: 0}
    for src, names in regions.items():
        tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                tgt = node.targets[0] if node.targets else None
            elif isinstance(node, ast.AnnAssign):  # 本门用的是带注解的赋值，只认 Assign 会整片漏掉
                tgt = node.target
            else:
                continue
            if not (isinstance(tgt, ast.Name) and tgt.id in names):
                continue
            for call in ast.walk(node):
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                        and call.func.attr == "compile"):
                    continue
                checked[src.name] += 1
                assert len(call.args) == 1 and not call.keywords, (
                    f"{src.name} 的 {tgt.id} 出现了带 flags 参数的模式编译，"
                    f"对账面不完整：{ast.unparse(call)[:70]}"
                )
    # 条数也是判据：工具侧 9 条内联 + DSN 引用 + 2 条 ALLOW + ASSIGN + FAKE = 14；
    # 本门侧 10 + 2 + ASSIGN + FAKE + 那条从工具主循环里提名出来的豁免正则 = 15。
    assert checked == {_TOOL_PATH.name: 14, _GUARDS_PATH.name: 15}, checked


def test_the_card_named_script_gives_a_vacuous_pass_on_a_file_argument() -> None:
    """把「为什么不当子进程直调它」钉成可重跑读数，而不是一句辩解。

    该目录的命中来自其中两个文件（`.py` 1 条 + `.txt` 4 条，共 5 条）。按**目录**扫 ⇒ 5 条；
    按其中的 `.txt` **文件**路径扫 ⇒ 0 条 rc=0（扫描集是 `rglob("*")`，对文件根返回空集）。
    照卡面 S00P.1.1 直调就是造一个永绿的安全门。
    用的是 git 跟踪在册的文件，不依赖任何并发会话的未跟踪产物。
    """
    victim = _ROOT / "docs" / "任务规划V0.13.0" / "evidence" / "314d7f2" / (
        "probe_bots_read_by_plain_user.txt")
    assert victim.is_file(), "对账基准文件不在 ⇒ 这条读数无法复现"

    def run(arg: Path) -> tuple[int, str]:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(_TOOL_PATH), str(arg)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return proc.returncode, proc.stdout

    dir_rc, dir_out = run(victim.parent)
    file_rc, file_out = run(victim)
    assert "HIGH 命中：5" in dir_out, f"目录读数变了，需要重新核对：{dir_out[-200:]}"
    assert dir_rc == 1
    assert "HIGH 命中：0" in file_out and file_rc == 0, "该脚本已能按文件扫，本用例可撤（见 S00T 迁移）"


# ═══════════════════════════ E. 假阳性家族：钉住现状，不自行收窄

@pytest.mark.parametrize(
    "text, why",
    [
        # 一律在 `= ` 之后断开拼接：本文件自身也在门的扫描面上，形状不能留在源码文本里
        ("DSN = " + 'os.environ["AIDEANBOT_TEST_PG_DSN"]', "环境变量引用，值不在文本里"),
        ("leaks webhook token: " + "True", "探针读数里的布尔值"),
    ],
    ids=["变量引用", "布尔读数"],
)
def test_known_false_positive_families_still_fire_on_the_doc_face(text: str, why: str) -> None:
    """文档面（`code=False`）的读数**一字未变**：S27.V15.1 ④ 把这条钉成硬约束。

    现读自 V0.13.0/V0.14.0 证据件：`assign` 启发式对本仓文档 10 连发全假。
    源码面（`code=True`）的同一形状由 §H 证明不再误报——两面口径不同是刻意的：
    文档里"键名 = 表达式"读起来仍像一句赋值说明，宁多报；源码里它有语法含义。
    """
    hits, _ = guards.secret_scan(text)
    assert [h[0] for h in hits] == ["assign"], f"{why}：判据行为已变，请同步 P-36 与 {hits}"


def test_false_positives_cannot_widen_the_gate_to_the_whole_repo() -> None:
    """为什么门只扫「本批」而不是全仓：全仓口径下这些假阳性会立刻把门关掉（卡面阻塞条件①）。"""
    paths, _whence, err = guards.secret_scope("HEAD")
    assert err == ""
    assert all("STEP-R0+00C_combined_simulated" not in p for p in paths), (
        "扫描面里出现了历史遗留件 ⇒ 已经退化成全仓口径"
    )


# ═══════════════════════════ F. 门本体：取值口径、三态、不短路、缺席只报真缺席


def _fake_git(monkeypatch, *, staged: str = "", committed: str = "", rev_rc: int = 0,
              blobs: dict[str, bytes] | None = None) -> None:
    def fake(*args: str) -> tuple[int, str]:
        if args[0] == "diff" and "--cached" in args:
            return 0, staged
        if args[0] == "rev-parse":
            return rev_rc, ""
        if args[0] == "diff":
            return 0, committed
        return 0, ""

    table = blobs or {}

    def fake_bytes(*args: str) -> tuple[int, bytes]:
        # secret_blob 走 `git show <ref>:<路径>`：索引面是 `:x.md`，提交面是 `HEAD:x.md`
        if args[0] != "show" or len(args) != 2:
            return 1, b""
        _ref, _, rel = args[1].partition(":")
        if rel not in table:
            return 1, b""
        return 0, table[rel]

    monkeypatch.setattr(guards, "_git", fake)
    monkeypatch.setattr(guards, "_git_bytes", fake_bytes)


def test_scope_prefers_the_index_and_falls_back_to_the_committed_batch(monkeypatch) -> None:
    _fake_git(monkeypatch, staged="a.md\n", committed="b.md\n")
    assert guards.secret_scope("origin/main") == (["a.md"], "index", "")
    _fake_git(monkeypatch, staged="", committed="b.md\nc.md\n")
    paths, whence, err = guards.secret_scope("origin/main")
    assert paths == ["b.md", "c.md"] and whence == "head" and err == ""


def test_unresolvable_base_is_red_not_green(monkeypatch) -> None:
    """索引为空 + 基线不可解析 ⇒ 门什么都没看。当 0 就是「看不见=通过」。"""
    _fake_git(monkeypatch, staged="", rev_rc=1)
    assert guards.secret_shape_check("nope") == 1


def test_empty_scope_is_third_state(monkeypatch) -> None:
    _fake_git(monkeypatch, staged="", committed="")
    assert guards.secret_shape_check("origin/main") == 3


def test_deleted_and_binary_paths_are_skipped_not_vacuous(monkeypatch) -> None:
    _fake_git(monkeypatch, staged="gone.md\nblob.bin\nreal.md\n",
              blobs={"blob.bin": b"\x00\x01binary-ish", "real.md": b"nothing sensitive here\n"})
    assert guards.secret_shape_check("origin/main") == 0  # 跳过 2、实扫 1，不是「什么都没扫」


def test_every_path_skipped_is_third_state_not_pass(monkeypatch) -> None:
    """复核抓出的第二条偏绿：整批都是二进制/删除时，「实扫 0 + HIGH 0」曾被读成通过。

    一条都没看成 ≠ 看过了 ⇒ 这一维没有终判 ⇒ 3。
    """
    _fake_git(monkeypatch, staged="blob.bin\n", blobs={"blob.bin": b"\x00\x01\x02\x03"})
    assert guards.secret_shape_check("origin/main") == 3


def test_oversized_blob_is_skipped_with_a_countable_reading(monkeypatch) -> None:
    """超限文件的跳过要能被读数看见（而不是静默少扫）：整批只剩它 ⇒ 第三态。"""
    _fake_git(monkeypatch, staged="big.md\n", blobs={"big.md": b"a" * (guards._SECRET_MAX_BYTES + 1)})
    assert guards.secret_shape_check("origin/main") == 3


def _stub_evidence(monkeypatch, tmp_path: Path, *, coupling: int, secret: int,
                   tool_results: list[tuple[int, str, str]] | None = None,
                   missing: tuple[str, ...] = ()) -> list[list[str]]:
    """把 evidence_check 的其余维度按住，只看「前置门 × 复跑 × 工具步」的编排。"""
    calls: list[list[str]] = []
    queue = list(tool_results or [])
    (tmp_path / "prove_x.py").write_text("print(1)\n", encoding="utf-8")

    def fake_run(cmd: list[str], cwd: Any = None, **kw: Any) -> SimpleNamespace:
        calls.append([str(c) for c in cmd])
        rc, out, err = queue.pop(0) if queue else (0, "", "")
        return SimpleNamespace(returncode=rc, stdout=out, stderr=err)

    monkeypatch.setattr(guards, "coupling_check", lambda base: coupling)
    monkeypatch.setattr(guards, "secret_shape_check", lambda base: secret)
    monkeypatch.setattr(guards, "ROOT", tmp_path)
    monkeypatch.setattr(guards, "EVIDENCE_PROOFS", ["prove_x.py"])
    monkeypatch.setattr(guards, "subprocess", SimpleNamespace(run=fake_run))
    monkeypatch.setattr(guards, "shutil_which", lambda n: None if n in missing else "/usr/bin/" + n)
    monkeypatch.setattr(guards, "_venv_script", lambda n: None)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    return calls


def test_red_pre_gate_short_circuits_and_is_reported(monkeypatch, tmp_path, capsys) -> None:
    calls = _stub_evidence(monkeypatch, tmp_path, coupling=0, secret=1)
    assert guards.evidence_check("HEAD") == 1
    assert calls == [], "前置门判红后不该再复跑证据/跑工具"
    assert "SKIP" not in capsys.readouterr().out


def test_third_state_from_the_secret_gate_does_not_skip_the_proofs(monkeypatch, tmp_path) -> None:
    """前置门只「无可检面」时不许就地返回：否则干净工作树上本目标失去主用途。"""
    calls = _stub_evidence(monkeypatch, tmp_path, coupling=0, secret=3)
    assert guards.evidence_check("origin/main") == 3
    flat = [" ".join(c) for c in calls]
    assert any("prove_x.py" in c for c in flat), f"证据复跑被第三态短路了：{calls}"
    assert any("/usr/bin/ruff" in c for c in flat) and any("/usr/bin/gitleaks" in c for c in flat)
    assert "prove_x.py" in " ".join(calls[0]), f"复跑不是第一件事：{calls}"


def test_both_pre_gates_run_even_when_the_first_is_red(monkeypatch) -> None:
    """两道前置门之间不许互相遮蔽（S00T.V14.2 刚修过同一个毛病）。"""
    seen: list[str] = []
    monkeypatch.setattr(guards, "coupling_check", lambda base: seen.append("c") or 1)
    monkeypatch.setattr(guards, "secret_shape_check", lambda base: seen.append("s") or 1)
    monkeypatch.setattr(guards, "EVIDENCE_PROOFS", [])
    assert guards.evidence_check("HEAD") == 1
    assert seen == ["c", "s"], seen


def test_secret_gate_runs_before_the_evidence_reruns(monkeypatch, tmp_path, capsys) -> None:
    """顺序用**行为**证明，而不是比对源码文本：命中时复跑连一次都不该被尝试。

    把 EVIDENCE_PROOFS 指到一个不存在的脚本上——若复跑在前，输出里必有「证据脚本不存在」。
    绑源码形状的「谁在前面」断言，会在下一次重构里把改进读成破坏（本轮已在
    `test_guard_rounds.py` 的同族用例上踩过一次并改成 AST 语义查找）。
    """
    calls = _stub_evidence(monkeypatch, tmp_path, coupling=0, secret=1)
    monkeypatch.setattr(guards, "EVIDENCE_PROOFS", ["absent_proof.py"])
    assert guards.evidence_check("HEAD") == 1
    assert calls == []
    assert "证据脚本不存在" not in capsys.readouterr().out


def test_absent_tool_warning_names_only_the_absent_tool(monkeypatch, tmp_path, capsys) -> None:
    """改前 ruff 缺席也会打印「SKIP(tool missing) gitleaks」——一条假缺席读数。"""
    _stub_evidence(monkeypatch, tmp_path, coupling=0, secret=0, missing=("ruff",))
    assert guards.evidence_check("HEAD") == 3
    out = capsys.readouterr().out
    assert "SKIP(tool missing) ruff" in out
    assert "SKIP(tool missing) gitleaks" not in out, f"gitleaks 明明在场：{out}"


def test_gitleaks_failed_to_scan_is_third_state_not_pass(monkeypatch, tmp_path, capsys) -> None:
    """@win 实测：gitleaks 自报 failed to scan 却 rc=0。门不许把它读成「扫过且干净」。

    给第三态而不是判红：这一维没有终判 ≠ 扫出了凭据。把两者混成一个红，
    就是拿狼来了消耗门禁信用——本批文件自身的判定已由前置的敏感形门给出（P-37）。
    """
    err = '1:32PM ERR failed to scan Git repository error="stderr is not empty"'
    _stub_evidence(monkeypatch, tmp_path, coupling=0, secret=0,
                   tool_results=[(0, "", ""), (0, "", err)])
    assert guards.evidence_check("HEAD") == 3
    assert "没有终判" in capsys.readouterr().out


def test_clean_tool_output_still_passes(monkeypatch, tmp_path) -> None:
    """上一条的极性对照：rc=0 且无 failed to scan ⇒ 必须 0，否则门只会一路判红。"""
    _stub_evidence(monkeypatch, tmp_path, coupling=0, secret=0,
                   tool_results=[(0, "", ""), (0, "", "no leaks found"), (0, "", "")])
    assert guards.evidence_check("HEAD") == 0


def test_a_nonzero_tool_rc_is_propagated(monkeypatch, tmp_path) -> None:
    """再一条极性对照：工具自己 rc=1（真报了 leak）⇒ 门红，且不走「failed to scan」那支。"""
    _stub_evidence(monkeypatch, tmp_path, coupling=0, secret=0,
                   tool_results=[(0, "", ""), (1, "leak found", ""), (0, "", "")])
    assert guards.evidence_check("HEAD") == 1


# ═══════════════════════════ G. 端到端：一次性真仓库里把 S00P.1.2 的两档跑出来


def _git_in(tmp: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.name=Gate Test", "-c", "user.email=gate@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        cwd=str(tmp), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, f"git {' '.join(args)} 失败：{proc.stderr}"
    return proc.stdout.strip()


def _scaffold(tmp: Path) -> Path:
    repo = tmp / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "docs" / "06_validation" / "evidence" / "EVD-X").mkdir(parents=True)
    (repo / "apps" / "api" / "tests").mkdir(parents=True)
    (repo / "scripts" / "guards.py").write_text(_GUARDS_PATH.read_text(encoding="utf-8"),
                                                encoding="utf-8")
    (repo / "apps" / "api" / "tests" / "test_seed.py").write_text(
        "def test_seed():\n    assert True\n", encoding="utf-8")
    (repo / "notes.txt").write_text("base\n", encoding="utf-8")
    _git_in(repo, "init", "-q", "-b", "main")
    _git_in(repo, "add", "-A")
    _git_in(repo, "commit", "-q", "-m", "chore: 基线（含 1 条用例）")
    return repo


_STEP_CODE = (
    "import importlib.util,sys;"
    "s=importlib.util.spec_from_file_location('g','scripts/guards.py');"
    "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
    "sys.exit(m.secret_shape_check('HEAD'))"
)


def _run(repo: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "scripts/guards.py", *args],
        cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, proc.stdout


def _run_step(repo: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", _STEP_CODE],
        cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, proc.stdout


def test_end_to_end_staged_shape_blocks_then_the_placeholder_releases(tmp_path: Path) -> None:
    """S00P.1.2 的两档，本轮现跑：含形状 ⇒ 红；换成占位 ⇒ 绿。"""
    repo = _scaffold(tmp_path)
    (repo / "leaky.md").write_text(_dsn() + "\n", encoding="utf-8")
    _git_in(repo, "add", "leaky.md")
    rc, out = _run_step(repo)
    assert rc == 1, f"待提交面含连接串形状却放行：{out}"
    assert "HIGH dsn-embedded-password" in out and PW not in out, out

    (repo / "leaky.md").write_text(_dsn(pw="${PGPASS}") + "\n", encoding="utf-8")
    _git_in(repo, "add", "leaky.md")
    rc, out = _run_step(repo)
    assert rc == 0, f"占位形必须放行（同一构造器只换口令段）：{out}"
    assert "ALLOWED 放行 1" in out, out


def test_end_to_end_the_step_is_a_blocking_member_of_evidence_check(tmp_path: Path) -> None:
    """接线证明：命中时 `evidence-check` 整体必须红，且红在复跑之前（否则只是并列存在）。"""
    repo = _scaffold(tmp_path)
    base = _git_in(repo, "rev-parse", "HEAD")
    (repo / "leaky.md").write_text(_dsn() + "\n", encoding="utf-8")
    _git_in(repo, "add", "leaky.md")
    rc, out = _run(repo, "evidence-check", "--base", base)
    assert rc == 1, out
    assert "HIGH dsn-embedded-password" in out
    assert "── " not in out, f"敏感形门没挡在复跑之前：{out}"


def test_end_to_end_committed_batch_is_scanned_when_the_index_is_empty(tmp_path: Path) -> None:
    """索引为空时退到 base..HEAD：CI/推完之后再跑门，仍看得见这一批（不是每次都空、每次都绿）。"""
    repo = _scaffold(tmp_path)
    base = _git_in(repo, "rev-parse", "HEAD")
    (repo / "leaky.md").write_text(_dsn() + "\n", encoding="utf-8")
    _git_in(repo, "add", "leaky.md")
    _git_in(repo, "commit", "-q", "-m", "docs: 合成批次（含形状）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "scripts/guards.py", "evidence-check", "--base", base],
        cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 1, proc.stdout
    assert "HIGH dsn-embedded-password" in proc.stdout

    # 第三态：范围与索引都空 ⇒ 门什么都没看，不许伪装成通过
    # （这里直接跑这一步而非整个 evidence-check：脚手架里没有 EVIDENCE_PROOFS 的那几个脚本，
    #  走整门会先撞上「证据脚本不存在」，那是脚手架的问题，不是这一维的读数。）
    assert _run_step(repo)[0] == 3


def test_end_to_end_the_index_blob_is_scanned_not_the_worktree(tmp_path: Path) -> None:
    """复核抓出的偏绿主路径：`git add` 之后把工作树洗成占位值，索引里的 blob 仍带凭据。

    门若读工作树 ⇒ rc=0，凭据照常随提交入库。修法是内容一律经 `git show :路径` 取索引那份。
    """
    repo = _scaffold(tmp_path)
    (repo / "leaky.md").write_text(_dsn() + "\n", encoding="utf-8")
    _git_in(repo, "add", "leaky.md")
    (repo / "leaky.md").write_text(_dsn(pw="${PGPASS}") + "\n", encoding="utf-8")
    rc, out = _run_step(repo)
    assert rc == 1, f"门读了工作树而不是索引 ⇒ 凭据照样入库：{out}"
    assert "取材面=index" in out, out

    _git_in(repo, "add", "leaky.md")  # 占位版进索引 ⇒ 该放行
    rc2, out2 = _run_step(repo)
    assert rc2 == 0, f"索引里已是占位形却仍红：{out2}"
    assert "取材面=index" in out2


def test_end_to_end_a_cjk_named_path_is_actually_scanned(tmp_path: Path) -> None:
    """中文名文件必须真的被扫到——本卡第一次实跑时 7 个待检路径只扫了 5 个。

    根因：git 默认把非 ASCII 路径转义成八进制串，门拿那个字符串去拼路径 ⇒ 文件"不存在"
    ⇒ 被计成「本批已删除」跳过。修法是 `_git()` 统一带 `-c core.quotepath=false`。
    这条用例是那个修复的变异杀手：把参数去掉，rc 从 1 变 0（永绿）。
    """
    repo = _scaffold(tmp_path)
    (repo / "敏感形待检.md").write_text(_dsn() + "\n", encoding="utf-8")
    _git_in(repo, "add", "敏感形待检.md")
    rc, out = _run_step(repo)
    assert rc == 1, f"中文名文件被跳过了（quotepath 回归）：{out}"
    assert "敏感形待检.md" in out and "跳过 0" in out, out
    assert PW not in out, "输出里不许带出口令正文（打码判据同样适用于非 ASCII 路径）"


def test_the_implementation_files_themselves_carry_no_shape() -> None:
    """门不能咬自己的实现与本测试。S00P.2.1 的规矩先约束写规矩的人。

    形状只允许出现在**拼接**里：这几条文本都必须 0 命中。
    清单里没有 `scripts/entry.py`——它现有两处 `dsn = <变量引用>` 会被 `assign` 判 HIGH，
    那是 §E 登记的假阳性家族命中了在册代码（P-36），不属本卡允许面，故不在此背书也不在此修。
    """
    mine = [_GUARDS_PATH, Path(__file__), _ROOT / "Makefile",
            _ROOT / "docs" / "04_engineering" / "conventions.md"]
    mine += sorted((_ROOT / "docs" / "06_validation" / "evidence" / "EVD-V4-00P").glob("*.md"))
    for path in mine:
        if not path.is_file():
            continue
        hits, _allowed = guards.secret_scan(path.read_text(encoding="utf-8"))
        assert hits == [], f"{path.name} 里留下了敏感形：{[(h[0], h[1]) for h in hits]}"


# ═══════════════════════════ H. 源码模式（S27.V15.1 / D-V12-21）
#
# 判据（卡面 ①～④，逐条对应下面的用例）：
#   ① 不报：键名在**代码位**、值里没有任何引号（含反引号）且不是纯数字 ⇒ 表达式；
#   ② 照报：键名落在字符串/注释里（文本本身就是字面量，含跨行三引号与反引号）、
#      反引号模板、纯数字值、整体就是一个字面量的直接赋值、以及表达式里带**值类**字面量
#      （≥8 字符且非占位、非全大写环境变量名）的兜底写法；
#   ③ 全仓自有源码：新门只能少报表达式，不能少报任何含**值类**字面量的行；
#   ④ 文档面（code=False）与十条具名规则、SECRET_ALLOW/SECRET_ASSIGN/SECRET_FAKE 字节不变。
#
# 本文件的形状一律跨字符串边界拼接（理由同文件头第 3 条）：运行期拼出的串进判据，
# 源码文本里的行不留完整形状——否则本文件自己会被门判红。

_SRC_EXPRESSION_CASES = [
    ("secret" + " = decrypt_channel" + "_secret(conn, row.secret),", "键名等于解密函数调用"),
    ("payload = {" + "secret" + ": form.secret}", "对象里键名冒号接表单属性"),
    ("token" + " = settings.access" + "_token", "键名等于配置属性"),
]


@pytest.mark.parametrize("text, why", _SRC_EXPRESSION_CASES, ids=[c[1] for c in _SRC_EXPRESSION_CASES])
def test_source_mode_does_not_report_pure_expressions(text: str, why: str) -> None:
    """① 这三条正是 P-40 把 bots.py / page.tsx / registry.py / push_scheduler.py 挡住的原因。"""
    assert guards.secret_scan(text, code=True)[0] == [], f"{why} 仍被误报"


_VALUED = "hunter2" + "secret99"          # 13 字符，非占位、非全大写环境变量名
_ENVNAME = "AIDEANBOT_TEST" + "_PG_DSN"   # 全大写环境变量名：是名字，不是值

_SRC_MUST_REPORT = [
    (_dsn(), "双引号字符串里的连接串（具名规则）", "hash"),
    ('DOC = """\nAPI' + '_KEY=' + _VALUED + '\n"""', "字符串里的环境行（大写键名等于值）", "hash"),
    ("# password" + " = " + _VALUED, "井号注释里的赋值", "hash"),
    ("// token" + " = " + _VALUED, "双斜杠注释里的赋值", "slash"),
    ("const s = `password" + "=" + _VALUED + "`", "反引号模板里的赋值", "slash"),
    ("password" + " = 12345678", "纯数字口令", "hash"),
    ('DOC = """\n' + "password" + " = " + _VALUED + '\n"""', "三引号跨行字符串里的赋值", "hash"),
    ("const t = `\n" + "token" + " = " + _VALUED + "\n`", "反引号跨行字符串里的赋值", "slash"),
    ("token" + ' = os.getenv("' + _ENVNAME + '", "' + _VALUED + '")', "取环境变量带写死兜底值", "hash"),
    ("api_key" + ' = cfg.get("k", "' + _VALUED + '")', "字典 get 带写死兜底值", "hash"),
    ("secret" + ' = os.environ.get("X") ?? "' + _VALUED + '"', "空值合并的写死兜底值", "slash"),
    ("secret" + ' = os.environ.get("X") || "' + _VALUED + '"', "逻辑或的写死兜底值", "slash"),
    ("secret" + ' = os.environ.get("X") or "' + _VALUED + '"', "or 的写死兜底值", "hash"),
    ("secret" + ' = "' + _VALUED + '" if flag else other', "三元的写死兜底值", "hash"),
    ("secret" + ' = "' + _VALUED + '" + suffix', "字符串拼接的写死兜底值", "hash"),
]


@pytest.mark.parametrize("text, why, lang", _SRC_MUST_REPORT, ids=[c[1] for c in _SRC_MUST_REPORT])
def test_source_mode_still_reports_every_literal_shape(text: str, why: str, lang: str) -> None:
    """② 两轮独立复查构造的全部反例，一条都不能少（D-V12-21 的验收口径）。"""
    assert guards.secret_scan(text, code=True, lang=lang)[0] != [], f"{why} 在源码模式下漏报了"


def test_source_mode_skips_an_env_name_argument_but_not_a_fallback_value() -> None:
    """极性成对：同一个调用，只把第二参数从"名字"换成"值"，判定必须翻转。

    没有这一对，上面「带兜底值要报」可能只是"所有带引号的都报"，而「纯表达式不报」
    也可能只是"所有调用都不报"——两种解释都过得去，判据就没有分辨率。
    """
    only_name = "token" + ' = os.getenv("' + _ENVNAME + '")'
    with_value = "token" + ' = os.getenv("' + _ENVNAME + '", "' + _VALUED + '")'
    assert guards.secret_scan(only_name, code=True)[0] == []
    assert guards.secret_scan(with_value, code=True)[0] != []


def test_source_mode_treats_a_keyed_lookup_as_a_reference_not_a_value() -> None:
    """键位里的字面量是**字段名**，不是值：`x=body["x"]` 与 `x=form.get("x", "")` 都是表达式。

    回归来源（S27.3 首版自伤）：首版把下标/首实参里的字段名当成值类字面量，于是
    `app/providers/aidean/client.py`、`app/api/v1/auth.py` 这两份**改前能过门**的文件被
    新口径判红——放宽表达式的那批改动，又把两处表达式关回门里。判据：键位（`[` 之后、
    `.get(`/`.pop(`/`.setdefault(` 的第一个实参）里的字面量不参与"值类"判定。
    """
    access = "access" + "_token"
    refresh = "refresh" + "_token"
    ident = "id" + "_token"
    code = (
        "def pair(body):\n"
        "    return TokenPair(\n"
        f'        {access}=body["{access}"],\n'
        f'        {refresh}=body["{refresh}"],\n'
        f'        {ident}=body.get("{ident}", ""),\n'
        "    )\n"
    )
    assert guards.secret_scan(code, code=True)[0] == []


def test_source_mode_still_reports_a_hardcoded_fallback_after_a_keyed_lookup() -> None:
    """键位放过 ≠ 整行放过：同一个 `.get` 的第二个实参是值，必须照报。

    与上一条成对：只把"字段名"换成"写死兜底值"，判定必须翻转，否则「键位放过」
    与「所有调用都不报」两种解释都过得去。
    """
    key = "api" + "_key"
    code = f'{key} = cfg.get("{key}", "{_VALUED}")'
    assert [h[1] for h in guards.secret_scan(code, code=True)[0]] == [1]


def test_source_mode_keeps_the_named_rules_untouched() -> None:
    """④ 十条具名规则在源码面一字不改：连接串/私钥块/token 前缀都必须照报。"""
    for text in (_dsn(), PEM, GH, AKIA):
        assert guards.secret_scan(text, code=True)[0] != [], text[:12]


def test_source_mode_catches_a_token_suffixed_key() -> None:
    """S27.3 / D-V12-05：`\\b` 边界抓不到 `APP_TOKEN` 这类前缀常量名（P-41）。

    只补 `_TOKEN` 后缀这一族；其余前缀名（`DEFAULT_SECRET` 等）仍按 P-41 的登记留在原地。
    """
    text = "APP" + '_TOKEN = "' + _VALUED + '"'
    assert [h[0] for h in guards.secret_scan(text, code=True)[0]] == ["assign"]


def test_source_mode_is_opt_in_so_the_doc_face_cannot_drift() -> None:
    """④ 默认参数必须仍是文档面：漏掉默认值会让全仓文档读数一夜之间变样。"""
    expr = _SRC_EXPRESSION_CASES[0][0]
    assert guards.secret_scan(expr)[0] != []
    assert guards.secret_scan(expr, code=True)[0] == []


_NAMED_CLEAN_SOURCES = [
    "apps/api/app/api/v1/bots.py",
    "apps/web/app/bots/page.tsx",
    "apps/api/app/providers/discovery/registry.py",
    "apps/api/app/services/push_scheduler.py",
    "scripts/entry.py",
]


@pytest.mark.parametrize("rel", _NAMED_CLEAN_SOURCES)
def test_named_source_files_have_zero_hits_under_source_mode(rel: str) -> None:
    """① 卡面点名的 5 个文件必须全文 0 命中——它们正是 STEP-26/28/10/05 要改的文件。

    改前（严格口径）这 5 个文件共 2+3+4+1+2 = 12 条 HIGH，全是表达式；
    门没有豁免通道，所以不修这一条，后面四张卡的提交会被永久挡住。
    """
    text = (_ROOT / rel).read_text(encoding="utf-8", errors="replace")
    hits, _ = guards.secret_scan(text, code=True)
    assert hits == [], f"{rel} 仍有 {len(hits)} 条：{[(h[0], h[1]) for h in hits]}"


def _tracked_source_files() -> list[str]:
    proc = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files"],
                          cwd=str(_ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr
    exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
    return sorted(p for p in proc.stdout.splitlines()
                  if Path(p).suffix in exts and not p.startswith(".project/"))


_KEYED_CALL = re.compile(r"\.(?:get|pop|setdefault|getlist|getall)\s*\(\s*$")


def _value_like_literals(line: str) -> list[str]:
    """行内**值位**的「值类」字面量：≥8 字符、非占位、非全大写环境变量名。

    键位（`[` 之后、键值访问的首实参）不算——那里的字面量是字段名，`body["access_token"]`
    的右值来自 `body` 而不是那串名字。这一层是实现侧 `_literal_is_key` 的**独立复写**：
    守卫若直接调实现，就成了"用实现证明实现"，判据没有分辨率。
    """
    out: list[str] = []
    for m in re.finditer(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`", line):
        lit = m.group(0)[1:-1]
        if not guards._src_value_like(lit):
            continue
        i = m.start() - 1
        while i >= 0 and line[i] in " \t":
            i -= 1
        if i >= 0 and line[i] == "[":
            continue
        if i >= 0 and line[i] == "(" and _KEYED_CALL.search(line[:i + 1]):
            continue
        # 字典/JSON 键名（行首或 `{`/`,` 之后、紧跟冒号）是字段名，不是值；
        # 三元表达式的真分支也以冒号结尾，但它前面是 `?`，不会被这条豁免吃掉。
        j = m.end()
        while j < len(line) and line[j] in " \t":
            j += 1
        if (j < len(line) and line[j] == ":" and (i < 0 or line[i] in "{,")):
            continue
        # 不含凭据的 URL 是地址，不是值位凭据；带 `@` 的 URL 仍按值类算。
        if "://" in lit and "@" not in lit:
            continue
        # S29.3 / P-45：`getattr(obj, "属性名", 默认)` 的第二个实参是**名字**，不是值。
        # 独立复写这一档：找字面量左侧最近的未闭合 `(`，数它与字面量之间的顶层逗号。
        depth = 0
        commas = 0
        open_at = -1
        j = m.start() - 1
        while j >= 0:
            ch = line[j]
            if ch in ")]}":
                depth += 1
            elif ch in "([{":
                if depth == 0:
                    open_at = j
                    break
                depth -= 1
            elif ch == "," and depth == 0:
                commas += 1
            j -= 1
        if (open_at >= 0 and line[open_at] == "(" and commas == 1
                and re.search(r"\bgetattr$", line[:open_at].rstrip())):
            continue
        out.append(lit)
    return out


def test_source_mode_never_drops_a_line_carrying_a_value_literal() -> None:
    """③ 全仓自有源码的新旧命中集合对照，判据是**包含关系**而不是计数相等。

    只允许少报「不含值类字面量」的表达式行（例如键名等于一次环境变量读取）；
    任何含值类字面量的行，改前报、改后也必须报——否则就是安全面的倒退（复查第 2 轮的 B 条）。
    """
    files = _tracked_source_files()
    assert len(files) > 300, f"扫描面只有 {len(files)} 个文件，疑似 ls-files 取空"
    regressions: list[str] = []
    for rel in files:
        text = (_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        old = guards.secret_scan(text)[0]
        new = guards.secret_scan_for_path(text, rel)[0]
        old_lines = {no for _n, no, _s in old}
        new_lines = {no for _n, no, _s in new}
        lines = text.splitlines()
        for no in sorted(old_lines - new_lines):
            if _value_like_literals(lines[no - 1]):
                regressions.append(f"{rel}:{no}")
    assert regressions == [], f"源码模式少报了含值类字面量的行：{regressions[:10]}"


def test_source_mode_only_adds_hits_carrying_a_value_literal() -> None:
    """③ 的另一半读数：源码面比文档面**多报**的每一行都必须是真字面量（S29.2 口径）。

    口径演进（S29 卡面「新增命中逐行列出且每条人工判定'真字面量'；新增误报 0」）：

    - S27 只有 `_TOKEN` 后缀族一条新增来源，当时把「新增」钉成"必须匹配后缀族"；
    - S29.1/S29.2 按裁决新收短首段兜底、类型注解、引号键名、下标键位与大写常量族，
      新增面合法扩大——但**每条新增行都必须载有值位的值类字面量**（或仍属后缀族，
      那是 S27 已背书的一条，允许它的短值夹具）。

    若哪天有人把表达式过滤删掉（纯表达式也报），新增行里不会再有值类字面量，这里立刻红。
    """
    files = _tracked_source_files()
    added: list[str] = []
    for rel in files:
        text = (_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        old_lines = {no for _n, no, _s in guards.secret_scan(text)[0]}
        new_lines = {no for _n, no, _s in guards.secret_scan_for_path(text, rel)[0]}
        lines = text.splitlines()
        for no in sorted(new_lines - old_lines):
            line = lines[no - 1]
            if guards.SECRET_ASSIGN_SUFFIX.search(line):
                continue
            if not _value_like_literals(line):
                added.append(f"{rel}:{no}")
    assert added == [], f"源码模式新增了不含值类字面量的命中（判据被放宽）：{added[:10]}"


# ═══════════════════════════ I. 接线与二进制属性（S27.V15.1 / S27.4）


def test_the_gate_switches_source_mode_by_extension(monkeypatch) -> None:
    """判据实体有了 `code=` 参数 ≠ 门在用它。按扩展名接线才是 P-40 真正被解开的那一步。

    两档对照：同一个表达式，放在 `.py` 里放行、放在 `.md` 里照报（文档面口径不变）。
    """
    expr = ("secret" + " = decrypt_channel" + "_secret(conn, row.secret)\n").encode()
    _fake_git(monkeypatch, staged="app/x.py\n", blobs={"app/x.py": expr})
    assert guards.secret_shape_check("HEAD") == 0, "源码面没有走源码模式 ⇒ bots.py 仍会被挡"

    _fake_git(monkeypatch, staged="notes.md\n", blobs={"notes.md": expr})
    assert guards.secret_shape_check("HEAD") == 1, "文档面被一起放宽了 ⇒ 违反 S27.V15.1 ④"


def test_docx_is_declared_binary_so_gitleaks_stops_failing_on_windows() -> None:
    """S27.4 / D-V12-06：Git for Windows 的 system 级 gitattributes 给 `*.docx` 注册了
    `diff=astextplain`，而 `docx2txt.exe` 未装 ⇒ gitleaks 自报 `failed to scan` 却 rc=0（P-37）。

    仓库级 `*.docx binary` 覆盖 system 级 textconv，让 Windows 侧的权威步不再 fail-open。
    """
    lines = (_ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    rules = {" ".join(line.split("#", 1)[0].split()) for line in lines}
    assert "*.docx binary" in rules, "缺少 `*.docx binary`：Windows 上 gitleaks 仍会 failed to scan"
    # 只补扩展名是打地鼠：现读触发点从 docx 漂到 odt 再漂到 rtf，全在 vendored 子树里。
    # 子树级 `-diff` 才是让 @win 权威步真正不再 fail-open 的那一条（EVD-V15-27/s27_4.txt）。
    assert "/.project/** -diff" in rules, (
        "缺少 `/.project/** -diff`：system 级 attributes 仍会把整族办公文档交给 textconv，"
        "`failed to scan` 会换个扩展名继续出现"
    )
    # 只补扩展名是打地鼠：现读触发点从 docx 漂到 odt 再漂到 rtf，全在 vendored 子树里。
    # 子树级 `-diff` 才是让 @win 权威步真正不再 fail-open 的那一条（EVD-V15-27/s27_4.txt）。
    assert "/.project/** -diff" in rules, (
        "缺少 `/.project/** -diff`：system 级 attributes 仍会把整族办公文档交给 textconv，"
        "`failed to scan` 会换个扩展名继续出现"
    )


# ═══════════════════════════ J. S29.1/S29.2 召回补缺（P-41 + P-44）
#
# 根因（STEP-27 独立复查 A 项）：老 `SECRET_ASSIGN` 要求**赋值号后第一段 ≥4 字符**。
# 右值以短标识符开头时（`x or …`、`c ? …`、`(x || …`），正则在那一位就落空，
# 整行进不到 `_source_hit` ⇒ 兜底字面量永远看不见。旧门也漏，属存量缺口。
# 本组形状同样跨字符串边界拼接（理由同文件头第 3 条）。

_S29_VALUE = "hunter2" + "secret99"   # 13 字符，非占位、非全大写环境变量名

_S291_REPORT = [
    ("token = x or " + '"' + _S29_VALUE + '"', "hash", "或运算"),
    ("token = x ?? " + '"' + _S29_VALUE + '"', "slash", "空值合并"),
    ("token = x || " + '"' + _S29_VALUE + '"', "slash", "逻辑或"),
    ("token = c ? " + '"' + _S29_VALUE + '" : "othersecretvalue"', "slash", "三元两个分支"),
    ("token = x + " + '"' + _S29_VALUE + '"', "hash", "字符串拼接"),
    ("token = (x || " + '"' + _S29_VALUE + '")', "slash", "括号或运算"),
]


@pytest.mark.parametrize("text, lang, why", _S291_REPORT, ids=[c[2] for c in _S291_REPORT])
def test_s291_short_first_segment_still_reports_the_fallback(text: str, lang: str, why: str) -> None:
    """S29.1 先红判据：首段不足 4 字符时，写死的兜底字面量必须照报。"""
    assert guards.secret_scan(text, code=True, lang=lang)[0] != [], f"{why}：短首段整类漏报"
    # 同一条文本在文档面必须**保持改前读数**（严格口径仍要求首段 ≥4 字符）：
    # 这不是缺陷，是 S27.V15.1 ④「文档面逐字节不变」的硬约束。
    assert guards.secret_scan(text)[0] == [], f"{why}：文档面被一起放宽了"


_S291_PURE = [
    "token" + " = settings.token",
    "secret" + " = decrypt" + "(row.secret)",
    "password" + " = db.lookup" + "(user)",
    "api_key" + " = os.environ" + "[KEY]",
    "token" + " = await get_token" + "()",
    "secret" + ' = form["secret"]',
    "password" + ' = request.form.get("password")',
    "token" + ' = cfg.get("k")',
    "secret" + " = self._secret",
    "api_key" + " = payload.api_key",
]


@pytest.mark.parametrize("text", _S291_PURE)
def test_s291_pure_expressions_stay_silent(text: str) -> None:
    """S29.1 的另一半：放开下限不能把纯表达式放回来（复查 A 项「不报」清单）。"""
    assert guards.secret_scan(text, code=True)[0] == [], f"纯表达式被误报：{text}"


_S292_REPORT = [
    ('password: str = "' + _S29_VALUE + '"', "hash", "带类型注解的赋值"),
    ('{"password": "' + _S29_VALUE + '"}', "slash", "带引号键名（双引号）"),
    ("{'token': '" + _S29_VALUE + "'}", "hash", "带引号键名（单引号）"),
    ('"Authorization"' + ': "Bearer abcdefghijkl"', "slash", "Authorization 键名"),
    ('os.environ["API_KEY"] = "' + _S29_VALUE + '"', "hash", "下标赋值"),
    ('cfg["token"] = "' + _S29_VALUE + '"', "hash", "下标赋值（token）"),
    ('password: str = Field(default="' + _S29_VALUE + '")', "hash", "Field 带注解"),
    ('DEFAULT_PASSWORD = "' + _S29_VALUE + '"', "hash", "大写常量 _PASSWORD"),
    ('APP_API_KEY = "' + _S29_VALUE + '"', "hash", "大写常量 _API_KEY"),
]


@pytest.mark.parametrize("text, lang, why", _S292_REPORT, ids=[c[2] for c in _S292_REPORT])
def test_s292_recall_classes_report_their_literal(text: str, lang: str, why: str) -> None:
    """S29.2 逐类先红后绿：每类都必须报出写死字面量。"""
    assert guards.secret_scan(text, code=True, lang=lang)[0] != [], f"{why}：召回缺口仍在"


_S292_QUIET = [
    ('{"password": form.password}', "slash", "对象键名接表单属性"),
    ("{'token': payload.token}", "hash", "对象键名接载荷属性"),
    ('"Authorization": f"Bearer {token}"', "slash", "模板串里的变量"),
    ('os.environ["API_KEY"] = os.getenv("SOME_KEY")', "hash", "下标赋值的右值是读取"),
    ('cfg["token"] = settings.token', "hash", "下标赋值的右值是属性"),
    ('password: str = os.getenv("PGPASSWORD")', "hash", "注解赋值的右值是读取"),
]


@pytest.mark.parametrize("text, lang, why", _S292_QUIET, ids=[c[2] for c in _S292_QUIET])
def test_s292_no_new_false_positive_on_the_same_shapes(text: str, lang: str, why: str) -> None:
    """S29.2 的收类门槛：同一形状只把右值换成表达式 ⇒ 必须 0 命中。

    没有这一半，「收类」可能只是把表达式重新关回门里（S27.3 首版自伤的同族）。
    """
    assert guards.secret_scan(text, code=True, lang=lang)[0] == [], f"{why}：新增误报"


# ═══════════════════════════ K. S29.3 getattr 第二个参数是属性名（P-45）

def test_s293_getattr_second_argument_is_a_name_not_a_value() -> None:
    """`getattr(obj, "attr_name", default)` 的第二个参数是**名字**，不是兜底值。

    reranker.py:145 的误报就是它：两个 `getattr` 的属性名都是 ≥8 字符字面量。
    默认值位（第三参数起）仍按值判定——见下一条极性对照。
    """
    call = ("api_key" + ' = str(getattr(settings, "rerank_api_key", "")'
            ' or getattr(settings, "embedding_api_key", "") or "")')
    assert guards.secret_scan(call, code=True)[0] == [], "属性名被当成值"


def test_s293_getattr_default_value_still_reports() -> None:
    """极性对照：同一个调用，把第三参数换成 ≥8 字符非占位字面量 ⇒ 必须报。"""
    call = ("api_key" + ' = getattr(settings, "rerank_api_key", "' + _S29_VALUE + '")')
    assert guards.secret_scan(call, code=True)[0] != []


def test_s293_the_real_reranker_file_has_zero_hits() -> None:
    """S29.3 的验收面：业务文件 reranker.py 全仓口径下 0 命中（改前 1 条）。"""
    path = _ROOT / "apps" / "api" / "app" / "providers" / "reranker.py"
    text = path.read_text(encoding="utf-8", errors="replace")
    hits, _ = guards.secret_scan_for_path(text, str(path))
    assert hits == [], f"reranker.py 仍有 {len(hits)} 条：{[(h[0], h[1]) for h in hits]}"
