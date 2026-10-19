"""STEP-00T V14 两道闸的判据用例（S00T.V14.1 / S00T.V14.2）。

为什么单独一个文件、且必须是「纯函数 + 合成输入」：这两道门管的是**治理**，
不是业务行为。喂真实 git 状态会让用例依赖本机 HEAD（今天绿、明天红），
而判据本身是否敏感就永远测不出来——本轮已经为「空守卫」返工过一次。

来源：D-14（≤2 轮，第 3 轮熔断）、D-V4-03（证据净增 ⇒ 用例净增 ≥1）、
D-V11-04（阈值以 D-14 为准，不是 S0G.2.1 旧卡面的 >3）、F-V14-06（两条裁决在
`scripts/`、`Makefile`、`.github/` 里都找不到执行代码）。
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOTS = [
    up for up in Path(__file__).resolve().parents
    if (up / "scripts" / "guards.py").is_file() and (up / "Makefile").is_file()
]
assert _ROOTS, "向上找不到同时含 scripts/guards.py 与 Makefile 的仓库根"
_ROOT = _ROOTS[0]
_GUARDS_PATH = _ROOT / "scripts" / "guards.py"

_spec = importlib.util.spec_from_file_location("bothot_guards_under_test", _GUARDS_PATH)
assert _spec is not None and _spec.loader is not None
guards: Any = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guards)

# 主题样本一律带 STEP- 前缀：判据按 `STEP-<id>` 归卡（规划方定的口径），
# 只写 L3 号（如 `S1.3.2`）的主题**不会**被归属——这条盲区在 §末尾单独有用例钉住，
# 并在 EVD-V14-00T §4 登记，不在执行方一侧擅自扩判据。


def _subject(step: str, n: int = 1, token: str = "返工") -> str:
    return f"fix(STEP-{step} S{step}.1): 第 {n} 轮{token}——合成主题 {n}"


# ═══════════════════════════════════ A. D-14 轮次熔断门


def test_rounds_gate_allows_exactly_two_rounds() -> None:
    """D-14 的上界是「≤2 轮」，所以 2 次标记必须绿。"""
    subjects = [_subject("91"), _subject("91", 2)]
    assert guards.rounds_violations(subjects) == []


def test_rounds_gate_flags_the_third_round_and_names_the_card() -> None:
    """3 次标记 ⇒ 红，且必须点名是哪张卡（不点名的门无法据以停手）。"""
    subjects = [_subject("92"), _subject("92", 2), _subject("92", 3)]
    violations = guards.rounds_violations(subjects)
    assert len(violations) == 1, violations
    assert violations[0]["step"] == "92"
    assert violations[0]["count"] == 3
    assert len(violations[0]["subjects"]) == 3  # type: ignore[arg-type]


def test_rounds_gate_fires_on_explicit_round_number_alone() -> None:
    """只有一条主题、但直接写出「第 3 轮」⇒ 也必须红。

    只有「计数 >2」这一条路的话，跨提交边界的返工（第 1、2 轮在基线之前）就永远数不满，
    而「已经第 3 轮」这句话本身就是熔断条件。
    """
    assert len(guards.rounds_violations([_subject("93", 3)])) == 1
    # 第 2 轮不熔断（≤2 仍在允许范围内）
    assert guards.rounds_violations([_subject("93", 2)]) == []


def test_rounds_gate_accepts_the_english_round_spelling() -> None:
    """本仓真实主题里两种写法都有（`round-9` 与 `第N轮`），只认一种就会漏计。"""
    subjects = [
        "fix(STEP-94 S94.1): round-9 closures, 我写的判据自曝",
        "fix(STEP-94 S94.1): 第 10 轮仍红",
    ]
    violations = guards.rounds_violations(subjects)
    assert len(violations) == 1 and violations[0]["count"] == 2
    assert violations[0]["explicit_rounds"] == [9, 10]


def test_rounds_gate_counts_rework_token_without_round_number() -> None:
    """「返工」「重做」两个词都算标记；不含轮号的裸词也要计数。"""
    subjects = [
        "fix(STEP-95): 返工——判据是空的",
        "fix(STEP-95): 重做——换个判据",
        "fix(STEP-95): 又返工一次",
    ]
    assert len(guards.rounds_violations(subjects)) == 1


def test_rounds_gate_attributes_per_card_not_globally() -> None:
    """三张卡各一次返工 ⇒ 绿：D-14 管的是「同一任务连续 FAIL」，不是全仓库的返工总量。"""
    subjects = [_subject("96"), _subject("97"), _subject("98")]
    assert guards.rounds_violations(subjects) == []


def test_rounds_gate_ignores_subjects_without_markers() -> None:
    subjects = [
        "feat(STEP-99 S99.1): 新增两条用例",
        "docs(STEP-99/08): 补执行记录",
        "chore: 清理 scratch",
    ]
    assert guards.rounds_violations(subjects) == []


def test_rounds_gate_round_number_needs_a_word_boundary() -> None:
    """反证（首轮评审实测出的**假红**）：`background-3`、`around 3` 不是轮次。

    没有词界时 `reorder around 3 tests` 会被判成"第 3 轮"并直接熔断——
    门一红人就停手，假红的最终代价是门被关掉（本仓已经有关掉门的先例）。
    第 2 轮复验又补了两个同族形态：连字符前缀与下划线分隔。
    """
    assert guards._round_numbers("fix(STEP-01): tune background-3 timeout") == []
    assert guards._round_numbers("fix(STEP-01): reorder around 3 tests") == []
    assert guards._round_numbers("fix(STEP-01): second-round 3 of the review") == []
    assert guards._round_numbers("fix(STEP-01): back-ground-3 layout") == []
    assert guards.rounds_violations(["fix(STEP-01): tune background-3 timeout"]) == []
    # 但真正的几种写法必须仍然计数（防"为了修假红把判据修成永远空"）
    assert guards._round_numbers("fix(STEP-01): round-3 closures") == [3]
    assert guards._round_numbers("fix(STEP-01): 第 3 轮返工") == [3]
    assert guards._round_numbers("fix(STEP-01): Round 3") == [3]
    assert guards._round_numbers("fix(STEP-01): round_3 收尾") == [3]


def test_coupling_check_refuses_when_the_base_blob_cannot_be_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """杀掉一条变异：把 `coupling_check` 里的 fail-closed 分支删掉，其余 38 例仍然全绿。

    第 2 轮复验做变异测试时实测到的（"撤回接线 ⇒ 38 passed"）。纯函数 `missing_base_blobs`
    自己的用例证明不了 `coupling_check` **真的调了它**——这正是 F-V14-06 的形态：
    判据写在文件里，却没有任何东西保证它在执行路径上。
    """
    calls: list[tuple[str, ...]] = []

    def fake_git(*args: str) -> tuple[int, str]:
        calls.append(args)
        if args[0] == "rev-parse":
            return 0, "deadbeef"
        if args[0] == "diff":
            return 0, f"M\tapps/api/tests/test_seed.py\nA\t{EVIDENCE}\n"
        if args[0] == "ls-files":
            return 0, ""
        if args[0] == "cat-file":
            return 1, ""  # 基线里读不到那个 M 行的旧内容
        return 0, ""

    monkeypatch.setattr(guards, "_git", fake_git)
    assert guards.coupling_check("HEAD") == 1, "基线取不到时必须红，不许把「读不到」当「原来没有用例」"
    assert any(c[0] == "cat-file" for c in calls), f"根本没去核验基线 blob：{calls[:3]}"


def test_rounds_gate_attributes_cross_card_subjects_to_the_primary_card_only() -> None:
    """D-V12-02（S27.5）改了这条口径：跨卡提及**只计主卡**，不再连坐。

    改前口径是"提到就都算"，一条同时提到 20/22/23 的"第 3 轮"主题会让三张卡都越限
    （P-33 ③ 登记、评审叫"误杀"）。用户裁决取"只计主卡"，所以现在只有 20 越限。
    """
    subj = "fix(STEP-20 返工轮): 第 3 轮，顺带 STEP-23 与 STEP-22 的文本"
    violations = guards.rounds_violations([subj])
    assert sorted(str(v["step"]) for v in violations) == ["20"]
    assert all(v["explicit_rounds"] == [3] for v in violations)


def test_rounds_gate_cannot_attribute_a_card_named_only_by_l3_id() -> None:
    """`_STEP_ID_RE` 仍只认 `STEP-<id>`；L3 号的反推由 `_primary_card` 单独负责（S27.5）。

    真实例子就是规划方自己的提交风格 `docs(V0.14.0): …STEP-24/25 规划方自做…`
    ——`STEP-24/25` 里的第二个 id（25）不在 `_STEP_ID_RE` 的口径内，主卡是 24。
    """
    assert guards._STEP_ID_RE.findall("docs(V0.14.0): 推送任务创建恒 500（STEP-24/25 自做）") == ["24"]
    assert guards._STEP_ID_RE.findall("docs(裁决台账): S1.3.2 的第 7 轮熔断") == []


def test_rounds_gate_now_attributes_l3_only_subjects() -> None:
    """S27.5 / D-V12-02 关掉了这条盲区：主题只写 L3 号时按第一段反推卡号。

    证据（改前）：`git log` 里 `docs(裁决台账): 登记 D-V8-05——S1.3.2 的「比对器全捕」判据触发
    D-14 熔断（第 7 轮，机械门实读 8>2）` 这条主题含第 7 轮，却既无 `STEP-` 前缀
    也无卡号可归 ⇒ 改前本门放行（EVD-V14-00T §4-3 登记的真实盲区）。
    """
    subject = "docs(裁决台账): 登记 D-V8-05——S1.3.2 的第 7 轮熔断（机械门实读 8>2）"
    assert guards._STEP_ID_RE.findall(subject) == []
    assert [v["step"] for v in guards.rounds_violations([subject])] == ["1"]


def test_rounds_cli_is_fail_closed_on_unresolvable_base() -> None:
    """基线不可解析 ⇒ rc=1。静默跳过会让「没 fetch」看起来像「检查过了」。"""
    assert guards.rounds_check("no-such-ref-8f3a1c") == 1


def test_rounds_cli_returns_three_on_empty_range_not_zero() -> None:
    """`HEAD..HEAD` 为空 ⇒ rc=3（第三态），不能算通过。

    这条是本门最重要的反直觉设计：GitHub 只对多提交推送的**末端**提交建 run，
    推送后 `origin/main..HEAD` 必然为空。若空范围返回 0，「CI 复跑」与「什么都没看」
    在读数上就长得一模一样——正是 F-V14-06 里「签了但没人执行」的同一种失真。
    """
    assert guards.rounds_check("HEAD") == 3


# ═══════════════════════════════════ B. D-V4-03 证据↔用例耦合门

EVIDENCE = "docs/06_validation/evidence/EVD-V14-99/prove_x.py"
TESTS = "apps/api/tests/test_coupled.py"


def _fake_files(**contents: str):
    """把路径→内容做成两个读取回调（head 侧与工作树同义，base 侧另给）。"""

    def read(path: str) -> str:
        return contents.get(path, "")

    return read


def test_coupling_red_when_evidence_added_without_new_cases() -> None:
    rows = [("A", EVIDENCE, None)]
    counts = guards.coupling_counts(rows, _fake_files(), _fake_files())
    assert counts == {"evidence_added": 1, "tests_delta": 0}
    assert guards.coupling_violated(counts["evidence_added"], counts["tests_delta"]) is True


def test_coupling_green_when_a_case_lands_in_the_same_batch() -> None:
    rows = [
        ("A", EVIDENCE, None),
        ("A", TESTS, None),
    ]
    counts = guards.coupling_counts(
        rows,
        _fake_files(**{TESTS: "def test_a():\n    assert True\n"}),
        _fake_files(),
    )
    assert counts == {"evidence_added": 1, "tests_delta": 1}
    assert guards.coupling_violated(counts["evidence_added"], counts["tests_delta"]) is False


def test_coupling_green_when_nothing_was_added_to_evidence() -> None:
    """门只管「新增证据」这一侧；纯改代码的批次不许被它拦。"""
    rows = [("M", TESTS, None)]
    counts = guards.coupling_counts(
        rows,
        _fake_files(**{TESTS: "def test_a():\n    assert True\n\ndef test_b():\n    assert True\n"}),
        _fake_files(**{TESTS: "def test_a():\n    assert True\n"}),
    )
    assert counts["evidence_added"] == 0
    assert counts["tests_delta"] == 1
    assert guards.coupling_violated(counts["evidence_added"], counts["tests_delta"]) is False


def test_coupling_red_when_cases_net_decrease() -> None:
    """卡面写的是「用例净增 = 0 ⇒ 红」；这里取 `< 1`，即净减也要红。

    加证据脚本同时删用例是更坏的情形，按字面「=0」判会放行。这一处收紧是本增量的执行方
    唯一改动判据强度的地方，登记在 EVD-V14-00T §3 待规划方追认。
    """
    rows = [("A", EVIDENCE, None), ("M", TESTS, None)]
    counts = guards.coupling_counts(
        rows,
        _fake_files(**{TESTS: "def test_a():\n    assert True\n"}),
        _fake_files(**{TESTS: "def test_a():\n    assert True\n\ndef test_b():\n    assert True\n"}),
    )
    assert counts == {"evidence_added": 1, "tests_delta": -1}
    assert guards.coupling_violated(counts["evidence_added"], counts["tests_delta"]) is True


def test_untracked_evidence_script_counts_as_added() -> None:
    """未 `git add` 的新证据脚本同样要配对用例；漏掉这一支，门在提交前就是摆设。"""
    rows = [("U", EVIDENCE, None)]
    counts = guards.coupling_counts(rows, _fake_files(), _fake_files())
    assert counts["evidence_added"] == 1
    assert guards.coupling_violated(counts["evidence_added"], counts["tests_delta"]) is True


def test_renamed_evidence_script_is_not_a_new_one() -> None:
    """R（改名）既不算净增证据、也不该逼出用例——否则「搬个目录」被门拦住。"""
    rows = [("R", "docs/06_validation/evidence/EVD-V14-99/probe_x.py", EVIDENCE)]
    counts = guards.coupling_counts(rows, _fake_files(), _fake_files())
    assert counts["evidence_added"] == 0
    assert guards.coupling_violated(counts["evidence_added"], counts["tests_delta"]) is False


_TWO_CASES = "def test_a():\n    assert True\n\ndef test_b():\n    assert True\n"


def test_test_file_renamed_away_from_test_prefix_counts_as_removed() -> None:
    """反证（首轮评审实测出的绕过）：把 `test_gone.py` 改名成 `helper_x.py` 时用例真的消失了。

    只看 new_path 的实现会整条跳过（新路径不再是 `test_`），`tests_delta` 记 0 ⇒
    门在"删用例最彻底"的形态上反而放行。
    """
    rows = [
        ("R", "apps/api/tests/helpers/helper_x.py", TESTS),
        ("A", EVIDENCE, None),
    ]
    counts = guards.coupling_counts(rows, _fake_files(), _fake_files(**{TESTS: _TWO_CASES}))
    assert counts == {"evidence_added": 1, "tests_delta": -2}, counts
    assert guards.coupling_violated(counts["evidence_added"], counts["tests_delta"]) is True


def test_test_file_renamed_keeps_both_sides_counted() -> None:
    """同为 test_ 的改名要两侧各算：旧 2 条、新 3 条 ⇒ 净增 +1（不是 0，也不是 +3）。"""
    rows = [("R", "apps/api/tests/test_renamed.py", TESTS)]
    counts = guards.coupling_counts(
        rows,
        _fake_files(**{"apps/api/tests/test_renamed.py": _TWO_CASES + "\ndef test_c():\n    assert True\n"}),
        _fake_files(**{TESTS: _TWO_CASES}),
    )
    assert counts["tests_delta"] == 1, counts


def test_missing_base_blob_is_refused_instead_of_counted_as_zero() -> None:
    """基线里读不到的旧文件必须红——空串会被当成"原来没有用例"，方向是**偏绿**。

    实测过的偏差：`read_base` 返回 "" 时 M 行报成"用例净增 1"（旧 2 条被抹成 0）。
    """
    rows = [("M", TESTS, None), ("A", EVIDENCE, None)]
    assert guards.missing_base_blobs(rows, lambda rel: False) == [TESTS]
    assert guards.missing_base_blobs(rows, lambda rel: True) == []
    # A/U 行没有基线版本，不该被这条判据拦（否则每个新文件都会红）
    assert guards.missing_base_blobs([("A", TESTS, None), ("U", TESTS, None)], lambda rel: False) == []


def test_deleting_an_evidence_script_can_offset_a_new_one() -> None:
    """净增按 A/U − D 计：本批次「迁走一个脚本 + 新增一个脚本」= 0，不该误报。"""
    rows = [("D", EVIDENCE, None), ("A", "docs/06_validation/evidence/EVD-V14-99/prove_y.py", None)]
    counts = guards.coupling_counts(rows, _fake_files(), _fake_files())
    assert counts["evidence_added"] == 0


def test_case_counter_counts_ast_not_lines() -> None:
    """用例数必须来自 AST：注释、字符串里的 `def test_`、以及非 test_ 前缀都不算。"""
    source = (
        "def test_real():\n    assert True\n"
        "\n"
        "async def test_async_real():\n    assert True\n"
        "\n"
        "def helper():\n    assert True\n"
        "\n"
        "# def test_commented_out():\n"
        "#     assert True\n"
        "\n"
        'DOC = "def test_in_a_string():\\n    pass"\n'
        "\n"
        "class TestNested:\n"
        "    def test_method(self):\n        assert True\n"
    )
    assert guards.count_test_cases(source) == 3
    # 反证「按行数/grep」会得出什么：`def test_` 的字面出现次数严格大于真用例数
    # （注释与字符串里的那些也被数进去），所以卡面要求「用 AST 数，不用 grep 行数」。
    assert source.count("def test_") > guards.count_test_cases(source)
    assert guards.count_test_cases("def test_broken(:\n") == 0  # 语法错误 ⇒ 0，不抛


def test_path_classifiers_do_not_overmatch() -> None:
    """两个 glob 判定各自的负例：判宽了会误计，判窄了会漏计。"""
    assert guards._is_evidence_py(EVIDENCE) is True
    assert guards._is_evidence_py("docs/06_validation/evidence/EVD-V14-99/notes.md") is False
    assert guards._is_evidence_py("docs/06_validation/evidence/prove.py") is True
    assert guards._is_evidence_py("apps/api/tests/evidence_x.py") is False
    assert guards._is_tests_py(TESTS) is True
    assert guards._is_tests_py("apps/api/tests/proofs/test_provider_shapes.py") is True
    assert guards._is_tests_py("apps/api/tests/conftest.py") is False
    assert guards._is_tests_py("apps/api/tests/helpers/testkit.py") is False
    assert guards._is_tests_py("apps/api/app/tests/test_x.py") is False


def test_parse_name_status_covers_plain_and_rename_rows() -> None:
    out = (
        f"A\t{EVIDENCE}\n"
        f"M\t{TESTS}\n"
        f"D\tdocs/06_validation/evidence/EVD-V2-00/prove_provider_shapes.py\n"
        f"R100\t{EVIDENCE}\tdocs/06_validation/evidence/EVD-V14-99/probe_x.py\n"
        "\n"
    )
    rows = guards.parse_name_status(out)
    assert rows == [
        ("A", EVIDENCE, None),
        ("M", TESTS, None),
        ("D", "docs/06_validation/evidence/EVD-V2-00/prove_provider_shapes.py", None),
        ("R", "docs/06_validation/evidence/EVD-V14-99/probe_x.py", EVIDENCE),
    ]


# ═══════════════════════ C. 接线判据：F-V14-06 的病根是「有裁决、没代码、没人调」


def _makefile_text() -> str:
    return (_ROOT / "Makefile").read_text(encoding="utf-8")


def test_rounds_check_is_registered_in_guards_and_makefile() -> None:
    """子命令必须挂在 `guards.py` 的分发表上，且 Makefile 有对应目标。

    写成用例的理由：F-V14-06 的事实就是「D-14/D-V4-03 在 scripts/、Makefile、.github/
    里都找不到执行代码」。只加函数不接线，等于把同一个失真再生产一遍。
    """
    assert "rounds-check" in guards.GUARDS, "rounds-check 未进入子命令分发表"
    assert guards.rounds_check in guards.GUARDS.values()
    mk = _makefile_text()
    assert "rounds-check" in mk, "Makefile 缺 rounds-check 目标"
    assert guards.evidence_check in guards.GUARDS.values()


def test_guard_aggregate_target_includes_every_subcommand() -> None:
    """`make guard` 必须覆盖全部门——一个不点的门等于没有门。

    本仓的复合目标写法是「前置目标 + `@:`」（同 `test:`/`lint:`），所以判据取
    `guard:` 那一行的**前置列表**，不是 recipe 体。
    """
    mk = _makefile_text()
    line = next((ln for ln in mk.splitlines() if ln.startswith("guard:")), None)
    assert line is not None, "Makefile 没有聚合目标 `guard:`（04 §8 的完成定义引用了它）"
    prereq = line.split(":", 1)[1].split("##")[0].split()
    for name in guards.GUARDS:
        assert name in prereq, f"`make guard` 的前置未覆盖 {name}（实读前置={prereq}）"
    assert sorted(prereq) == sorted(guards.GUARDS), f"前置列表与子命令表不一致：{prereq}"


def test_makefile_has_no_undefined_variable_and_the_check_itself_has_polarity() -> None:
    """`$(VAR)` 未定义会展开成空串 ⇒ recipe 退化成"把子命令名当可执行文件跑"。

    现读到实证：`GUARDS` 在本仓从未定义过，`make guard-ports` 实测 `Error 2`
    （旧 Makefile 用 `make -f` 复跑为证），而 `forwarded()` 只看 recipe 里有没有
    `$(GUARDS)` 字样 ⇒ "已转调实体脚本"这句声明自己也是空头的。
    本用例同时喂正反两侧，防止这条新判据写成永远绿。
    """
    cep_path = _ROOT / "scripts" / "check_entry_parity.py"
    cep_spec = importlib.util.spec_from_file_location("cep_under_test", cep_path)
    assert cep_spec is not None and cep_spec.loader is not None
    cep = importlib.util.module_from_spec(cep_spec)
    cep_spec.loader.exec_module(cep)

    assert cep.undefined_variables(_makefile_text()) == [], "现行 Makefile 里出现了未定义变量"
    # 反证 1：未定义的守卫变量必须被抓出（这正是 HEAD 上的实际状态）
    broken = "GUARDS_X ?= python scripts/guards.py\n\nfoo:\n\t@$(GUARDS) foo\n"
    assert cep.undefined_variables(broken) == ["GUARDS"], broken
    # 反证 2：定义了就不再报
    fixed = "GUARDS_X := python scripts/guards.py\nGUARDS := python scripts/guards.py\n\nfoo:\n\t@$(GUARDS) foo\n"
    assert cep.undefined_variables(fixed) == [], fixed
    # 反证 3：调用方变量只在赋值位出现才豁免；放进命令位一样报
    assert cep.undefined_variables('x:\n\t@BOTHOT_MSG="$(MSG)" run\n') == []
    assert cep.undefined_variables("run:\n\t@$(MSG)\n") == ["MSG"]
    # 反证 4（评审实测）：make 的单字符变量形式 `$X` 也是引用，只看 `$(...)` 会整类漏检
    assert cep.undefined_variables("x:\n\t@echo $F\n") == ["F"], "裸 $F 必须被看见"
    assert cep.undefined_variables("F := makefile\tx:\n\t@echo $F\n") == []
    # `$$(...)` 是转义给 shell 的，不该算 make 变量引用
    assert cep.undefined_variables("x:\n\t@echo $$(shell date)\n") == []


def test_entry_parity_holds_after_the_new_make_targets() -> None:
    """新增 Makefile 目标必须同时在 `entry.py` 的任务表里注册。

    `scripts/check_entry_parity.py` 的判据是「Makefile 目标名 ⊆ entry.BY_NAME」，
    它的存在理由和这两道闸一模一样：转调是名字对名字的绑定，漏一侧不会有任何一侧报错。
    """
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(_ROOT / "scripts" / "check_entry_parity.py")],
        cwd=str(_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "rounds-check" in (
        (_ROOT / "scripts" / "entry.py").read_text(encoding="utf-8")
    ), "rounds-check 未在 entry.py 注册"


def _first_call_index(fn: ast.FunctionDef, name: str) -> int | None:
    """函数体里第一条「调用了 name()」的顶层语句下标（按子树找，不绑语法形状）。

    写成 AST 语义而非 `if coupling_check(...):` 的形状匹配：S00P 把前置门改成
    「两道门各自跑完再汇总」之后，调用还在、顺序还在，只是换了写法——
    绑形状的断言会把**改进**读成**破坏**，那和绑形状的判据一样脆弱。
    """
    for i, node in enumerate(fn.body):
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and getattr(sub.func, "id", "") == name:
                return i
    return None


def _first_proofs_loop_index(fn: ast.FunctionDef) -> int:
    for i, node in enumerate(fn.body):
        for sub in ast.walk(node):
            if isinstance(sub, ast.For) and any(
                    isinstance(n, ast.Name) and n.id == "EVIDENCE_PROOFS" for n in ast.walk(sub.iter)):
                return i
    raise AssertionError("evidence_check 里找不到 EVIDENCE_PROOFS 复跑循环")


def test_evidence_check_calls_the_coupling_gate_before_the_scripts() -> None:
    """耦合门必须在复跑脚本**之前**被调用：脚本一红就 return，之后的判据永远跑不到。"""
    tree = ast.parse(_GUARDS_PATH.read_text(encoding="utf-8"), filename=str(_GUARDS_PATH))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "evidence_check")
    coupling = _first_call_index(fn, "coupling_check")
    assert coupling is not None, "evidence_check 里没有 coupling_check 判据"
    proofs = _first_proofs_loop_index(fn)
    assert coupling < proofs, "耦合门排在脚本复跑之后 ⇒ 脚本一红它就永远不跑"
    returns = [i for i, node in enumerate(fn.body) if isinstance(node, ast.Return)]
    assert coupling < min(returns, default=len(fn.body)), "耦合门之前就有 return ⇒ 它永远不会被调用"


def test_coupling_check_is_fail_closed_on_unresolvable_base() -> None:
    assert guards.coupling_check("no-such-ref-8f3a1c") == 1


@pytest.mark.parametrize("token", ["D-14", "D-V4-03"])
def test_signed_rulings_are_now_named_in_the_gate_sources(token: str) -> None:
    """裁决编号要出现在门的源码里，否则「这条门实现哪条裁决」不可考证。

    F-V14-06 的复算方式是 `git grep -n "D-14" scripts/` 得 0 命中；本用例把同一个
    grep 变成常驻判据——将来谁把注释删了，门还在但可追溯性断了，也要红。
    """
    corpus = _GUARDS_PATH.read_text(encoding="utf-8") + _makefile_text() + (
        Path(__file__).read_text(encoding="utf-8")
    )
    assert token in corpus, f"{token} 未在门的可读文本中出现"


# ═══════════════════════ D. 端到端：在一次性真 git 仓库里把两条红路跑出来
#
# 为什么不能只留合成入参：`rounds_check` / `coupling_check` 的真实风险全在 git 取值口径
# （base 解析、pathspec、未跟踪支、log 范围、短路顺序）。纯函数用例证明不了这些。
# 一次性仓库放在 tmp_path 里，与主仓的 HEAD/工作区彻底无关 ⇒ 不会"今天绿、明天红"。


def _git_in(tmp: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.name=Gate Test", "-c", "user.email=gate@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        cwd=str(tmp), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, f"git {' '.join(args)} 失败：{proc.stderr}"
    return proc.stdout.strip()


def _scaffold(tmp: Path) -> Path:
    """造一个最小仓库：scripts/guards.py 用**现行实现**，基线含 1 条用例。"""
    repo = tmp / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "docs" / "06_validation" / "evidence" / "EVD-X").mkdir(parents=True)
    (repo / "apps" / "api" / "tests").mkdir(parents=True)
    (repo / "scripts" / "guards.py").write_text(_GUARDS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    (repo / "apps" / "api" / "tests" / "test_seed.py").write_text(
        "def test_seed():\n    assert True\n", encoding="utf-8"
    )
    (repo / "notes.txt").write_text("base\n", encoding="utf-8")
    _git_in(repo, "init", "-q", "-b", "main")
    _git_in(repo, "add", "-A")
    _git_in(repo, "commit", "-q", "-m", "chore: 基线（含 1 条用例）")
    return repo


def _commit(repo: Path, msg: str) -> str:
    notes = repo / "notes.txt"
    notes.write_text(notes.read_text(encoding="utf-8") + msg + "\n", encoding="utf-8")
    _git_in(repo, "add", "-A")
    _git_in(repo, "commit", "-q", "-m", msg)
    return _git_in(repo, "rev-parse", "HEAD")


def _run(repo: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "scripts/guards.py", *args],
        cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, proc.stdout


def test_end_to_end_rounds_gate_fires_on_the_third_round(tmp_path: Path) -> None:
    repo = _scaffold(tmp_path)
    base = _git_in(repo, "rev-parse", "HEAD")  # 基线 = 脚手架那次提交，不是第一条返工
    _commit(repo, "fix(STEP-77 S77.1): 返工——第一次")
    assert _run(repo, "rounds-check", "--base", base)[0] == 0, "1 轮必须放行（D-14 的上界是 ≤2）"
    _commit(repo, "fix(STEP-77 S77.1): 返工——第二次")
    assert _run(repo, "rounds-check", "--base", base)[0] == 0, "2 轮必须放行"
    _commit(repo, "fix(STEP-77 S77.1): 返工——第三次")
    rc, out = _run(repo, "rounds-check", "--base", base)
    assert rc == 1, "第 3 轮必须熔断"
    assert "STEP-77" in out and "3 次" in out, f"必须点名是哪张卡：{out}"


def test_end_to_end_rounds_gate_empty_range_is_third_state(tmp_path: Path) -> None:
    """推送之后 `origin/main..HEAD` 必然为空 ⇒ 只能给第三态，给 0 就是伪装成通过。"""
    repo = _scaffold(tmp_path)
    assert _run(repo, "rounds-check", "--base", "HEAD")[0] == 3
    assert _run(repo, "rounds-check", "--base", "no-such-ref")[0] == 1


def test_end_to_end_coupling_gate_blocks_orphan_evidence_and_releases_it(tmp_path: Path) -> None:
    repo = _scaffold(tmp_path)
    base = _git_in(repo, "rev-parse", "HEAD")
    (repo / "docs" / "06_validation" / "evidence" / "EVD-X" / "prove_a.py").write_text(
        "print(1)\n", encoding="utf-8"
    )
    rc, out = _run(repo, "evidence-check", "--base", base)
    assert rc == 1, "未跟踪的新证据脚本 + 零新用例 ⇒ 必须拦"
    assert "证据脚本净增 1" in out and "用例净增 0" in out, out
    # 顺序判据：耦合门在脚本复跑**之前**，所以这条批次里连"证据脚本不存在"都不该出现
    assert "证据脚本不存在" not in out and "── " not in out, f"耦合门没有短路，或被排在复跑之后：{out}"

    (repo / "apps" / "api" / "tests" / "test_coupled.py").write_text(
        "def test_coupled():\n    assert True\n", encoding="utf-8"
    )
    rc, out = _run(repo, "evidence-check", "--base", base)
    assert "证据脚本净增 1，用例净增 1" in out, out
    assert "❌ 加了证据脚本却没加可跑用例" not in out
    assert "证据脚本不存在" in out or "── " in out, "放行后必须继续走脚本复跑（耦合门不是终态门）"


# ═══════════════════════ E. 主仓真实状态上的交叉核对（口径第二遍）


def _git_out(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout


def test_coupling_git_side_equals_an_independent_recount() -> None:
    """门的 git 侧取值必须与一次独立重数**相等**（不是"看起来合理"）。

    为什么要第二遍：本会话已有两次「探针自己骗自己」（substring 相关性、被嵌套括号打败的
    正则）。只测纯函数的话，`coupling_check` 里 base、pathspec、未跟踪支这三处口径错了也不会红，
    而那三处正是"门在真实批次上是否真看得见东西"的全部风险所在。
    """
    base = "HEAD"
    tracked = _git_out("diff", "--name-status", base, "--", guards.EVIDENCE_ROOT, guards.TESTS_ROOT)
    untracked = _git_out(
        "ls-files", "--others", "--exclude-standard", "--", guards.EVIDENCE_ROOT, guards.TESTS_ROOT
    ).splitlines()
    rows = guards.parse_name_status(tracked) + [("U", p, None) for p in untracked if p.strip()]

    def read_head(rel: str) -> str:
        path = _ROOT / rel
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""

    def read_base(rel: str) -> str:
        probe = subprocess.run(["git", "cat-file", "-e", f"{base}:{rel}"], cwd=str(_ROOT))
        return _git_out("show", f"{base}:{rel}") if probe.returncode == 0 else ""

    gate = guards.coupling_counts(rows, read_head, read_base)

    base_evidence = {
        p for p in _git_out("ls-tree", "-r", "--name-only", base, "--", guards.EVIDENCE_ROOT).splitlines()
        if p.endswith(".py")
    }
    worktree_evidence = {
        p.as_posix().replace("\\", "/")
        for p in (_ROOT / guards.EVIDENCE_ROOT).rglob("*.py")
        if ".git" not in p.parts
    }
    manual_added = len(worktree_evidence - base_evidence)
    manual_removed = len(base_evidence - worktree_evidence)
    assert gate["evidence_added"] == manual_added - manual_removed, (
        f"门={gate['evidence_added']} 独立重数={manual_added}−{manual_removed}"
        f"（门侧多出的行={[r for r in rows if guards._is_evidence_py(r[1])]}"
        f"，重数侧新增={sorted(worktree_evidence - base_evidence)}，"
        f"重数侧删除={sorted(base_evidence - worktree_evidence)}）"
    )


# ═════════════════ F. STEP-27：GUARD_BASE（S27.1）、CI 接线（S27.2）、轮次门扩判据（S27.5）


def test_default_base_reads_the_guard_base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """S27.1：范围门（耦合/敏感形/轮次）的默认基线统一读 `GUARD_BASE`。

    为什么要有它：CI 里 `origin/main` 在 push 事件上就是"刚推完的 HEAD"，范围恒空 ⇒ 门永远
    第三态；而门必须判"这一次推送改了什么"，基线只能由事件给出（`github.event.before`）。
    """
    monkeypatch.setenv("GUARD_BASE", "deadbeef")
    assert guards.default_base() == "deadbeef"
    monkeypatch.delenv("GUARD_BASE")
    assert guards.default_base() == guards.DEFAULT_BASE == "origin/main"


def test_main_uses_the_env_base_for_scope_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    """未传 `--base` 时，`main()` 必须把环境基线交给门——只加一个函数不算接线。"""
    seen: list[str] = []
    monkeypatch.setitem(guards.GUARDS, "rounds-check", lambda base: seen.append(base) or 0)
    monkeypatch.setenv("GUARD_BASE", "cafe1234")
    assert guards.main(["rounds-check"]) == 0
    assert seen == ["cafe1234"]


def test_explicit_base_still_beats_the_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """显式 `--base` 优先于环境：本机复跑历史批次时不能反过来被 CI 变量劫持。"""
    seen: list[str] = []
    monkeypatch.setitem(guards.GUARDS, "rounds-check", lambda base: seen.append(base) or 0)
    monkeypatch.setenv("GUARD_BASE", "cafe1234")
    assert guards.main(["rounds-check", "--base", "beef5678"]) == 0
    assert seen == ["beef5678"]


def test_a_bad_base_from_the_env_is_red_and_named(monkeypatch: pytest.MonkeyPatch) -> None:
    """坏基线 ⇒ rc=1 并点名。静默退回 origin/main 会让"基线传错了"看起来像"检查过了"。"""
    monkeypatch.setenv("GUARD_BASE", "no-such-ref-27")
    assert guards.main(["rounds-check"]) == 1


def test_non_scope_gates_still_reject_a_base_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    """极性对照：`--base` 只对两道范围门有效，其余门被传了必须报错（口径不能被这次改动放宽）。"""
    assert guards.main(["guard-ports", "--base", "HEAD"]) == 1


def _ci_backend_block() -> str:
    text = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "\n  backend:" in text and "\n  frontend:" in text, "ci.yml 的 job 结构变了，本用例需重读"
    return text.split("\n  backend:", 1)[1].split("\n  frontend:", 1)[0]


def test_ci_backend_job_runs_both_scope_gates_with_the_event_base() -> None:
    """S27.2：两道范围门必须在 backend job 里、用事件给出的基线、以 rc 判失败。

    这条用例是"门进了 CI"的唯一机检：只写进 Makefile 的门在 CI 里等于不存在
    （本仓先例：`check_docs_consistency.py` 早就在仓库里，却长期零调用点）。
    """
    block = _ci_backend_block()
    assert "rounds-check" in block, "backend job 没有跑轮次门"
    assert "evidence-check" in block, "backend job 没有跑证据门"
    assert "GUARD_BASE" in block, "范围门没有拿到事件基线 ⇒ 在 CI 上范围恒空（永远第三态）"
    assert "github.event.before" in block, "基线没有接 push 事件的 before"
    assert "pull_request.base.sha" in block or "pull_request.base.sha" in block, "PR 没有用 base sha"
    assert "0000000000000000000000000000000000000000" in block, "首推（before 全 0）没有兜底"
    assert "fetch-depth: 0" in block, (
        "checkout 仍是默认 depth=1 ⇒ before/base 的提交对象不在本地，门会 fail-closed 判红"
    )
    assert "set -e" in block or "set -euo pipefail" in block, "两条门之间没有短路保护：前一条红后一条照样跑"
    assert "GUARD_GITLEAKS_COVERED" in block, (
        "backend job 没装 gitleaks，evidence-check 会把「工具缺席」判成第三态 ⇒ CI 恒红；"
        "必须显式记「由 Security 工作流覆盖」"
    )


def test_rounds_gate_counts_chinese_numerals(monkeypatch: pytest.MonkeyPatch) -> None:
    """S27.5 / D-V12-02：本仓真实存在「第二轮」「第十一轮」写法，只认阿拉伯数字会漏计。"""
    for cn, n in {"三": 3, "七": 7, "十": 10, "十一": 11, "二十": 20}.items():
        assert guards._round_numbers(f"fix(STEP-88): 第{cn}轮返工") == [n], cn
    assert guards.rounds_violations(["fix(STEP-88): 第三轮返工"])[0]["explicit_rounds"] == [3]
    # 中文数字必须仍受词界约束：`第一轮` 合法，`统一轮` 不是轮次
    assert guards._round_numbers("fix(STEP-88): 统一轮次口径") == []


def test_rounds_gate_infers_the_card_from_an_l3_id() -> None:
    """S27.5 / D-V12-02：主题只写 L3 号（`S1.3.2`）时按第一段反推卡号。

    改前这是已登记的真实盲区：`docs(裁决台账): …S1.3.2 的第 7 轮熔断…` 含第 7 轮却零归属。
    """
    violations = guards.rounds_violations(["docs(裁决台账): S1.3.2 的第 7 轮熔断"])
    assert [v["step"] for v in violations] == ["1"]
    assert guards._STEP_ID_RE.findall("fix(S27.3): 第 3 轮") == []
    assert guards._primary_card("fix(S27.3): 第 3 轮") == "27"


def test_rounds_gate_counts_only_the_primary_card_of_a_cross_card_subject() -> None:
    """S27.5 / D-V12-02：一条主题跨卡提及只计**主卡**（首个 STEP id），不再连坐。

    改前口径是"提到就都算"，一条 `STEP-20/22/23 第 3 轮` 会让三张卡同时熔断——
    被连坐的卡并没有第 3 轮，熔断停的是不该停的活。
    """
    subject = "fix(STEP-20 返工轮): 第 3 轮，顺带 STEP-23 与 STEP-22 的文本"
    assert [v["step"] for v in guards.rounds_violations([subject])] == ["20"]


def test_primary_card_prefers_step_prefix_over_l3_id() -> None:
    """两种写法同时出现时以 `STEP-` 为准：`STEP-27 S27.3` 的主卡是 27，不是 27（同号）也一样。"""
    assert guards._primary_card("fix(STEP-24/25): S25.1 第 2 轮") == "24"
    assert guards._primary_card("chore: 没有卡号") == ""
