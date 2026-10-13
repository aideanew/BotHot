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

写留档这一步本身要回读，而且**按字节**回读（本轮实测撞过一次 `OSError [Errno 22]`：整份重放跑完、
最后一次回填炸掉，磁盘上留下带 `PLACEHOLDER_L_OUT` 的半成品，而驱动自己一声不吭地过）。见 `write_out` /
`write_ok` 与 M 段。第九轮复审 id 1 补的一课：回读如果走 `read_text`，磁盘上落成 CRLF 的文件解码后与意图
**逐字相同**，那道「逐字相同」的门会放行一份字节完全不同的留档——所以比对放在 `read_bytes` 层。
同一条复审还纠了两处话：`Errno 22` 的成因先前写成「win32 文件被瞬时占用」是猜的（本机实测被读柄持有
时覆盖写不抛），以及「最多试 5 次、每次等 0.3 秒」当时没有任何判据（`ATTEMPTS` 改 1 照样 PASS）。

还有一条依赖要写清（同一轮实测）：**A–I 段的命令是从上一版留档里取的**，所以把 `out_s213.txt` 删掉
就断了自举——不是「它可以从零生成」。删掉后驱动给 FAIL rc=1 并说明怎么恢复，而不是 traceback。
"""

from __future__ import annotations

import datetime
import inspect
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
# 解释器的对象表示里带内存地址（`<function <lambda> at 0x0000020594854400>`）。第十一轮复审在临时
# worktree 里整份重放、与在库留档逐行对比，抓到这处地址每次重跑必不同——它和墙钟是同一类读数，
# 当时却只归一化了墙钟。口径统一：两类都归一化，且都在文件头声明（声明里写了几个形状就得归一化几个）。
MEMADDR = re.compile(r"\b0x[0-9a-fA-F]{5,}\b")


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


#: 「最多试 5 次、每次之间等 0.3 秒」这两个数字。两条都由 M 段判（第九轮复审 id 2：把
#: `range(5)` 改成 `range(1)`、把 `sleep(0.3)` 改成 `sleep(0)`，`--self-test` 照样 rc=0 PASS
#: ⇒ 重试在那道门眼里是装饰）。现在「第 1、2 次写不进、第 3 次成功」是 M 段的一条真实用例。
#: 第十轮复审 10-3 补的是**剩下那一半**：M 段每条注入用例都传 `sleep=slept.append`，而 `main()`
#: 只按默认值调用 ⇒ 把签名里的 `sleep=time.sleep` 换成 `sleep=lambda _s: None` 时 20 条照样绿。
#: 所以 M 段现在既判注入通道，也判默认值本身（`inspect.signature` + 一发按墙上时钟量等待的默认重试）。
ATTEMPTS = 5
PAUSE = 0.3
BOM = b"\xef\xbb\xbf"
CRLF = b"\r\n"

#: 留档头部那句「判据条数」的**生产者**（第十轮复审 10-1：上一版它是模板字面量
#: `BD-1…BD-6 行为面、BD-7…BD-16 结构面`，没有任何命令产它——加一条 BD 判据，十九段读数全绿，
#: 只有头部在撒谎。这是同一类缺陷第四次复发，所以这次连头部一起纳入 `--self-test` 的判据面）。
BEH_LABEL = re.compile(r'^\s*out\.append\(\(\s*f?"(BD-\d+)\b', re.M)
STR_LABEL = re.compile(r'^\s*check\(\s*f?"(BD-\d+)\b', re.M)


def bd_ids(path: pathlib.Path | None = None) -> tuple[list[str], list[str]]:
    """从 harness 源码里数出登记在册的 BD 判据，返回 (行为面 id, 结构面 id)，各按号数排序。

    两条通道按**调用形状**分：行为面是 `out.append(("BD-N …", 条件, 原因))`（`_behavior_cases`
    交回样本对、由 `run()` 逐条下判），结构面是直接 `check("BD-N …", *判决)`。分开数是故意的：
    「判据条数恰好等于变异条数」那种蒙混在这一版头部里也没有藏身之处。
    """
    src = (path or EV / "prove_biz_delegation.py").read_text(encoding="utf-8-sig")
    lines = src.splitlines(keepends=True)
    beh = {m.group(1) for ln in lines if (m := BEH_LABEL.match(ln))}
    strct = {m.group(1) for ln in lines if (m := STR_LABEL.match(ln))}
    key = lambda s: int(s.split("-")[1])  # noqa: E731 - BD-2 要排在 BD-10 前面
    return sorted(beh, key=key), sorted(strct, key=key)


def bd_headline() -> str:
    """留档头部那句判据条数的正文，全部由 `bd_ids()` 现算（`ATTEMPTS`/`PAUSE` 同理，见 `main()`）。"""
    beh, strct = bd_ids()
    if not beh or not strct:  # 数不出来就不写一句好听的话，宁可在头部留下 FAIL 字样
        return f"# **判据条数：FAIL——从 harness 里数到行为面 {beh!r} / 结构面 {strct!r}，头部无从生成**"
    return (f"# **判据条数：{len(beh) + len(strct)} 条——行为面 {beh[0]}…{beh[-1]} {len(beh)} 条、"
            f"结构面 {strct[0]}…{strct[-1]} {len(strct)} 条（本行由 `bd_ids()` 现算，非手抄）**")


def write_ok(intent: str, raw: bytes) -> str:
    """写入算不算成功：**磁盘字节必须与要落下去的字节逐字节相同**。空串才算成，否则给原因。

    第二个参数是 `bytes` 不是文本，因为回读走 `read_bytes`。文本模式带通用换行翻译：磁盘上落成
    CRLF 的文件解码后与意图**逐字相同**，于是「逐字相同」这道门会放行一份字节完全不同的留档
    ——第九轮复审 id 1 实测：落盘换成 CRLF 后 `write_out` 返回空串（判成功），磁盘上 4 个 CR，
    `read_text` 看不出任何异常。所以比对放在字节层。

    四种坏形状分开给原因，因为后果与修法都不同（M 段逐个判**原因文本**，不只判「非空」——
    第九轮复审 id 3：只判非空时，半成品那条分支改成 `if False:` 也照样 PASS，因为通用分支
    顺手把话说了，等于那条反证不可假）：
    - CRLF = 内容对、字节不对。别写成「`git diff` 会整片变红」——本机 `core.autocrlf=true` 而
      `.gitattributes` 只钉了 `*.sh eol=lf`，第十轮复审 10-11 在临时仓库实测：纯 CRLF 化之后
      `git diff --stat` 反而是**空**的。所以这一类只能靠字节层看见，靠 diff 或文本回读都会漏；
    - BOM = 编码被改写；
    - 留着 `PLACEHOLDER_L_OUT` **而意图里没有** = **半成品冒充成品**（回填那一步失败时的形状，本轮
      真撞到过一次）；两个条件缺一不可——写入 #1 的意图本来就带占位符，只查盘上有没有就会误点它；
    - 其余 = 落下去的是另一个版本（截断、被并发写坏）。

    **分支顺序是 CRLF → BOM → 半成品，不是半成品在最前**（第十轮复审 10-4）：`main()` 的第一次
    写入里，意图**本身就**带着占位符（L 的读数位要等命令跑完才回填），所以只要字节不对，
    「磁盘上有占位符」这句话对 CRLF / BOM / 截断任何一种坏形状都成立——半成品排在最前时，
    生产写入点上另外三个原因永远不可达，实测把 `_disk_write` 退回文本模式（落 CRLF）后，
    驱动报的是「回填那一步没成功」，而磁盘上 CR=269、回填其实跑得好好的。裁决仍是红，诊断是错的。
    """
    want = intent.encode("utf-8")
    if raw == want:
        return ""
    text = raw.decode("utf-8", errors="replace")
    cr_count = raw.count(b"\r")
    if raw.replace(CRLF, b"\n") == want:
        return f"落下去的是 CRLF 版本（{cr_count} 个 CR）：内容解码后相同、字节不同，文本模式回读看不出来"
    if raw.startswith(BOM):
        head = raw[:len(BOM)]
        return f"落下去的带 BOM（前 {len(BOM)} 字节 {head!r}）：编码被改写"
    if PLACEHOLDER in text and PLACEHOLDER not in intent:
        # 这句**不许把占位标记本身打印出来**（第十一轮复审的 MAJOR）：这一条原因会变成 M 段的一行
        # 读数落进留档，而 L 的回填原先是对整份文件做全局替换——标记在段体里出现几次就被填几次，
        # 于是整段 L 输出被塞进另一条判据的读数里，且回读比对看不见（意图早已是污染后的串）。
        # 现在回填只认唯一一处（见 `main()`），这里也不再复制标记。
        return "磁盘上仍是半成品（留着 L 段读数位那个占位标记）——回填那一步没成功"
    return f"回读与写入不是同一份字节（写 {len(want)} 字节，读回 {len(raw)} 字节）"


def _disk_write(text: str) -> None:
    OUT.write_text(text, encoding="utf-8", newline="\n")


def _disk_read() -> bytes:
    return OUT.read_bytes()


def write_out(text: str, *, write=_disk_write, read=_disk_read, sleep=time.sleep,
              attempts: int = ATTEMPTS, pause: float = PAUSE) -> str:
    """落盘 + 按字节回读比对，最多试 `attempts` 次、每次失败之间等 `pause` 秒。

    成功返回空串，失败返回原因——**不 raise**：本项目「崩栈不是裁决」。

    这不是防御性口味：本轮整份重放跑完后，最后一次回填以 `OSError [Errno 22] Invalid argument`
    失败，驱动一声不吭地过，而磁盘上留下的是**带占位符的半成品**。「写出 431 行」这句话如果只由驱动
    自己声明，就和它要取代的那句「每一段都重放过」一样不可证——所以写完必须把内容读回来对一遍。
    第九轮复审 id 2 另外纠了一句话：原先把 `Errno 22` 解释成「win32 上文件被瞬时占用」，那是**猜的**，
    本机实测对不上——持普通读柄时覆盖写**不抛**（CPython 在 win32 不设 deny 模式），而这两类的真实形状是
    「目标是一个目录」⇒ `PermissionError [Errno 13]`、「名字含保留字符（`*`）」⇒ `OSError [Errno 22]`。
    两者都是 `OSError`，所以这道门的覆盖面按**异常族**声明、不按 errno 号声明；`pause` 只是给真·瞬时
    占用留一次机会（本机测不到这种占用，故不声称它救过谁）。

    `write`/`read`/`sleep` 可注入，生产路径全部用默认值。注入不是为了绕开磁盘，而是让
    「第 1 次失败、第 3 次成功」和「一直失败时要试满 5 次」这两种形状能在 M 段被真实驱动——
    否则「最多试 5 次」这句话永远假不了。
    """
    last = "没试过"
    for i in range(attempts):
        try:
            write(text)
            last = write_ok(text, read())
        except OSError as exc:  # 写不进，或写得进却读不回
            last = f"落盘或回读抛异常：{type(exc).__name__}: {exc}"
        if not last:
            return ""
        if i + 1 < attempts:
            sleep(pause)
    return last


def run_cmd(cmd: str, title: str, notes: str = "") -> str:
    r = subprocess.run([BASH, "-c", cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=ROOT, env=ENV)
    raw = ((r.stdout or "") + (r.stderr or "")).rstrip()
    out = MEMADDR.sub("0x<redacted>", TIMING.sub("in <redacted>s", raw))
    rc = r.returncode
    if rc == 2:
        # 三档退出码里最容易被读错的一档：2 是「压根没测到」，不是「测出红」。它在留档里必须
        # 明写出来，否则读者把 INCONCLUSIVE 当 1 读，就是拿「没测」冒充「测出不合格」。
        out += "\n**INCONCLUSIVE：判据没跑，别把这一档读成真红**"
    print(f"{title[:60]} … rc={rc}")
    return f"{title}\n{notes}$ {cmd}\n{out}\nrc={rc}\n"


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


def k_sections() -> tuple[list[str], list[str]]:
    """K 段六条（每台 harness 三条：裸跑 / 关 guard / 抽靶）。返回 (段文本, 缺陷清单)。

    临时副本没删干净是**缺陷**不是异常：上一版这里是裸 `assert`（第十轮复审 10-8），
    `python -O` 下整条被剥掉，驱动会一边留着 `_tmp_*` 一边打印「回读逐字节相同」。
    """
    chunks, defects, n = [], [], 0
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
        if (EV / leftover).exists():
            defects.append(f"K 段的临时副本没删干净：{leftover}")
    return chunks, defects


G24 = ROOT / "docs/06_validation/evidence/EVD-V2-00/g24_static_check.py"
G_TITLE = "########## G 仓库静态自检（E/F/I/W/UP/B 机检子集；文件清单由 glob 现算）"
G_TEST_FILES = ("apps/api/tests/test_kb_longlink_ingest.py", "apps/api/tests/test_article_identity.py")


def g_section() -> tuple[str, list[str]]:
    """G 段：仓库静态自检，**文件清单由 `EV/*.py` glob 现算**（第十轮复审 10-14）。返回 (段文本, 缺陷)。

    上一版这一串的七个文件名是我手改进留档的 `$ ` 行里的（`git show d80eeaf -- out_s213.txt`
    就能看到那行 `$` 被改过一次），后果是新入库的 `block_article_identity_plugin.py` 一直游离在
    门禁之外，而且没有任何命令判「清单与包内文件相符」。现在加一个 `.py` 进本包就自动进门禁。
    两处 `apps/api/tests` 文件是被检对象的另一端，不在本包，仍按名登记。

    **这一段的读数必须承重**（第十一轮复审 NIT①）：上一版它只是把 `g_section()` 的文本塞进留档，
    `defects` 一个字都不收——实测往本包放一份有违规的 `.py`，G 段自己记 `rc=1`、表里写「合计违规 1 条」，
    驱动整趟仍 rc=0 交付。静态门禁报了红而驱动绿，等于门禁只在正文里好看。现在三判：末行必须 `rc=0`、
    必须出现「合计违规 0 条」、表里 `===` 的份数必须等于命令里列出的份数（少一份就是 glob 与命令脱节）。
    """
    files = [RELPATH(p) for p in sorted(EV.glob("*.py"))]
    listed_names = [*G_TEST_FILES, *files]
    text = run_cmd(f"python {RELPATH(G24)} " + " ".join(listed_names), G_TITLE)
    defects: list[str] = []
    if not text.rstrip().endswith("rc=0"):
        defects.append(f"G 段静态自检没下绿裁决：末行 {text.rstrip().splitlines()[-1]!r}")
    if "合计违规 0 条" not in text:
        defects.append("G 段静态自检报的不是「合计违规 0 条」——门禁红了就不许交出绿留档")
    blocks = len(re.findall(r"(?m)^=== ", text))
    if blocks != len(listed_names):
        defects.append(f"G 段命令列出 {len(listed_names)} 份文件，表里只有 {blocks} 份——"
                       f"清单与被检结果脱节（glob 现算的那几份与写进命令的那几份不是同一批）")
    return text, defects


#: 段落来源登记表（第十轮复审 10-8 逼出来的显式数据结构）。
#: ARCHIVED = 命令从**上一版留档**里取、由驱动逐字重跑；CODE = 命令由本文件的代码现生成。
#: 上一版的写法是 `assert len(sections) == 9`：段数是个 magic number，改段式就得同步改它，
#: 而且它是裸 assert——`python -O` 下整条被剥掉，实测驱动照样写出一份缺了 H 段的留档并打印
#: 「回读逐字节相同」。现在期望段名取自这张表，缺一段、多一段都下得了裁决而不是 traceback。
ARCHIVED = ("A", "B", "C", "D", "E", "F", "H", "I")
CODE = ("G", "J", "K", "M", "N", "L")


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


def self_test(listing: bool = False) -> int:
    """M 段：判的不是留档内容，而是「驱动自己会不会静默交出一份假留档」这两条通道还在不在。

    第八轮复审 id 4 指出 L 段机检只看 `$ ` 把手在不在，把命令换成 `$ 不是命令` 它照样报「无」。
    所以取命令这件事另开反证：把手丢了仍能取到同一条命令、heredoc 要接配对、配对断了要 raise、
    整段无命令要 raise、取出来的是读数形状也要 raise（旧驱动正是栽在这一步，抄旧输出且不报错）。
    写入回读是本轮自己撞出来的第二条：整份重放跑完、最后一次回填抛 `OSError [Errno 22]`，磁盘上
    留下 L 读数位还空着的半成品——如果「写出 N 行」只是驱动自己的一句 print，半成品就能冒充成品。

    条数**不写死**：每跑一条判据都经 `check()` 记一笔账，末尾打印 `len(ran)` 与分组小计。
    这一版之前那句「11 条」是手抄的，同一批里 `j_attack_r7.py` 也写死过「10 发攻击」（实为 8+2）
    ——第九轮复审 id 7/8 两次都抓到同一类漂移，所以改成代码现算，句子与磁盘不可能再各说各话。
    第十轮复审 10-1 指出这句话只管到 M 段自己：留档**头部**那句「判据条数：16 条」还是字面量，
    于是新增第四组 `头部现算`——它判的正是「头部那个数是不是量出来的」（删一行判据，清单必须跟着变）。
    """
    ran: list[str] = []
    fails: list[str] = []

    def check(group: str, label: str, reason: str) -> None:
        """记一条反证的账：`reason` 非空即为红。分组名用来现算「取命令 n / 写入判据 n / 写入通道 n」。"""
        ran.append(f"{group}｜{label}")
        if reason:
            fails.append(f"[{group}] {label}：{reason}")

    def raises(body: str) -> str:
        """extract_cmd 在这类段体上必须 raise；返回文本就是当年「静默抄旧输出」的形状。"""
        try:
            got = repr(extract_cmd(body))
        except ValueError:
            return ""
        return f"本该 raise，实得 {got}"

    g1 = "取命令"
    with_handle = "\n# n\n$ python a.py --x\nout\nrc=0\n"
    no_handle = "\n# n\npython a.py --x\nout\nrc=0\n"
    check(g1, "把手在位取对", "" if extract_cmd(with_handle) == "python a.py --x" else repr(extract_cmd(with_handle)))
    check(g1, "把手丢了仍取到同一条",
          "" if extract_cmd(no_handle) == "python a.py --x"
          else "剥掉 `$ ` 把手就取不到——旧驱动先取走把手再输出，把手一丢便无命令可跑")
    heredoc = "\n$ python - <<'PY'\nprint(1)\nPY\nout\nrc=0\n"
    got_heredoc = extract_cmd(heredoc)
    check(g1, "heredoc 接配对到 PY",
          "" if got_heredoc == "python - <<'PY'\nprint(1)\nPY" else f"实得 {got_heredoc!r}")
    check(g1, "整段只剩注释与空行必须 raise", raises("\n# 只有注释\n\n"))
    check(g1, "heredoc 没有配对 PY 必须 raise", raises("\n$ python - <<'PY'\nprint(1)\nrc=0\n"))
    check(g1, "第一条非注释行是读数必须 raise", raises("\nrc=0\nout\n"))

    good = "# 段\n$ cmd\n某段的一条读数\nrc=0\n"
    good_b = good.encode("utf-8")
    g2 = "写入判据"
    check(g2, "字节逐位相同才算成", write_ok(good, good_b))
    half = good.replace("某段的一条读数", PLACEHOLDER).encode("utf-8")
    # 判**原因文本**而不是只判非空：只判非空时，`if PLACEHOLDER in text:` 改成 `if False:` 也照样 PASS
    # （通用「不一致」分支顺手把话说完），那条反证就不可假——第九轮复审 id 3。
    reason = write_ok(good, half)
    check(g2, "半成品给专属原因（点名「半成品」）", "" if "半成品" in reason else f"实得 {reason!r}")
    reason = write_ok(good, good_b[:-4])
    # 第十轮复审 10-9：原判据写成 `"字节" in reason`，而 CRLF 与 BOM 那两条原因里也带「字节」这个词
    # （实测都为真）——它验的是一个词，不是标签承诺的那个号数。现在把两个数写进期望串里。
    delta = f"写 {len(good_b)} 字节，读回 {len(good_b) - 4} 字节"
    check(g2, f"截断报出这两个号（{delta}）", "" if delta in reason else f"实得 {reason!r}")
    # 字节层独有的两类（文本回读看不出来，第九轮复审 id 1）：CRLF 与 BOM 必须各有判据、各点自己的名。
    reason = write_ok(good, good.replace("\n", "\r\n").encode("utf-8"))
    check(g2, "CRLF 版按字节判红（点名 CRLF）", "" if "CRLF" in reason else f"实得 {reason!r}")
    reason = write_ok(good, BOM + good_b)
    check(g2, "带 BOM 判红（点名 BOM）", "" if "BOM" in reason else f"实得 {reason!r}")
    # 生产写入点的形状（第十轮复审 10-4）：`main()` 第一次落盘时，意图**本身就带着**占位符
    # （L 的读数位要等命令跑完才回填）。半成品分支若排在 CRLF/BOM 之前，任何一种字节坏都塌成
    # 「回填没成功」——实测把 `_disk_write` 退回文本模式后 CR=269 却报半成品。裁决仍红，诊断是错的。
    site = good.replace("某段的一条读数", PLACEHOLDER)
    reason = write_ok(site, site.replace("\n", "\r\n").encode("utf-8"))
    check(g2, "意图自带占位符时坏在换行 ⇒ 仍须点名 CRLF（不许塌成「半成品」）",
          "" if "CRLF" in reason and "半成品" not in reason else f"实得 {reason!r}")
    # 同一支的第二档：**意图自己带占位符**时（写入 #1 的真实形状），盘上留不留占位符都不说明问题，
    # 半成品那条分支必须让位给真实原因——判据是「盘上有占位符 **且** 意图里没有」，两个条件缺一不可。
    site_b = site.encode("utf-8")
    reason = write_ok(site, site_b[:-4])
    check(g2, "意图自带占位符而盘上只是截断 ⇒ 报字节差，不许报半成品",
          "" if "半成品" not in reason and f"写 {len(site_b)} 字节，读回 {len(site_b) - 4} 字节" in reason
          else f"实得 {reason!r}")

    g3 = "写入通道"
    escaped: list[str] = []

    def safe(**kw) -> str:
        """调 `write_out` 并把**逃逸出来的异常**记进 `escaped`（第十轮复审 10-10 的第 ② 档）。

        `write_out` 的契约是「返回原因，不 raise」。把它的 `except OSError` 换成别的类时，
        原来这一整段会当场以 traceback 收场——一个裁决都读不到，正是本项目禁的形状。
        所以这一档不靠「崩了就算红」，而是自己判：任何一次注入式失败都不许把异常抛出门外。
        """
        try:
            return write_out(**kw)
        except Exception as exc:
            escaped.append(f"{type(exc).__name__}: {exc}")
            return ""

    # 两条端到端走真磁盘：把模块级 `OUT` 临时挪到系统临时目录，一次真写成、一次写不进。
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="rp_selftest_"))

    def land_crlf(text: str) -> None:
        (tmp / "liar2.txt").write_text(text.replace("\n", "\r\n"), encoding="utf-8", newline="\n")

    real_out = OUT
    try:
        globals()["OUT"] = tmp / "ok.txt"
        reason = safe(text=good)
        check(g3, "临时目录里真写成", reason)
        on_disk = (tmp / "ok.txt").read_bytes() if (tmp / "ok.txt").exists() else None
        check(g3, "磁盘上的字节就是这一份", "" if on_disk == good_b else f"write_out 说成功了，磁盘上是 {on_disk!r}")
        # 默认 `read` 走的那道口也要能抓 CRLF（第十轮复审 10-12）。下面「说谎的落盘」那发注入的是
        # `read=liar_target.read_bytes`，**绕开了** `_disk_read`——把 `_disk_read` 退回文本模式
        # （第九轮那条 MAJOR 的原样）时 M 段照样全绿，等于默认值没人判。这一发不注入 read。
        globals()["OUT"] = tmp / "liar2.txt"
        reason = safe(text=good, write=land_crlf)
        check(g3, "不注入 read 的那次 CRLF 必须照样报红（默认回读道口不是装饰）",
              "" if "CRLF" in (reason or "") else f"盘上是 CRLF 版而 write_out 返回 {reason!r}")
        # 指向目录本身：win32 实测抛 `PermissionError [Errno 13]`（早先注释写的 IsADirectoryError
        # 是没测过的猜测，第九轮复审 id 4）。这道门按 OSError 族收，所以只要求「报得出原因」。
        globals()["OUT"] = tmp
        check(g3, "目标是目录时必须报原因而不是静默过",
              "" if safe(text=good) else "落盘失败却被当成成功——半成品就能冒充成品")
    finally:
        globals()["OUT"] = real_out
        shutil.rmtree(tmp, ignore_errors=True)

    # 重试循环承重（第九轮复审 id 2）：第 1、2 次抛、第 3 次真写成 ⇒ 整体必须成功且磁盘上是那一份。
    # 把 `ATTEMPTS` 改成 1，这一条立刻红——「最多试 5 次」从不可假变成可假。
    tmp2 = pathlib.Path(tempfile.mkdtemp(prefix="rp_retry_"))
    target = tmp2 / "flaky.txt"
    tries: list[int] = []
    slept: list[float] = []

    def flaky_write(text: str) -> None:
        tries.append(1)
        if len(tries) < 3:
            raise PermissionError(13, "Permission denied")
        target.write_text(text, encoding="utf-8", newline="\n")

    reason = safe(text=good, write=flaky_write, read=target.read_bytes, sleep=slept.append)
    check(g3, "第 3 次才成功的写要救回来（ATTEMPTS 改 1 即红）", reason)
    landed = target.read_bytes() if target.exists() else None
    check(g3, "救回来时恰好试 3 次且落盘正确",
          "" if len(tries) == 3 and landed == good_b else f"试了 {len(tries)} 次，磁盘是 {landed!r}")
    check(g3, "两次失败之间各等 PAUSE 秒（PAUSE 归零即红）",
          "" if slept == [PAUSE, PAUSE] and PAUSE >= 0.2
          else f"实际等待 {slept!r}、PAUSE={PAUSE}——不等待的重试救不了任何瞬时占用")

    # 「说谎的落盘」：写调用没抛，但磁盘上落下来的不是那一份（CRLF 版，解码后逐字相同）。
    # 这一条判的是 `write_out` 有没有真的把磁盘读回来比——把 `last = write_ok(text, read())`
    # 换成 `last = ""` 时，前面所有判据照样绿（写进去的内容与意图无关地正确），只有这条会红。
    liar_target = tmp2 / "liar.txt"

    def lying_write(text: str) -> None:
        liar_target.write_text(text.replace("\n", "\r\n"), encoding="utf-8", newline="\n")

    reason = safe(text=good, write=lying_write, read=liar_target.read_bytes, sleep=lambda _s: None)
    check(g3, "落盘内容与意图不逐位相同时必须报红（回读真的取自磁盘）",
          "" if "CRLF" in (reason or "") else f"落下去的是 CRLF 版本，write_out 却返回 {reason!r}"
          "——它没有把磁盘读回来比")

    # 一直失败：必须试满 ATTEMPTS 次，且两类坏输入都要把异常类名带进原因（读者据此分辨形状）。
    for bad_exc in (OSError(22, "Invalid argument"), PermissionError(13, "Permission denied")):
        n: list[int] = []

        def always_fail(text: str, _e=bad_exc) -> None:
            n.append(1)
            raise _e

        reason = safe(text=good, write=always_fail, read=lambda: b"", sleep=lambda _s: None)
        name = type(bad_exc).__name__
        check(g3, f"{name} 一路试满 {ATTEMPTS} 次并报出类名",
              "" if len(n) == ATTEMPTS and name in (reason or "")
              else f"试了 {len(n)} 次，原因 {reason!r}")
    shutil.rmtree(tmp2, ignore_errors=True)

    check(g3, "注入的失败一次都不许把异常抛出门外（崩栈不是裁决）",
          "" if not escaped else f"{len(escaped)} 处逃逸，第一处：{escaped[0]}")

    # 默认参数自己也要有人判（第十轮复审 10-3）。上面每一条注入用例都传 `sleep=slept.append`
    # 或 `sleep=lambda _s: None`，而 `main()` 两处调用只给 `text` ⇒ 把签名里的
    # `sleep=time.sleep` 换成 `sleep=lambda _s: None` 时 20 条判据照样全绿——
    # 「每次失败之间真的等待」这句话在生产路径上一直是不可假的。两发堵死：
    # ① 默认值本身就是那个可调用对象；② 一发**只注入 write** 的失败重试，按墙上时钟量等待。
    params = inspect.signature(write_out).parameters
    check(g3, "默认 sleep 就是 time.sleep（生产路径等的是真时钟，不是被换成空函数）",
          "" if params["sleep"].default is time.sleep else f"默认值实为 {params['sleep'].default!r}")
    check(g3, f"默认 attempts/pause 就是模块级 ATTEMPTS/PAUSE（{ATTEMPTS}/{PAUSE}）",
          "" if params["attempts"].default == ATTEMPTS and params["pause"].default == PAUSE
          else f"实得 {params['attempts'].default}/{params['pause'].default}")
    ticks: list[int] = []

    def never_lands(text: str) -> None:
        ticks.append(1)
        raise OSError(22, "Invalid argument")

    t0 = time.monotonic()
    reason = safe(text=good, write=never_lands)
    waited = time.monotonic() - t0
    floor = (ATTEMPTS - 1) * PAUSE * 0.6
    check(g3, f"只注入 write 的默认重试：试满 {ATTEMPTS} 次且耗时 ≥ {floor:.2f}s 且报得出原因",
          "" if len(ticks) == ATTEMPTS and waited >= floor and reason
          else f"试了 {len(ticks)} 次、耗时 {waited:.2f}s、原因 {reason!r}")

    # 头部那句「判据条数」（第十轮复审 10-1）。它原先是模板字面量，没有任何命令产它：
    # 加一条 BD 判据，留档每一段读数照样绿，只有头部在撒谎——同一类缺陷第四次复发。
    # 现在 `bd_ids()` 从 harness 源码现数，而这三条判据保证「现数」不是又一句叙述：
    # 前两条判清单自己的形状，第三条**真的删一行**再看清单跟不跟着变（`return` 写成常量的话，
    # 第三条立刻红）。
    g4 = "头部现算"
    beh_ids, str_ids = bd_ids()
    check(g4, "行为面 id 从 BD-1 起连续（否则头部那句区间不是人话）",
          "" if beh_ids == [f"BD-{i}" for i in range(1, len(beh_ids) + 1)] else f"实得 {beh_ids!r}")
    check(g4, "结构面非空、与行为面不相交（合计就是头部那个数）",
          "" if str_ids and not set(beh_ids) & set(str_ids) else f"行为 {beh_ids!r} 结构 {str_ids!r}")
    # 第十一轮复审 10-1 的残余：头部那句写的是两个**区间**（`BD-1…BD-6` 与 `BD-7…BD-16`），
    # 而当时只判了行为面区间连续——结构面若从 BD-9 起跳，头部照样拼出「BD-7…BD-16」却与磁盘不符。
    check(g4, "两个区间首尾相接、合起来是 BD-1…BD-N（头部那两句区间才是人话）",
          "" if beh_ids + str_ids == [f"BD-{i}" for i in range(1, len(beh_ids) + len(str_ids) + 1)]
          else f"拼接实得 {(beh_ids + str_ids)!r}")
    tmpd = pathlib.Path(tempfile.mkdtemp(prefix="bd_head_"))
    try:
        src_lines = (EV / "prove_biz_delegation.py").read_text(encoding="utf-8-sig").splitlines(keepends=True)
        drop = next((i for i, ln in enumerate(src_lines) if STR_LABEL.match(ln)), None)
        if drop is None:
            check(g4, "找得到可删的结构判据行", "harness 里一条结构判据都没数到，清单无从反证")
        else:
            gone = STR_LABEL.match(src_lines[drop]).group(1)
            harness = tmpd / "harness.py"
            harness.write_text("".join(src_lines[:drop] + src_lines[drop + 1:]), encoding="utf-8")
            beh2, str2 = bd_ids(harness)
            check(g4, f"删掉 {gone} 那一行 ⇒ 清单必须正好少它一条、行为面不受影响",
                  "" if str2 == [s for s in str_ids if s != gone] and beh2 == beh_ids
                  else f"删了 {gone} 仍得 结构{str2!r} 行为{beh2!r}")
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)

    groups: dict[str, list[str]] = {}
    for item in ran:
        group, label = item.split("｜", 1)
        groups.setdefault(group, []).append(label)
    if listing:
        # 给反证电池enumerate判据用的机器可读档（每行 `组｜判据名`）。电池拿它算「哪些判据至今
        # 没有一发能把它打红的变异」——没有这一档，那句「每条判据都配了变异」就只能是形容词。
        for item in ran:
            print(item)
        return 1 if fails else 0
    tally = "；".join(f"{k} {len(v)} 条（{'、'.join(v)}）" for k, v in groups.items())
    for f in fails:
        print(f"FAIL 重放器自证：{f}")
    if fails:
        print(f"红 {len(fails)} 条 / 共跑 {len(ran)} 条判据")
        return 1
    print("OK   重放器自证：取命令按段落版式而非 `$ ` 把手，把手丢了照样取到同一条；"
          "整段无命令 / heredoc 配对断了 / 第一条非注释行是读数 ⇒ 三种情况一律 raise；"
          "写留档按**字节**回读逐位相同，CRLF / BOM / 半成品 / 截断四种各有专属原因（半成品排在"
          "字节层两类之后，因为生产写入点的意图本来就带占位符），"
          f"重试要真的试满 {ATTEMPTS} 次、每次之间真的等 {PAUSE} 秒（注入通道与默认值各判一次），"
          "写不进磁盘时报原因而不是静默过；头部那句判据条数由 `bd_ids()` 从 harness 现数")
    print(f"SELF-TEST PASS：{len(ran)} 条反证全过（{tally}）"
          f"——取不到命令时驱动停下，落不进磁盘时驱动也停下，两种都不许抄旧输出")
    return 0


def main() -> int:
    if not OUT.exists():
        # 自举依赖：A–I 段的命令是从**上一版留档**里取的，留档不在就无命令可跑。本轮实测把
        # `out_s213.txt` 删掉后，驱动直接以 `FileNotFoundError` traceback 收场——那不是裁决，按项目纪律落 FAIL。
        print(f"FAIL 交付：{OUT} 不存在——A–I 段的命令取自这份留档，它没了就断链；"
              f"先 `git checkout -- {RELPATH(OUT)}` 恢复再重放（G/J/K/M/N/L 几段不依赖它）。")
        return 1
    sections = [(t, b) for t, b in split_sections(OUT.read_text(encoding="utf-8"))
                if re.match(r"^########## [A-I] ", t)]
    want = sorted([*ARCHIVED, "G"])  # G 在旧留档里也是归档段，只是从本轮起命令改由 `g_section()` 现生成
    found = sorted(t.split()[1] for t, _ in sections)
    if found != want:
        print(f"FAIL 交付：留档的 A–I 段与登记表不符——期望 {want}，实得 {found}；"
              f"某一段的标题被改过或丢了，重放会静默少跑一段，拒绝交出这份留档")
        return 1
    rendered, defects = [], []
    for title, body in sections:
        letter = title.split()[1]
        if letter == "G":
            g_text, g_defects = g_section()
            rendered.append(g_text)
            defects += g_defects
            continue
        try:
            cmd = extract_cmd(body)
        except ValueError as exc:
            defects.append(f"{letter} 段取不到命令：{exc}")
            continue
        rendered.append(run_cmd(cmd, title))

    j = run_cmd(f"python {RELPATH(EV / 'j_attack_r7.py')}",
                "########## J 第七轮复审的闭合实测：四发「def 还在但活绑定已换」+ 四发「调用点在但结果不进锚」+ 两发崩栈面",
                "# 驱动是**入库件** `j_attack_r7.py`（改前版 harness 由 `git show de78125:…` 取，改后即本包这一版）。\n"
                "# 上一版把整份攻击脚本原样内嵌进本文件，代价是留档与在库驱动各一份、会漂移；现在命令就是驱动本身\n"
                "# （原先那句「这 92 行」是个没量过的历史数——第十轮复审 10-1，已删；行数要看得 `wc -l` 现量）。\n"
                "# 临时件两个（探针 harness、kb 攻击副本）都由驱动自己删，J-11/J-12 是回读。\n")
    probe = EV / "_harness_prefix_r7.py"
    if probe.exists():
        defects.append(f"J 段跑完后探针 harness 仍在：{probe}")
    k_chunks, k_defects = k_sections()
    defects += k_defects
    if defects:
        # 崩栈不是裁决，但「有缺陷还继续写留档」也不是：这三处（取不到命令 / K 或 J 的临时件没删）
        # 都说明这一趟重放没跑完，写下去就是一份缺段的留档冒充十九段。
        for d in defects:
            print(f"FAIL 交付：{d}")
        return 1

    ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")[:25]
    hh = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                        capture_output=True, text=True, env=ENV, cwd=ROOT).stdout.strip()
    # HEAD 之外到底还带不带未提交改动，是让 `git status` 说的，不是我抄的（第八轮复审 id 7：
    # 上一版把「+工作区未提交改动」和 Python 版本号写死在模板里，在干净工作树上跑也会自称有改动）
    # 计数口径也要说清（第九轮复审 id 5）：本留档只担保 `docs/06_validation` + `apps/api` 两条路径，
    # 全仓库另有未跟踪项时（`_workspace/`、规划目录……），只报范围内的数字会让人以为整棵树干净。
    # 两个**历史**实测形状：dcb1ffb 那次重放时工作区有 7 个待提交文件，头部只报「6 项」（步卡在
    # `docs/任务规划V0.3.0/` 下，不在担保路径里）——所以「范围内」与「全仓库」两句话分开说，各自带号数。
    # 本轮这一趟跑出来的号数**不在注释里抄**（第十轮复审 10-5：上一版把「现在再跑则是范围内 0 项 /
    # 全局 3 项」写死在这里，同一次提交里留档第 2 行却是「5 项 / 8 项」，两句话当场互相矛盾；
    # 抄来的工作区形状一 commit 就腐烂）——要看就读本文件生成物的第 2 行，那才是 `_porcelain` 现算的。
    def _porcelain(*pathspec: str) -> int:
        args = ["git", "status", "--porcelain"]
        if pathspec:
            args += ["--", *pathspec]
        r = subprocess.run(args, capture_output=True, text=True, env=ENV, cwd=ROOT)
        return len([ln for ln in (r.stdout or "").splitlines() if ln.strip()])

    scoped, total = _porcelain("docs/06_validation", "apps/api"), _porcelain()
    if scoped:
        state = f"范围内（docs/06_validation + apps/api）未提交 {scoped} 项｜全仓库未提交 {total} 项"
    elif total:
        state = f"范围内干净｜全仓库另有 {total} 项未提交，本留档不担保它们"
    else:
        state = "工作树干净（全局 `git status --porcelain` 为空）"
    pyv, plat = sys.version.split()[0], sys.platform
    head_bd = bd_headline()  # 第十轮复审 10-1：这一句从前是模板字面量，加一条判据它不会跟着变
    head_retry = f"重试要真的试满 {ATTEMPTS} 次且每次之间真的等 {PAUSE} 秒（注入通道与默认值各判一次）"
    head_causes = "CRLF / BOM / 半成品 / 截断四种各有专属原因（按这个顺序判）"
    header = f"""# STEP-02 S2.1.3 执行留档（kb._biz_from_url 委托解析层）
