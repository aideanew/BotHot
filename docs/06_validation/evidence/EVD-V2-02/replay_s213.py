"""重放器：把 `out_s213.txt` 每一段记录的命令**真正重跑一遍**，整份重写证据文件。

跑法（仓库根）：`PYTHONIOENCODING=utf-8 python docs/06_validation/evidence/EVD-V2-02/replay_s213.py`

为什么它必须待在本包里而不是临时目录里：上一版驱动放在 `_workspace/`（不入库），于是
「每次改 harness 都要重跑它」这条纪律只剩 README 里的一句话——驱动一丢，留档就再也无法自证被重放过。

它自己也是被这一轮账教训出来的（见 README §4.9 S-2）：更早那版按 `^$ ` 前缀找命令、输出时又剥掉前缀，
前缀一丢就**不跑而直接抄旧输出**，且不报错。现在按段落版式取命令（标题后第一条非 `#` 非空行，
heredoc 取到配对的 `PY`），输出时统一补 `$ `，并在收尾加 L 段机检「每一段都留得下一条 `$ ` 命令」。
L 那条机检判的是**把手在不在**，不是**命令跑不跑得起**（把某段的命令换成 `$ THIS IS NOT A COMMAND`
它照样说「无」）——所以它只保证「读者知道该重跑什么」，取命令这件事本身的正确性由 M 段
（本文件 `--self-test`）判：剥掉 `$ ` 前缀仍能取到同一条命令，且**没有命令的段落必须 raise**，
返回空值就是当年「静默抄旧输出」的形状。

A–I 从文件里取命令重放；J 由 `j_attack_r7.py` 现跑；K 是编码自证的现跑；M 是本驱动器 `--self-test`
的现跑；L 现跑并回填。
它写什么必须写清（第八轮复审 id 4）：**它会重写本包内被跟踪的 `out_s213.txt`**，K.2/K.5 与 K.3/K.6
那四条 `sed` 命令还会在本包目录里各落一个用完即删的临时副本（`_tmp_ng.py`、`_tmp_noarrow.py`；
同一段里的回读就是它们的删除证明）。
它**不写任何被测文件**：A 段的 kb 临时副本写在 kb.py 同目录并当场 unlink，J 段的探针 harness 跑完即删。

写留档这一步本身要回读（本轮实测撞过一次 `OSError [Errno 22]`：整份重放跑完、最后一次回填炸掉，
磁盘上留下带 `PLACEHOLDER_L_OUT` 的半成品，而驱动自己一声不吭地过）。见 `write_out` / `write_ok` 与 M 段。

还有一条依赖要写清（同一轮实测）：**A–I 段的命令是从上一版留档里取的**，所以把 `out_s213.txt` 删掉
就断了自举——不是「它可以从零生成」。删掉后驱动给 FAIL rc=1 并说明怎么恢复，而不是 traceback。
"""

from __future__ import annotations

import datetime
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

EV = pathlib.Path(__file__).resolve().parent
ROOT = EV.parents[3]
OUT = EV / "out_s213.txt"
PLACEHOLDER = "# PLACEHOLDER_L_OUT"
BASH = r"C:\Program Files\Git\bin\bash.exe"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}
TMPNG = (EV / "_tmp_ng.py").relative_to(ROOT).as_posix()
RELPATH = lambda p: p.relative_to(ROOT).as_posix()  # noqa: E731 - 只是把路径转成命令里的 posix 形式
# 段落标题里的 `⇒` 与 pytest 汇总行的墙钟：前者在 win32 默认 cp936 输出流上编不出来（本项目
# 禁的「没有裁决」第三态，与两份 harness 同一个症状），后者每次重跑必然不同（留着就等于留一份
# 不可复现的读数）。所以先钉输出流，再把墙钟归一化成 `in <redacted>s`。
TIMING = re.compile(r"\bin \d+\.\d+s\b")


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


_ensure_utf8_stdout()


def split_sections(text: str) -> list[tuple[str, str]]:
    parts = re.split(r"(?m)^(########## .*)$", text)
    return [(parts[i], parts[i + 1] if i + 1 < len(parts) else "") for i in range(1, len(parts), 2)]


