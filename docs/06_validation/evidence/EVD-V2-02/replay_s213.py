"""重放器：把 `out_s213.txt` 每一段记录的命令**真正重跑一遍**，整份重写证据文件。

跑法（仓库根）：`PYTHONIOENCODING=utf-8 python docs/06_validation/evidence/EVD-V2-02/replay_s213.py`

为什么它必须待在本包里而不是临时目录里：上一版驱动放在 `_workspace/`（不入库），于是
「每次改 harness 都要重跑它」这条纪律只剩 README 里的一句话——驱动一丢，留档就再也无法自证被重放过。

它自己也是被这一轮账教训出来的（见 README §4.9 S-2）：更早那版按 `^$ ` 前缀找命令、输出时又剥掉前缀，
前缀一丢就**不跑而直接抄旧输出**，且不报错。现在按段落版式取命令（标题后第一条非 `#` 非空行，
heredoc 取到配对的 `PY`），输出时统一补 `$ `，并在收尾加 L 段机检「每一段都留得下一条 `$ ` 命令」。

A–I 从文件里取命令重放；J 由 `j_attack_r7.py` 现跑；K 是编码自证的现跑；L 现跑并回填。
只读工作树与被测文件（A 段的临时副本写在 kb.py 同目录并当场 unlink，J 段的探针 harness 跑完即删）。
"""

from __future__ import annotations

import datetime
import os
import pathlib
import re
import subprocess

EV = pathlib.Path(__file__).resolve().parent
ROOT = EV.parents[3]
OUT = EV / "out_s213.txt"
BASH = r"C:\Program Files\Git\bin\bash.exe"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}
TMPNG = (EV / "_tmp_ng.py").relative_to(ROOT).as_posix()
RELPATH = lambda p: p.relative_to(ROOT).as_posix()  # noqa: E731 - 只是把路径转成命令里的 posix 形式


def split_sections(text: str) -> list[tuple[str, str]]:
    parts = re.split(r"(?m)^(########## .*)$", text)
    return [(parts[i], parts[i + 1] if i + 1 < len(parts) else "") for i in range(1, len(parts), 2)]


def extract_cmd(body: str) -> str:
    """段体里第一条非 `#`、非空的行就是命令；heredoc 取到配对的 `PY` 行。"""
    lines = body.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() and not ln.startswith("#"))
    lines[start] = re.sub(r"^\$ ", "", lines[start])
    if "<<" not in lines[start]:
        return lines[start]
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "PY")
    return "\n".join(lines[start:end + 1])


