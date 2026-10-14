"""重放器：把 `out_s213.txt` 每一段记录的命令**真正重跑一遍**，整份重写证据文件。

跑法（仓库根）：`PYTHONIOENCODING=utf-8 python docs/06_validation/evidence/EVD-V2-02/replay_s213.py`

为什么它必须待在本包里而不是临时目录里：上一版驱动放在 `_workspace/`（不入库），于是
「每次改 harness 都要重跑它」这条纪律只剩 README 里的一句话——驱动一丢，留档就再也无法自证被重放过。

它自己也是被第八轮那批账教训出来的（见 README §4.9 S-2）：更早那版按 `^$ ` 前缀找命令、输出时又剥掉前缀，
前缀一丢就**不跑而直接抄旧输出**，且不报错。现在按段落版式取命令（标题后第一条非 `#` 非空行，
heredoc 取到配对的 `PY`），输出时统一补 `$ `，并在收尾加 L 段机检「每一段都留得下一条 `$ ` 命令」。
L 那条机检判的是**把手在不在**，不是**命令跑不跑得起**（把某段的命令换成 `$ THIS IS NOT A COMMAND`
它照样说「无」）——所以它只保证「读者知道该重跑什么」，取命令这件事本身的正确性由 M 段
（本文件 `--self-test`）判：剥掉 `$ ` 前缀仍能取到同一条命令，且**没有命令的段落必须 raise**，
返回空值就是当年「静默抄旧输出」的形状。

A–I 从文件里取命令重放（登记表 `ARCHIVED`）；J 由 `j_attack_r7.py` 现跑；K 是编码自证的现跑
（每台 harness 三条，台数在 `K_HARNESSES`）；M 是本驱动器 `--self-test` 的现跑；N 是反证电池；
O 是 S2.1.4/S2.1.5 那台锚定/兜底证明台的现跑；L 现跑并回填——除 A–I 外的段都由 `CODE` 这张表登记。
它写什么必须写清（第八轮复审 id 4）：**它会重写本包内被跟踪的 `out_s213.txt`**，K 段里「关 guard」与
「抽靶」那两类 `sed` 命令还会对每台 harness 在本包目录里各落一个用完即删的临时副本
（`_tmp_ng.py`、`_tmp_noarrow.py`；同一段里的回读就是它们的删除证明，跑完仍在就是缺陷）。
它**不写任何被测文件**：A 段的 kb 临时副本写在 kb.py 同目录并当场 unlink，J 段的探针 harness 跑完即删。

写留档这一步本身要回读，而且**按字节**回读（第八轮当时实测撞过一次 `OSError [Errno 22]`：整份重放跑完、
最后一次回填炸掉，磁盘上留下带 `PLACEHOLDER_L_OUT` 的半成品，而驱动自己一声不吭地过）。见 `write_out` /
`write_ok` 与 M 段。第九轮复审 id 1 补的一课：回读如果走 `read_text`，磁盘上落成 CRLF 的文件解码后与意图
**逐字相同**，那道「逐字相同」的门会放行一份字节完全不同的留档——所以比对放在 `read_bytes` 层。
同一条复审还纠了两处话：`Errno 22` 的成因先前写成「win32 文件被瞬时占用」是猜的（本机实测被读柄持有
时覆盖写不抛），以及「最多试 5 次、每次等 0.3 秒」当时没有任何判据（`ATTEMPTS` 改 1 照样 PASS）。

还有一条依赖要写清（同一轮实测）：**A–I 段的命令是从上一版留档里取的**，所以把 `out_s213.txt` 删掉
就断了自举——不是「它可以从零生成」。删掉后驱动给 FAIL rc=1 并说明怎么恢复，而不是 traceback。
"""

from __future__ import annotations

import ast
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
# 段落标题里的 `⇒` 在 win32 默认 cp936 输出流上编不出来（本项目禁的「没有裁决」第三态，与两份
# harness 同一个症状），所以先钉输出流。再往下是**读数归一化登记表**：一张表同时管三件事——
# `apply_norm()` 按它改写段体、M 段按它发正反两档判据、留档头部那句「命中 N 处」按它现算。
# 为什么每行都带「必须命中」与「必须不命中」两个样本（第十二轮复审 B3）：上一版头部用模板字面量
# 写着「段体里有三类读数……都在 `run_cmd()` 里统一处理」，而实测在库留档里 `0x<redacted>`
# **一处都没有**（墙钟那式 2 处、③ 的标注 1 处）——「处理了」这句话只能靠留档恰好含有那个形状
# 才谈得上被证，留档里没有就永远假不了（G-23）。现在每条规则自带靶子，不跑子进程也能把
# 「命中」与「不该命中」两档都试出来；`0x12` 那种短串是故意留在反例里的（阈值 5 位不是装饰）。
NORMALIZATIONS = (
    # (类名, 正则, 替换文本, 必须命中的样本, 必须不命中的样本)
    ("墙钟", r"\bin \d+\.\d+s\b", "in <redacted>s", "in 12.34s", "in 5s"),
    ("内存地址", r"\b0x[0-9a-fA-F]{5,}\b", "0x<redacted>",
     "<function x at 0x7ffa1b2c3d40>", "<function x at 0x12>"),
)
# 解释器的对象表示里带内存地址（`<function <lambda> at 0x0000020594854400>`）。第十一轮复审在临时
# worktree 里整份重放、与在库留档逐行对比抓到它每次重跑必不同——它和 pytest 汇总行的墙钟是同一类
# 读数，当时却只归一化了墙钟。口径统一：登记表里有几条，头部就得报几条的命中处数。
INCON = "rc=2 补注"
INCON_MARK = "**INCONCLUSIVE：判据没跑，别把这一档读成真红**"
NORM_CLASSES = tuple(name for name, *_ in NORMALIZATIONS) + (INCON,)
NORM_RE = {name: re.compile(pat) for name, pat, *_ in NORMALIZATIONS}
# 每段命令输出的命中处数在这里累加，头部那句「命中现算」读它；M 段用**另开的字典**驱动同一个函数。
NORM_HITS: dict[str, int] = {name: 0 for name in NORM_CLASSES}


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
#: 只有头部在撒谎。这是同一类缺陷第四次复发，所以那一轮起连头部一起纳入 `--self-test` 的判据面）。
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


#: 第二台 harness（S2.1.4/S2.1.5）的判据登记形状：`CHECKS` 里每条都是 `("AF-Xn", 标签, 判据函数)`。
#: 与 BD 那两条正则不同——AF 台把判据集中在一张元组表里登记，所以头部按表数，不按调用点数。
#: 号数分三段捕获（前缀 / 面字母 / 数字）：`AF-P0` 的数字在第三个分组里，早期版本按 BD 的
#: 两段形状 `int(s.split("-")[1])` 取号 ⇒ 第十三轮（`078dc30`）实测驱动在 `o_section()` 里抛
#: `ValueError: invalid literal for int() with base 10: 'P0'` 收场（崩栈不是裁决，见 M 段 锚定台现算）。
AF_LABEL = re.compile(r'^\s+\("(AF)-([A-Z])(\d+)"')
AF_GROUP_NAME = {"P": "前提面", "B": "锚定行为面", "A": "片段行为面", "S": "结构面"}


def af_ids(path: pathlib.Path | None = None) -> dict[str, list[str]]:
    """从 `prove_anchor_fallback.py` 的 `CHECKS` 登记表里现数 AF 判据，按面分组、组内按号数排序。"""
    src = (path or EV / "prove_anchor_fallback.py").read_text(encoding="utf-8-sig")
    groups: dict[str, list[tuple[int, str]]] = {}
    for ln in src.splitlines():
        m = AF_LABEL.match(ln)
        if m:
            groups.setdefault(m.group(2), []).append((int(m.group(3)), f"AF-{m.group(2)}{m.group(3)}"))
    return {k: [i for _, i in sorted(set(v))] for k, v in groups.items()}


def _af_num(af_id: str, letter: str) -> int | None:
    """取 `AF-<面字母><号数>` 的号数；形状不符返回 None。

    这里**不抛**是有意的：第十三轮实测过一发 `int("P0")` 的 `ValueError`，驱动以 traceback 收场、
    一个裁决都读不到——正是项目纪律禁的那第三种形态。None 让判据自己变红。
    """
    tail = af_id[len(f"AF-{letter}"):] if af_id.startswith(f"AF-{letter}") else ""
    return int(tail) if tail.isdigit() else None


def af_headline(path: pathlib.Path | None = None) -> str:
    """头部那句 AF 判据条数：全部由 `af_ids()` 现算，四个面没齐就写下 FAIL 而不是写句漂亮话。

    这一行存在的理由和 BD 那一行一样（第十轮复审 10-1 的第四次复发）：模板字面量里的号数不会
    跟着判据表变。范围也要说清——`bd_headline()` 那句只担保 `prove_biz_delegation.py`，
    它数不到这里；S2.1.4/S2.1.5 的判据面由本行负责，两行合起来才是这一份留档的全部。
    `path` 是给 M 段留的把手：反证电池要把「删掉一行判据」这件事真的做一次，
    而删的那一份只能躺在系统临时目录里（在本包里落副本 = 上一轮那起「变异版重写仓库留档」的事故）。
    """
    groups = af_ids(path)
    if not groups or set(groups) != set(AF_GROUP_NAME):
        return (f"# **AF 判据条数：FAIL——从 `prove_anchor_fallback.py` 的 `CHECKS` 只数到 "
                f"{ {k: len(v) for k, v in groups.items()} }，四个面没齐，头部无从生成**")
    parts = "、".join(f"{AF_GROUP_NAME[k]} {v[0]}…{v[-1]} {len(v)} 条" for k, v in sorted(groups.items()))
    return (f"# **AF 判据条数：{sum(len(v) for v in groups.values())} 条——{parts}"
            f"（本行由 `af_ids()` 现算，非手抄；上一行那句「判据条数」只担保 BD 一台，"
            f"两台合起来才是 S2.1.3 + S2.1.4/S2.1.5 的判据面）**")


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
    - 留着 `PLACEHOLDER_L_OUT` **而意图里没有** = **半成品冒充成品**（回填那一步失败时的形状，第八轮
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

    这不是防御性口味：第八轮那一趟整份重放跑完后，最后一次回填以 `OSError [Errno 22] Invalid argument`
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


def apply_norm(text: str, rc: int, hits: dict[str, int]) -> str:
    """把登记表里每一条归一化作用到一段命令输出上，命中处数累加进 `hits`；`rc == 2` 补 ③ 那句标注。

    单独成一个函数（而不是写在 `run_cmd` 里）：M 段要在**不跑子进程**的前提下把它驱动起来，
    拿一段带墙钟、带对象地址、rc 各档的假输出，看改写、计数与标注是不是都和登记表一一对上。
    上一版这些形状只有写在 `run_cmd` 里、只能等留档恰好撞出来才算被看过（第十二轮复审 B3）。
    """
    for name, _pat, rep, _pos, _neg in NORMALIZATIONS:
        text, n = NORM_RE[name].subn(rep, text)
        hits[name] = hits.get(name, 0) + n
    if rc == 2:
        text += "\n" + INCON_MARK
        hits[INCON] = hits.get(INCON, 0) + 1
    return text


def norm_ledger(counts: dict[str, int], text: str) -> tuple[str, list[str]]:
    """头部那句「命中 N 处」的正文与缺陷清单——同一个数由**两条独立通道**得到再比一次。

    ① `run_cmd` 每跑一段就地经 `apply_norm()` 累加的 `counts`；
    ② 对交付正文（从第一条 `########## ` 起，头部那段声明不参与）把每处的替换文本再数一遍。
    两条不符即缺陷：只留 ① 时，「把 `run_cmd` 里的调用删掉」会让计数一路是 0 而正文照样带着
    `<redacted>`；只留 ② 时，替换文本写进注释里就能凭空凑数。0 处也照样打印 0——
    「这一趟没撞到」和「这条规则不在」是两句话，上一版把后者混进了前者。
    """
    cut = text.find("########## ")
    readings = text if cut < 0 else text[cut:]
    defects: list[str] = []
    for name, _pat, rep, _pos, _neg in NORMALIZATIONS:
        again = readings.count(rep)
        if counts.get(name, 0) != again:
            defects.append(f"归一化「{name}」两条通道不符：`apply_norm` 累加 {counts.get(name, 0)} 处，"
                           f"正文里替换文本再数是 {again} 处")
    again = readings.count(INCON_MARK)
    if counts.get(INCON, 0) != again:
        defects.append(f"归一化「{INCON}」两条通道不符：累加 {counts.get(INCON, 0)} 处，"
                       f"正文里标注再数是 {again} 处")
    headline = ("# 读数归一化命中**现算**（两条通道相符才交付）："
                + "｜".join(f"{name} {counts.get(name, 0)} 处" for name in NORM_CLASSES)
                + "（0 也照写：这一趟没撞到，不等于登记表里没这条规则）")
    return headline, defects


#: 每一段**末行那条 `rc=`** 的预期档。缺这张表时的形状（第十二轮自查）：G 段在第十一轮被修成
#: 「报了红就不交付」，而 M（驱动自证）与 N（反证电池）报了红却照样落进留档、整趟 rc=0——
#: 读者要自己从十九段读数里发现哪一段红了，那不是交付者该留的活。
#: A 段是**改前红重放**（把在库件换成修复前的形状再跑一次），它必须一直红，红了才叫证明了这条修复承重；
#: D 段是**本机无 structlog / sqlalchemy**，pytest 连收集都跑不起来 ⇒ 2（「压根没测到」），不是 1。
EXPECTED_RC = {"A": 1, "D": 2}


def rc_gate(text: str) -> list[str]:
    """逐段核末行 `rc=N` 与 `EXPECTED_RC`；`rc=2` 的那段必须带着 ③ 那句标注。"""
    defects: list[str] = []
    for title, body in split_sections(text):
        m = re.match(r"########## ([A-Z])", title)
        letter = m.group(1) if m else "?"
        lines = [ln for ln in body.splitlines() if ln.strip()]
        tail = re.fullmatch(r"rc=(\d+)", lines[-1]) if lines else None
        if not tail:
            defects.append(f"{letter} 段末行不是 `rc=N` 形状（{lines[-1][:40]!r}）——这一段的裁决读不出来")
            continue
        got, want = int(tail.group(1)), EXPECTED_RC.get(letter, 0)
        if got != want:
            defects.append(f"{letter} 段末行 rc={got}，登记表要的是 rc={want}"
                           f"（红就是红，别让它只在段体里出声而整趟照样交付）")
        if got == 2 and INCON_MARK not in body:
            defects.append(f"{letter} 段 rc=2 却没有 ③ 那句标注——「压根没测到」会被读成真红")
    return defects


def stray_copy(here: pathlib.Path, ev: pathlib.Path) -> str:
    """这一份驱动有没有权重写留档：只有**在册那一份**有权。空串=有权，非串=点名拒收。

    为什么要这一条（第十二轮实测）：复核时把一份打了变异的驱动副本放进本包（`_v12_a2d.py`）直接跑，
    `EV` 由 `__file__` 推出、正指着仓库里的证据包，于是 `OUT` 就是**在库的** `out_s213.txt`——
    变异版把整份留档重写了，N 段标题当场变成 M 段。反证电池的副本不受影响：它整包拷进临时目录，
    `__file__` 与 `EV/replay_s213.py` 仍是同一个路径，写的也只是它自己那份副本。
    """
    reg = (ev / "replay_s213.py").resolve()
    return "" if here.resolve() == reg else (
        f"跑的是 {here.name}，而有权重写 `{reg.name}` 同级留档的只有在册那一份——"
        f"变异副本请拷到临时目录里跑（`mutate_replay_r9.py` 的 `stage()` 就是这么做的）")