#: 留档读数长得就这个样子（`rc=0`、`合计 PASS=…`、`OK/FAIL …`）。段里第一条非注释行撞上它们，
#: 说明这一段没有命令、只有读数——旧驱动会在这种情况下把旧输出抄下去且不报错。
READING_LIKE = re.compile(r"^(rc=\d+|合计|PASS |FAIL |BAD |OK |INCONCLUSIVE|段数|缺 |目标：)")


def extract_cmd(body: str) -> str:
    """段体里第一条非 `#`、非空的行就是命令；heredoc 取到配对的 `PY` 行。

    取不到、或取出来的是读数形状 ⇒ **raise**，不返回空值也不返回那行文本。宁可不生成留档，
    也不能让「没跑到」冒充「跑到了」。
    """
    lines = body.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() and not ln.startswith("#"))
    except StopIteration:
        raise ValueError("段里只剩注释与空行，取不到命令——拒绝用旧读数填空") from None
    lines[start] = re.sub(r"^\$ ", "", lines[start])
    if "<<" in lines[start]:
        try:
            end = next(i for i in range(start + 1, len(lines)) if lines[i] == "PY")
        except StopIteration:
            raise ValueError(f"heredoc 没有配对的 `PY` 结束行：{lines[start]!r}") from None
        cmd = "\n".join(lines[start:end + 1])
    else:
        cmd = lines[start]
    if READING_LIKE.match(cmd):
        raise ValueError(f"第一条非注释行读起来像留档读数而不像命令：{cmd!r}——拒绝把它当命令跑")
    return cmd


def write_ok(intent: str, readback: str) -> str:
    """写入算不算成功：**回读必须与要写的内容逐字相同**。空串才算成，否则给原因。

    两种坏形状分开给原因，因为后果不同：还留着 `PLACEHOLDER_L_OUT` = **半成品冒充成品**（回填那一步
    失败时的形状，本轮真的撞到过一次）；其余不一致 = 落下去的是另一个版本（截断、被并发写坏、编码改写）。
    """
    if readback == intent:
        return ""
    if PLACEHOLDER in readback:
        return f"磁盘上仍是半成品（留着 {PLACEHOLDER}）——回填那一步没成功"
    return f"回读与写入不一致（写 {len(intent)} 字，读回 {len(readback)} 字）"


def write_out(text: str) -> str:
    """落盘 + 回读比对，最多试 5 次。成功返回空串，失败返回原因——**不 raise**：本项目「崩栈不是裁决」。

    这不是防御性口味：本轮整份重放跑完后，最后一次回填以 `OSError [Errno 22]`（win32 上文件被瞬时占用）
    失败，驱动一声不吭地过，而磁盘上留下的是**带占位符的半成品**。「写出 431 行」这句话如果只由驱动
    自己声明，就和它要取代的那句「每一段都重放过」一样不可证——所以写完必须把内容读回来对一遍。
    """
    last = "没试过"
    for _ in range(5):
        try:
            OUT.write_text(text, encoding="utf-8", newline="\n")
            last = write_ok(text, OUT.read_text(encoding="utf-8"))
        except OSError as exc:  # 写不进，或写得进却读不回
            last = f"落盘或回读抛异常：{type(exc).__name__}: {exc}"
        if not last:
            return ""
        time.sleep(0.3)
    return last