def run_cmd(cmd: str, title: str, notes: str = "") -> str:
    r = subprocess.run([BASH, "-c", cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=ROOT, env=ENV)
    out = ((r.stdout or "") + (r.stderr or "")).rstrip()
    print(f"{title[:60]} … rc={r.returncode}")
    return f"{title}\n{notes}$ {cmd}\n{out}\nrc={r.returncode}\n"


K_TITLE = "########## K.1 BD 裸跑（cp936 输出流，guard 在位）"
K_NOTES = (
    "# 提交前自查发现的第三类崩溃面：`⇒` 在 win32 默认 cp936 上编不出来，`--self-test` 的标签打印会\n"
    "# UnicodeEncodeError——既不是绿也不是红，正是本项目禁止的「没有裁决」第三种形态。\n"
    "# 四条命令：K.1/K.3 证明现在裸跑不崩（rc=0、traceback 行数 0），K.2/K.4 把 `_ensure_utf8_stdout()`\n"
    "# 关掉复现改前，证明 harness 里新加的「编码自证」档是承重的而非装饰。\n"
)


def k_sections() -> list[str]:
    chunks, n = [], 0
    for name, script in (("BD", EV / "prove_biz_delegation.py"), ("PI", EV / "prove_article_identity.py")):
        rel = RELPATH(script)
        # `grep -c` 命中 0 行时自己返回 1，会把「没崩」误报成失败，所以显式吃掉它的退出码
        bare = (f'PYTHONIOENCODING= python {rel} --self-test > /tmp/k_{name}.out 2> /tmp/k_{name}.err; '
                f'rc=$?; tb=$(grep -c Traceback /tmp/k_{name}.err || true); '
                f'echo "rc=$rc  stderr 里 traceback 行数=$tb"; tail -1 /tmp/k_{name}.out')
        noguard = (rf"sed 's/^_ensure_utf8_stdout()$/pass  # guard disabled/' {rel} > {TMPNG} && "
                   f"PYTHONIOENCODING=utf-8 python {TMPNG} --self-test 2>&1 | grep 编码自证; "
                   f"rm -f {TMPNG}; ls {TMPNG} 2>&1 | tail -1")
        for cmd in (bare, noguard):
            n += 1
            first = n == 1
            title = K_TITLE if first else (f"########## K.{n} {name} "
                                           f"{'关 guard 复现改前' if n % 2 == 0 else '裸跑（cp936，guard 在位）'}")
            chunks.append(run_cmd(cmd, title, K_NOTES if first else ""))
    assert not (EV / "_tmp_ng.py").exists(), "K 段的关 guard 副本没删干净"
    return chunks


L_HEAD = "########## L 重放器自检：每段都必须留得下一条逐字可重跑的 `$ ` 命令\n"
L_CMD = """python - <<'PY'
import pathlib, re
t = pathlib.Path('docs/06_validation/evidence/EVD-V2-02/out_s213.txt').read_text(encoding='utf-8')
parts = re.split(r'(?m)^(########## .*)$', t)
bad = [parts[i].split()[1] for i, p in enumerate(parts) if p.startswith('########## ')
       and not any(ln.startswith('$ ') for ln in parts[i + 1].splitlines())]
print('段数（含本段）：', len([p for p in parts if p.startswith('########## ')]))
print('缺 `$ ` 命令的段：', bad or '无——本文件每一段都留得下重跑入口')
PY"""


def main() -> int:
    sections = [(t, b) for t, b in split_sections(OUT.read_text(encoding="utf-8"))
                if re.match(r"^########## [A-I] ", t)]
    assert len(sections) == 9, f"A–I 段应为 9，实得 {len(sections)}：{[t[:14] for t, _ in sections]}"
    rendered = [run_cmd(extract_cmd(body), title) for title, body in sections]

    j = run_cmd(f"python {RELPATH(EV / 'j_attack_r7.py')}",
                "########## J 第七轮复审的闭合实测：四发「def 还在但活绑定已换」+ 四发「调用点在但结果不进锚」+ 两发崩栈面",
                "# 驱动是**入库件** `j_attack_r7.py`（改前版 harness 由 `git show de78125:…` 取，改后即本包这一版）。\n"
                "# 上一版把这 92 行原样内嵌进本文件，代价是留档与在库驱动各一份、会漂移；现在命令就是驱动本身。\n"
                "# 临时件两个（探针 harness、kb 攻击副本）都由驱动自己删，J-11/J-12 是回读。\n")
    probe = EV / "_harness_prefix_r7.py"
    assert not probe.exists(), f"J 段跑完后探针 harness 仍在：{probe}"

    ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")[:25]
    hh = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                        capture_output=True, text=True, env=ENV, cwd=ROOT).stdout.strip()
    header = f"""# STEP-02 S2.1.3 执行留档（kb._biz_from_url 委托解析层）
# 时间 {ts}｜HEAD={hh}+工作区未提交改动（第七轮复审处置批 + 提交前自查的编码崩溃面，差异表 D-11）｜Python 3.11.9｜win32
# 本机依赖实测：structlog / sqlalchemy 皆无（kb.py:22-25 模块级导入）⇒ D 段只能证明「收集期即失败」，用例本身交 CI（J-5）
# **判据条数：16 条——BD-1…BD-6 行为面、BD-7…BD-16 结构面。**
#   本文件每一段的命令都由**在库件** `replay_s213.py` 逐字重跑生成（`python docs/06_validation/evidence/
#   EVD-V2-02/replay_s213.py`），并由 L 段机检「每段都留得下一条 `$ ` 命令」。上一版留档做不到这点：驱动放在
#   不入库的 `_workspace/` 里、按 `$ ` 前缀找命令又在输出时剥掉前缀，前缀一丢就**不跑而直接抄旧输出**且不报错
#   ——这条账记在 README §4.9 S-2 与卡面差异表 D-11。
# 每段 `$` 行就是**逐字可重跑**的单行命令（heredoc 段用 `python - <<'PY' … PY`，在 git bash 下、仓库根跑）
# 判据计数口径：BD-15 排在最前打印（它是行为面六条的前提），编号仍按追加顺序，不打乱既有 BD-1…BD-14 的锚
# `PYTHONIOENCODING=utf-8` 现在只影响输出**好不好读**，不再是脚本**活不活得下来**的前提：见 K.1/K.3 两条裸跑

"""
    # 两段式落 L：先把 L 段连同占位符写进去，再跑 L 的命令，最后回填——这样 L 的读数描述的是
    # **交付出去的这一份**（含 L 自己），而不是它运行前那一刻还没写完的版本。
    body = header + "\n".join(rendered) + "\n" + j + "\n" + "\n".join(k_sections())
    PLACEHOLDER = "# PLACEHOLDER_L_OUT"
    OUT.write_text(body + "\n" + L_HEAD + "$ " + L_CMD + "\n" + PLACEHOLDER + "\n",
                   encoding="utf-8", newline="\n")
    lr = subprocess.run([BASH, "-c", L_CMD], capture_output=True, text=True,
                        encoding="utf-8", errors="replace", cwd=ROOT, env=ENV)
    lout = ((lr.stdout or "") + (lr.stderr or "")).rstrip() + f"\nrc={lr.returncode}"
    OUT.write_text(OUT.read_text(encoding="utf-8").replace(PLACEHOLDER, lout),
                   encoding="utf-8", newline="\n")
    print(lout)
    print(f"写出 {OUT}（{len(OUT.read_text(encoding='utf-8').splitlines())} 行）")
    return 0 if "缺 `$ ` 命令的段： 无" in lout else 1


if __name__ == "__main__":
    raise SystemExit(main())
