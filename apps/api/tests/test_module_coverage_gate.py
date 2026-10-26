"""STEP-06 S6.3.1.1 的常驻反证：模块覆盖率门**真的会拦**，且阈值表没有被悄悄下调。

为什么必须有一条反证：`--cov-fail-under` 那种"总分够了就算过"的门不会自己变红，而按模块判的门
多了两个新的静默失效面——
① coverage.json 读不到（CI 里那一步没跑、路径写错）；
② 阈值表里的某个模块在 coverage.json 里命中 0 个文件（改名/删文件）。
这两种情况的共同点是"一条都没判"，而在 shell 里"一条都没判"和"全判过了"退出码可以一样。
所以每一面都要有自己的输入：全达标 / 单模块不达标 / 全局掉线 / 阈值调高 / 阈值调低被拒 /
缺输入 / 形状不符 / 模块失配，再加一条静态闸盯住阈值表本身。

判据跑的是仓库里那份脚本（`importlib` 按路径加载 `scripts/check_module_coverage.py`），
不是本文件抄一份逻辑——抄的那份红了不代表 CI 里那段会红。
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

# apps/api/tests/<本文件> ⇒ parents = [tests, api, apps, 仓库根]
REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "check_module_coverage.py"

#: 卡面 §1 的模块线，逐字对照（表被改小时这条先红，逼改的人来改卡）。
CARD_THRESHOLDS = {
    "app/services/article_identity.py": 100.0,
    "app/services/manifest.py": 85.0,
    "app/services/kb.py": 85.0,
    "app/services/subscription.py": 85.0,
    "app/providers/article_sources/dajiala.py": 80.0,
    "app/providers/article_sources/justoneapi.py": 80.0,
    "app/providers/article_sources/tikhub.py": 80.0,
    "app/providers/article_sources/wellbyte.py": 80.0,
}
CARD_GLOBAL_MIN = 79.0


def _gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bothot_module_coverage", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _doc(*, drop: str = "", offset: float = 0.0) -> dict[str, object]:
    """一份形状合法的 coverage.json：每个模块正好落在自己的线上，再整体加 `offset`。

    刻意按**各自阈值**造数而不是造一个统一值：`article_identity` 的线是 100，
    给它 85% 会让"这份输入本该绿"的基准用例自己先红（我第一版就是这么错的）。
    `drop` 用来模拟「那个文件不见了」。
    """
    files = {
        key: {
            "summary": {
                "percent_covered": line + offset,
                "num_statements": 200,
                "missing_lines": int(round(200 * (100 - (line + offset)) / 100)),
            }
        }
        for key, line in CARD_THRESHOLDS.items()
        if key != drop
    }
    return {"files": files, "totals": {"percent_covered": 90.0, "num_statements": 1000, "missing_lines": 100}}


def _json(tmp_path: Path, doc: dict[str, object]) -> str:
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return str(path)


def test_threshold_table_matches_the_card() -> None:
    """阈值表必须仍是卡面那组数：悄悄把 100 改 95、把 85 改 70 就是"把红灯改成绿灯"。"""
    gate = _gate()
    assert gate.THRESHOLDS == CARD_THRESHOLDS, gate.THRESHOLDS
    assert gate.GLOBAL_MIN == CARD_GLOBAL_MIN


def test_gate_passes_when_every_module_meets_its_line(tmp_path: Path) -> None:
    rc = _gate().main(["--json", _json(tmp_path, _doc())])
    assert rc == 0, rc


def test_gate_fails_on_one_module_below_its_own_line(tmp_path: Path) -> None:
    """85 那组里掉一条就红——而且是 rc=1（判红），不是 rc=2（没判）。"""
    doc = _doc()
    files = doc["files"]
    assert isinstance(files, dict)
    files["app/services/kb.py"] = {"summary": {"percent_covered": 84.99, "num_statements": 200, "missing_lines": 30}}
    rc = _gate().main(["--json", _json(tmp_path, doc)])
    assert rc == 1, rc


def test_gate_fails_when_global_drops_below_its_line(tmp_path: Path) -> None:
    """模块全绿、全局掉线也必须红：两道门是 AND，不是二选一。"""
    doc = _doc()
    doc["totals"] = {"percent_covered": 78.9, "num_statements": 1000, "missing_lines": 211}
    rc = _gate().main(["--json", _json(tmp_path, doc)])
    assert rc == 1, rc


def test_raising_a_threshold_turns_green_into_red(tmp_path: Path) -> None:
    """S6.3.1.1 的字面要求：人为调高阈值 ⇒ rc≠0。

    同一份输入、同一个脚本，只多一个 `--set`。这条证的是"绿是判出来的，不是恒绿的"。
    """
    gate = _gate()
    path = _json(tmp_path, _doc())
    assert gate.main(["--json", path]) == 0, "各模块恰好落线时本该绿"
    assert gate.main(["--json", path, "--set", "app/services/kb.py=85.01"]) == 1


def test_lowering_a_threshold_via_the_counterproof_channel_is_refused(tmp_path: Path) -> None:
    """`--set` 只许调高（独立验证者指出：允许写小就是给门禁装了个「跑不过就关掉它」的开关）。

    这条用例的存在理由：`--set article_identity=0` 原本会打印「达标」并 rc=0 —— 一个
    永远不红的降级出口，比没有门更糟，因为它长得像门。
    """
    gate = _gate()
    path = _json(tmp_path, _doc())
    assert gate.main(["--json", path, "--set", "app/services/kb.py=80"]) == 2
    assert gate.main(["--json", path, "--set", "app/services/article_identity.py=0"]) == 2
    assert gate.main(["--json", path, "--set", "app/services/kb.py=abc"]) == 2
    assert gate.main(["--json", path, "--set", "app/services/nosuch.py=99"]) == 2


def test_missing_input_is_not_pass(tmp_path: Path) -> None:
    """coverage.json 不存在 ⇒ rc=2 且必须与 0/1 区分开（"没跑"不是"过了"）。"""
    rc = _gate().main(["--json", str(tmp_path / "nope.json")])
    assert rc == 2, rc


def test_unparseable_input_is_not_pass(tmp_path: Path) -> None:
    path = tmp_path / "coverage.json"
    path.write_text("{not json", encoding="utf-8")
    assert _gate().main(["--json", str(path)]) == 2


def test_wrong_shape_is_not_pass(tmp_path: Path) -> None:
    """形状不符（缺 totals）⇒ rc=2：宁可不判也不把 0% 当成读数。"""
    assert _gate().main(["--json", _json(tmp_path, {"files": {}})]) == 2


def test_threshold_key_matching_no_file_is_not_pass(tmp_path: Path) -> None:
    """模块改名/文件消失后，那条阈值就失去了作用面——必须点名失配，而不是跳过它继续绿。"""
    rc = _gate().main(["--json", _json(tmp_path, _doc(drop="app/services/kb.py"))])
    assert rc == 2, rc


def test_ci_wires_the_gate_after_the_pytest_step() -> None:
    """接线本身也要有常驻判据：ci.yml 里没有 coverage-gate 那一步时，本卡就白做。

    这条不是形式检查——门禁脚本没接进 CI 与"接了但永远不满足"在读数上看不出区别。
    """
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "check_module_coverage.py" in text, "ci.yml 未接模块覆盖率门"
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "coverage-gate" in makefile, "Makefile 缺 coverage-gate 目标"
    entry = (REPO_ROOT / "scripts" / "entry.py").read_text(encoding="utf-8")
    assert "coverage-gate" in entry, "entry.py 未注册 coverage-gate（check_entry_parity 会红）"


# ── STEP-55 S55.2（P-125）：`_match` 的键形归一 ─────────────────────────
#
# 上面那批用例喂的都是**正斜杠**键（CI 的形状），所以它们对"@win 的反斜杠相对键"完全失明：
# 旧 `_match` 把 needle 拼成 `/app/services/kb.py` 再要求 `endswith`，而本机 coverage.json
# 的键是 `app\services\kb.py`（归一后 `app/services/kb.py`，没有前导斜杠）⇒ 8 个阈值键
# 全判"命中 0 个"、门在 Windows 上不可复算（读数在 `EVD-V21-55/s55_2_pre_fix_rc2.txt`）。
# 下面四条盯的就是这件事本身，而不是"改完能跑"：一条防漏判、一条防过松、一条防多命中被吞。

_WIN_KEY = "app\\services\\kb.py"
_LINUX_KEY = "app/services/kb.py"


def test_windows_backslash_relative_key_hits_exactly_one() -> None:
    """本机形状：反斜杠相对键必须命中恰一个（改前这条是 0 个 ⇒ 门 NOT-PASS）。"""
    files = {_WIN_KEY: {}, "app\\services\\manifest.py": {}, "app\\models\\entities.py": {}}
    hits = _gate()._match("app/services/kb.py", files)
    assert hits == [_WIN_KEY], hits


def test_linux_forward_slash_key_still_hits_exactly_one() -> None:
    """CI 形状不能被这次归一弄坏：正斜杠相对键、以及带运行目录前缀的深度路径都各命中一个。"""
    gate = _gate()
    direct = gate._match(_LINUX_KEY, {_LINUX_KEY: {}, "app/services/manifest.py": {}})
    assert direct == [_LINUX_KEY], direct
    deep = gate._match(_LINUX_KEY, {"/home/runner/work/BotHot/BotHot/apps/api/app/services/kb.py": {}})
    assert deep == ["/home/runner/work/BotHot/BotHot/apps/api/app/services/kb.py"], deep
    dotted = gate._match(_LINUX_KEY, {"./app/services/kb.py": {}})
    assert dotted == ["./app/services/kb.py"], dotted


def test_multiple_hits_are_returned_so_the_gate_reports_them() -> None:
    """命中多于一个必须原样返回（调用方据此判 NOT-PASS），不许取第一个替它受审。"""
    files = {"app/services/kb.py": {}, "other/app/services/kb.py": {}}
    assert len(_gate()._match(_LINUX_KEY, files)) == 2


def test_normalization_is_not_a_substring_match() -> None:
    """归一只换形状，不许放松判据：文件名前缀相同、目录名尾部相同的都必须 0 命中。

    这条是防"把门修成永远绿"的——如果归一顺手做成 `in`/前缀匹配，下面两种都会误命中，
    于是模块改名或被人塞一个同名文件进来都不会红，而读数上看不出区别。
    """
    gate = _gate()
    assert gate._match(_LINUX_KEY, {"app/services/kb_more.py": {}}) == []
    assert gate._match(_LINUX_KEY, {"app/services/xkb.py": {}}) == []
    assert gate._match(_LINUX_KEY, {"app/providers/kb.py": {}}) == []


def test_gate_survives_a_non_utf8_console(tmp_path: Path) -> None:
    """控制台语言不许决定门的结果：达标末行是 `✅`，在 cp936/gbk 流上会抛 UnicodeEncodeError。

    P-125 的第二条失配因与 `_match` 无关——本机把键形修好之后，附录 A 那条命令**照原样**跑仍然
    rc=1（八个模块逐行打印"达标"，然后在末行崩，读数在 `EVD-V21-55/s55_2_cp936_before_after.md`）。
    这里不改本机 locale，而是用 `PYTHONIOENCODING=gbk` 把编码钉成和它一样：gbk 是 Python 自带的
    码表，Linux CI 上也能造出同一个流 ⇒ 这条用例在两个平台上判的是同一件事。
    """
    path = _json(tmp_path, _doc())
    env = {**os.environ, "PYTHONIOENCODING": "gbk"}
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", path],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        check=False,
    )
    out = run.stdout.decode("utf-8", errors="replace")
    assert run.returncode == 0, f"rc={run.returncode}\n{out}\n{run.stderr.decode('utf-8', 'replace')}"
    # 只看 rc 会被"其实一条都没判"骗过去：必须真的打印出达标末行（它正是原先崩掉的那一行）
    assert "全部模块与全局达标" in out, out