def run_cmd(cmd: str, title: str, notes: str = "") -> str:
    r = subprocess.run([BASH, "-c", cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=ROOT, env=ENV)
    raw = ((r.stdout or "") + (r.stderr or "")).rstrip()
    rc = r.returncode
    # 三档退出码里最容易被读错的一档：2 是「压根没测到」，不是「测出红」，它必须明写在段体末尾。
    out = apply_norm(raw, rc, NORM_HITS)
    print(f"{title[:60]} … rc={rc}")
    return f"{title}\n{notes}$ {cmd}\n{out}\nrc={rc}\n"


K_TITLE = "########## K.1 BD 裸跑（cp936 输出流，guard 在位）"
#: 编码面的被测清单：每台 harness 三条命令（裸跑 / 关 guard / 抽靶），K 段的条数由这张表现算。
#: 第十二轮之后新增 `prove_anchor_fallback.py`（S2.1.4/S2.1.5）也带 `_ensure_utf8_stdout()`，
#: 所以它进的是同一档，不是另起一段——三台一起跑，读者才能看到「编码面」是一层而不是一次。
K_HARNESSES = (("BD", "prove_biz_delegation.py"), ("PI", "prove_article_identity.py"),
               ("AF", "prove_anchor_fallback.py"))
K_NOTES = (
    f"# 提交前自查发现的第三类崩溃面：`⇒` 在 win32 默认 cp936 上编不出来，`--self-test` 的标签打印会\n"
    f"# UnicodeEncodeError——既不是绿也不是红，正是本项目禁止的「没有裁决」第三种形态。\n"
    f"# {len(K_HARNESSES) * 3} 条命令 = 每台 harness 三条：裸跑证明现在不崩（rc=0、traceback 行数 0）；"
    f"关 guard 复现改前，"
    f"\n# 证明 `_ensure_utf8_stdout()` 承重；**抽靶**（把所有 ⇒ 换成 `->`）证明「编码自证」档不是装饰——\n"
    f"# 靶字被抽掉后子进程照样全绿，若不查 ⇒ 是否真出现过，那一档就会假绿。\n"
    f"# 三台的清单在 `K_HARNESSES`，条数不由本注释里的数字担保（新入库一台就自动多三条）。\n"
)
# 关 guard 与抽靶两份临时件都必须由同一条命令删掉，末尾的 `ls` 是删除回读
TMPNA = (EV / "_tmp_noarrow.py").relative_to(ROOT).as_posix()


def k_sections() -> tuple[list[str], list[str]]:
    """K 段 = `len(K_HARNESSES) × 3` 条（每台 harness 三条：裸跑 / 关 guard / 抽靶）。返回 (段文本, 缺陷清单)。

    临时副本没删干净是**缺陷**不是异常：上一版这里是裸 `assert`（第十轮复审 10-8），
    `python -O` 下整条被剥掉，驱动会一边留着 `_tmp_*` 一边打印「回读逐字节相同」。
    """
    chunks, defects, n = [], [], 0
    kinds = ("裸跑（cp936，guard 在位）", "关 guard 复现改前", "抽靶：⇒ 全换成 -> 后不许假绿")
    for name, script in ((k, EV / v) for k, v in K_HARNESSES):
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
#: 本机证不了的那一半**交给谁**（文件 + 顶层用例名）。这张表是一条判据的输入，不是文档：
#: 第十三轮把 P-4 用例按卡面从 `test_kb_longlink_ingest.py` 搬到 `test_kb_multisource_anchor.py`，
#: 而「真库那条走 `某文件::某用例`」这句话从前只写在 harness 的 print 与 O 段的注释里——
#: 搬一次就烂掉，而没有任何一条判据会说「指针指空了」（G-23 禁的正是这种只会说好话的声明）。
#: 现在文件名与用例名集中登记，落盘前逐条核对磁盘上确有其事；表与仓库各改一头，G 段就红。
REAL_DB_TARGETS = (
    ("apps/api/tests/test_kb_multisource_anchor.py", "test_multi_source_no_crash"),
    ("apps/api/tests/test_kb_multisource_anchor.py", "test_biz_anchor_wins_when_both_anchors_exist"),
    ("apps/api/tests/test_asset_fragment_guard.py", "test_url_fragment_short_returns_none_and_zero_query"),
    ("apps/api/tests/test_asset_fragment_guard.py", "test_url_fragment_empty_returns_none_without_warning"),
    ("apps/api/tests/test_asset_fragment_guard.py", "test_url_fragment_boundary_is_exactly_min_len"),
    ("apps/api/tests/test_asset_fragment_guard.py", "test_url_fragment_query_is_source_scoped_like"),
    ("apps/api/tests/test_kb_longlink_ingest.py", "test_long_link_yields_non_empty_biz"),
)
#: 本步新出来的用例文件：**它们每一条会被 pytest 收集的用例都必须在上面的表里**（A 组 NI-2：
#: 从前只按文件级判，一份文件四条用例登记两条也算「确有其事」）。判据是 `db_pointer_missing`。
#: 这份名单本身不许手抄维持（第十四轮 C 组 C-14-08）：`registry_drift()` 拿 git 的本步新增集合对账，
#: 「本步又新写了第三份用例文件却谁都不登记」那条路从此要出声。基线取 V0.5.0 建卡时的 `65f508b`。
STEP_TEST_BASE = "65f508b"
STEP_NEW_TEST_FILES = ("apps/api/tests/test_kb_multisource_anchor.py",
                       "apps/api/tests/test_asset_fragment_guard.py")


def _parse_or_none(path: pathlib.Path, rel: str, bad: list[str]) -> ast.Module | None:
    """把用例文件解析成 AST；解析不了就**点名成缺陷**而不是让 traceback 冒充裁决。

    第十四轮 C 组 C-14-10：这两个指针函数当时直接 `ast.parse`，一份 `def test_ok(:` 或一份
    非 UTF-8（带 `# -*- coding: gbk -*-`，CPython 认它）的用例文件都会让整趟 `main()` 以
    traceback 收场——既不是红档也不是 INCONCLUSIVE 档，正是本包一路在堵的那种形态。
    """
    try:
        return ast.parse(path.read_text(encoding="utf-8-sig"))
    except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
        bad.append(f"{rel} 读不出用例清单：{type(exc).__name__}: {exc}——指针核对在这一条上没跑成，"
                   f"不许当成「没有缺陷」")
        return None


def _collect_cases(tree: ast.Module) -> list[str]:
    """pytest 真会收集的用例名：顶层 `test*` 函数，以及 `Test*` 类里的 `test*` 方法。

    类里那种登记成 `类::用例`——因为那句交代得写成 `file::类::用例` 才真的跑得动；
    **不以 `Test` 开头的类不算**（pytest 默认 `python_classes = Test*`，把没人收集的函数要求成
    登记项，等于让判据咬合法形状）。第十四轮 C 组 C-14-08：上一版这两张指针判据对同一个形状
    给出相反答案——`db_pointer_defects` 把类方法判成指空，`db_pointer_missing` 却只看 `tree.body`
    那一层、压根不要求登记它。口径统一成「pytest 收得到就必须登记，登记名要能被跑动」。
    """
    out: list[str] = []

    def visit(body: list[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test"):
                    out.append(f"{prefix}{node.name}")
            elif isinstance(node, ast.ClassDef):
                # pytest 的默认口径两半：`python_classes` 名字匹配（默认 `Test*`）**且**该类没有
                # `__init__`；但 `unittest.TestCase` 的子类**不看名字**也照收（pytest 文档明写的例外）。
                # 十六轮复核报的就是这条例外没进射程：`class Helper(unittest.TestCase): def test_u`
                # 会被真收集，而旧写法既不要它登记也判它合法——两边读数都错。
                testcase = any(ast.unparse(b).endswith("TestCase") for b in node.bases)
                has_init = any(isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef))
                               and st.name == "__init__" for st in node.body)
                if testcase or (node.name.startswith("Test") and not has_init):
                    # 前缀要**累加**：第十五轮 E 组实测嵌套类读出来是 `TestInner::test_c`，
                    # 那既不是能跑的 node id（pytest 要 `TestOuter::TestInner::test_c`），
                    # 也不是「不收集」——两边读数都错。
                    visit(node.body, f"{prefix}{node.name}::")
            elif isinstance(node, ast.If):
                visit(node.body, prefix)
                for extra in (node.orelse,):
                    visit(extra, prefix)
            elif isinstance(node, ast.Try):
                visit(node.body, prefix)
                for handler in node.handlers:
                    visit(handler.body, prefix)      # E 组：except 体里的 def 同样会被收集
                visit(node.orelse, prefix)
                visit(node.finalbody, prefix)
            elif isinstance(node, ast.With):
                visit(node.body, prefix)             # `with ...: def test_x()` 也是模块级执行
            elif isinstance(node, (ast.For, ast.While)):
                visit(node.body, prefix)             # 循环体里的 def 在收集期就执行了（十六轮复核）
                visit(node.orelse, prefix)
            elif isinstance(node, ast.Match):
                for case in node.cases:
                    visit(case.body, prefix)         # `match/case` 体同理

    visit(tree.body, "")
    return out


#: 值形状：字面量里有 `=`、引号、`%…%`，或**任何数字**，就是在断言一个会被渲染成绑定参数的值
#: （`LIMIT 1` 在默认方言里是 `LIMIT :param_1`——纯关键字的断言不含数字，两者分得开）。
_VALUE_SHAPE = re.compile(r"=|['\"%]|\d")


def sql_render_defects(text: str, where: str = "文件") -> list[str]:
    """用例里「对 `compile()` 渲染出的文本断言字面值」这件事，是**可静态抓到的恒红形状**。

    SQLAlchemy 的默认方言把值渲染成绑定参数（`content_assets.source_id = :source_id_1
    AND … LIKE :url_1 LIMIT :param_1`），于是
    `assert "source_id = 'src-1'" in str(stmt.compile())` 在 CI/真库上必红、在本机恒不可跑。
    第十七轮由 `docs/任务规划V0.8.0/evidence/61358c3/pytest_local_noPG.txt` 的 CI 实测抓到；
    本包此前十六轮都没抓到，**因为这条判据根本不存在**——这是「判据的覆盖面=上一轮想到的形状」
    那一族的第 N 次现场。

    抓法不 grep 字形，按 AST 认两件事：
    ① 哪些名字的值来自 `str(….compile(…))`（也认内联写法 `X in str(stmt.compile())`、
       海象 `if (sql := str(…)):` 与 `for sql in [str(…)]:` 这两种**在表达式/循环目标上**的绑定）；
    ② 有没有一句 `in` 比较：左操作数是**带值形状**的字符串字面量（含 `=`、引号、`%…%` 或任何数字），
       右操作数落在 ① 那些名字/表达式上。

    三处**明认的边界**（第十八轮复核定下来写在这里，不是留给读者猜）：
    - 宁严勿宽：值形状含「任何数字」，所以 `assert ":param_1" in sql`、`"sha256" in sql`
      这类**在默认方言下其实正确**的断言也会被点名。占位符与含数字的关键字要不要放行属改契约，
      与 BD-12 同一处理；本判据选的是「多问一处」而不是「漏一族」。
    - 豁免只认 `compile_kwargs` 这一个通道（关键字或位置第二实参）；
      `compile(**{"literal_binds": True})` 与 `compile(dialect="literal_binds")` **不豁免**——
      那两个写法根本不内联值，放过它们就是放过恒红。
    - 跨文件的辅助函数（别的模块返回渲染文本）与 f-string 左值不在射程内：那需要一个全仓的
      过程间分析，代价与收益不匹配，留 J-6/J-7 的连库面与 CI 兜。
    - **按名字记污点、不分作用域**（flow-insensitive）：两个函数都用 `sql` 这个名字时，一处绑定
      会把另一处的引用也点亮——过判方向，同上一条契约。它的副作用是**探针必须给两段用不同变量名**，
      否则两条分支任一被削掉，缺陷数照样是 2，电池那两发就测不出差别（第十八轮实测到这件事）。
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as exc:
        return [f"{where} 读不出 AST：{type(exc).__name__}: {exc}——这一档没判成，不是判绿"]
    rendered: set[str] = set()      # 值是「渲染文本」的名字（污点沿赋值传播）
    rendered_lists: set[str] = set()  # 假会话里 append 渲染文本的那个属性名（如 `calls`）
    bad: list[str] = []

    def base_rendered(node: ast.AST) -> bool:
        """这一子树里是否出现「会丢值的」渲染：`x.compile()` 或 `str(x.compile())`。

        **带 `compile_kwargs={"literal_binds": True}` 的渲染不算**——那种写法就是把值内联进文本，
        断言字面值正是它的用途（V0.8.0 STEP-00C 卡 S0C.1.2 给的修法即此）。豁免只认
        `compile_kwargs` 这一个通道（第十八轮 R18-7：上一版只看「某个关键字的值里含那个字样」，
        于是 `compile(**{"literal_binds": True})` 与 `compile(dialect="literal_binds")`
        也被放过——那两个写法并不内联值，放过就是放过恒红）。
        """
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                f = sub.func
                if isinstance(f, ast.Attribute) and f.attr == "compile":
                    kw = next((k for k in sub.keywords if k.arg == "compile_kwargs"), None)
                    positional = sub.args[1] if len(sub.args) > 1 else None
                    got = (("literal_binds" in ast.unparse(kw.value)) if kw is not None
                           else (positional is not None
                                 and "literal_binds" in ast.unparse(positional)))
                    if not got:
                        return True
                if isinstance(f, ast.Name) and f.id == "str" and sub.args \
                        and base_rendered(sub.args[0]):
                    return True

        return False

    def is_rendered(node: ast.AST) -> bool:
        """这个表达式读的是不是渲染文本：内含 `…compile()` 调用、内含被污名化的名字，或取自律会话。"""
        if isinstance(node, ast.Name):
            return node.id in rendered
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) \
                and node.value.attr in rendered_lists:
            return True   # `sess.calls[0]`：假会话往里塞的就是渲染文本
        if base_rendered(node):
            return True
        # `flat = " ".join(sql.split())` 这种**在受污名字上调方法**的写法：污点在子节点里
        # （`walk` 会连自己一起给，必须跳过，否则这里无限递归）
        return any(is_rendered(sub) for sub in ast.walk(node) if sub is not node)

    # 先认假会话：`async def scalar(self, stmt): self.<attr>.append(str(stmt.compile()))`
    # （必须同时认 `AsyncFunctionDef`——仓库里的夹具是 async 的，第一版只认 def 就漏了整条链）
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "scalar":
            for c in (x for x in ast.walk(n) if isinstance(x, ast.Call)):
                f = c.func
                if isinstance(f, ast.Attribute) and f.attr == "append" \
                        and isinstance(f.value, ast.Attribute) and base_rendered(c):
                    rendered_lists.add(f.value.attr)

    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and any(is_rendered(sub) for sub in ast.walk(n.value)):
            # 污点要**顺着赋值传播**：真实用例是 `sql = str(x.compile())` → `flat = " ".join(sql.split())`
            # → `assert "…" in flat`，只认第一跳的判据等于没判（第十七轮自查实测：第一版就这样漏的）
            for t in n.targets:
                if isinstance(t, ast.Name):
                    rendered.add(t.id)
        elif isinstance(n, ast.NamedExpr) and is_rendered(n.value) \
                and isinstance(n.target, ast.Name):
            rendered.add(n.target.id)          # `if (sql := str(x.compile())):` 也是绑定（R18-8）
        elif isinstance(n, (ast.For, ast.AsyncFor)) and is_rendered(n.iter):
            for t in (n.target,):
                if isinstance(t, ast.Name):
                    rendered.add(t.id)         # `for sql in [str(x.compile())]:` 同算
        elif isinstance(n, ast.Assert):
            for cmp in (x for x in ast.walk(n.test) if isinstance(x, ast.Compare)
                        and any(isinstance(op, ast.In) for op in x.ops)):
                left, right = cmp.left, cmp.comparators[0]
                if isinstance(left, ast.Constant) and isinstance(left.value, str) \
                        and _VALUE_SHAPE.search(left.value) and is_rendered(right):
                    bad.append(f"{where}:{n.lineno} 对 compile 渲染文本断言字面值 {left.value!r}"
                               "——默认方言把值渲染成绑定参数，这句在 CI 上必红；"
                               "要判值就走 `compile().params` 的值侧，要判单行就走 `get_limit()`")
    return bad


def db_pointer_defects(targets: tuple[tuple[str, str], ...],

                       root: pathlib.Path = ROOT) -> list[str]:
    """逐条核对「交给真库的那些用例」在 `root` 下确有其事：文件在、那句指针点到的 `def` 在。

    走 AST 而不是 grep：用例名出现在注释里不算数（那正是这句话最容易烂成的样子——
    文件还在、函数已经改名）。参数化用例的顶层 `def` 名不变，所以 `@pytest.mark.parametrize`
    那种写法不需要在这里特判。登记名带 `::` 的按类方法解析（`类::用例`），因为那句交代
    要写成 `file::类::用例` 才真的能跑。

    `root` 是给 M 段留的把手：反证电池把本包拷进系统临时目录跑，那份副本的 `ROOT` 上面
    **没有** `apps/`（第十三轮实测：基线因此报「5 处文件不存在」，整批电池判 INCONCLUSIVE——
    自己的判据把自己的电池弄成没裁决，这是最糟的一种红）。所以 M 段只对着一棵临时造假的小树判
    语义，真正那张 `REAL_DB_TARGETS` 由 `g_section()` 在仓库根上核对、不符就不交付。
    """
    bad: list[str] = []
    for rel, fn in targets:
        path = root / rel
        if not path.is_file():
            bad.append(f"真库指针指向的文件不存在：{rel}::{fn}")
            continue
        tree = _parse_or_none(path, rel, bad)
        if tree is None:
            continue
        names = _collect_cases(tree)
        if fn not in names:
            bad.append(f"{rel} 里没有 pytest 会收集的用例 {fn}（实有 {sorted(names)[:4]}…）——"
                       f"那句话就又是一句过期的交代")
    return bad

G_TITLE = ("########## G 仓库静态自检（E/F/I/W/UP/B 机检子集；被检清单 = 在库登记表 `EV_PY` + 本步仓库件 "
           "`G_TEST_FILES`，两份都由代码现拼，不在正文里抄号数）")
#: 本步在**仓库侧**触碰的 Python：S2.1.1–S2.1.5 的用件（用例 + 两份生产件）一起进 G 段门禁。
#: 名字仍叫 `G_TEST_FILES`：README §4.11 id 34 与卡面 D-14 那两处历史说明按这个名字记的账，
#: 改名会让那些句子指向一个不存在的东西——口径写在话里，不写在标识符里。
G_TEST_FILES = ("apps/api/tests/test_kb_longlink_ingest.py", "apps/api/tests/test_article_identity.py",
                "apps/api/tests/test_kb_multisource_anchor.py", "apps/api/tests/test_asset_fragment_guard.py",
                "apps/api/app/services/kb.py", "apps/api/app/repositories/asset.py")

#: 本包**登记在册**的证明脚本：G 段的被检清单取自这张表，不再 `EV.glob("*.py")` 现算。
#: 第十一轮复审 NIT② 之后我把它改成了 glob，代价反过来落在自己身上（第十二轮实测）：复核智能体
#: 往本包丢了一份 `_v12_a2d.py` 做临时副本，glob 当场把它吸收进被检清单——留档里那条 `$ ` 命令和
#: `===` 表跟着一起变，「读者看到的被检文件集」被一次复核动作改写了，而没有任何一条判据说这不行。
#: 现在清单是登记的，包内出现**未登记**的 `.py` 判缺陷、登记了却不在包里也判缺陷（当场点名，
#: 既不静默扩清单，也不静默少检）。新入库一份证明脚本 = 同时进这张表，改一处就够。
EV_PY = ("block_article_identity_plugin.py", "j_attack_r7.py", "mutate_replay_r9.py",
         "prove_anchor_fallback.py", "prove_article_identity.py", "prove_biz_delegation.py",
         "replay_s213.py")


def g_section() -> tuple[str, list[str]]:
    """G 段：仓库静态自检，被检清单 = `G_TEST_FILES` + `EV_PY`。返回 (段文本, 缺陷)。

    上一版这一串的七个文件名是我手改进留档的 `$ ` 行里的（`git show d80eeaf -- out_s213.txt`
    就能看到那行 `$` 被改过一次），后果是新入库的 `block_article_identity_plugin.py` 一直游离在
    门禁之外，而且没有任何命令判「清单与包内文件相符」。第十轮复审 10-14 因此改成 glob，
    第十二轮又发现 glob 会把复核临时件一并吸进清单（见 `EV_PY` 上方那段），所以现在是
    **登记清单 + 双向相符判据**：既不漏检，也不被外来文件悄悄改写。

    **这一段的读数必须承重**（第十一轮复审 NIT①）：上一版它只是把 `g_section()` 的文本塞进留档，
    `defects` 一个字都不收——实测往本包放一份有违规的 `.py`，G 段自己记 `rc=1`、表里写「合计违规 1 条」，
    驱动整趟仍 rc=0 交付。静态门禁报了红而驱动绿，等于门禁只在正文里好看。现在三判：末行必须 `rc=0`、
    必须出现「合计违规 0 条」、表里 `===` 的份数必须等于命令里列出的份数（少一份就是清单与命令脱节）。
    """
    present = sorted(p.relative_to(EV).as_posix() for p in EV.rglob("*.py"))
    extra = [p for p in present if p not in EV_PY]
    missing = [p for p in EV_PY if p not in present]
    files = [RELPATH(EV / p) for p in EV_PY]
    listed_names = [*G_TEST_FILES, *files]
    text = run_cmd(f"python {RELPATH(G24)} " + " ".join(listed_names), G_TITLE)
    defects: list[str] = []
    if extra:
        defects.append(f"本包有未登记在册的 .py：{extra}——把它们放进被检清单，就等于让一次复核动作"
                       f"改写留档的 `$ ` 命令与 `===` 表；要进门禁就登记进 `EV_PY`，是临时件就删掉")
    if missing:
        defects.append(f"登记在册的 .py 不在包里：{missing}——清单与被检对象脱节，这一列就是漏检")
    if not text.rstrip().endswith("rc=0"):
        defects.append(f"G 段静态自检没下绿裁决：末行 {text.rstrip().splitlines()[-1]!r}")
    if "合计违规 0 条" not in text:
        defects.append("G 段静态自检报的不是「合计违规 0 条」——门禁红了就不许交出绿留档")
    blocks = len(re.findall(r"(?m)^=== ", text))
    if blocks != len(listed_names):
        defects.append(f"G 段命令列出 {len(listed_names)} 份文件，表里只有 {blocks} 份——"
                       f"清单与被检结果脱节（登记的那几份与跑出来的那几份不是同一批）")
    defects += db_pointer_defects(REAL_DB_TARGETS)
    defects += db_pointer_missing(REAL_DB_TARGETS)
    # 第十七轮：本步那些「假会话只记一条渲染 SQL」的用例，断言写字面值就会在 CI 恒红
    # （V0.8.0 的 CI 实测抓到 `test_asset_fragment_guard.py:143-145` 三条全红）。这条判据在那之前不存在。
    for rel in sorted({p for p, _ in REAL_DB_TARGETS} | set(STEP_NEW_TEST_FILES)):
        f = ROOT / rel
        if f.is_file():
            defects += sql_render_defects(f.read_text(encoding="utf-8-sig"), rel)
    fresh = new_test_files_from_git()
    if fresh is None:
        defects.append("本步新增用例文件的清单没跑成（git 取不到读数）——`registry_drift` 这一判据**没跑**，"
                       "不是通过了；按「没测到」记成缺陷而不是静默放行")
    else:
        defects += registry_drift(STEP_NEW_TEST_FILES, fresh)
    covered = {f for f, _ in REAL_DB_TARGETS}
    for must in STEP_NEW_TEST_FILES:
        if must not in covered:
            defects.append(f"真库指针表没登记 {must}——本步新写的连库用例没人交代去哪跑；"
                           f"把这张表清空也能「一条都不缺」，所以这里按文件级点名")
    # 孤儿编译件（第十三轮 B 组 R13B-17）：本包 `__pycache__` 里躺着一份
    # `_harness_probe.cpython-311.pyc`，它的**源文件早已不在仓库里**——`EV.glob("*.py")` 看不见 `.pyc`、
    # `stray_copy()` 只管「谁有权落盘」，于是第十二轮那起「变异副本留在包里」的同族残留停在原地，
    # 而 M 段那句「本包里的变异副本没有落盘权」读起来像已经清了。
    for orphan in orphan_pycs():
        defects.append(f"本包有源文件已不存在的编译件：{orphan}——它是哪一发变异留下的？"
                       f"清掉它并写清来路（现读 `ls {RELPATH(EV)}/__pycache__`）")
    return text, defects


#: S2.1.4/S2.1.5 那台证明面（`prove_anchor_fallback.py`）的三个入口，各成一段：
#: O.1 基线（磁盘上的 kb.py + asset.py 现在绿不绿）、O.2 反证电池（改坏必须红 / 等价不许假红 /
#: 三档退出码 + 编码面）、O.3 判据清单（这一台的分母，与头部 `af_ids()` 那句对账）。
O_HARNESS = "prove_anchor_fallback.py"
O_TITLES = (
    "########## O.1 S2.1.4/S2.1.5 证明面基线：磁盘上的 kb.py + asset.py（AST 取活绑定 exec + 记账假会话）",
    "########## O.2 锚定台反证电池：改坏必须红 / 等价不许假红 / 三档退出码与编码面都分得开",
    "########## O.3 锚定台判据清单：`--list-checks` 自报的分母，与头部那句 AF 条数两条通道对账",
)
O_NOTES = (
    "# 这一段为什么在本包里：S2.1.4 的缺陷形状是**崩栈**（`scalar_one_or_none()` 撞见多行时抛"
    "`MultipleResultsFound`，有依赖环境实测读数 `docs/任务规划V0.3.0/evidence/probes_4afaedd.txt:19`），"
    "而本机没有 sqlalchemy 与 structlog（`kb.py:22-25` 模块级导入）⇒ pytest 那条用例在本机连收集都过不去。\n"
    "# 所以这里的取证方式是「AST 从磁盘源码里取出那两个函数的**活绑定**、单独 compile+exec，"
    "配一台如实实现 `limit(1)` 截断与多行抛错的记账假会话」：它证明的是**生产代码向 DB 要了什么**，"
    "不证明 SQL 引擎侧的真实执行——后者仍交 `test_kb_multisource_anchor.py`（P-4 转正 + 锚定顺序）与"
    "`test_asset_fragment_guard.py`（需依赖）⇒ README §5 J-1/J-5，"
    "两份的文件名与用例名都登记在 `REAL_DB_TARGETS`，由 G 段逐条核对磁盘上确有其事。\n"
    "# S2.1.5 的判据不是「不崩」而是「不猜」：`%s%` 那类短片段 `.limit(1)` 也不崩，却会把**另一篇**"
    "资产当命中返回（缓存复用错文章、版本比对错 hash），所以这里同时数 SQL 条数（应为 0）与 WARNING 次数。\n"
)


def _fn_tree(fn: object) -> ast.FunctionDef:
    """把某个函数自己的源码解析成 AST（`inspect.getsource` 的行号从 1 起，相对顺序仍真实）。"""
    return ast.parse(inspect.getsource(fn)).body[0]  # type: ignore[union-attr]


def _first_call_line(tree: ast.AST, callee: str) -> int:
    """某次调用第一次出现的行号（相对函数自身，从 1 起）；没有则 0。"""
    lines = [n.lineno for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == callee]
    return min(lines) if lines else 0


def _call_args(tree: ast.AST, callee: str) -> list[list[str]]:
    """对 `callee(...)` 每一次调用的实参 unparse 列表（位置参数在前，关键字记成 `名=值`）。"""
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == callee:
            args = [ast.unparse(a) for a in n.args]
            args += [f"{k.arg}={ast.unparse(k.value)}" for k in n.keywords]
            out.append(args)
    return out


def _call_args_ok(tree: ast.AST, callee: str, table: str) -> bool:
    """存在一次 `callee(<table>)`，其对象根是仓库根 `ROOT`（省略即用默认，或显式写 `ROOT`）。

    第十三轮 A 组 MI-4：这条从前是 `inspect.getsource(...)` 的子串匹配，双向都错——
    写成 `db_pointer_defects(targets=REAL_DB_TARGETS)`（语义正确）被判红（假红），
    而 `db_pointer_defects(REAL_DB_TARGETS, ROOT / "docs")`（核对错了根）子串照样命中（漏检）。
    现在按实参判，位置与关键字两种写法同权，第二个位置实参也当 root 看
    （电池实测：只判 `root=` 关键字时，`ROOT / "docs"` 那一发漂移照样绿——漏检档自己又被漏掉一次）。
    """
    calls = _call_args(tree, callee)
    for args in calls:
        positional = [a for a in args if "=" not in a]
        kwargs = dict(a.split("=", 1) for a in args if "=" in a)
        table_arg = positional[0] if positional else kwargs.get("targets", kwargs.get("table"))
        if table_arg != table:
            continue
        if len(positional) > 1:
            root_arg = positional[1]
        else:
            root_arg = kwargs.get("root", "ROOT")
        if root_arg == "ROOT":
            return True
    return False


def _calls_brief(tree: ast.AST, callee: str) -> list[list[str]]:
    """给 FAIL 读数用的调用实参原样（`_call_args_ok` 拒了之后要知道它到底被怎么调的）。"""
    return _call_args(tree, callee)


def orphan_pycs(ev: pathlib.Path = EV) -> list[str]:
    """本包上下那些**源文件已经不存在**的 `.pyc`（R13B-17 的形状），递归找，不止 `__pycache__` 一层。

    只判孤儿：正常跑出来的新编译件不该被咬（第十二轮那条口径——见什么的都有探测器不等于有判据）。
    为什么这算缺陷：`EV.glob("*.py")` 看不见 `.pyc`、`stray_copy()` 只管「谁有权落盘」，
    于是「包里躺过一发变异副本」这件事在两份判据之间是隐形的，而 M 段那句
    「本包里的变异副本没有落盘权」读起来像已经清干净了。
    第十四轮 C 组 C-14-09：上一版只 `glob("__pycache__/*.pyc")`，子目录里的
    `sub/__pycache__/x.cpython-311.pyc` 与直接落在包根的 `x.cpython-311.pyc` 两种位置全都隐形——
    见不到的那两类恰好也是复核临时件最常落的形状，所以改成 `rglob` 并按编译件自己的位置找源文件。
    """
    out = []
    for pyc in sorted(ev.rglob("*.pyc")):
        stem = pyc.name.split(".")[0]
        home = pyc.parent.parent if pyc.parent.name == "__pycache__" else pyc.parent
        if not (home / f"{stem}.py").exists():
            out.append(f"{pyc.relative_to(ev).as_posix()}")
    return out


#: 自指措辞登记表（第十四轮 D 组 D-14-02 立，第十五轮 E 组扩）。留档每轮由驱动**整份重打**，
#: 所以「写它的那一轮」绝不能用代词说：那等于让第八轮那次 `OSError [Errno 22]` 在下一轮的纸上
#: 重新自称刚发生。第十五轮 E 组报的是**射程**：登记表只有三个词时，同族的另外几种写法全部放行——
#: 驱动自己的源码里当时还剩四处，兄弟台的一条判据名也带着这类代词被逐字印进留档，而那条判据读起来是绿的。
#: 所以表扩到八个词。这里有一条**扫描器自己的代价**必须写清：它不区分「使用」与「引用」，
#: 于是连解释这条纪律都不能把那些词照抄出来（本文件与注释提到它时一律改写成「这类代词」——
#: 第十四轮那版把上一句写成原词时，M 段这一判在**新写的注释自己**上就红了，那是现场而不是故事）。
#: 登记表用拼接而不是字面量也是同一原因：它要扫的对象包括驱动自己的源码，写成字面量就永久命中定义那一行。
SELF_REF_MARKS = ("本" + "轮", "本" + "次", "本" + "趟", "本" + "回合",
                  "这" + "一轮", "这" + "次", "这" + "回")


def self_ref_defects(text: str, where: str = "文本") -> list[str]:
    """点名「用代词说事」的行（行号 + 原句片段）；空表 = 没有那种措辞。

    判的是**措辞**而不是内容：指名轮次（`第八轮`、`65f508b`）的旧事一律放行——那种句子每一轮重印
    都仍然为真，而代词那句每一轮重印都换了一个所指。留档与驱动源码走同一份登记表，
    所以「注释里把第八轮的事故说成刚刚发生」和「头部模板字面量每轮自称正在发生」是同一个缺陷的两侧。
    """
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        hit = [m for m in SELF_REF_MARKS if m in line]
        if hit:
            out.append(f"{where}第 {i} 行用自指措辞 {'/'.join(hit)} 说话：{line.strip()[:56]!r}"
                       f"——事故与读数要指名轮次或提交，代词每轮重印都会把旧事说成新事")
    return out


def _cond_uses(node: ast.AST, want: str) -> bool:
    """这个条件表达式是不是「无条件地」读了 `want`（裸名字、双重取反、`len(want)` 与 0 比）。"""
    if isinstance(node, ast.Name):
        return node.id == want
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _cond_uses(node.operand, want)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "len":
        return any(_cond_uses(a, want) for a in node.args)
    if isinstance(node, ast.Compare):
        sides = [node.left, *node.comparators]
        return any(_cond_uses(s, want) for s in sides) and any(
            isinstance(c, ast.Constant) and c.value == 0 for c in node.comparators)
    if isinstance(node, ast.BoolOp):
        return any(_cond_uses(v, want) for v in node.values)
    return False


def _cond_is_dead(node: ast.AST) -> bool:
    """条件里出现常量假（`if False and defects:`）——那种门永不成立，与把门拆了等价。"""
    if isinstance(node, ast.Constant) and not node.value:
        return True
    if isinstance(node, ast.BoolOp):
        return any(_cond_is_dead(v) for v in node.values)
    return False


def _gate_lines(tree: ast.AST, want: str) -> tuple[list[int], list[int]]:
    """返回 (以 `want` 为拒收条件的 If 行号, 恒假条件的 If 行号)。

    第十四轮 C 组 C-14-07：`if defects:` 换成 `if len(defects) > 0:` 行为一字不差，旧判据却报**假红**
    （它只认 `ast.Name` 那一种形状）；而 C-14-04 那一发 `if False and defects:` 旧判据只是「找不到门」，
    这句话本身没说清「门被拆了」与「门是死的」是两件事。现在两种分开点名。
    """
    live, dead = [], []
    for n in ast.walk(tree):
        if not isinstance(n, ast.If):
            continue
        if _cond_is_dead(n.test):
            dead.append(n.lineno)
        elif _cond_uses(n.test, want):
            live.append(n.lineno)
    return live, dead


def _merge_targets(tree: ast.AST, target: str) -> tuple[list[str], list[str]]:
    """返回 (被无条件并入 `target` 的名字, 可疑形状说明)。

    接受 `target += X`、`target = target + X`、`target = list(target) + list(X)`（C-14-07 的等价形状）；
    **不接受**任何「名字在场而值被筛掉」的包装：带 `if` 的推导式（C-14-04）、`filter(...)`、以及任何
    包着 `lambda` 的调用。第十五轮 E 组实测：旧写法对 Call 的实参无脑收名字，于是
    `defects += list(filter(lambda d: False, g_defects))` 一路全绿——形状、名字、门都在，
    门里却永远收不到东西，这正是「形状保留、语义掏空」的第二发。
    """
    names: list[str] = []
    odd: list[str] = []

    def harvest(node: ast.AST) -> None:
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, (ast.ListComp, ast.GeneratorExp, ast.SetComp, ast.DictComp)):
            if len(node.generators) > 1:
                # `[d for d in g_defects for _ in ()]`：形状、名字、门都在，值恒空——
                # 第二个 for 挂一个空可迭代对象就足以把合并掏空（第十六轮复核报的那发）。
                odd.append(f"第 {getattr(node, 'lineno', 0)} 行：多重 for 的推导式并入（任一层为空即恒空）")
            for gen in node.generators:
                if gen.ifs:
                    odd.append(f"第 {getattr(node, 'lineno', 0)} 行用带 if 的推导式并入（名字在场、值可恒空）")
                if isinstance(gen.iter, (ast.List, ast.Tuple, ast.Set, ast.Dict)) and not gen.iter.elts:
                    odd.append(f"第 {getattr(node, 'lineno', 0)} 行：推导式遍历一个空字面量（恒不产出）")
                harvest(gen.iter)
            for part in ([node.elt] if isinstance(node, (ast.ListComp, ast.GeneratorExp, ast.SetComp))
                         else [node.key, node.value]):
                harvest(part)
        elif isinstance(node, (ast.BinOp, ast.BoolOp)):
            for child in (node.values if isinstance(node, ast.BoolOp) else [node.left, node.right]):
                harvest(child)
        elif isinstance(node, (ast.List, ast.Tuple)):
            for e in node.elts:
                harvest(e)
        elif isinstance(node, ast.Call):
            fname = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else "")
            if fname in {"filter", "filterfalse", "compress", "dropwhile"} or any(
                    isinstance(a, ast.Lambda) for a in node.args):
                odd.append(f"第 {node.lineno} 行：经 {fname or 'lambda'} 过滤后再并入（与「带 if 的推导式」同一类）")
            for a in node.args:
                harvest(a)
            if isinstance(node.func, ast.Attribute):
                harvest(node.func.value)

    for n in ast.walk(tree):
        if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and n.target.id == target:
            harvest(n.value)
        elif isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == target for t in n.targets):
            harvest(n.value)
    return [x for x in names if x != target], odd


def _defect_names(tree: ast.AST) -> list[str]:
    """函数里出现过的所有 `*_defects` 名字。

    第十五轮 E 组：交付门那组合并名单从前是写死的 `{"g_defects", "k_defects"}`——
    「新接一段证明、它的缺陷却不并进拒收清单」这种形状没人判（实测「J 段缺陷不并入」全绿）。
    现在白名单从 main 的代码本身现取：凡是 `x_defects` 这个名字出现过，它就必须被并进某道门。
    **取名字时要排掉「被调用的那个名字」**：`self_ref_defects(...)` 也是 Load 上下文里的 Name，
    但它是一个函数而不是缺陷清单（第一版把它算进白名单，于是这条判据在正常代码上假红）。
    """
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    return sorted({n.id for n in ast.walk(tree)
                   if isinstance(n, ast.Name) and n.id.endswith("_defects")
                   and n.id != "defects" and n.id not in called})


def _sink_line(tree: ast.AST) -> int:
    """函数体内第一次「往磁盘写」的行号——按 **sink 的语义**认，不按某几个函数名。

    第十四轮 C 组 C-14-05：旧判据只认被调用者字面叫 `write_out` 的那一次，于是门之前插一句
    `OUT.write_text("坏留档")` 完全合法——磁盘先被改坏、门之后才出声。
    第十五轮 E 组：把 sink 做成一份**函数名名单**还是同一个毛病（`shutil.copyfile`、`os.replace`、
    `os.write`、句柄 `.write(...)`、`tempfile.mkstemp` + rename 全都溜过去）。

    所以这里认「写动作」这一族，但**只认到不会被日常代码撞上的程度**：
    `write*`/`truncate`/`mkstemp`/`unlink`/`mkdir*`/`rmtree`/`copyfile` 直接算；`replace`/`rename`
    只在接受者是 `os`/`shutil`/`pathlib` 这类模块名时算（否则 `str.replace` 与 `list.copy`
    会被当成落盘——第一版就踩了：把 `append` 也放进名单，`defects.append(...)` 当场变成「第一次 sink」，
    整道顺序判据在每一次正常交付上假红）。主路径上真正落盘的只有 `write_out` 与 `_disk_write` 两处，
    宽判只可能早报红，不会放过坏形状。
    """
    plain = ("write", "write_text", "write_bytes", "writelines", "truncate", "mkstemp",
             "unlink", "mkdir", "makedirs", "rmtree", "copyfile", "chown", "chmod")
    module_y = ("replace", "rename", "remove", "copyfile", "copy2", "write")
    lines = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name):
            if f.id in ("write_out", "_disk_write"):
                lines.append(n.lineno)
            elif f.id == "open":
                mode = ast.unparse(n.args[1]) if len(n.args) > 1 else next(
                    (ast.unparse(k.value) for k in n.keywords if k.arg == "mode"), "")
                if any(t in mode for t in ("w", "a", "x")):
                    lines.append(n.lineno)
        elif isinstance(f, ast.Attribute):
            if f.attr in plain or f.attr.startswith("write"):
                lines.append(n.lineno)
            elif f.attr == "open":
                # `fh = OUT.open("w")` 之后 `print(…, file=fh)`：写动作藏在两行里，句柄换了名字
                # （第十六轮复核报的那发——旧写法只认裸 `open(...)` 的名字形态，属性形态整个漏掉）。
                mode = ast.unparse(n.args[0]) if n.args else next(
                    (ast.unparse(k.value) for k in n.keywords if k.arg == "mode"), "")
                if any(t in mode for t in ("w", "a", "x")):
                    lines.append(n.lineno)
            elif f.attr in module_y and isinstance(f.value, ast.Name) and f.value.id in {
                    "os", "shutil", "pathlib", "tempfile", "io", "sys"}:
                lines.append(n.lineno)
        if isinstance(f, ast.Name) and f.id == "print" and any(
                k.arg == "file" for k in n.keywords):
            # 写句柄的另一种形态：`print("坏留档", file=fh)`。它自己不是 sink，但**拿着 w 模式句柄**
            # 的 print 就是那次写；上一行那句 `OUT.open("w")` 已经把行号交了，这一条是双保险。
            lines.append(n.lineno)
    return min(lines) if lines else 0


def _escape_lines(tree: ast.AST) -> list[int]:
    """函数体内的提前逃逸：`sys.exit` / `os._exit` / `exit` / `quit`，以及 `raise SystemExit[...]`。

    两道拒收门排在落盘之前只保证「走到门时不落盘」；门之前先离开进程的话整趟根本走不到门，
    既不落盘也不拒收，磁盘上留着上一版留档冒充当轮的交付。第十四轮只堵了 `sys.exit(0)`，
    第十五轮 E 组实测 `raise SystemExit(0)` 与裸 `raise SystemExit` 都不算逃逸——
    同一种离开的方式换个写法就躲过去，正是这一族一路在犯的「认字形不认语义」。
    """
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute) and f.attr in ("exit", "_exit"):
                out.append(n.lineno)
            elif isinstance(f, ast.Name) and f.id in ("exit", "quit"):
                out.append(n.lineno)
        elif isinstance(n, ast.Raise):
            raised = n.exc
            if isinstance(raised, ast.Call):
                raised = raised.func
            if ((isinstance(raised, ast.Name) and raised.id == "SystemExit")
                    or (isinstance(raised, ast.Attribute) and raised.attr == "SystemExit")):
                out.append(n.lineno)
    return out


def _return_tuple_names(tree: ast.AST) -> list[str]:
    """函数末尾 `return a, b` 返回的那几个名字（不是元组或不是名字返回的都记 `()`）。"""
    last = [n for n in ast.walk(tree) if isinstance(n, ast.Return)]
    if not last:
        return []
    val = max(last, key=lambda n: n.lineno).value
    if isinstance(val, ast.Tuple):
        return [ast.unparse(e) for e in val.elts]
    return [ast.unparse(val)] if val is not None else []


def db_pointer_missing(targets: tuple[tuple[str, str], ...], root: pathlib.Path = ROOT,
                       must_files: tuple[str, ...] = STEP_NEW_TEST_FILES) -> list[str]:
    """本步新用例文件里**每一条 pytest 会收集的用例**都得在指针表里登记（第十三轮 A 组 NI-2）。

    从前只按文件级判：两份新文件各有四条用例、表里只登记了两条，那句话照样绿——
    「确有其事」判到文件就停了，等于把「本机证不了的那一半交给谁」说了一半。
    第十四轮 C 组 C-14-08 又把范围推进一步：`class Test*:` 里的方法与 `if True:` 里定义的函数
    都会被 pytest 收集，所以它们也得登记，登记名写成 `类::用例`（与 `db_pointer_defects` 同一口径，
    两张判据不许对同一个形状给出相反答案）。
    """
    bad: list[str] = []
    listed = {f"{f}::{fn}" for f, fn in targets}
    for rel in must_files:
        path = root / rel
        if not path.is_file():
            bad.append(f"新用例文件不在磁盘上：{rel}")
            continue
        tree = _parse_or_none(path, rel, bad)
        if tree is None:
            continue
        for case in _collect_cases(tree):
            if f"{rel}::{case}" not in listed:
                bad.append(f"{rel}::{case} 没登记进指针表（本机证不了它的运行，也没人交代去哪跑）")
    return bad


def registry_drift(registered: tuple[str, ...], present: tuple[str, ...]) -> list[str]:
    """把「登记在 `STEP_NEW_TEST_FILES` 里的新用例文件」与「git 说本步新增的那几份」对齐（双向）。

    第十四轮 C 组 C-14-08 的另一半：`STEP_NEW_TEST_FILES` 是手抄的两行文件名，于是「本步又新写了
    第三份连库用例」这件事在这两张判据里**根本不存在**——不登记就不判，正好绕开整条门禁。
    现在集合由 `g_section()` 从 git 现取（`--diff-filter=A` 自本步基线 `STEP_TEST_BASE` 起，
    再加未跟踪的 `test_*.py`），两边差集都点名。
    """
    reg, got = set(registered), set(present)
    bad: list[str] = []
    for extra in sorted(reg - got):
        bad.append(f"{extra} 登记成「本步新用例文件」，git 却说它不是本步新增的——"
                   f"这张表陈旧了，按文件级点名的那条判据也就跟着陈旧")
    for miss in sorted(got - reg):
        bad.append(f"本步新增了 {miss} 却没登记进 `STEP_NEW_TEST_FILES`——"
                   f"不在表里的用例文件，用例级点名与文件级点名都判不到它")
    return bad


def new_test_files_from_git(root: pathlib.Path = ROOT,
                            base: str = STEP_TEST_BASE) -> tuple[str, ...] | None:
    """本步在 `apps/api/tests` 下**新出现**的用例文件：git 里新增的 + 工作区未跟踪的。

    git 拿不到读数时返回 `None`（不是空元组）——空集在这里会被读成「本步没有新文件」，
    而那正好是这条核对最不该给出的答案；`g_section()` 收到 `None` 就把「没跑成」记成缺陷。
    """
    out: list[str] = []
    for argv in (["git", "diff", "--name-only", "--diff-filter=A", base, "HEAD", "--", "apps/api/tests"],
                 ["git", "ls-files", "--others", "--exclude-standard", "--", "apps/api/tests"]):
        try:
            r = subprocess.run(argv, capture_output=True, text=True, env=ENV, cwd=root)
        except OSError as exc:
            print(f"INCONCLUSIVE git 取不到新用例文件清单：{type(exc).__name__}: {exc}")
            return None
        if r.returncode:
            return None
        out += [ln.strip() for ln in (r.stdout or "").splitlines()
                if ln.strip().endswith(".py") and pathlib.PurePosixPath(ln).name.startswith("test")]
    return tuple(sorted(set(out)))


def o_ledger(af: dict[str, list[str]], o1: str, o2: str, o3: str) -> list[str]:
    """把 O 段三条读数与 `af_ids()` 的登记表对账，返回缺陷清单（空 = 三条读数彼此自洽）。

    做成**纯函数**是有意的：这一段跑一次要起三台子进程（基线 + 反证电池 + 清单），
    M 段若想把「这里核的三件事」自己反证一遍，就得等电池跑完 ⇒ 一次自证变成几十秒，
    而纯字符串进、缺陷出之后，M 段可以当场喂进「对齐的一份」与五种「故意对不上」的读数。
    ① O.1 那句「合计 PASS=p FAIL=f｜判据登记 n 条」里 `f` 必须为 0 且 `p == n`（自报计数自己得对齐）；
    ② `n` 必须等于登记表条数；③ O.3 的清单**逐条 id** 必须与登记表同一批（不只比条数——
      少一条又多一条时条数是相等的，那种读数才最像绿的）。
    O.2 的「SELF-TEST PASS」字样一起判：电池红了就不能交出绿留档。
    """
    defects: list[str] = []
    flat = [i for k in sorted(af) for i in af[k]]
    total = len(flat)
    if not total:
        defects.append(f"O 段没有分母：`af_ids()` 从 {O_HARNESS} 的 `CHECKS` 里一条判据都没数到——"
                       f"登记表形状变了（不是 `(\"AF-Xn\", 标签, 判据)` 一行一条），三处对账全部无从判定")
    # 合计行按**全部匹配**判，不只取第一条（第十三轮 A 组 MI-5：喂进两行合计、第二行才是真裁决时，
    # `re.search` 读第一行就绿了）。有多行合计本身就是异常形状，一并点名。
    tally = re.findall(r"合计 PASS=(\d+) FAIL=(\d+)｜判据登记 (\d+) 条", o1)
    if not tally:
        defects.append("O.1 里读不到「合计 PASS=… FAIL=…｜判据登记 … 条」这句计数——判据面无从对账")
    elif len(tally) > 1:
        defects.append(f"O.1 里有 {len(tally)} 行合计计数（{tally}）——同一段交出多个分母，无法判哪一个是裁决")
    else:
        p, f_, n_ = (int(x) for x in tally[0])
        if f_ or p != n_:
            defects.append(f"O.1 计数不对齐：PASS={p} FAIL={f_} 登记={n_}——应为 FAIL=0 且 PASS 等于登记条数")
        if n_ != total:
            defects.append(f"O.1 自报登记 {n_} 条，头部 `af_ids()` 从 `CHECKS` 数到 {total} 条——"
                           f"两条通道不是同一批判据")
    # O.2 判**末行**而不是「字样出现过」（同一发 MI-5：红档里回引一次旧绿字样就能骗过子串匹配）。
    # 末行要先剔掉驱动自己加的两类尾巴：段末那条 `rc=N`，以及 rc=2 时补的 INCONCLUSIVE 标注——
    # 否则「末行」永远是 `rc=0`，这条判据会在每一次正常交付上假红（第十三轮处置批自查撞上的，M 段有对照档）。
    content = [ln for ln in o2.rstrip().splitlines()
               if ln.strip() and not ln.startswith("rc=") and not ln.startswith(INCON_MARK)]
    last_o2 = content[-1] if content else ""
    if not last_o2.startswith("SELF-TEST PASS"):
        defects.append(f"O.2 的反证电池末行不是以「SELF-TEST PASS」开头而是 {last_o2!r}——"
                       f"改坏必须红这条通道没过，不能交出绿留档"
                       f"（判**前缀**而不是「字样出现过」：M 段第二档探针实测红档里回引一句"
                       f"「（上一档曾报 SELF-TEST PASS）」在子串匹配下照样读绿）")
    listed = [ln.split("｜")[0] for ln in o3.splitlines() if ln.startswith("AF-")]
    if total and sorted(set(listed)) != sorted(set(flat)):
        defects.append(
            f"O.3 清单与登记表不是同一批（清单 {len(listed)} 行 / 登记 {total} 条）——"
            f"只在清单：{sorted(set(listed) - set(flat))}；只在登记：{sorted(set(flat) - set(listed))}。"
            f"分母对不上时「覆盖 n/n 条」那句读数没有意义")
    if total and len(listed) != len(set(listed)):
        defects.append(f"O.3 清单里有重复 id（{len(listed)} 行、去重后 {len(set(listed))} 条）"
                       f"——同一批判据被数了两次，覆盖率的分母就是假的")
    return defects


def o_section() -> tuple[list[str], list[str]]:
    """O 段三条命令 + 一次 `o_ledger()` 对账。返回 (段文本, 缺陷清单)。

    与 G 段同一条教训（第十一轮复审 NIT①）：段文本塞进留档不等于它的读数被判过——
    核对逻辑在 `o_ledger()` 里，M 段那组「锚定台现算」判据负责反证它真的会红。
    """
    rel = RELPATH(EV / O_HARNESS)
    chunks = [
        run_cmd(f"python {rel}", O_TITLES[0], O_NOTES),
        run_cmd(f"python {rel} --self-test", O_TITLES[1]),
        run_cmd(f"python {rel} --list-checks", O_TITLES[2]),
    ]
    return chunks, o_ledger(af_ids(), chunks[0], chunks[1], chunks[2])


#: 段落来源登记表（第十轮复审 10-8 逼出来的显式数据结构）。
#: ARCHIVED = 命令从**上一版留档**里取、由驱动逐字重跑；CODE = 命令由本文件的代码现生成。
#: 上一版的写法是 `assert len(sections) == 9`：段数是个 magic number，改段式就得同步改它，
#: 而且它是裸 assert——`python -O` 下整条被剥掉，实测驱动照样写出一份缺了 H 段的留档并打印
#: 「回读逐字节相同」。现在期望段名取自这张表，缺一段、多一段都下得了裁决而不是 traceback。
ARCHIVED = ("A", "B", "C", "D", "E", "F", "H", "I")
CODE = ("G", "J", "K", "M", "N", "O", "L")


L_HEAD = "########## L 重放器自检：每段都必须留得下一条逐字可重跑的 `$ ` 命令\n"
L_CMD = """python - <<'PY'
import pathlib, re
t = pathlib.Path('docs/06_validation/evidence/EVD-V2-02/out_s213.txt').read_text(encoding='utf-8')
parts = re.split(r'(?m)^(########## .*)$', t)
bad = [parts[i].split()[1] for i, p in enumerate(parts) if p.startswith('########## ')
       and not any(ln.startswith('$ ') for ln in parts[i + 1].splitlines())]
print('段数（含本段）：', len([p for p in parts if p.startswith('########## ')]))
print('其中不同段字母：', len({p.split()[1][:1] for p in parts if p.startswith('########## ')}))
print('缺 `$ ` 命令的段：', bad or '无——本文件每一段都留得下重跑入口')
PY"""


def self_test(listing: bool = False) -> int:
    """M 段：判的不是留档内容，而是「驱动自己会不会静默交出一份假留档」这两条通道还在不在。

    第八轮复审 id 4 指出 L 段机检只看 `$ ` 把手在不在，把命令换成 `$ 不是命令` 它照样报「无」。
    所以取命令这件事另开反证：把手丢了仍能取到同一条命令、heredoc 要接配对、配对断了要 raise、
    整段无命令要 raise、取出来的是读数形状也要 raise（旧驱动正是栽在这一步，抄旧输出且不报错）。
    写入回读是第八轮自己撞出来的第二条：整份重放跑完、最后一次回填抛 `OSError [Errno 22]`，磁盘上
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

    # 第二台 harness（S2.1.4/S2.1.5）的同一组反证。上一轮「头部现算」那组只管到了 BD 一台，
    # 第十三轮新增 O 段与 `af_headline()`/`o_ledger()`：如果只加读数、不加反证，就等于把第十轮 10-1
    # 那条纪律在第二台上重新欠一遍（第五次复发）。这一组还顺带堵了第十三轮**真的踩过**的那发
    # `ValueError: invalid literal for int() with base 10: 'P0'`——崩栈不是裁决，所以它现在有靶子。
    g8 = "锚定台现算"
    af_map = af_ids()
    flat_af = [i for k in sorted(af_map) for i in af_map[k]]
    total_af = len(flat_af)
    bad_faces: list[str] = []
    for letter, ids in sorted(af_map.items()):
        nums = [_af_num(i, letter) for i in ids]
        if not ids or any(n is None for n in nums):
            bad_faces.append(f"{letter} 面 id 形状不是 AF-{letter}<数字>：{ids!r}")
        elif nums != list(range(nums[0], nums[0] + len(nums))):
            bad_faces.append(f"{letter} 面号数不连续：{ids!r}")
    check(g8, "四个面齐、面内号数从首号起连续（头部那两个区间才是人话）",
          "" if set(af_map) == set(AF_GROUP_NAME) and not bad_faces
          else f"面集合 {sorted(af_map)!r}，问题：{bad_faces or '面集合没齐'}")
    head_af_now = af_headline()
    check(g8, f"头部那句 AF 条数就是现算的 {total_af} 条，且不带 FAIL 字样",
          "" if "FAIL" not in head_af_now and f"AF 判据条数：{total_af} 条" in head_af_now
          else f"实得 {head_af_now!r}")
    tmpa = pathlib.Path(tempfile.mkdtemp(prefix="af_ledger_"))
    try:
        src_lines = (EV / O_HARNESS).read_text(encoding="utf-8-sig").splitlines(keepends=True)
        picks = [(i, m.group(2), f"AF-{m.group(2)}{m.group(3)}")
                 for i, ln in enumerate(src_lines) if (m := AF_LABEL.match(ln))]
        target = next(((i, k, s) for i, k, s in reversed(picks) if len(af_map.get(k, [])) > 1), None)
        if target is None:
            check(g8, "找得到可删的判据行（面内至少两条，删了才看得出清单跟着变）",
                  f"登记表里没有一个面有多条判据：{ {k: len(v) for k, v in af_map.items()} }")
        else:
            idx, face, gone = target
            harness = tmpa / "harness.py"
            harness.write_text("".join(src_lines[:idx] + src_lines[idx + 1:]), encoding="utf-8")
            af2 = af_ids(harness)
            flat2 = [i for k in sorted(af2) for i in af2[k]]
            check(g8, f"删掉 {gone} 那一行 ⇒ 清单正好少它一条",
                  "" if flat2 == [i for i in flat_af if i != gone] else f"删了 {gone} 仍得 {flat2!r}")
            head2 = af_headline(harness)
            check(g8, f"同一发删行 ⇒ 头部那句跟着变成 {total_af - 1} 条（不是写死的数）",
                  "" if f"AF 判据条数：{total_af - 1} 条" in head2 else f"实得 {head2!r}")
        shape = tmpa / "shape.py"
        shape.write_text('CHECKS = (\n    ("AF-S10", x)\n    ("AF-S2", x)\n    ("AF-P0", x)\n)\n',
                         encoding="utf-8")
        got_shape = af_ids(shape)
        check(g8, "形状档：AF-P0 不被当成数字、AF-S2 排在 AF-S10 前（第十三轮那发 ValueError 的原样）",
              "" if got_shape == {"S": ["AF-S2", "AF-S10"], "P": ["AF-P0"]} else f"实得 {got_shape!r}")

        o1_ok = f"合计 PASS={total_af} FAIL=0｜判据登记 {total_af} 条"
        o3_ok = "\n".join(f"{i}｜标签" for i in flat_af)
        ok_probe = o_ledger(af_map, o1_ok, "SELF-TEST PASS：若干条", o3_ok)
        check(g8, "对账：三条读数彼此自洽时不给缺陷（这道核对不是只会红）",
              "" if not ok_probe else f"实报 {len(ok_probe)} 处：{ok_probe[0]}")
        for label, o1_txt, want in (
                ("有判据红", f"合计 PASS={total_af} FAIL=1｜判据登记 {total_af} 条", "O.1 计数不对齐"),
                ("PASS 少于登记", f"合计 PASS={total_af - 1} FAIL=0｜判据登记 {total_af} 条", "O.1 计数不对齐"),
                ("登记数虚报", f"合计 PASS={total_af} FAIL=0｜判据登记 {total_af + 1} 条", "两条通道不是同一批判据"),
                ("整句计数丢了", "合计……这句压根没有", "判据面无从对账")):
            got = o_ledger(af_map, o1_txt, "SELF-TEST PASS：若干条", o3_ok)
            check(g8, f"对账探针：O.1 换成「{label}」必须点名「{want}」",
                  "" if any(want in d for d in got) else "沉默——这一档就是不可假的判据")
        got = o_ledger(af_map, o1_ok, "SELF-TEST FAIL：某发变异没红", o3_ok)
        check(g8, "对账探针：O.2 电池没绿时必须点名",
              "" if any("O.2" in d for d in got) else "沉默")
        second = o1_ok.replace(f"PASS={total_af} FAIL=0", f"PASS={total_af} FAIL=1", 1)
        got = o_ledger(af_map, o1_ok + "\n" + second, "SELF-TEST PASS：若干条", o3_ok)
        check(g8, "对账探针：O.1 出现两行合计（第二行才是真裁决）必须点名「多个分母」（MI-5 首档）",
              "" if any("多个分母" in d for d in got) else f"实得 {got!r}")
        got = o_ledger(af_map, o1_ok,
                       "SELF-TEST FAIL：2 处\n（上一档曾报 SELF-TEST PASS）\nrc=0\n", o3_ok)
        check(g8, "对账探针：红档里回引旧绿字样不许算绿（MI-5 第二档，从前子串匹配会读绿）",
              "" if any("O.2" in d for d in got) else f"实得 {got!r}")
        # 第十三轮处置批自查补的一档（改「判末行」时差点把自己锁死）：段体末尾那条 `rc=0` 与 rc=2 时补的
        # INCONCLUSIVE 标注都是**驱动自己加的尾巴**，不是 harness 的裁决行。剔不干净的话，
        # 「O.2 末行须是 SELF-TEST PASS」会在每一次正常交付上假红——所以这里把带尾巴的形状喂进去。
        tail_ok = o_ledger(af_map, o1_ok, "…\nSELF-TEST PASS：若干条\nrc=0\n", o3_ok)
        check(g8, "对账：O.2 的末行判定要剔掉段末 `rc=` 尾巴（否则每次正常交付都假红）",
              "" if not tail_ok else f"实报 {len(tail_ok)} 处：{tail_ok[0]}")
        incon_tail = o_ledger(af_map, o1_ok, f"…\n{INCON_MARK}\nrc=2\n", o3_ok)
        check(g8, "对账：INCONCLUSIVE 标注也算尾巴（剔完之后没有裁决行 ⇒ 必须点名）",
              "" if any("O.2" in d for d in incon_tail) else f"实得 {incon_tail!r}")
        swapped = flat_af[:-1] + ["AF-Z9"]
        got = o_ledger(af_map, o1_ok, "SELF-TEST PASS：若干条", "\n".join(f"{i}｜标签" for i in swapped))
        check(g8, "对账探针：O.3 少一条又多一条（条数相等）必须两端都点名",
              "" if any(flat_af[-1] in d and "AF-Z9" in d for d in got) else f"实得 {got!r}")
        got = o_ledger(af_map, o1_ok, "SELF-TEST PASS：若干条", "\n".join(f"{i}｜标签" for i in [flat_af[0], *flat_af]))
        check(g8, "对账探针：O.3 同一 id 列两行必须报重复（只比集合就等于没比）",
              "" if any("重复" in d for d in got) else f"实得 {got!r}")
        got = o_ledger({}, "合计 PASS=0 FAIL=0｜判据登记 0 条", "SELF-TEST PASS：若干条", "")
        check(g8, "对账探针：登记表空了要说「没有分母」（不许沉默交出绿留档）",
              "" if any("没有分母" in d for d in got) else f"实得 {got!r}")
    finally:
        shutil.rmtree(tmpa, ignore_errors=True)
    check(g8, "o_section 真的把三条读数交给 o_ledger（按 AST 取实参，不 grep 正文）",
          "" if _first_call_line(_fn_tree(o_section), "o_ledger")
          and _return_tuple_names(_fn_tree(o_section))[:1] == ["chunks"]
          else f"实得调用 {_calls_brief(_fn_tree(o_section), 'o_ledger')}、"
               f"返回 {_return_tuple_names(_fn_tree(o_section))!r}")
    check(g8, f"锚定台 {O_HARNESS} 在 EV_PY 登记表里（不在册就既不进 G 段门禁、也不算被检清单）",
          "" if O_HARNESS in EV_PY else f"实登记 {EV_PY!r}")

    # 真库指针（第十三轮自己撞出来的那一类）：P-4 用例按卡面换了文件，而「那条走 某文件::某用例」
    # 这句话从前只活在注释与 print 里——没人核对磁盘上确有其事。现在表在 `REAL_DB_TARGETS`，
    # G 段落盘前在**仓库根**上逐条核对，M 段只判这道核对的**语义**。
    # 为什么 M 段不直接判那张真表（第十三轮实测踩过）：电池把本包拷进临时目录跑，副本的 `ROOT`
    # 上面没有 `apps/` ⇒ 五条指针全报「文件不存在」，基线不绿、整批 INCONCLUSIVE——
    # 判据把自己的电池弄成「没有裁决」，是最糟的一种红。所以这里造一棵临时小树当世界。
    g9 = "真库指针"
    staged = pathlib.Path(tempfile.mkdtemp(prefix="ptr_selftest_"))
    try:
        (staged / "apps" / "tests").mkdir(parents=True)
        (staged / "apps" / "tests" / "t_one.py").write_text(
            "import pytest\n\n\ndef test_alpha():\n    pass\n\n\n"
            "@pytest.mark.parametrize('x', [1])\nasync def test_beta(x):\n    assert x\n\n\n"
            "class TestHelper:\n    def test_gamma(self):\n        pass\n\n\n"
            "class Helper:\n    def test_not_collected(self):\n        pass\n\n\n"
            "class TestOuter:\n    class TestInner:\n        async def test_deep(self):\n            pass\n\n\n"
            "try:\n    raise RuntimeError\nexcept RuntimeError:\n    def test_in_handler():\n        pass\n"
            "else:\n    def test_in_else():\n        pass\nfinally:\n    def test_in_final():\n        pass\n\n\n"
            "with pytest.MonkeyPatch().context() as _mp:\n    def test_in_with():\n        pass\n\n\n"
            "for _i in [1]:\n    def test_in_loop():\n        pass\n\n\n"
            "match _i:\n    case 1:\n        def test_in_match():\n            pass\n\n\n"
            "class UTHelper(unittest.TestCase):\n    def test_in_unittest(self):\n        pass\n\n\n"
            "class TestHasInit:\n    def __init__(self):\n        self.x = 1\n\n"
            "    def test_not_collected_init(self):\n        pass\n\n\n"
            "if True:\n    def test_delta():\n        pass\n", encoding="utf-8")
        four = ("apps/tests/t_one.py", "test_alpha")
        full = (("apps/tests/t_one.py", "test_alpha"), ("apps/tests/t_one.py", "test_beta"),
                ("apps/tests/t_one.py", "TestHelper::test_gamma"), ("apps/tests/t_one.py", "test_delta"))
        deep = tuple(("apps/tests/t_one.py", n) for n in (
            "TestOuter::TestInner::test_deep", "test_in_handler", "test_in_else",
            "test_in_final", "test_in_with", "test_in_loop", "test_in_match",
            "UTHelper::test_in_unittest"))
        check(g9, "指针核对：文件在、用例在 ⇒ 静默（这道核对不是只会红）",
              "" if not db_pointer_defects(full, staged)
              else f"实报 {db_pointer_defects(full, staged)!r}")
        got = db_pointer_defects((("apps/tests/t_one.py", "test_alpfa"),), staged)
        check(g9, "探针：用例名漂移必须点名（改名而没人动那句话就会红）",
              "" if any("pytest 会收集的用例" in d for d in got) else "沉默——这一档不可假")
        got = db_pointer_defects((("apps/tests/t_none.py", "test_alpha"),), staged)
        check(g9, "探针：文件不存在必须点名",
              "" if any("不存在" in d for d in got) else "沉默")
        # 第十四轮 C 组 C-14-08：两张判据从前对**同一个形状**给出相反答案——`db_pointer_defects`
        # 把「类里的方法」判成指空，`db_pointer_missing` 却根本不要求登记它（只看 `tree.body` 那一层）。
        # pytest 实际会收集类方法，所以统一口径：登记名允许 `类::用例`，只写裸用例名仍然指空。
        got = db_pointer_defects((("apps/tests/t_one.py", "test_gamma"),), staged)
        check(g9, "探针：类里的方法只写裸用例名仍算指针指空（那句 `file::test_gamma` 跑不动）",
              "" if any("pytest 会收集的用例" in d for d in got) else f"实得 {got!r}")
        check(g9, "探针：同一份类方法按 `类::用例` 登记时核对得到（不许一律判红）",
              "" if not db_pointer_defects((("apps/tests/t_one.py", "TestHelper::test_gamma"),), staged)
              else "登记成 `TestHelper::test_gamma` 仍然红——那这张表就没法登记类里的用例了")
        # 用例级完整性（A 组 NI-2 + C-14-08 的类内 / `if` 内形状 + 第十五轮 E 组的嵌套类与
        # try/except/else/finally、with 体）：小树里 pytest 会收集 9 条，登记表只写一条
        # ⇒ 其余 8 条必须逐条点名；全登记 ⇒ 必须静默。
        one_only = db_pointer_missing((four,), staged, must_files=("apps/tests/t_one.py",))
        named = {d.split("::", 1)[1].split(" ")[0] for d in one_only}
        check(g9, "用例级点名：登记表漏掉文件里的用例必须逐条出声（NI-2 + 嵌套类 + handler/else/finally + with"
                  " + 循环/match 体 + unittest.TestCase 子类）",
              "" if len(one_only) == 11 and named == {
                  "test_beta", "TestHelper::test_gamma", "test_delta",
                  "TestOuter::TestInner::test_deep", "test_in_handler", "test_in_else",
                  "test_in_final", "test_in_with", "test_in_loop", "test_in_match",
                  "UTHelper::test_in_unittest"} else f"实得 {sorted(named)!r}")
        # 绿档两侧：pytest 的默认口径**不收**这两种形状，把它们算进射程就是判据咬合法形状——
        # ① 不以 Test 开头且不是 TestCase 的类；② 名字以 Test 开头但自带 `__init__` 的类（文档明写跳过）。
        check(g9, "绿档：`Helper`（非 Test 名）与 `TestHasInit`（有 __init__）那两条不许被要求登记"
                  "（第十六轮复核给这条白名单补的反面——只看名字会把 pytest 不收集的形状也判成欠登记）",
              "" if "test_not_collected" not in named and "TestHasInit::test_not_collected_init" not in named
              else f"误咬 {sorted(named)!r}")
        check(g9, "探针：嵌套 Test 类要登记成 `外层::内层::用例`——只给内层前缀那种名字既跑不动也不算登记",
              "" if any("TestOuter::TestInner::test_deep" in d for d in one_only)
              else f"实得 {sorted(named)!r}")
        check(g9, "用例级判据的绿档：收集面全登记时必须静默（条数由 `_collect_cases` 现算，"
                  "这里不抄；不以 Test 开头又没有 __init__ 例外的那两条不许被要求登记）",
              "" if not db_pointer_missing((*full, *deep), staged, must_files=("apps/tests/t_one.py",))
              else f"实报 {db_pointer_missing((*full, *deep), staged, must_files=('apps/tests/t_one.py',))!r}")
        ghost = db_pointer_missing((four,), staged, must_files=("apps/tests/t_none.py",))
        check(g9, "用例级判据：文件本身不在也要出声（不许把它读成「没有用例」而静默通过）",
              "" if any("不在磁盘上" in d for d in ghost) else f"实得 {ghost!r}")
        # 解析不了的那一档（第十四轮 C 组 C-14-10）：崩栈不是裁决，而这两张核对当时直接 `ast.parse`，
        # 一份语法坏掉或用 GBK 存的用例文件会让整趟 `main()` 以 traceback 收场。
        (staged / "apps" / "tests" / "t_broken.py").write_text("def test_ok(:\n    pass\n", encoding="utf-8")
        broken = db_pointer_missing((four,), staged, must_files=("apps/tests/t_broken.py",))
        broken2 = db_pointer_defects((("apps/tests/t_broken.py", "test_ok"),), staged)
        check(g9, "探针：用例文件语法坏了要点名成缺陷，而不是让 SyntaxError 冒充裁决",
              "" if any("SyntaxError" in d for d in broken) and any("SyntaxError" in d for d in broken2)
              else f"实得 missing={broken!r} defects={broken2!r}")
        (staged / "apps" / "tests" / "t_gbk.py").write_bytes(
            "# -*- coding: gbk -*-\ndef test_中文():\n    pass\n".encode("gbk"))
        gbk = db_pointer_missing((four,), staged, must_files=("apps/tests/t_gbk.py",))
        check(g9, "探针：非 UTF-8 的用例文件（CPython 认 coding 注释）同样点名而不是抛 UnicodeDecodeError",
              "" if any("UnicodeDecodeError" in d for d in gbk) else f"实得 {gbk!r}")
    finally:
        shutil.rmtree(staged, ignore_errors=True)
    covered = {f for f, _ in REAL_DB_TARGETS}
    check(g9, f"真表非空（登记 {len(REAL_DB_TARGETS)} 条）——清空这张表就注销了整条门禁",
          "" if len(REAL_DB_TARGETS) >= 3 else f"实登记 {REAL_DB_TARGETS!r}")
    check(g9, "本步两份新用例文件都在表里（按文件级点名，空表与缺文件都出声）",
          "" if set(STEP_NEW_TEST_FILES) <= covered else f"实覆盖 {sorted(covered)!r}")
    check(g9, "指针表里的文件同时进 G 段门禁（交代去哪儿跑的文件，自己先得过静态自检）",
          "" if covered <= set(G_TEST_FILES) else f"漏进门禁：{sorted(covered - set(G_TEST_FILES))!r}")
    check(g9, "本包没有「源文件已不存在」的孤儿编译件（R13B-17：那是一发变异留下的影子）",
          "" if not orphan_pycs() else f"实得 {orphan_pycs()!r}")
    # 孤儿探测的**射程**（第十四轮 C 组 C-14-09）：上一版只 glob 包根那一层 `__pycache__`，
    # 子目录里的与直接落在包根的 `.pyc` 两类位置全都隐形——而复核临时件恰恰爱落在这两处。
    pack = pathlib.Path(tempfile.mkdtemp(prefix="pyc_selftest_"))
    try:
        (pack / "sub" / "__pycache__").mkdir(parents=True)
        (pack / "__pycache__").mkdir(parents=True)
        for rel in ("__pycache__/gone.cpython-311.pyc",
                    "sub/__pycache__/deep_gone.cpython-311-pytest-9.1.1.pyc",
                    "root_stray.cpython-311.pyc", "keep.py", "__pycache__/keep.cpython-311.pyc"):
            f = pack / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"x")
        found = set(orphan_pycs(pack))
        check(g9, "孤儿编译件：子目录与包根那两类位置都要点名（只 glob 一层就是见不到的不算判据）",
              "" if found == {"__pycache__/gone.cpython-311.pyc",
                              "sub/__pycache__/deep_gone.cpython-311-pytest-9.1.1.pyc",
                              "root_stray.cpython-311.pyc"} else f"实得 {sorted(found)!r}")
        check(g9, "绿档：源文件在册的编译件不许被咬（见什么的探测器等于没判）",
              "" if not any("keep" in x for x in found) else f"误咬 {sorted(found)!r}")
    finally:
        shutil.rmtree(pack, ignore_errors=True)
    # 名单本身不许手抄维持（第十四轮 C 组 C-14-08 的另一半）：`STEP_NEW_TEST_FILES` 不在表里，
    # 用例级与文件级两条判据就都判不到它——「本步又新写第三份连库用例」这件事等于没发生。
    check(g9, "登记表与 git 现取集合相符时静默（这条核对不是只会红）",
          "" if not registry_drift(("a.py", "b.py"), ("a.py", "b.py"))
          else f"实报 {registry_drift(('a.py', 'b.py'), ('a.py', 'b.py'))!r}")
    check(g9, "探针：本步新增了用例文件却没登记 ⇒ 必须点名（不登记就绕开整条门禁）",
          "" if any("b.py" in d for d in registry_drift(("a.py",), ("a.py", "b.py")))
          else "沉默——那张手抄名单还是可以陈旧着")
    check(g9, "探针：登记表里那份已经不是本步新增 ⇒ 也点名（陈旧名单让文件级那条一起陈旧）",
          "" if any("old.py" in d for d in registry_drift(("a.py", "old.py"), ("a.py",)))
          else "沉默")
    gtree = _fn_tree(g_section)
    check(g9, "g_section 真的在仓库根上调 db_pointer_defects（按 AST 取实参，不再 grep 正文）",
          "" if _call_args_ok(gtree, "db_pointer_defects", "REAL_DB_TARGETS")
          else f"实得调用 { _calls_brief(gtree, 'db_pointer_defects')}")
    check(g9, "g_section 真的调 db_pointer_missing（用例级那条也得接进交付判据）",
          "" if _first_call_line(gtree, "db_pointer_missing") else "g_section 里没有那次调用")
    # 第十七轮：V0.8.0 的 CI 实测抓到本步一条用例恒红（断言 `str(stmt.compile())` 里的字面值，
    # 而默认方言把值渲染成 `:source_id_1`）。这条判据当时不存在，所以十六轮都没抓到——现在补上，
    # 并且三档各配靶：坏形状必须红、修好的语义 API 不许红、污点传播断链（只认第一跳）也必须红。
    render_bad = (
        "class S:\n    def __init__(self):\n        self.calls = []\n\n"
        "    async def scalar(self, stmt):\n        self.calls.append(str(stmt.compile()))\n"
        "        return 1\n\n\n"
        "async def t(sess):\n    sql = sess.calls[0]\n    flat = ' '.join(sql.split())\n"
        '    assert "source_id = \'src-1\'" in flat\n    assert "LIMIT 1" in flat.upper()\n')
    render_good = (
        "class S:\n    def __init__(self):\n        self.calls = []\n\n"
        "    async def scalar(self, stmt):\n        self.calls.append(stmt)\n        return 1\n\n\n"
        "async def t(sess):\n    stmt = sess.calls[0]\n    assert stmt.get_limit() == 1\n"
        "    params = stmt.compile().params\n"
        '    assert any(v == "src-1" for v in params.values())\n'
        '    assert "LIKE" in str(stmt.compile()).upper()\n')
    render_defects = sql_render_defects(render_bad, "坏样例.py")
    check(g9, "探针：对 compile 渲染文本断言字面值必须点名（CI 上恒红的那一类，第十七轮由 V0.8.0 抓到）",
          "" if len(render_defects) == 2 else f"实得 {len(render_defects)} 条：{render_defects!r}")
    check(g9, "探针：污点要沿赋值与方法调用传播（`sess.calls[0]`→`sql`→`flat` 三跳都要跟上）",
          "" if {d.split(":")[1].strip().split(" ")[0] for d in render_defects}
          == {str(i) for i, ln in enumerate(render_bad.splitlines(), 1) if " in flat" in ln}
          else f"只点到这些行：{[d.split('——')[0] for d in render_defects]!r}")

    check(g9, "绿档：改成读 `get_limit()` 与 `compile().params` 的值侧之后不许再咬"
              "（「assert 里出现 .compile()」这种粗判会连正确写法一起咬掉）",
          "" if not sql_render_defects(render_good, "好样例.py")
          else f"误咬 {sql_render_defects(render_good, '好样例.py')!r}")
    # 绿档第二侧：V0.8.0 STEP-00C 给的修法是**带 literal_binds 的渲染**——那种写法就是把值内联进文本，
    # 断言字面值是它的用途。豁免掉了这一格，判据就会把修法本身判成缺陷（假红方向，同样要配靶）。
    render_lb = (
        "class S:\n    def __init__(self):\n        self.calls = []\n\n"
        "    async def scalar(self, stmt):\n"
        '        self.calls.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))\n'
        "        return 1\n\n\n"
        "async def t(sess):\n    flat = ' '.join(sess.calls[0].split())\n"
        '    assert "source_id = \'src-1\'" in flat\n')
    check(g9, "绿档：带 `literal_binds` 的渲染文本里断言字面值**是正当用法**，不许咬（这条豁免本身要能红）",
          "" if not sql_render_defects(render_lb, "修好的样例.py")
          else f"误咬 {sql_render_defects(render_lb, '修好的样例.py')!r}")
    # 第十八轮复核（R18-7/08）补的两端：豁免只认 `compile_kwargs` 这一个通道；污点要认
    # 海象与循环目标上的绑定。前者防「放过恒红」，后者防「换一种绑定写法就隐身」。
    render_escape = (
        "async def t(q):\n    sql = q.compile(**{\"literal_binds\": True})\n"
        '    assert "source_id = \'src-1\'" in str(sql)\n'
        "async def u(q):\n    flat = str(q.compile(dialect=\"literal_binds\"))\n"
        '    assert "LIMIT 1" in flat\n')
    check(g9, "探针：`compile(**{…})` 与 `compile(dialect=\"literal_binds\")` 不内联值，"
              "不许被 `compile_kwargs` 的豁免放过（R18-7）",
          "" if len(sql_render_defects(render_escape, "假豁免.py")) == 2
          else f"实得 {sql_render_defects(render_escape, '假豁免.py')!r}")
    # 两处绑定各用一个**不同的变量名**：这条判据是按名字记污点、不区分作用域（flow-insensitive），
    # 两段共用 `sql` 时，一处绑定的污点会把另一处也点亮——探针于是失去分辨力，两发变异都测不出差别
    # （第十八轮实测到：把 NamedExpr 或 For 任一分支关掉，缺陷数仍是 2/2）。这既是我这条探针的教训，
    # 也是这条判据的一个**过判方向**：跨函数同名会把没被渲染文本污染的引用一起点名。
    render_walrus = (
        "async def t(q):\n    if (sql_w := str(q.compile())):\n"
        '        assert "source_id = \'src-1\'" in sql_w\n'
        "async def u(q):\n    for sql_f in [str(q.compile())]:\n"
        '        assert "LIMIT 1" in sql_f\n')

    check(g9, "探针：海象绑定与循环目标上的渲染绑定也要点名（R18-8——只认 `=` 赋值的话，换一种绑定就隐身）",
          "" if len(sql_render_defects(render_walrus, "换绑定.py")) == 2
          else f"实得 {sql_render_defects(render_walrus, '换绑定.py')!r}")

    check(g9, "g_section 真的把这条接进交付判据（写了不调用 = 又一句好听的话）",
          "" if _first_call_line(gtree, "sql_render_defects") else "g_section 里没有那次调用")
    check(g9, "g_section 真的拿 git 现取的新增清单去喂 registry_drift（探测器写了不调用就是形容词）",
          "" if _first_call_line(gtree, "registry_drift") and _first_call_line(gtree, "new_test_files_from_git")
          else f"registry_drift 在第 {_first_call_line(gtree, 'registry_drift')} 行、"
               f"git 取清单在第 {_first_call_line(gtree, 'new_test_files_from_git')} 行")
    check(g9, "git 取不到清单时按「没跑成」记缺陷，而不是交空集让那条核对静默放行",
          "" if any("None" in ast.unparse(n.test) for n in ast.walk(gtree) if isinstance(n, ast.If))
          else "g_section 里没有「fresh 是 None 就出声」那一叉")
    check(g9, "g_section 的被检清单用 rglob 而不是只 glob 一层（子目录里那册未登记的 .py 与它的编译件互相打掩护）",
          "" if any(isinstance(n.func, ast.Attribute) and n.func.attr == "rglob"
                    for n in ast.walk(gtree) if isinstance(n, ast.Call))
          else "g_section 里没有 rglob 取件的那一次调用")
    check(g9, "g_section 末尾返回的是它自己的缺陷清单，不是空表（`return text, []` 就是把门禁注销）",
          "" if _return_tuple_names(gtree) == ["text", "defects"]
          else f"实得 return {_return_tuple_names(gtree)!r}")

    # 交付门（第十三轮 A 组 MA-3）：G/J/K/O 的缺陷最后都由 `main()` 那两道 `if` 拒收，
    # 而「门在不在」从前没有任何判据——实测把 `defects += g_defects` 改成 `pass`、把
    # `return text, defects` 改成 `return text, []`、把 `if defects:` 改成 `if False and defects:`，
    # M 段 74 条与电池 73/73 全部照样绿：被覆盖的是「判据」，从来不是「判据所在的交付门」。
    # 所以这一组判的是 main 的**形状与顺序**（AST，不收 BoolOp 那种永远不成立的死门）。
    g10 = "交付门"
    mtree = _fn_tree(main)
    d_live, d_dead = _gate_lines(mtree, "defects")
    l_live, l_dead = _gate_lines(mtree, "late")
    check(g10, "main 里以 `defects` 为条件的拒收门在位（`if defects:` 与 `if len(defects) > 0:` 同权，"
               "行为一字不差的改写不许多报一条红）",
          "" if d_live else "找不到以 defects 为条件的拒收门")
    check(g10, "main 里以 `late` 为条件的拒收门同形状在位",
          "" if l_live else "找不到以 late 为条件的拒收门")
    check(g10, "拒收条件里不许出现恒假的与项（`if False and defects:` 留着门的形状却永远不成立）",
          "" if not d_dead + l_dead else f"恒假条件在第 {sorted(d_dead + l_dead)} 行")
    merged, merged_odd = _merge_targets(mtree, "defects")
    late_merged, late_odd = _merge_targets(mtree, "late")
    want_merged = _defect_names(mtree)
    check(g10, "main 里每一个 `*_defects` 都被**无条件**并进某道拒收门（名单从代码现取，"
               "带 if 的推导式与 filter/lambda 都不收：名字在场而值可恒空）",
          "" if set(want_merged) <= set(merged) | set(late_merged) and not merged_odd + late_odd
          else f"没并进门的：{sorted(set(want_merged) - set(merged) - set(late_merged))!r}｜"
               f"可疑形状 {merged_odd + late_odd}｜实接 defects={sorted(set(merged))} late={sorted(set(late_merged))}")
    check(g10, "白名单不是写死的三条（`_defect_names` 现取；清空它 ⇒ 这一判永远假不了）",
          "" if len(want_merged) >= 3 else f"现取到 {want_merged!r}")
    sink = _sink_line(mtree)
    check(g10, "两道拒收门都排在第一次落盘之前（落盘按 **sink** 认：write_out / _disk_write / X.write_text 都算）",
          "" if sink and all(x < sink for x in d_live + l_live)
          else f"落盘在第 {sink} 行，门在 {sorted(d_live + l_live)}")
    esc = _escape_lines(mtree)
    check(g10, "main 体内不许有 sys.exit / exit 逃逸（门之前先退出 = 既不落盘也不拒收，旧留档冒充交付）",
          "" if not esc else f"main 第 {sorted(esc)} 行有退出逃逸")
    sr_calls = [n.lineno for n in ast.walk(mtree) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == "self_ref_defects"]
    check(g10, "自指扫描真的接进 main 且排在落盘之前（探测器写了不调用，就又是一句好听的话）",
          "" if sr_calls and min(sr_calls) < sink else f"调用行 {sorted(sr_calls)}，落盘在第 {sink} 行")

    # 轮次自指（第十四轮 D 组 D-14-02）。第十三轮那批把**头部模板字面量**改成了指名轮次，而同一族的
    # 另外两处一直活着：驱动注释里还有三行把第八轮那次 `OSError [Errno 22]` 写成「跑到当轮就撞到的」，
    # M 段一条判据的**名字**也被逐字印进留档（L 段第 479 行那串就是现场）。留档每轮整份重打，
    # 所以代词那句每重印一次就换一个所指——改一次措辞只能管到这一次，得让它有靶子。
    g11 = "轮次自指"
    # 扫描面：驱动 + 包里**每一册在册的** `.py`（第十五轮 E 组：从前只扫驱动，而兄弟台的判据名
    # 会被逐字印进留档——「驱动干净」这句话的射程当时只到它自己。登记表本身按 EV_PY 走，
    # 未登记的临时副本另由 g_section 点名，所以这里也不会把复核件算进来）。
    pkg_defects: list[str] = []
    scanned: list[str] = []
    here = pathlib.Path(__file__)
    face = [here, *(EV / p for p in EV_PY)]
    missing: list[str] = []
    for f in face:
        # 按**运行中的这一份**与包内在册件走，不拼 ROOT 相对路径：反证电池是把整包拷进系统临时目录
        # 跑的，那里没有 `apps/`、也没有仓库根那层结构——拼路径会让每一册都「文件不存在」而静默跳过，
        # 于是这一判在变异副本上永远绿（判据在自己的电池上失能，是最糟的一种静默）。
        if f.is_file():
            scanned.append(f.name)
            pkg_defects += self_ref_defects(f.read_text(encoding="utf-8-sig"), f.name)
        else:
            missing.append(f.name)
    check(g11, "包内每一册在册 .py 的源码都没有自指措辞（注释与判据名都算：下一轮读的人不知道那句是谁写的）",
          "" if not pkg_defects else f"{len(pkg_defects)} 处，第一处：{pkg_defects[0]}")
    # 「扫描面有多宽」不能只在**别人有缺陷时**才出声：兄弟台此刻干净，把 face 缩成 `[here]`
    # 上面那一判照样绿（第十五轮 E 组实测：这一发变异跑出 rc=0）。所以另立一条**对账扫描面本身**的判据，
    # 它读的是「该扫的册子」（从在册登记表 EV_PY 现取，**不是**从 face 现取——用 face 对账 face，
    # 缩面会两边一起变小而永远绿）与「实扫的册子」两个集合，与内容无关。
    want_face = sorted({here.name, *(pathlib.Path(p).name for p in EV_PY)})
    check(g11, "扫描面 = 驱动 + 全部在册件（应扫集合从登记表现取并与实扫对账：缩成只扫驱动一册 ⇒ 这里红，"
               "与那一册此刻干不干净无关）",
          "" if sorted(set(scanned)) == want_face and not missing
          else f"该扫 {want_face}、实扫 {sorted(set(scanned))}、读不到 {sorted(missing)}")
    # 探针里的样本也用拼接：这一行既要把措辞喂进探测器，又不能让它出现在**源码**里——
    # 写成一条字面量就会被上面那一判点名（它判的是「有没有拿代词说事」，分不清那串字符是数据还是句子）。
    dirty_probe = "第一行正常\n本" + "轮实测撞过一次\n第三行也正常\n"
    hit_probe = self_ref_defects(dirty_probe, "探针")
    check(g11, "探针：措辞混进文本时必须点名行号（探测器不许只在干净文本上静默）",
          "" if len(hit_probe) == 1 and "第 2 行" in hit_probe[0] else f"实得 {hit_probe!r}")
    eight_probe = self_ref_defects("第一行正常\n这" + "次实测先量过一遍\n", "探针")
    check(g11, "探针：登记表扩到八个词之后，同族的第二种代词写法也要被点名（射程不许停在三个字）",
          "" if len(eight_probe) == 1 and "第 2 行" in eight_probe[0] else f"实得 {eight_probe!r}")
    named_probe = self_ref_defects("第八轮当时实测撞过一次\n`65f508b` 那批重印过\n", "探针")
    check(g11, "探针：指名轮次与提交的句子一律放行（否则这条判据变成「不许提轮次」，那是禁止记账）",
          "" if not named_probe else f"误咬 {named_probe!r}")
    check(g11, "登记表非空且每一项都不是空串（清空它 ⇒ 上面两条探针只剩一档，这句话就又假不了了）",
          "" if len(SELF_REF_MARKS) >= 2 and all(SELF_REF_MARKS) else f"实得 {SELF_REF_MARKS!r}")

    # 读数归一化（第十二轮复审 B3）。上一版头部那句「段体里有三类读数……都在 `run_cmd()` 里统一处理」
    # 是模板字面量：实测在库留档里墙钟 2 处、③ 的标注 1 处、② **一处都没有**——那句声明只能靠留档
    # 恰好撞出那个形状才谈得上被证，撞不出来就永远假不了（G-23 禁的就是这种永不失败的断言）。
    # 现在每条规则自带「必须命中 / 必须不命中」两档靶子，不跑子进程也判得动；计数与正文再走两条通道对账。
    # 反样本不是凑数：`in 5s` 缺小数、`0x12` 不足 5 位，把阈值放宽就当场红。
    g5 = "归一化"
    for name, _pat, rep, pos, neg in NORMALIZATIONS:
        hit: dict[str, int] = {}
        rewrote = apply_norm(pos, 0, hit)
        check(g5, f"{name}：正样本必须被改写且计一处",
              "" if rep in rewrote and pos not in rewrote and hit.get(name) == 1
              else f"改写后还留着原样本，或计数不是 1：{hit!r}")
        keep: dict[str, int] = {}
        kept = apply_norm(neg, 0, keep)
        check(g5, f"{name}：反样本（差一位/缺小数）不许动",
              "" if kept == neg and keep.get(name, 0) == 0 else f"被误改写或计数不是 0：{keep!r}")
    h2: dict[str, int] = {}
    marked = apply_norm("某段读数", 2, h2)
    check(g5, "rc=2 才补 ③ 那句标注（末行与计数都要跟上）",
          "" if marked.endswith(INCON_MARK) and h2.get(INCON) == 1
          else f"补注={marked.endswith(INCON_MARK)}、计数 {h2!r}")
    for rc in (0, 1):
        h3: dict[str, int] = {}
        plain = apply_norm("某段读数", rc, h3)
        check(g5, f"rc={rc} 不许补 ③ 的标注（真红与没测到是两档）",
              "" if plain == "某段读数" and h3.get(INCON, 0) == 0 else f"被补了标注或计数 {h3!r}")
    check(g5, "run_cmd 真的调 apply_norm 并把 NORM_HITS 传进去（登记了却不调＝头部那几处计数是空的）",
          "" if "apply_norm(raw, rc, NORM_HITS)" in inspect.getsource(run_cmd)
          else "run_cmd 源码里没有那条调用——头部那句就又是一句叙述")
    probe_txt = ("########## Z 探针段\n$ cmd\n读数 "
                 + "／读数 ".join(rep for _n, _p, rep, _a, _b in NORMALIZATIONS)
                 + "\n" + INCON_MARK + "\nrc=0\n")
    want_counts = {name: 1 for name in NORM_CLASSES}
    led_head, led_bad = norm_ledger(want_counts, probe_txt)
    check(g5, "账：两条通道相符时不给缺陷（三类各一处都认下来）",
          "" if not led_bad else f"{len(led_bad)} 处不符：{led_bad[0]}")
    off = dict(want_counts)
    off[NORM_CLASSES[0]] = 0
    _, led_bad2 = norm_ledger(off, probe_txt)
    check(g5, f"账：故意少算 {NORM_CLASSES[0]} 一处 ⇒ 必须点名它（这条核对才可假）",
          "" if len(led_bad2) == 1 and NORM_CLASSES[0] in led_bad2[0] else f"实得 {len(led_bad2)} 处")
    check(g5, "头部那句把登记表里每一类都点到了（少一类就是又一句好听的话）",
          "" if all(name in led_head for name in NORM_CLASSES) else "有一类没出现在正文里")

    # 段末裁决（第十二轮自查）：G 段在第十一轮被修成「报了红就不交付」，而 M/N 报了红却照样落进留档、
    # 整趟 rc=0——读者得自己从十九段读数里找哪一段红了。这张 `EXPECTED_RC` 把「哪一段该出什么档」
    # 变成登记，A 段（改前红重放）必须一直红，D 段（本机无依赖）必须是 2 而不是 1。
    g6 = "段末裁决"

    def sec(letter: str, rc: int, with_mark: bool = False) -> str:
        return (f"########## {letter} 探针段\n$ cmd\n读数\n"
                + (INCON_MARK + "\n" if with_mark else "") + f"rc={rc}\n")

    good_probe = sec("A", 1) + sec("D", 2, True) + sec("B", 0)
    check(g6, "登记的三档预期（A 红 / D 没测到 / B 绿）各自自证干净（登记表被改写就红）",
          "" if not rc_gate(good_probe) else f"{len(rc_gate(good_probe))} 处：{rc_gate(good_probe)[0]}")
    for probe, who, shape in ((sec("B", 1), "B", "该绿的段报了红"),
                              (sec("D", 2), "D", "rc=2 却没带那句标注")):
        got = rc_gate(probe)
        check(g6, f"探针：{shape}必须点出 {who} 段",
              "" if any(who in d for d in got) else "rc_gate 沉默——这一段就能无声交付")
    check(g6, "探针：末行不是 `rc=N` 形状的段也要报（不许当成没这条判据）",
          "" if rc_gate("########## C 探针段\n$ cmd\n读数\nrc=没测\n") else "沉默")
    check(g6, "EXPECTED_RC 的键都得在探针里出现过（空挂的登记等于没登记）",
          "" if set(EXPECTED_RC) <= set("ADB") else f"实登记 {sorted(EXPECTED_RC)!r}")

    # 落盘权（第十二轮实测的事故形状）：复核时把一份打了变异的驱动副本放进本包直接跑，
    # `OUT` 跟着指到仓库里的 `out_s213.txt`，留档就被变异版重写了（N 段标题当场变成 M 段）。
    # `EV_PY` 那条相符判据堵的是「别把外来 .py 算进被检清单」，这一条堵的是「别拿外来 .py 当交付者」。
    g7 = "落盘权"
    check(g7, "在册件自己有权重写留档（判绿的那一档）",
          "" if not stray_copy(EV / "replay_s213.py", EV) else "在册件被自己的判定拒了")
    check(g7, "本包里的变异副本 _v12_a2d.py 必须被拒（第十二轮那起事故的原样）",
          "" if stray_copy(EV / "_v12_a2d.py", EV) else "变异副本也被当成有权落盘的那一份")
    tmpz = pathlib.Path(tempfile.mkdtemp(prefix="stray_"))
    try:
        check(g7, "临时目录里那份同名件允许落盘（它写的是自己那一份，不是仓库）",
              "" if not stray_copy(tmpz / "replay_s213.py", tmpz) else "反证电池的副本通道被堵死了")
    finally:
        shutil.rmtree(tmpz, ignore_errors=True)

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
          "写不进磁盘时报原因而不是静默过；头部那句判据条数由 `bd_ids()` 从 harness 现数，"
          "第二台（S2.1.4/S2.1.5）的头部与 O 段对账同样由 `af_ids()`/`o_ledger()` 现数并各配反证；"
          "读数归一化每一条都有正/反两档靶子且计数与正文两条通道对账；"
          "每段末行 `rc=` 与 `EXPECTED_RC` 相符；本包里的变异副本没有落盘权；"
          "「交真库跑」那句话点到的文件与用例逐条在磁盘上核对过，本步新增的用例文件与 git 现取的那份对过账；"
          "驱动源码与拼好的整份留档都没有用自指措辞说事")
    print(f"SELF-TEST PASS：{len(ran)} 条反证全过（{tally}）"
          f"——取不到命令时驱动停下，落不进磁盘时驱动也停下，两种都不许抄旧输出")
    return 0


