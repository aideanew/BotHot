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
def test_known_false_positive_families_fire_today(text: str, why: str) -> None:
    """现读自 V0.13.0/V0.14.0 证据件：`assign` 启发式对本仓文档 10 连发全假。

    本用例**钉住现状而非背书**：规则收窄属安全判据语义变更，卡面写明需单独评审、
    且禁止执行方自建 allowlist，故登记交规划方/00S（P-36），这里只留可重跑的读数。
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


# ═══════════════════════════ G. P-40 / D-V12-19：源码文件里只报带引号的赋值


@pytest.mark.parametrize(
    "line",
    [
        # 一律拼接：本文件自身在门的扫描面上
        "        " + "secret" + "=decrypt_channel_secret(ch.id, ch.secret_enc),",
        "          " + "secret" + ": formData.secret,",
        "    " + "token" + " = settings.feishu_token",
    ],
    ids=["函数调用", "属性访问", "设置引用"],
)
def test_code_expressions_are_not_values(line: str) -> None:
    assert guards.secret_scan(line, code=True)[0] == []
    # 同一行放在文档里仍按宽口径报——收窄只作用于源码
    assert [h[0] for h in guards.secret_scan(line)[0]] == ["assign"]


def test_quoted_literal_in_code_is_still_high() -> None:
    hits, _ = guards.secret_scan("token" + ' = "hunter2secret99"', code=True)
    assert [h[0] for h in hits] == ["assign"]
    hits, _ = guards.secret_scan("const " + "password" + ": 'hunter2secret99',", code=True)
    assert [h[0] for h in hits] == ["assign"]


def test_named_rules_still_fire_in_code() -> None:
    hits, _ = guards.secret_scan("x = " + AKIA, code=True)
    assert hits, "具名规则在源码里被一起关掉了"


def test_gate_applies_code_mode_by_suffix(monkeypatch) -> None:
    expr = ("secret" + ": formData.secret\n").encode()
    _fake_git(monkeypatch, staged="a.tsx\nb.md\n", blobs={"a.tsx": expr, "b.md": expr})
    assert guards.secret_shape_check() == 1  # b.md 仍报
    _fake_git(monkeypatch, staged="a.tsx\n", blobs={"a.tsx": expr})
    assert guards.secret_shape_check() == 0

