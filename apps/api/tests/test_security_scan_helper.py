"""STEP-38 用例：扫描器步的重试与「未运行」判定（P-77），以及扫描输入必须来自锁文件（P-55）。

被测实体是 `scripts/security_scan.py`（工作流四步共用的执行体）。为什么把它做成 Python 而不是
留在 YAML 里内联 bash：判据要能在**任何一台机器上**被反证——"两次都没产出报告 ⇒ 红且原因写
'扫描器未运行'"这件事，只有在能被注入的形状上才能钉成常驻用例；留在 bash 里就只能靠推一次
故意弄坏的 main 去验，那种反证有窗口期，而常驻用例没有。

三道判据各自的假绿形状（用例逐条对着钉）：
- 只看 rc：pip-audit / gitleaks 检出漏洞时 rc 非 0，把 rc 当"工具坏"就永久红；反过来只看
  "报告存在"又会被**上一轮留下的残缺报告**骗过去 ⇒ 判据必须是"本轮删过之后重新产出的报告"。
- 0 字节的报告：命令创建文件后崩在半路 ⇒ 存在但换不来结论，与"没有"同权。
- 无限重试：把"这个环境跑不成"伪装成"跑得慢"，最后由 30 分钟 job 超时收场，日志里没有原因。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOTS = [
    up for up in Path(__file__).resolve().parents
    if (up / "scripts" / "security_scan.py").is_file() and (up / ".github").is_dir()
]
assert _ROOTS, "向上找不到同时含 scripts/security_scan.py 与 .github 的仓库根"
_ROOT = _ROOTS[0]

_spec = importlib.util.spec_from_file_location("bothot_security_scan", _ROOT / "scripts" / "security_scan.py")
assert _spec is not None and _spec.loader is not None
scan: Any = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan)

_SECURITY_YML = _ROOT / ".github" / "workflows" / "security.yml"


class _Proc:
    def __init__(self, rc: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


def _runner(writes: list[bool], rcs: list[int], report: Path, payloads: list[str] | None = None):
    """按轮次产出报告（或不产出）的假 runner；同时记下被调用了几次。"""
    calls: list[int] = []

    def run(cmd, cwd=None, capture_output=False, text=False, env=None):  # noqa: ANN001, ANN001
        n = len(calls)
        calls.append(n + 1)
        if writes[n]:
            report.write_text((payloads or ["{}" * 20])[n], encoding="utf-8")
        return _Proc(rcs[n], stderr=f"attempt {n + 1} 的报错原文")

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_first_attempt_success_does_not_retry(tmp_path: Path) -> None:
    report = tmp_path / "r.json"
    runner = _runner([True], [0], report)
    slept: list[float] = []
    out = scan.run_scanner("x", ["cmd"], report, runner=runner, sleep=slept.append)
    assert out["status"] == scan.RAN
    assert len(out["tries"]) == 1 and not slept, "第一轮就跑成了还重试 ⇒ 红的原因会被时间掩盖"


def test_second_attempt_success_retries_exactly_once(tmp_path: Path) -> None:
    report = tmp_path / "r.json"
    runner = _runner([False, True], [2, 0], report, payloads=["", "payload-from-second-try"])
    slept: list[float] = []
    out = scan.run_scanner("x", ["cmd"], report, runner=runner, sleep=slept.append)
    assert out["status"] == scan.RAN
    assert len(out["tries"]) == 2 and slept == [scan.RETRY_DELAY_S], out
    assert out["tries"][0]["report_bytes"] == 0 and out["tries"][1]["report_bytes"] > 0


def test_two_failed_attempts_say_the_scanner_did_not_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = tmp_path / "r.json"
    runner = _runner([False, False], [2, 2], report)
    out = scan.run_scanner("x", ["cmd"], report, runner=runner, sleep=lambda _s: None)
    printed = capsys.readouterr().out
    assert out["status"] == scan.SCANNER_ERROR
    assert out["reason"].startswith("扫描器未运行"), out["reason"]
    assert out["last_rc"] == 2, "最后一轮的 rc 必须还能取回（gitleaks 用它区分检出与工具坏）"
    # 反向的一截：结论既不能写成"有漏洞"也不能写成"没漏洞"
    assert "本维**没有终判**" in printed, printed


def test_vulnerabilities_found_is_not_a_tool_failure(tmp_path: Path) -> None:
    """极性 4：rc 非 0 且报告在 ⇒ ran（"扫描成功且发现问题"），裁决权在末尾汇总门禁。"""
    report = tmp_path / "r.json"
    runner = _runner([True], [1], report, payloads=['{"leak": "x"}' * 3])
    out = scan.run_scanner("gitleaks", ["cmd"], report, runner=runner, sleep=lambda _s: None)
    assert out["status"] == scan.RAN and out["last_rc"] == 1, out


def test_empty_report_counts_as_no_result(tmp_path: Path) -> None:
    """0 字节的报告与"没有"同权：命令创建文件后崩在半路是真实形状。"""
    report = tmp_path / "r.json"
    runner = _runner([True, True], [0, 0], report, payloads=["", ""])
    out = scan.run_scanner("x", ["cmd"], report, runner=runner, sleep=lambda _s: None)
    assert out["status"] == scan.SCANNER_ERROR
    assert all(t["report_bytes"] == 0 for t in out["tries"]), out["tries"]


def test_a_stale_report_from_before_does_not_count(tmp_path: Path) -> None:
    """判据 2 的正身：跑之前磁盘上就有报告（上一批 artifact / 上一次调试留下），
    本轮命令什么也没写 ⇒ 必须判"未运行"。不删旧文件的实现会把它读成"跑成了"。"""
    report = tmp_path / "r.json"
    report.write_text("STALE-FROM-PREVIOUS-RUN" * 10, encoding="utf-8")
    runner = _runner([False, False], [3, 3], report)
    out = scan.run_scanner("x", ["cmd"], report, runner=runner, sleep=lambda _s: None)
    assert out["status"] == scan.SCANNER_ERROR, out
    assert not report.exists(), "helper 应删掉旧报告且本轮没写回 ⇒ 磁盘上不该再有残缺报告"


def test_status_file_round_trip_lets_the_next_step_read_rc(tmp_path: Path) -> None:
    report, status = tmp_path / "r.json", tmp_path / "s.json"
    runner = _runner([True], [1], report, payloads=['{"findings": 1}' * 4])
    scan.run_scanner("gitleaks", ["cmd"], report, runner=runner, sleep=lambda _s: None, status_file=status)
    data = json.loads(status.read_text(encoding="utf-8"))
    assert data["status"] == scan.RAN and data["last_rc"] == 1 and data["name"] == "gitleaks"


def test_cli_reports_no_command_as_scanner_error(tmp_path: Path) -> None:
    status = tmp_path / "s.json"
    rc = scan.main(["--name", "x", "--report", str(tmp_path / "r.json"), "--status-file", str(status)])
    assert rc == 1
    assert json.loads(status.read_text(encoding="utf-8"))["status"] == scan.SCANNER_ERROR


def test_cli_end_to_end_with_a_real_command(tmp_path: Path) -> None:
    """真子进程一发：命令自己写报告 ⇒ helper 退 0；命令什么都不写 ⇒ 退 1。

    只测注入的假 runner 会漏掉一件事——`--` 之后的 argv 到底有没有原样传下去。
    """
    report = tmp_path / "out.json"
    write_cmd = [sys.executable, "-c", "import pathlib; pathlib.Path('out.json').write_text('{}')"]
    rc = scan.main(["--name", "real", "--report", str(report), "--cwd", str(tmp_path), "--"] + write_cmd)
    assert rc == 0 and report.is_file()
    empty_cmd = [sys.executable, "-c", "pass"]
    assert scan.main(["--name", "real", "--report", str(report), "--cwd", str(tmp_path), "--"] + empty_cmd) == 1


# ─── 工作流接线面：门没接进 CI 就等于不存在（F-V14-06 的同形教训）──────────────────

def _yml() -> str:
    return _SECURITY_YML.read_text(encoding="utf-8")


def test_all_four_scanner_steps_go_through_the_helper() -> None:
    yml = _yml()
    assert yml.count("scripts/security_scan.py") == 4, "四道扫描步必须都走同一个执行体"
    for name in ("pip-audit", "pnpm-audit", "trivy", "gitleaks"):
        assert f'--name {name}' in yml, f"{name} 步没接重试执行体"
    assert yml.count('echo "SCANNER_ERROR" > "$verdict"') == 4, "每步仍要先写最坏结果"


def test_scan_input_is_derived_from_the_lock_file() -> None:
    """P-55 / D-V18-12 的机检：Python 侧扫描输入 = `uv.lock` 导出的固定清单。"""
    yml = _yml()
    assert "uv export --frozen --extra dev" in yml, "① 不再从 uv.lock 导出扫描输入"
    assert "-r requirements-from-lock.txt" in yml and "--no-deps" in yml
    assert 'UV_VERSION: "' in yml, "uv 必须与另外三个工具同口径钉版本"
    assert "requirements-from-lock.txt" in yml.split("Upload security reports")[1], "扫描输入没进 artifact，无法复核"
    # 逐行判"旧形状没有回来"：整文件搜会把**解释旧做法的那条注释**也算进去（本文件就写着它），
    # 所以按行剥注释——否则这条断言永远是红的，很快就会被当噪音删掉。
    live = [ln for ln in yml.splitlines() if not ln.strip().startswith("#")]
    assert not any('pip install -e ".[dev]"' in ln for ln in live), "审计当场解析出来的环境那一形状回来了"


def test_thresholds_and_allowlists_are_untouched() -> None:
    """§13 禁止面的常驻守卫：本卡只准改"怎么跑"，不准改"什么算红"。"""
    yml = _yml()
    assert 'PIP_AUDIT_IGNORE_VULNS: ""' in yml, "接受基线（空=零容忍）被动过"
    assert 'HIGH = {"critical", "high"}' in yml, "pnpm 侧阻断线被动过"
    assert 'HIGH = {"CRITICAL", "HIGH"}' in yml, "trivy 侧阻断线被动过"
    assert "(blocking if (sev in HIGH and fixed) else warn)" in yml, "trivy 的『有修复版本才阻断』被动过"
    assert 'verdict.write_text("BLOCK" if blocking else "OK")' in yml
    # 切片必须落在**汇总门禁那一步**上：`汇总门禁` 这四个字在文件里还出现在别处
    # （job 级 env 的"汇总门禁的过渡开关"注释），用短串 split 会切到错误的窗口。
    gate = yml.split("      - name: 汇总门禁")
    assert len(gate) == 2, "汇总门禁步骤标题不唯一或不见了"
    for name in ("pip-audit", "pnpm-audit", "trivy", "gitleaks"):
        assert name in gate[1], f"汇总门禁里 {name} 的裁决位不见了"


def test_helper_is_parseable_and_has_the_two_attempt_contract() -> None:
    """把"重试次数=2"钉住：改成 1 就失去重试的意义，改成 5 会把红灯拖成超时且没人读原因。"""
    assert scan.ATTEMPTS == 2
    assert scan.RETRY_DELAY_S > 0
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(_ROOT / "scripts" / "security_scan.py"), "--help"],
        capture_output=True, text=True, cwd=str(_ROOT),
    )
    assert proc.returncode == 0 and "--report" in proc.stdout