def run_cmd(cmd: str, title: str, notes: str = "") -> str:
    r = subprocess.run([BASH, "-c", cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=ROOT, env=ENV)
    out = TIMING.sub("in <redacted>s", ((r.stdout or "") + (r.stderr or "")).rstrip())
    print(f"{title[:60]} … rc={r.returncode}")
    return f"{title}\n{notes}$ {cmd}\n{out}\nrc={r.returncode}\n"


K_TITLE = "########## K.1 BD 裸跑（cp936 输出流，guard 在位）"
K_NOTES = (
    "# 提交前自查发现的第三类崩溃面：`⇒` 在 win32 默认 cp936 上编不出来，`--self-test` 的标签打印会\n"
    "# UnicodeEncodeError——既不是绿也不是红，正是本项目禁止的「没有裁决」第三种形态。\n"
    "# 六条命令，每台 harness 三条：裸跑证明现在不崩（rc=0、traceback 行数 0）；关 guard 复现改前，\n"
    "# 证明 `_ensure_utf8_stdout()` 承重；**抽靶**（把所有 ⇒ 换成 `->`）证明「编码自证」档不是装饰——\n"
    "# 靶字被抽掉后子进程照样全绿，若不查 ⇒ 是否真出现过，那一档就会假绿。\n"
)
# 关 guard 与抽靶两份临时件都必须由同一条命令删掉，末尾的 `ls` 是删除回读
TMPNA = (EV / "_tmp_noarrow.py").relative_to(ROOT).as_posix()


def k_sections() -> list[str]:
    chunks, n = [], 0
    kinds = ("裸跑（cp936，guard 在位）", "关 guard 复现改前", "抽靶：⇒ 全换成 -> 后不许假绿")
    for name, script in (("BD", EV / "prove_biz_delegation.py"), ("PI", EV / "prove_article_identity.py")):
        rel = RELPATH(script)
        # `grep -c` 命中 0 行时自己返回 1，会把「没崩」误报成失败，所以显式吃掉它的退出码
        cmds = [
            (f'PYTHONIOENCODING= python {rel} --self-test > /tmp/k_{name}.out 2> /tmp/k_{name}.err; '
             f'rc=$?; tb=$(grep -c Traceback /tmp/k_{name}.err || true); '
             f'echo "rc=$rc  stderr 里 traceback 行数=$tb"; tail -1 /tmp/k_{name}.out'),
            (rf"sed 's/^_ensure_utf8_stdout()$/pass  # guard disabled/' {rel} > {TMPNG} && "
             f"PYTHONIOENCODING=utf-8 python {TMPNG} --self-test 2>&1 | grep 编码自证; "
             f"rm -f {TMPNG}; ls {TMPNG} 2>&1 | tail -1"),
            (rf"sed 's/⇒/->/g' {rel} > {TMPNA} && "
             f"PYTHONIOENCODING=utf-8 python {TMPNA} --self-test 2>&1 | grep 编码自证; "
             f"rm -f {TMPNA}; ls {TMPNA} 2>&1 | tail -1"),
        ]
        for kind, cmd in zip(kinds, cmds):
            n += 1
            first = n == 1
            title = K_TITLE if first else f"########## K.{n} {name} {kind}"
            chunks.append(run_cmd(cmd, title, K_NOTES if first else ""))
    for leftover in ("_tmp_ng.py", "_tmp_noarrow.py"):
        assert not (EV / leftover).exists(), f"K 段的临时副本没删干净：{leftover}"
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


def self_test() -> int:
    """M 段：判的不是留档内容，而是「驱动自己会不会静默交出一份假留档」这两条通道还在不在。

    第八轮复审 id 4 指出 L 段机检只看 `$ ` 把手在不在，把命令换成 `$ 不是命令` 它照样报「无」。
    所以取命令这件事另开反证：把手丢了仍能取到同一条命令、heredoc 要接配对、配对断了要 raise、
    整段无命令要 raise、取出来的是读数形状也要 raise（旧驱动正是栽在这一步，抄旧输出且不报错）。
    写入回读是本轮自己撞出来的第二条：整份重放跑完、最后一次回填抛 `OSError [Errno 22]`，磁盘上
    留下 L 读数位还空着的半成品——如果「写出 N 行」只是驱动自己的一句 print，半成品就能冒充成品。
    """
    fails: list[str] = []
    if extract_cmd("\n# n\n$ python a.py --x\nout\nrc=0\n") != "python a.py --x":
        fails.append("带 `$ ` 把手的段取错")
    if extract_cmd("\n# n\npython a.py --x\nout\nrc=0\n") != "python a.py --x":
        fails.append("剥掉 `$ ` 把手就取不到同一条命令——旧驱动先取走把手再输出，把手一丢便无命令可跑")
    heredoc = "\n$ python - <<'PY'\nprint(1)\nPY\nout\nrc=0\n"
    if extract_cmd(heredoc) != "python - <<'PY'\nprint(1)\nPY":
        fails.append(f"heredoc 段没接配对到 `PY`：{extract_cmd(heredoc)!r}")
    for label, body in (
        ("整段只剩注释与空行", "\n# 只有注释\n\n"),
        ("heredoc 没有配对 PY", "\n$ python - <<'PY'\nprint(1)\nrc=0\n"),
        ("第一条非注释行是读数", "\nrc=0\nout\n"),
    ):
        try:
            got = repr(extract_cmd(body))
            fails.append(f"{label} 本该 raise，实得 {got}——返回文本就等于抄旧读数")
        except ValueError:
            pass
    good = "# 段\n$ cmd\n段数（含本段）： 18\nrc=0\n"
    if write_ok(good, good):
        fails.append(f"逐字相同的写入被判成失败：{write_ok(good, good)}")
    half = good.replace("段数（含本段）： 18", PLACEHOLDER)
    if not write_ok(good, half):
        fails.append(f"留着 {PLACEHOLDER} 的半成品被当成成品放行")
    if not write_ok(good, good[:-4]):
        fails.append("写 40 字、读回 36 字却算成功")
    # 两条**端到端**：把模块级 `OUT` 临时挪到系统临时目录，一次真写成、一次写不进。
    # 只测 `write_ok` 的话，`write_out` 的重试与异常分支没人跑过——那条 `OSError` 就是从这里来的。
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="rp_selftest_"))
    real_out = OUT
    try:
        globals()["OUT"] = tmp / "ok.txt"
        reason = write_out(good)
        if reason:
            fails.append(f"正常写入被报成失败：{reason}")
        on_disk = (tmp / "ok.txt").read_text(encoding="utf-8") if (tmp / "ok.txt").exists() else None
        if on_disk != good:
            fails.append(f"write_out 说成功了，磁盘上却不是这一份：{on_disk!r}")
        globals()["OUT"] = tmp  # 指向目录本身：写入必抛 IsADirectoryError
        if not write_out(good):
            fails.append("落盘失败却被当成成功——半成品就能冒充成品")
    finally:
        globals()["OUT"] = real_out
        shutil.rmtree(tmp, ignore_errors=True)
    for f in fails:
        print(f"FAIL 重放器自证：{f}")
    if fails:
        return 1
    print("OK   重放器自证：取命令按段落版式而非 `$ ` 把手，把手丢了照样取到同一条；"
          "整段无命令 / heredoc 配对断了 / 第一条非注释行是读数 ⇒ 三种情况一律 raise；"
          "写留档要回读逐字相同，半成品与截断都不算成功，写不进磁盘时要报原因而不是静默过")
    print(
        "SELF-TEST PASS：11 条反证全过（取命令 6 条：把手在/把手丢/配对截断/整段无命令/配对断了/读出读数；"
        "写入判据 3 条：逐字相同才算成 / 留着占位符的半成品不算 / 字数不一致不算；"
        "写入端到端 2 条：临时目录里真写成且磁盘上就是这一份 / 目标是目录写不进必须报原因）"
        "——取不到命令时驱动停下，落不进磁盘时驱动也停下，两种都不许抄旧输出"
    )
    return 0