def main() -> int:
    why = stray_copy(pathlib.Path(__file__), EV)
    if why:
        # 变异副本抢先拒收：留档是**在这一步之后**才被重写的，等到收尾的段集合判据出声时，
        # 磁盘上那份已经被改坏了（第十二轮实测：本包里跑一份 `_v12_a2d.py`，N 段标题当场变成 M 段）。
        print(f"FAIL 交付：{why}")
        return 1
    if not OUT.exists():
        # 自举依赖：A–I 段的命令是从**上一版留档**里取的，留档不在就无命令可跑。第八轮当时实测把
        # `out_s213.txt` 删掉后，驱动直接以 `FileNotFoundError` traceback 收场——那不是裁决，按项目纪律落 FAIL。
        print(f"FAIL 交付：{OUT} 不存在——A–I 段的命令取自这份留档，它没了就断链；"
              f"先 `git checkout -- {RELPATH(OUT)}` 恢复再重放（G/J/K/M/N/L 几段不依赖它）。")
        return 1
    sections = [(t, b) for t, b in split_sections(OUT.read_text(encoding="utf-8"))
                if re.match(r"^########## [A-I] ", t)]
    # G 在旧留档里也是归档段，只是自 `65f508b`（第十轮处置批）起命令改由 `g_section()` 现生成
    want = sorted([*ARCHIVED, "G"])
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
                "########## J 第七轮复审的闭合实测：四发「def 还在但活绑定已换」"
                "+ 四发「调用点在但结果不进锚」+ 两发崩栈面",
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

    # 两段式落 L：先把 L 段连同占位符写进去，再跑 L 的命令，最后回填——这样 L 的读数描述的是
    # **交付出去的这一份**（含 L 自己），而不是它运行前那一刻还没写完的版本。
    m = run_cmd(f"python {RELPATH(pathlib.Path(__file__))} --self-test",
                "########## M 取命令与落盘通道自证：把手丢了仍取到同一条，取不到就 raise；写入按字节回读逐位相同",
                "# L 只数把手，M 判的是驱动自己的两条通道：第八轮复审 id 4 说「把某段命令换成 `$ 不是命令`，"
                "L 照样报无」——那条批评成立，所以补取命令这一档；第八轮当时实测撞到过一次回填 "
                "`OSError [Errno 22]`"
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
    # N 段：每条新判据的「改坏必须红 / 等价不许假红」电池。它必须在留档落盘**之前**跑——
    # 电池会把整个证据包（含 out_s213.txt）拷进临时目录，拷到半成品就等于把半成品当成了基准。
    n = run_cmd(f"python {RELPATH(EV / 'mutate_replay_r9.py')}",
                "########## N 反证电池：M 段每条判据都要有一发能把它打红的变异（覆盖率现算，缺一条就 rc≠0）",
                "# 这一段的存在理由：第九轮报回的两条 MAJOR，恰好是上一版电池的读数**证明不了**的"
                "（回读走文本模式 ⇒ CRLF 能骗过；`ATTEMPTS`/`PAUSE` 没人判 ⇒ 改 1 改 0 照样 PASS）。\n"
                "# 所以每条新判据都要先发变异确认能红，再发等价写法确认不假红；变异锚找不到时报 FAIL 而不是跳过"
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
    ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")[:25]
    # O 段：S2.1.4/S2.1.5 的证明面 + 它自己的反证电池 + 它的判据清单（三条命令，读数在 `o_section()`
    # 里逐条核对，不是把文本塞进留档就算跑过——与 G 段同一条教训）。排在 N 之后只因为 M/N 已经把
    # 「驱动自己」与「M 段判据的电池」跑完；O 这一段管的是**仓库侧那两个函数**，与前两台并列。
    o_chunks, o_defects = o_section()
    hh = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                        capture_output=True, text=True, env=ENV, cwd=ROOT).stdout.strip()
    # HEAD 之外到底还带不带未提交改动，是让 `git status` 说的，不是我抄的（第八轮复审 id 7：
    # 上一版把「+工作区未提交改动」和 Python 版本号写死在模板里，在干净工作树上跑也会自称有改动）
    # 计数口径也要说清（第九轮复审 id 5）：本留档只担保 `docs/06_validation` + `apps/api` 两条路径，
    # 全仓库另有未跟踪项时（`_workspace/`、规划目录……），只报范围内的数字会让人以为整棵树干净。
    # 两个**历史**实测形状：dcb1ffb 那次重放时工作区有 7 个待提交文件，头部只报「6 项」（步卡在
    # `docs/任务规划V0.3.0/` 下，不在担保路径里）——所以「范围内」与「全仓库」两句话分开说，各自带号数。
    # 这一趟跑出来的号数**不在注释里抄**（第十轮复审 10-5：上一版把「现在再跑则是范围内 0 项 /
    # 全局 3 项」写死在这里，同一次提交里留档第 2 行却是「5 项 / 8 项」，两句话当场互相矛盾；
    # 抄来的工作区形状一 commit 就腐烂）——要看就读本文件生成物的第 2 行，那才是 `_porcelain` 现算的。
    def _porcelain(*pathspec: str) -> int:
        args = ["git", "status", "--porcelain"]
        if pathspec:
            args += ["--", *pathspec]
        r = subprocess.run(args, capture_output=True, text=True, env=ENV, cwd=ROOT)
        return len([ln for ln in (r.stdout or "").splitlines() if ln.strip()])

    scoped, total = _porcelain("docs/06_validation", "apps/api"), _porcelain()
    # 口径要跟着号数走（第十三轮 B 组 R13B-06）：这两个数是**留档自身落盘之前**取的，
    # 所以 `out_s213.txt` 自己那一改不在里面——读者事后按 `git status --porcelain …` 现跑必然对不上，
    # 那不对是口径而不是虚报。两句命令都印在括号里，号数才有被复核的入口。
    scope_cmd = "`git status --porcelain -- docs/06_validation apps/api | wc -l`"
    if scoped:
        state = (f"范围内（docs/06_validation + apps/api）未提交 {scoped} 项｜全仓库未提交 {total} 项"
                 f"（口径：{scope_cmd} 与 `git status --porcelain | wc -l`，取于本留档落盘之前，"
                 f"故不含 `out_s213.txt` 自己这一改）")
    elif total:
        state = (f"范围内干净（{scope_cmd} 为 0）｜全仓库另有 {total} 项未提交，本留档不担保它们")
    else:
        state = "工作树干净（全局 `git status --porcelain` 为空）"
    pyv, plat = sys.version.split()[0], sys.platform
    head_bd = bd_headline()  # 第十轮复审 10-1：这一句从前是模板字面量，加一条判据它不会跟着变
    head_af = af_headline()  # 同上，管的是第二台 harness（S2.1.4/S2.1.5）：O 段与头部这句都从 `CHECKS` 现数
    head_retry = f"重试要真的试满 {ATTEMPTS} 次且每次之间真的等 {PAUSE} 秒（注入通道与默认值各判一次）"
    head_causes = "CRLF / BOM / 半成品 / 截断四种各有专属原因（按这个顺序判）"
    # 段末 `rc=` 与归一化命中都在**全部段跑完之后**才判（M/N 也在其中）：上一版的顺序是头部先写、
    # 段落后跑，于是头部那句「三类读数都处理了」描述的是上一版留档而不是这一趟（第十二轮复审 B3）。
    sections_text = ("\n".join(rendered) + "\n" + j + "\n" + "\n".join(k_chunks) + "\n" + m + "\n" + n
                     + "\n" + "\n".join(o_chunks))
    head_norm, norm_bad = norm_ledger(NORM_HITS, sections_text)
    hits_at_header = dict(NORM_HITS)
    late = rc_gate(sections_text) + norm_bad + o_defects
    if late:
        for d in late:
            print(f"FAIL 交付：{d}")
        return 1
    header = f"""# STEP-02 执行留档（S2.1.3 委托解析层 + S2.1.4 锚定兜底删除 + S2.1.5 片段长度守卫）
# 时间 {ts}｜HEAD={hh}｜{state}｜Python {pyv}｜{plat}
# 本机依赖实测：structlog / sqlalchemy 皆无（kb.py:22-25 模块级导入）
#   ⇒ D 段只能证明「收集期即失败」，用例本身交 CI（J-5）
# 范围要说清（第十三轮自查）：这一份留档从 S2.1.3 一路记到 S2.1.5，A–N 段仍是 S2.1.3 那一轮的账，
#   S2.1.4/S2.1.5 的读数在 **O 段**（证明面基线 / 它自己的反证电池 / 判据清单）与 G 段的被检清单里。
{head_bd}
{head_af}
#   本文件每一段的命令都由**在库件** `replay_s213.py` 逐字重跑生成（`python docs/06_validation/evidence/
#   EVD-V2-02/replay_s213.py`）。两道自检收尾：L 段机检「每段都留得下一条 `$ ` 命令」（只判把手在不在），
#   M 段机检驱动自己的两条通道（取命令：把手丢了仍取到同一条、取不到就 raise；落盘：写入必须按**字节**回读
#   逐位相同——{head_causes}，{head_retry}。
#   第八轮当时实测撞到过一次回填 `OSError [Errno 22]` 而驱动照过（那句账记在 README §4.9 S-2；
#   那句事故描述从前用的是自指措辞——每轮重印都把**写它的那一轮**冒充成**读它的那一轮**）；
#   第十三轮 B 组 R13B-07 抓到并把头部改成指名轮次，第十四轮 D 组发现驱动注释里还剩三处、
#   M 段的一条判据名也被印进留档，所以现在这句话是读数而不是声明：见 M 段「轮次自指」那一组，
#   它同时扫驱动源码与拼好的整份留档（模板字面量与判据名是两个不同的漏口））；
#   那句 Errno 22 的成因**不再写成「瞬时占用」**：
#   本机实测「被读柄持有」时覆盖写不抛，能稳定抛 Errno 22 的是 win32 保留字符名、抛 Errno 13 的是目标为目录）。
#   上一版留档这些都做不到：驱动放在不入库的 `_workspace/` 里、按 `$ ` 前缀找命令又在输出时剥掉前缀，
#   前缀一丢就**不跑而直接抄旧输出**且不报错
#   ——这条账记在 README §4.9 S-2 / §4.10 与卡面差异表 D-11/D-12。
# G 段的被检清单由**在库登记表** `EV_PY` 给出，不再是 `EV/*.py` glob 现算（第十二轮实测：复核时丢进
#   本包的一份变异副本被 glob 当场吸收进清单，`$ ` 命令与 `===` 表跟着一起变）；包内出现未登记的 `.py`
#   或登记件缺档都进缺陷清单。上一版这七个文件名是我手抄进 `$ ` 行的（第十轮复审 10-14）；
#   这一段自己承重（第十一轮复审 NIT①）：驱动核对「命令里列出的份数 == 表里 `===` 的份数」且末行必须
#   `rc=0`、必须出现「合计违规 0 条」，任何一条不符都进缺陷清单、整趟 rc=1——上一版 G 报了红而驱动照样绿
# 每段 `$` 行就是**逐字可重跑**的单行命令（heredoc 段用 `python - <<'PY' … PY`，在 git bash 下、仓库根跑）
# 判据计数口径：BD-15 排在最前打印（它是行为面六条的前提），编号仍按追加顺序，不打乱既有 BD 编号的锚
# `PYTHONIOENCODING=utf-8` 现在只影响输出**好不好读**，不再是脚本**活不活得下来**的前提：见 K.1/K.4 两条裸跑
# 每一段末行那条 `rc=` 与登记表 `EXPECTED_RC` 逐段核对：A 段（改前红重放）须 1、D 段（本机无依赖）须 2、
#   其余须 0。上一版只把 G 段那一条红线接进缺陷清单，M 与 N 报了红照样落进留档、整趟 rc=0 交付
#   （第十二轮自查）——读者得自己从十九段读数里发现哪一段红了，那不是交付者该留的活。
{head_norm}
#   三类各是什么：① pytest 墙钟 `\\bin \\d+\\.\\d+s\\b` → `in <redacted>s`（每次重跑必不同，留原值就是
#   留一份不可复现的读数，第八轮复审 id 1）；② 解释器对象表示里的内存地址 `0x…` → `0x<redacted>`
#   （同一类「每次必不同」，第十一轮复审 NIT③ 抓到上一版只归一化了①却写着「除这一处全是真实输出」）；
#   ③ 任何一档 `rc=2` 时末行补一句 INCONCLUSIVE 标注——那是「压根没测到」，不能让人读成真红。
#   上一版这里写的是「段体里有**三类**读数」这种不带号数的声明，而 ② 那一类在留档里一处都没有
#   （第十二轮复审 B3）：声明只能靠留档恰好撞出那个形状才谈得上被证，撞不出来就永远假不了。现在命中
#   处数由 `apply_norm()` 逐段累加、再对正文把替换文本数一遍，两条通道不符就不交付；每条规则另带
#   「必须命中 / 必须不命中」两档靶子，M 段不跑子进程也判得动。除这些命中处，段体里的读数全是命令的真实输出。

"""
    body = header + sections_text
    # 轮次自指扫描（第十四轮 D 组 D-14-02）：留档是**每轮整份重打**的，代词那句每重印一次就把所指
    # 换成跑这一趟的那一轮——第八轮那次 `OSError [Errno 22]` 因此在下一轮的纸上仍然自称刚刚发生。
    # 头部模板字面量与各台 harness 印出来的**判据名**是两个不同的漏口，所以扫的是拼好的整份。
    sr_bad = self_ref_defects(body, "留档正文")
    if sr_bad:
        for d in sr_bad:
            print(f"FAIL 交付：{d}")
        return 1
    # 段集合先在**落盘之前**核一遍（落盘之后再发现，磁盘上已经是一份缺段的留档了：第十二轮实测
    # 本包里那份变异副本跑完就把在库 `out_s213.txt` 的 N 段标题重写成了 M 段，收尾判据只能拒收、
    # 不能 undo）。L 段此刻还在占位符上，所以这一趟只核 A–N，L 留给落盘后那一遍。
    pre_letters = sorted({x.group(1) for x in re.finditer(r"(?m)^########## ([A-Z]+)", sections_text)})
    pre_want = sorted({*ARCHIVED, *CODE} - {"L"})
    if pre_letters != pre_want:
        print(f"FAIL 交付：还没落盘，段集合就已经与登记表不符——期望 {pre_want}，实得 {pre_letters}；"
              f"这一趟拒绝写盘（写下去就是一份缺段的留档，而磁盘上的旧那份已经被覆盖）")
        return 1
    err = write_out(body + "\n" + L_HEAD + "$ " + L_CMD + "\n" + PLACEHOLDER + "\n")
    if err:
        print(f"FAIL 交付：L 段还没落下去，拒绝交出半成品——{err}")
        return 1
    lr = subprocess.run([BASH, "-c", L_CMD], capture_output=True, text=True,
                        encoding="utf-8", errors="replace", cwd=ROOT, env=ENV)
    # L 的读数也走 `apply_norm`：头部那句「除这些命中处，段体里全是真实输出」要对着**交付的整份**成立，
    # 漏掉 L 就等于让一段没归一化的读数混进留档（真撞出墙钟时，头部那句计数还会少算）。
    lraw = ((lr.stdout or "") + (lr.stderr or "")).rstrip()
    lout = apply_norm(lraw, lr.returncode, NORM_HITS) + f"\nrc={lr.returncode}"
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
    # 交付出去的**这一份**再走一遍收尾闸门：段末 `rc=` 与登记表相符、归一化两条通道对得上账、
    # 且 L 回填没有再贡献新的命中（贡献了就说明头部那句描述的不是这一份）。
    final = rc_gate(written) + norm_ledger(NORM_HITS, written)[1] + self_ref_defects(written, "落盘后的留档")
    if NORM_HITS != hits_at_header:
        final.append(f"L 回填后又归一化了读数：头部那句写的是 {hits_at_header}，这一趟结束时是 {NORM_HITS}"
                     f"——声明描述的不是交付出去的这一份")
    if final:
        for d in final:
            print(f"FAIL 交付：{d}")
        return 1
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
    print(f"写出 {OUT}（{len(written.splitlines())} 行、{len(got_letters)} 个段字母——"
          f"标题行比它多，因为 K.1–K.6 共用一个字母，两个基数都现算，见 L 段那两行）｜"
          f"回读逐字节相同（比对走 `read_bytes`，不经换行翻译）")
    return 0 if "缺 `$ ` 命令的段： 无" in written else 1


if __name__ == "__main__":
    # `--self-test` 只判取命令这条路（M 段跑的就是它），不重写留档；不带它才整份重放；
    # `--list-checks` 只把 M 段那批判据按 `组｜判据名` 打一份清单，给反证电池算覆盖率用
    _args = sys.argv[1:]
    raise SystemExit(self_test(listing="--list-checks" in _args)
                     if ("--self-test" in _args or "--list-checks" in _args) else main())
