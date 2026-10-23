"""STEP-34 S34.5 / S34.6 / S34.8 的接线面用例：改动必须真的进了工作流才算存在。

先例与教训（F-V14-06 / P-56 / P-101）：判据"签了却没有执行代码，等于没签"——
掩码门当年的教训是"只写进 Makefile 的门在 CI 里等于不存在"，这三条同理：
- S34.5：make/entry 零/非零对等的 Linux 半边在 ubuntu backend job 里有了执行者；
- S34.6：faulthandler 转栈值（100）必须**小于** pytest-timeout 杀值（120），
  两把闹钟错开，"卡死先留栈再被杀"的时序保障才成立（P-54）；
- S34.8：ruff/mypy 的 scripts/** 面必须同时接进两处工作流与 entry.py
  （P-110 / D-V19-06：先清零再扩门；扩门那批本机与 @ci 都要绿）。
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOTS = [
    up for up in Path(__file__).resolve().parents
    if (up / "scripts" / "guards.py").is_file() and (up / "Makefile").is_file()
]
assert _ROOTS, "向上找不到同时含 scripts/guards.py 与 Makefile 的仓库根"
_ROOT = _ROOTS[0]

_CI_YML = _ROOT / ".github" / "workflows" / "ci.yml"
_CI_WIN_YML = _ROOT / ".github" / "workflows" / "ci-windows.yml"
_ENTRY_PY = _ROOT / "scripts" / "entry.py"

# ubuntu backend job 的 run 步默认 cwd=apps/api；从那里到仓库根 scripts 的相对路径
_SCRIPTS_TARGET = "../../scripts"


def test_faithhandler_stack_dump_value_is_smaller_than_the_kill_timeout() -> None:
    """S34.6（P-54）：转栈值 100 必须小于杀值 120——同阈值时谁先落地不确定，
    卡死用例可能"被杀得连栈都没留下"。断言直接比数值，写反了（≥）即红。"""
    text = _CI_WIN_YML.read_text(encoding="utf-8")
    stack = re.search(r"-o\s+faulthandler_timeout=(\d+)", text)
    kill = re.search(r"--timeout=(\d+)", text)
    assert stack and kill, "ci-windows.yml 里找不到 faulthandler_timeout 与 --timeout ⇒ 判据失去对象"
    assert int(stack.group(1)) < int(kill.group(1)), (
        f"转栈值 {stack.group(1)} 必须 < 杀值 {kill.group(1)}（P-54：先留栈再被杀）"
    )


def test_make_entry_parity_step_exists_in_ubuntu_backend_job() -> None:
    """S34.5（P-101）：Linux 半边的执行者必须在 ubuntu backend job 里真实存在，
    且至少覆盖 @win 复算表的 6 个任务、判据是零/非零一致（不比具体 rc 值）。"""
    text = _CI_YML.read_text(encoding="utf-8")
    m = re.search(r"- name: make/entry parity \((\d+) tasks[^\n]*\)\n((?:        .+\n)+)", text)
    assert m, "ci.yml backend job 没有 make/entry parity 步 ⇒ P-101 的 Linux 半边仍无执行者"
    count = int(m.group(1))
    body = m.group(2)
    tasks = re.findall(r"for task in ([a-z- ]+); do", body)
    assert tasks, "parity 步里没有任务循环 ⇒ 判据空转"
    listed = tasks[0].split()
    assert count == len(listed) == 6, f"任务数（{count}）与循环清单（{listed}）必须都是 6"
    for required in ("dev", "lint-backend", "guard-ports", "fmt-check-backend", "docker-ps", "migrate"):
        assert required in listed, f"@win 复算表任务 {required} 不在 Linux 半边：{listed}"
    assert "-eq 0" in body and "-ne 0" in body, "parity 步没有零/非零比较逻辑"


def test_scripts_lint_type_targets_are_wired_into_both_workflows_and_entry() -> None:
    """S34.8（P-110 / D-V19-06）：scripts/** 的 lint/type 面必须同时接进
    ci.yml、ci-windows.yml 的 lint/type 步与 entry.py 的 lint-backend/typecheck-backend。
    只接一处等于没接：@win 与 @linux 各有一份口径，漏一处就是半边无执行者。"""
    for wf, label in ((_CI_YML, "ci.yml"), (_CI_WIN_YML, "ci-windows.yml")):
        text = wf.read_text(encoding="utf-8")
        # 只看 run: 行（步名里也可能写着 "ruff check app tests" 字样，那不是执行体）
        run_lines = [ln for ln in text.splitlines() if ln.strip().startswith("run:")]
        lint_lines = [ln for ln in run_lines if "ruff check" in ln]
        type_lines = [ln for ln in run_lines if re.search(r"mypy\s+app", ln)]
        assert lint_lines and all(_SCRIPTS_TARGET in ln for ln in lint_lines), (
            f"{label} 的 ruff run 行没有带上 {_SCRIPTS_TARGET}：{lint_lines}"
        )
        assert type_lines and all(_SCRIPTS_TARGET in ln for ln in type_lines), (
            f"{label} 的 mypy run 行没有带上 {_SCRIPTS_TARGET}：{type_lines}"
        )
    entry = _ENTRY_PY.read_text(encoding="utf-8")
    assert '"../../scripts"' in entry, "entry.py 的 lint/type 工具步没有带上 ../../scripts"
    # entry.py 的注册是多行列表；确认两条任务的 steps 里都有 scripts 步
    for anchor in ('add("lint-backend"', 'add("typecheck-backend"'):
        start = entry.index(anchor)
        chunk = entry[start:start + 400]
        assert '"../../scripts"' in chunk, f"entry.py 的 {anchor}… 注册块没有 scripts 步"


def test_entry_lint_and_typecheck_run_clean_with_scripts_in_scope() -> None:
    """扩门后的实跑读数（本机 @win，2026-10-23）：两条任务 rc=0。
    用 subprocess 真跑而不是只查文本——"接线了"不等于"跑得过"。"""
    import subprocess
    import sys

    for args in (["lint-backend"], ["typecheck-backend"]):
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(_ROOT / "scripts" / "entry.py"), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(_ROOT), timeout=600,
        )
        assert proc.returncode == 0, f"entry.py {args[0]} rc={proc.returncode}\n{proc.stdout[-2000:]}"