# 时间 {ts}｜HEAD={hh}｜{state}｜Python {pyv}｜{plat}
# 本机依赖实测：structlog / sqlalchemy 皆无（kb.py:22-25 模块级导入）⇒ D 段只能证明「收集期即失败」，用例本身交 CI（J-5）
{head_bd}
#   本文件每一段的命令都由**在库件** `replay_s213.py` 逐字重跑生成（`python docs/06_validation/evidence/
#   EVD-V2-02/replay_s213.py`）。两道自检收尾：L 段机检「每段都留得下一条 `$ ` 命令」（只判把手在不在），
#   M 段机检驱动自己的两条通道（取命令：把手丢了仍取到同一条、取不到就 raise；落盘：写入必须按**字节**回读
#   逐位相同——{head_causes}，{head_retry}。
#   本轮重放就撞到过一次回填 `OSError [Errno 22]` 而驱动照过；那句 Errno 22 的成因**不再写成「瞬时占用」**：
#   本机实测「被读柄持有」时覆盖写不抛，能稳定抛 Errno 22 的是 win32 保留字符名、抛 Errno 13 的是目标为目录）。
#   上一版留档这些都做不到：驱动放在不入库的 `_workspace/` 里、按 `$ ` 前缀找命令又在输出时剥掉前缀，
#   前缀一丢就**不跑而直接抄旧输出**且不报错
#   ——这条账记在 README §4.9 S-2 / §4.10 与卡面差异表 D-11/D-12。
# G 段的被检文件清单由 `EV/*.py` **glob 现算**，不再是我抄进 `$ ` 行的七份（第十轮复审 10-14）；
#   这一段自己承重（第十一轮复审 NIT①）：驱动核对「命令里列出的份数 == 表里 `===` 的份数」且末行必须
#   `rc=0`、必须出现「合计违规 0 条」，任何一条不符都进缺陷清单、整趟 rc=1——上一版 G 报了红而驱动照样绿
# 每段 `$` 行就是**逐字可重跑**的单行命令（heredoc 段用 `python - <<'PY' … PY`，在 git bash 下、仓库根跑）
# 判据计数口径：BD-15 排在最前打印（它是行为面六条的前提），编号仍按追加顺序，不打乱既有 BD 编号的锚
# `PYTHONIOENCODING=utf-8` 现在只影响输出**好不好读**，不再是脚本**活不活得下来**的前提：见 K.1/K.4 两条裸跑
# 段体里有**三类**读数不是命令的原样输出，都在 `run_cmd()` 里统一处理，声明与实现一一对应：
#   ① pytest 墙钟 `\bin \d+\.\d+s\b` → `in <redacted>s`（每次重跑必不同，留原值就是留一份不可复现的读数，
#      第八轮复审 id 1）；② 解释器对象表示里的内存地址 `0x…` → `0x<redacted>`（同一类「每次必不同」，
#      第十一轮复审 NIT③ 抓到上一版只归一化了①却写着「除这一处全是真实输出」）；
#   ③ 任何一档 `rc=2` 时末行补一句 `**INCONCLUSIVE…**` 标注——那是「压根没测到」，不能让人读成真红。
#   除这三处，段体里的读数全是命令的真实输出（标题与 `#` 注是我写的，不是读数）。

