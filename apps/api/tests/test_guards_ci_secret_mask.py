"""STEP-32 S32.2 守卫用例：写进 `$GITHUB_ENV` 的生成值必须在同一步内先 `::add-mask::`。

为什么要有这道门（P-107）：`ci.yml` 的 `compose-smoke` job 用 `$(python3 -c ...)` 现场生成
两把一次性主密钥，然后**直接**写进 `$GITHUB_ENV`。GitHub 只掩码它见过的值，而 `>> $GITHUB_ENV`
不回显 ⇒ 值从未进日志？不——同一行的命令替换在 `set -x`/错误输出/后续步骤里都可能被带出，
且仓是 public、日志对外可读。修法只有"先赋值 → mask → 再写"这一种顺序是对的。

判据的分寸（写在这里免得后来人以为门管得不够宽）：
- 只管 `$GITHUB_ENV`，不管 `$GITHUB_OUTPUT`——卡面就是这么划的（D-V18-03），扩大范围要另开卡。
- 生成值追两层：`x=$(...)` 与 `y=$x`。第三层以上（`z=$(echo "$y")`）不在门内，因为它已经
  不是"把命令替换写进环境"的形状，而是普通字符串拼接。
- 掩码必须在写之前。生成的值若在**另一步**才写进 `$GITHUB_ENV`，本门按"同一步"口径放行
  （卡面原文如此）；已知的召回缺口登记在台账，不在此擅自扩判据。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_ROOTS = [
    up for up in Path(__file__).resolve().parents
    if (up / "scripts" / "guards.py").is_file() and (up / "Makefile").is_file()
]
assert _ROOTS, "向上找不到同时含 scripts/guards.py 与 Makefile 的仓库根"
_ROOT = _ROOTS[0]

_spec = importlib.util.spec_from_file_location("bothot_guards_ci_mask", _ROOT / "scripts" / "guards.py")
assert _spec is not None and _spec.loader is not None
guards: Any = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guards)

_SINK = 'echo "PUSH_SECRET_MASTER_KEY=$push_key" >> "$GITHUB_ENV"'


def _wf(body: list[str], *, extra_steps: list[list[str]] | None = None) -> str:
    """把正文行拼成**一个** `run: |` 步骤；`extra_steps` 再追加若干步骤。

    步骤边界是判据的一部分（掩码只在同一步内生效），所以这里必须能造出"跨步"的形状。
    """
    out = ["jobs:", "  t:", "    steps:"]
    for i, lines in enumerate([body] + (extra_steps or []), start=1):
        out.append(f"      - name: step{i}")
        out.append("        run: |")
        out.extend(f"          {line}" for line in lines)
    return "\n".join(out) + "\n"


# ─── 判据本体：合成输入的四极性 ────────────────────────────────────────────────

def test_inline_command_substitution_into_env_is_red() -> None:
    """P-107 的真实形状：`KEY=$(...)` 直接写 `$GITHUB_ENV` ⇒ 违规，且点名步骤与行号。"""
    text = _wf(['echo "K=$(python3 -c \'print(1)\')" >> "$GITHUB_ENV"'])
    v = guards.ci_mask_violations(text, "ci.yml")
    assert len(v) == 1, v
    assert v[0]["step"] == "step1"
    assert "GITHUB_ENV" in str(v[0]["why"])


def test_assign_then_mask_then_write_is_green() -> None:
    """S32.1 修好的形状必须绿——否则门会把正确写法也判红（假阳）。"""
    text = _wf(["push_key=$(python3 -c 'print(1)')",
                'echo "::add-mask::$push_key"',
                _SINK])
    assert guards.ci_mask_violations(text, "ci.yml") == []


def test_mask_after_write_is_red() -> None:
    """顺序敏感：先写后掩，写那一行的值在日志里已经是明文。"""
    text = _wf(["push_key=$(python3 -c 'print(1)')",
                _SINK,
                'echo "::add-mask::$push_key"'])
    assert len(guards.ci_mask_violations(text, "ci.yml")) == 1


def test_static_and_expression_writes_are_green() -> None:
    """假阳控制面：常量写入与 `${{ }}` 上下文写入都不是"本步生成的值"，不得判红。"""
    text = _wf(['echo "MODE=ci" >> "$GITHUB_ENV"',
                'echo "SHA=${{ github.sha }}" >> "$GITHUB_ENV"',
                'echo "DIR=$PWD" >> "$GITHUB_ENV"'])
    assert guards.ci_mask_violations(text, "ci.yml") == []


def test_generated_value_copied_through_a_second_variable_is_red() -> None:
    """换个变量名不能躲开门：`y=$x` 之后写 `$y` 仍是同一个生成值。"""
    text = _wf(["x=$(python3 -c 'print(1)')", "y=$x",
                'echo "K=$y" >> "$GITHUB_ENV"'])
    v = guards.ci_mask_violations(text, "ci.yml")
    assert len(v) == 1 and "y" in str(v[0]["why"]), v


def test_masking_a_different_variable_does_not_cover_the_leak() -> None:
    """掩了别的变量≠掩了这个变量（掩码按值登记，不是按步骤整片生效）。"""
    text = _wf(["a=$(python3 -c 'print(1)')", "b=$(python3 -c 'print(2)')",
                'echo "::add-mask::$a"',
                'echo "K=$b" >> "$GITHUB_ENV"'])
    v = guards.ci_mask_violations(text, "ci.yml")
    assert len(v) == 1 and "b" in str(v[0]["why"]), v


def test_mask_in_an_earlier_step_of_the_same_job_covers_the_write() -> None:
    """掩码一经登记就在整个 job 内持续生效，所以"上一步 mask、本步写"是安全形状，放行是对的。

    这条不是偷懒的绿灯：它钉住的是判据的**边界**——门管的是"值在写进 $GITHUB_ENV 之前
    有没有被登记成掩码"，不是"必须和写入同一步"。把两者混为一谈会让门在真实修法（生成与
    导出分居两步）上误红。
    """
    text = _wf(["x=$(python3 -c 'print(1)')", 'echo "::add-mask::$x"'],
               extra_steps=[['echo "K=$x" >> "$GITHUB_ENV"']])
    assert guards.ci_mask_violations(text, "ci.yml") == []


def test_comment_lines_do_not_count_as_mask_or_write() -> None:
    """注释既不算掩码也不算写入——这一发是**反自洗**极性，两条都要判。

    踩过的形状：判据最初写成 `if line.startswith("#") or "::add-mask::" in line`，
    于是"注释里提一句 `::add-mask::$x`"就把 `x` 登记成已掩码 ⇒ 真实泄漏放行。
    一条说明文字绝不能改变门的结论。
    """
    masked_by_comment = _wf(["x=$(python3 -c 'print(1)')",
                             '# echo "::add-mask::$x"',
                             'echo "K=$x" >> "$GITHUB_ENV"'])
    v = guards.ci_mask_violations(masked_by_comment, "ci.yml")
    assert len(v) == 1 and "x" in str(v[0]["why"]), v
    only_commented_write = _wf(["x=$(python3 -c 'print(1)')",
                                '# echo "K=$x" >> "$GITHUB_ENV"'])
    assert guards.ci_mask_violations(only_commented_write, "ci.yml") == []


def test_braced_mask_form_is_accepted() -> None:
    """`${x}` 与 `$x` 是同一个变量，不能只认一种写法。"""
    text = _wf(["x=$(python3 -c 'print(1)')",
                'echo "::add-mask::${x}"',
                'echo "K=${x}" >> "$GITHUB_ENV"'])
    assert guards.ci_mask_violations(text, "ci.yml") == []


# ─── 真仓库面：门必须真的在看现文件，而不是只看合成输入 ──────────────────────────

_CI_YML = _ROOT / ".github" / "workflows" / "ci.yml"


def test_real_workflows_pass_the_gate() -> None:
    """现读全部工作流必须零违规（交付判据之一）。"""
    files = sorted(p for p in (_ROOT / ".github" / "workflows").glob("*.y*ml"))
    assert files, "找不到任何工作流文件 ⇒ 门没有可检面"
    for path in files:
        rel = str(path.relative_to(_ROOT)).replace("\\", "/")
        assert guards.ci_mask_violations(path.read_text(encoding="utf-8"), rel) == [], rel


def test_deleting_the_mask_lines_from_ci_yml_turns_the_gate_red() -> None:
    """卡面指定的反证：把 S32.1 的两行 `::add-mask::` 删掉 ⇒ 守卫必须红。

    这条用例是"门确实咬在修复本身上"的唯一机检：若判据其实没绑定掩码行，
    删掉它照样绿，那这道门就只是把 ci.yml 现在的样子抄了一遍。
    """
    text = _CI_YML.read_text(encoding="utf-8")
    assert text.count("::add-mask::") >= 2, "ci.yml 里掩码行少于 2 行 ⇒ 反证的前提不成立"
    stripped = "\n".join(line for line in text.splitlines() if "::add-mask::" not in line)
    v = guards.ci_mask_violations(stripped, "ci.yml")
    assert len(v) == 2, v
    assert {"push_master_key", "engine_master_key"} <= {
        name for item in v for name in ("push_master_key", "engine_master_key") if name in str(item["why"])
    }


def test_the_old_p107_shape_still_reddens_the_gate() -> None:
    """修复前的真实形状（HEAD~ 之前）也必须红——否则门对这类缺陷根本没有召回。

    不读 git 历史（用例不能依赖本机 HEAD），把当时那两行原样写成合成输入。
    """
    body = ("echo \"PUSH_SECRET_MASTER_KEY=$(python3 -c 'import base64,os;"
            "print(base64.b64encode(os.urandom(32)).decode())')\" >> \"$GITHUB_ENV\"")
    assert len(guards.ci_mask_violations(_wf([body]), "ci.yml")) == 1


def test_gate_returns_zero_and_reports_a_nonempty_scanned_face(capsys: pytest.CaptureFixture[str]) -> None:
    """rc=0 必须伴随"确实扫到了写入面"：scanned==0 不是通过（本仓既有纪律）。"""
    rc = guards.guard_ci_secret_mask()
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "个工作流" in out and "行写 $GITHUB_ENV" in out, out
    assert "0 行写 $GITHUB_ENV" not in out, out


def test_gate_returns_third_state_when_it_has_nothing_to_judge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """两个"没有可检面"的形状都必须落 rc=3，不许落 rc=0。

    这是本门的 fail-closed 支路：目录空 ⇒ 什么都没看；有工作流但全仓不再写 `$GITHUB_ENV`
    ⇒ 判据本身失效。两种都"零违规"，把零违规当成通过就是自洗判据。
    断言看的是 rc **与**点名原因，不只 rc（rc 相同的两条支路要能分辨是谁在说话）。
    """
    empty = tmp_path / "workflows"
    empty.mkdir()
    monkeypatch.setattr(guards, "WORKFLOW_DIR", empty)
    assert guards.guard_ci_secret_mask() == 3
    assert "没有任何 workflow 文件" in capsys.readouterr().out

    (empty / "a.yml").write_text(_wf(['echo "MODE=ci" >> /tmp/other']), encoding="utf-8")
    assert guards.guard_ci_secret_mask() == 3
    out = capsys.readouterr().out
    assert "0 行写 $GITHUB_ENV" in out and "判据未被检验" in out, out


# ─── 接线面：门进了 Makefile / entry.py / CI 才算存在（F-V14-06 的同形教训）────────

def test_gate_is_registered_in_guards_makefile_and_entry() -> None:
    assert "guard-ci-secret-mask" in guards.GUARDS, "未进入子命令分发表"
    mk = (_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "guard-ci-secret-mask: ##" in mk, "Makefile 缺薄转调目标"
    aggregate = next(ln for ln in mk.splitlines() if ln.startswith("guard:"))
    assert "guard-ci-secret-mask" in aggregate.split(), f"聚合目标未包含新门：{aggregate}"
    entry = (_ROOT / "scripts" / "entry.py").read_text(encoding="utf-8")
    assert '"guard-ci-secret-mask"' in entry, "entry.py 未注册该任务（⇒ check_entry_parity 会红）"


def test_gate_is_called_in_ci_and_its_rc_can_fail_the_job() -> None:
    """只写进 Makefile 的门在 CI 里等于不存在；而且"调用了"不等于"能判失败"。

    三条都机检：调用行捕获 rc 到专属变量、有对该变量的非 0 判定、该判定分支里有 exit 1。
    """
    lines = [ln.strip() for ln in _CI_YML.read_text(encoding="utf-8").splitlines()]
    call = next((ln for ln in lines if "guard-ci-secret-mask" in ln and "|| rc_" in ln), "")
    assert call, "CI 没有把掩码门的 rc 捕获到变量：失败会直接被后一道门的 rc 覆盖"
    var = call.split("|| ")[1].split("=")[0].strip()
    check = next((ln for ln in lines if ln.startswith("if ") and f'"${var}"' in ln and "-ne 0" in ln), "")
    assert check, f"没有对 ${var} 判非 0（只看调用不等于判失败）"
    pos = lines.index(check)
    assert "exit 1" in lines[pos + 1:pos + 5], "非 0 判定分支里没有 exit 1"
    assert f"{var}=0" in lines, "rc 变量没有显式初始化：`set -u` 下未定义即整步报错"