def main() -> int:
    if not OUT.exists():
        # 自举依赖：A–I 段的命令是从**上一版留档**里取的，留档不在就无命令可跑。本轮实测把
        # `out_s213.txt` 删掉后，驱动直接以 `FileNotFoundError` traceback 收场——那不是裁决，按项目纪律落 FAIL。
        print(f"FAIL 交付：{OUT} 不存在——A–I 段的命令取自这份留档，它没了就断链；"
              f"先 `git checkout -- {RELPATH(OUT)}` 恢复再重放（J/K/M/L 三段不依赖它）。")
        return 1
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
    # HEAD 之外到底还带不带未提交改动，是让 `git status` 说的，不是我抄的（第八轮复审 id 7：
    # 上一版把「+工作区未提交改动」和 Python 版本号写死在模板里，在干净工作树上跑也会自称有改动）
    porcelain = subprocess.run(["git", "status", "--porcelain", "--", "docs/06_validation", "apps/api"],
                                capture_output=True, text=True, env=ENV, cwd=ROOT).stdout.strip()
    state = "工作树干净" if not porcelain else f"含未提交改动 {len(porcelain.splitlines())} 项"
    pyv, plat = sys.version.split()[0], sys.platform
    header = f"""# STEP-02 S2.1.3 执行留档（kb._biz_from_url 委托解析层）
# 时间 {ts}｜HEAD={hh}｜{state}｜Python {pyv}｜{plat}
# 本机依赖实测：structlog / sqlalchemy 皆无（kb.py:22-25 模块级导入）⇒ D 段只能证明「收集期即失败」，用例本身交 CI（J-5）
# **判据条数：16 条——BD-1…BD-6 行为面、BD-7…BD-16 结构面。**
#   本文件每一段的命令都由**在库件** `replay_s213.py` 逐字重跑生成（`python docs/06_validation/evidence/
#   EVD-V2-02/replay_s213.py`）。两道自检收尾：L 段机检「每段都留得下一条 `$ ` 命令」（只判把手在不在），
#   M 段机检驱动自己的两条通道（取命令：把手丢了仍取到同一条、取不到就 raise；落盘：写入必须回读逐字相同，
#   半成品不算成品——本轮重放就撞到过一次回填 `OSError [Errno 22]` 而驱动照过）。上一版留档这些都做不到：
#   驱动放在不入库的 `_workspace/` 里、按 `$ ` 前缀找命令又在输出时剥掉前缀，前缀一丢就**不跑而直接抄旧输出**且不报错
#   ——这条账记在 README §4.9 S-2 / §4.10 与卡面差异表 D-11/D-12。
# 每段 `$` 行就是**逐字可重跑**的单行命令（heredoc 段用 `python - <<'PY' … PY`，在 git bash 下、仓库根跑）
# 判据计数口径：BD-15 排在最前打印（它是行为面六条的前提），编号仍按追加顺序，不打乱既有 BD-1…BD-14 的锚
# `PYTHONIOENCODING=utf-8` 现在只影响输出**好不好读**，不再是脚本**活不活得下来**的前提：见 K.1/K.4 两条裸跑
# 凡 `in <redacted>s` 都是被**归一化**掉的 pytest 墙钟：它每次重跑必不同，留下原值就是留一份不可复现的读数
#   （第八轮复审 id 1）。除这一处，段体里的读数全是命令的真实输出（标题与 `#` 注是我写的，不是读数）。

"""
    # 两段式落 L：先把 L 段连同占位符写进去，再跑 L 的命令，最后回填——这样 L 的读数描述的是
    # **交付出去的这一份**（含 L 自己），而不是它运行前那一刻还没写完的版本。
    m = run_cmd(f"python {RELPATH(pathlib.Path(__file__))} --self-test",
                "########## M 取命令与落盘通道自证：把手丢了仍取到同一条，取不到就 raise；写入要回读逐字相同",
                "# L 只数把手，M 判的是驱动自己的两条通道：第八轮复审 id 4 说「把某段命令换成 `$ 不是命令`，"
                "L 照样报无」——那条批评成立，所以补取命令这一档；本轮重放又撞到一次回填 `OSError [Errno 22]`"
                "（磁盘上留下 L 读数位还空着的半成品，而驱动照过），所以同一档里再判「写入必须回读逐字相同」。\n")
    body = header + "\n".join(rendered) + "\n" + j + "\n" + "\n".join(k_sections()) + "\n" + m
    err = write_out(body + "\n" + L_HEAD + "$ " + L_CMD + "\n" + PLACEHOLDER + "\n")
    if err:
        print(f"FAIL 交付：L 段还没落下去，拒绝交出半成品——{err}")
        return 1
    lr = subprocess.run([BASH, "-c", L_CMD], capture_output=True, text=True,
                        encoding="utf-8", errors="replace", cwd=ROOT, env=ENV)
    lout = ((lr.stdout or "") + (lr.stderr or "")).rstrip() + f"\nrc={lr.returncode}"
    err = write_out(OUT.read_text(encoding="utf-8").replace(PLACEHOLDER, lout))
    if err:
        print(f"FAIL 交付：L 的回填没成功，磁盘上不是这一份——{err}")
        return 1
    written = OUT.read_text(encoding="utf-8")
    print(lout)
    print(f"写出 {OUT}（{len(written.splitlines())} 行）｜回读逐字相同")
    return 0 if "缺 `$ ` 命令的段： 无" in written else 1


if __name__ == "__main__":
    # `--self-test` 只判取命令这条路（M 段跑的就是它），不重写留档；不带它才整份重放
    raise SystemExit(self_test() if "--self-test" in sys.argv[1:] else main())