"""
    # 两段式落 L：先把 L 段连同占位符写进去，再跑 L 的命令，最后回填——这样 L 的读数描述的是
    # **交付出去的这一份**（含 L 自己），而不是它运行前那一刻还没写完的版本。
    m = run_cmd(f"python {RELPATH(pathlib.Path(__file__))} --self-test",
                "########## M 取命令与落盘通道自证：把手丢了仍取到同一条，取不到就 raise；写入按字节回读逐位相同",
                "# L 只数把手，M 判的是驱动自己的两条通道：第八轮复审 id 4 说「把某段命令换成 `$ 不是命令`，"
                "L 照样报无」——那条批评成立，所以补取命令这一档；本轮重放又撞到一次回填 `OSError [Errno 22]`"
                "（磁盘上留下 L 读数位还空着的半成品，而驱动照过），所以同一档里再判「写入必须回读比对」。\n"
                "# 第九轮复审又给了三条，都已落地：① 回读要走 `read_bytes`——文本模式带换行翻译，"
                "磁盘落成 CRLF 时解码后与意图**逐字相同**，旧判据照样放行（实测 `write_out` 返回空串＝判成功）；"
                "② 「最多试 5 次 / 每次等 0.3 秒」当时没人判，`ATTEMPTS` 改 1、`sleep` 改 0 都仍 PASS，"
                "现在「第 3 次才成功」与「总失败要试满 5 次」是 M 段的真实用例；③ 半成品那条反证只判「原因非空」，"
                "把分支删掉也照样绿，现在逐个点名原因（CRLF / BOM / 半成品 / 截断）。"
                "条数由 `check()` 现算并打印分组，不再手抄。\n"
                "# 第十轮复审又给了三条，都在这一档里判到了：① 留档**头部**那句「判据条数：16 条」原先是"
                "模板字面量（加一条 BD 判据它不会跟着变）⇒ 现在由 `bd_ids()` 从 harness 现数，并有一发反证"
                "**真的删掉一行判据**看清单跟不跟着变（把它写成 `return` 常量立刻红）；② 上面每条注入用例"
                "都自己传 `sleep=`，而 `main()` 两处调用只用默认值 ⇒ 默认 `sleep=time.sleep` 与「试满 "
                f"{ATTEMPTS} 次、等满 {(ATTEMPTS - 1) * PAUSE:.1f} 秒」的墙上时钟现在各有一条判据；"
                "③ `write_ok` 的四种原因原先把「半成品」排在最前，而生产写入点的意图**本身就带**占位符 "
                "⇒ 任何一种字节坏都塌成同一句「回填没成功」（实测：`_disk_write` 退回文本模式后盘上 CR=269，"
                "报的却是半成品），现在按生产形状调序，两种形状各一发判据。\n")
    # N 段：本轮新判据的「改坏必须红 / 等价不许假红」电池。它必须在留档落盘**之前**跑——
    # 电池会把整个证据包（含 out_s213.txt）拷进临时目录，拷到半成品就等于把半成品当成了基准。
    n = run_cmd(f"python {RELPATH(EV / 'mutate_replay_r9.py')}",
                "########## N 反证电池：M 段每条判据都要有一发能把它打红的变异（覆盖率现算，缺一条就 rc≠0）",
                "# 这一段的存在理由：第九轮报回的两条 MAJOR，恰好是上一版电池的读数**证明不了**的"
                "（回读走文本模式 ⇒ CRLF 能骗过；`ATTEMPTS`/`PAUSE` 没人判 ⇒ 改 1 改 0 照样 PASS）。\n"
                "# 所以本轮每条新判据先发变异确认能红，再发等价写法确认不假红；变异锚找不到时报 FAIL 而不是跳过"
                "（锚点漂了就等于这条反证被悄悄注销）。\n"
                "# 第十轮复审对着电池自己提了四条，都已落地：① 它原先只比 rc，**基线没绿也会让十发变异"
                "全报 OK**（实测：注入一条无关的红之后 10 发照样 OK）⇒ 现在先跑一次未变异的副本，"
                "不绿就整批判 INCONCLUSIVE（rc=2，不是 0 也不是 1）；② 每发变异还要**红在该红的判据组**，"
                "只「碰巧崩在别处」不算堵住；③ `N-iso` 那两行原先只是打印、没有判据（G-23）⇒ 现在"
                "隔离探测器自己被反证一次（故意改临时副本必须报红）；④ 它自己没有编码 guard，"
                "标签里出现 `⇒` 就整段崩在 cp936 输出流上 ⇒ 补 `_ensure_utf8_stdout()` 并让第十轮的"
                "新判据各带一发变异。文件名保留 `mutate_replay_r9.py`（第十轮只是扩它，不是另起一个）。\n"
                "# 第十一轮复审又对着电池自己提了三条，都已落地：① 它把 `rc≠0` 一律折成 RED，所以「崩在别处」"
                "与 rc=2（判据压根没跑）都会伪装成「这一发变异打中了」⇒ 现在三档分开读，rc=2 或 rc≠0 却一条"
                "可读 FAIL 都没有的都判 INCONCLUSIVE；② 末句「每条判据都有能把它打红的变异」当时是形容词"
                "（M 有 30 条，变异只有 17 发）⇒ 现在电池先跑 `replay_s213.py --list-checks` 拿到判据全清单，"
                "再按每一发红出来的 `[组] 判据名` 记账，末尾报「覆盖 n / 共 m 条」并把没有变异的判据**点名列出**，"
                "少一条就 rc≠0；③ 编码三发全绿时原先一声不出（等于注销），绿档不可证 ⇒ 现在三发各自把实得"
                "读数打出来（裸跑 rc、关 guard rc、抽靶后 rc），锚点不命中也逐发报而不只在批级兜。\n")
    body = header + "\n".join(rendered) + "\n" + j + "\n" + "\n".join(k_chunks) + "\n" + m + "\n" + n
    err = write_out(body + "\n" + L_HEAD + "$ " + L_CMD + "\n" + PLACEHOLDER + "\n")
    if err:
        print(f"FAIL 交付：L 段还没落下去，拒绝交出半成品——{err}")
        return 1
    lr = subprocess.run([BASH, "-c", L_CMD], capture_output=True, text=True,
                        encoding="utf-8", errors="replace", cwd=ROOT, env=ENV)
    lout = ((lr.stdout or "") + (lr.stderr or "")).rstrip() + f"\nrc={lr.returncode}"
    # 回填是**定位**而不是全局替换（第十一轮复审的 MAJOR）：上一版 `read_text().replace(标记, lout)`
    # 没有 `count=1`，而 `write_ok` 的半成品原因里当时正好打印着这个标记——那一行作为 M 段读数已经
    # 落进留档，于是全局替换把整段 L 输出塞进了另一条判据的读数中间（在库的 `out_s213.txt` N-11 那发
    # 就是事故现场），而字节回读比不出来：写下去的意图本身就是污染后的串。现在两处一起堵：
    # 读数里不再出现标记（见 `write_ok`），且这里要求「磁盘上恰好一处」，多一处就拒绝交付而不是静默自我污染。
    pending = OUT.read_text(encoding="utf-8")
    slots = pending.count(PLACEHOLDER)
    if slots != 1:
        print(f"FAIL 交付：L 读数位的占位标记在磁盘上有 {slots} 处，应为恰好 1 处——"
              f"多出来的那一处是某段读数把标记打印了出来，回填会把它一起替换掉（自我污染）；"
              f"少出来的那一处是 L 段没落下去。两种都不许交出这份留档")
        return 1
    err = write_out(pending.replace(PLACEHOLDER, lout, 1))
    if err:
        print(f"FAIL 交付：L 的回填没成功，磁盘上不是这一份——{err}")
        return 1
    written = OUT.read_text(encoding="utf-8")
    # 第二张登记表在这里承重（第十一轮复审 MINOR⑤：`CODE` 当时只被赋值、从不被读，
    # 而文档却写着「用 ARCHIVED/CODE 两张注册表核对」——G-23 禁的就是这种永不失败的断言）。
    # 输入侧的 `found != want` 只保证**旧留档**里 A–I 齐；这一条保证**交出去的这一份**
    # 归档段 + 现生成段一个都不少，`python -O` 那种「缺整段却报逐字节相同」的形状落在它身上。
    got_letters = sorted({m.group(1) for m in re.finditer(r"(?m)^########## ([A-Z]+)", written)})
    want_letters = sorted({*ARCHIVED, *CODE})
    if got_letters != want_letters:
        print(f"FAIL 交付：落下去的留档段集合与两张登记表不符——期望 {want_letters}，实得 {got_letters}"
              f"（缺的那几段是没跑还是被剥掉了，看标题；这一趟不能当成交付）")
        return 1
    print(lout)
    print(f"写出 {OUT}（{len(written.splitlines())} 行、{len(got_letters)} 段）｜"
          f"回读逐字节相同（比对走 `read_bytes`，不经换行翻译）")
    return 0 if "缺 `$ ` 命令的段： 无" in written else 1


if __name__ == "__main__":
    # `--self-test` 只判取命令这条路（M 段跑的就是它），不重写留档；不带它才整份重放；
    # `--list-checks` 只把 M 段那批判据按 `组｜判据名` 打一份清单，给反证电池算覆盖率用
    _args = sys.argv[1:]
    raise SystemExit(self_test(listing="--list-checks" in _args)
                     if ("--self-test" in _args or "--list-checks" in _args) else main())
