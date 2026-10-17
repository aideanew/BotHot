"""STEP-00H S00H.2.1 的常驻反证：CI-Windows 的 skip 门禁**有判定力**，不是恒绿。

为什么这条用例必须存在（不是"锦上添花"）：那段门禁脚本只在 `windows-latest` 的 runner 上执行，
本机 `@win` 跑不到 CI 上下文 ⇒ 它写错就是恒绿或恒红，而恒绿的那一种长得跟成功一模一样。
本卡刚把阈值从 320 收到测量值 441，**收紧一个数**这件事本身如果没有反证，
就只是一次"把红灯改成绿灯"的动作。判据全部跑从 `ci-windows.yml` 里**抽出来的同一段脚本**，
所以这里证的不是"我以为脚本会这样"，而是仓库里那份脚本。

四面 + 一条静态闸：阈值恰好=声明值时放行、+1 条即红（证明没留余量）、未知原因族即红且点名、
用例失败即红（即使 skip 全干净）、族表 token 必须仍能在测试源码里找到原文。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# apps/api/tests/<本文件> ⇒ parents = [tests, api, apps, 仓库根]
REPO_ROOT = Path(__file__).resolve().parents[3]
WF_PATH = REPO_ROOT / ".github" / "workflows" / "ci-windows.yml"
TESTS_DIR = Path(__file__).resolve().parent
_BLOCK_INDENT = " " * 10

# 与 ci-windows.yml 里 FAMILIES 同源的原因原文（改任何一条都会让静态那条用例先红）
_FAMILY_TOKENS = (
    "AIDEANBOT_TEST_PG_DSN 未设置",
    "PG 不可达",
    "PG:5433 不可达",
    "Redis 不可达",
    "LangBot :5300 不可达",
    "宿主未设这 6 个待清代理变量",
)


def _gate_script() -> str:
    """从工作流里抽出 heredoc 内的门禁脚本，去掉 YAML 块缩进并**先编译**。

    `compile()` 不是走过场：这段脚本的缩进同时受 YAML 块字面量和 Python 语法约束，
    改 YAML 时把某行少缩一格，语法就断——而那种断只在 runner 上才看得见。
    """
    raw = WF_PATH.read_text(encoding="utf-8")
    seg = raw[raw.index("- name: Windows skip 门禁") :]
    marker = "python - <<'PY'\n"
    head = seg.index(marker) + len(marker)
    body = seg[head : seg.index("\n" + _BLOCK_INDENT + "PY")]
    lines = [ln[len(_BLOCK_INDENT) :] if ln.startswith(_BLOCK_INDENT) else ln for ln in body.splitlines()]
    script = "\n".join(lines) + "\n"
    compile(script, "ci-windows.yml::Windows skip 门禁", "exec")
    return script


def _declared_baseline() -> int:
    raw = WF_PATH.read_text(encoding="utf-8")
    m = re.search(r'SKIP_BASELINE_WIN:\s*"(\d+)"', raw)
    assert m, "ci-windows.yml 里的 SKIP_BASELINE_WIN 不见了或写法变了（门禁按这个名字读 env）"
    return int(m.group(1))


def _family_skips(count: int) -> list[tuple[str, str]]:
    """造 `count` 条**全部落在已知族**的 skip（原因原文循环取用，族表顺序不参与判定）。"""
    msgs = [
        (f"{tok}：连库用例需要独立测试库" if tok.startswith("AIDEANBOT") else f"{tok}，恢复后复跑本用例")
        for tok in _FAMILY_TOKENS
    ]
    return [(f"tests.gen_case_{i}", msgs[i % len(msgs)]) for i in range(count)]


def _junit(skips: list[tuple[str, str]], *, failures: int = 0) -> str:
    """合成最小 junit：门禁只读 `testsuite@failures` 与 `testcase>skipped@message`。"""
    cases = "".join(
        f'<testcase classname="{cls}" name="n{i}" time="0.0"><skipped message="{msg}"/></testcase>'
        for i, (cls, msg) in enumerate(skips)
    )
    cases += "".join(
        f'<testcase classname="tests.bad" name="f{i}" time="0.0"><failure message="boom"/></testcase>'
        for i in range(failures)
    )
    total = len(skips) + failures
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<testsuite name="pytest" tests="{total}" failures="{failures}" errors="0"'
        f' skipped="{len(skips)}">{cases}</testsuite>'
    )


def _gate(tmp_path: Path, xml: str, baseline: int) -> subprocess.CompletedProcess[str]:
    (tmp_path / "pytest-report-win.xml").write_text(xml, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-c", _gate_script()],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "SKIP_BASELINE_WIN": str(baseline), "PYTHONUTF8": "1"},
    )


def test_gate_passes_at_exactly_the_declared_baseline(tmp_path: Path) -> None:
    baseline = _declared_baseline()
    assert baseline > 0, "阈值写成 0 会让整道门恒红——那也是失效"
    proc = _gate(tmp_path, _junit(_family_skips(baseline)), baseline)
    assert proc.returncode == 0, f"恰好等于声明值却被拒：{proc.stdout}{proc.stderr}"
    assert "✅" in proc.stdout


def test_gate_has_no_slack_one_more_skip_is_red(tmp_path: Path) -> None:
    """阈值 = 测量值 ⇒ 再多一条（哪怕原因合法）也必须红。

    这条盯的是"顺手留点余量"：余量就是「同数换因」那个洞的宽度。一旦有人把它写成 445，
    本卡抬阈值换来的判定力会整体退回去，而那在 CI 上看起来完全正常。
    """
    baseline = _declared_baseline()
    proc = _gate(tmp_path, _junit(_family_skips(baseline + 1)), baseline)
    assert proc.returncode == 1
    assert "超阈值" in proc.stdout


def test_gate_reds_on_a_reason_family_that_is_not_the_environment(tmp_path: Path) -> None:
    """无条件 skip 的形态：原因不属于任何已知环境族 ⇒ 红，且**点名**是哪条。

    只数总数的门抓不到它。这里给的是"总数不变、族未知"的形状——正是数闸的盲区。
    """
    skips = _family_skips(_declared_baseline() - 1) + [("tests.test_sneaky", "该平台暂不支持，先跳过")]
    proc = _gate(tmp_path, _junit(skips), _declared_baseline())
    assert proc.returncode == 1
    assert "未知族" in proc.stdout
    assert "tests.test_sneaky" in proc.stdout, "红了却不点名 ⇒ 下一张卡只能靠猜，等于没给诊断"


def test_gate_reds_on_failures_even_when_skips_are_clean(tmp_path: Path) -> None:
    """平台性断裂（有失败用例）是本 job 的头号判据，不能因为 skip 干净就放行。"""
    proc = _gate(tmp_path, _junit(_family_skips(3), failures=1), 999)
    assert proc.returncode == 1
    assert "失败用例" in proc.stdout


def test_family_tokens_still_exist_verbatim_in_the_test_sources() -> None:
    """族表的每个 token 必须仍能在 `apps/api/tests/**` 里找到**原文**。

    反向盯的是我自己：门禁认的是原因原文，所以 conftest 哪天改写那句提示，Windows 门会当场全红
    （这能被本条提前抓到）；而更坏的情形是有人为了催绿去改**族表 token**——那时也是本条红，
    逼他来现读一遍，而不是让闸门悄悄换掉语义。

    ⚠️ 语料必须**排除本文件**：族表 token 就写在这里，把自己算进语料的话这条用例恒真，
    正是本仓反复踩过的"用自己的实现喂自己的判据"。
    """
    here = Path(__file__).resolve()
    corpus = "\n".join(p.read_text(encoding="utf-8") for p in TESTS_DIR.rglob("*.py") if p.resolve() != here)
    missing = [tok for tok in _FAMILY_TOKENS if tok not in corpus]
    assert missing == [], f"族表里的原因原文在测试源码里找不到：{missing}"


def test_declared_baseline_is_written_as_a_measurement() -> None:
    """阈值必须写成 §7.3 的测量值，且收紧依据就写在 env 旁边。

    这条判不了 CI 上的真值（那是 `@ci` 的读数），它判的是"这个数有没有被当常量抄来抄去"：
    数值对不上、或者注释里"测量值"那句被删掉，都算红。
    """
    raw = WF_PATH.read_text(encoding="utf-8")
    assert re.search(r'SKIP_BASELINE_WIN:\s*"441"', raw), "阈值与 S00H.2.1/§7.3 的测量值不符"
    assert "测量值" in raw, "收紧依据必须写在 env 旁边，否则下一轮没人知道这个数从哪来"
