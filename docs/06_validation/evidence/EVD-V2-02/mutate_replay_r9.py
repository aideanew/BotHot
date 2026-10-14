"""反证电池：M 段（`replay_s213.py --self-test`）**每一条**判据都要有一发能把它打红的变异——覆盖率现算，缺一条就 rc≠0。

跑法（仓库根）：`PYTHONIOENCODING=utf-8 python docs/06_validation/evidence/EVD-V2-02/mutate_replay_r9.py`
它由 `replay_s213.py` 作为 **N 段**逐字重跑，读数落在 `out_s213.txt` N 段——于是「每一条判据都真的能假」
这句话不再是我的一句叙述，而是一条谁都能重跑的命令。

为什么需要它：第九轮复审报回的两条 MAJOR，本身就是**上一版反证电池的读数证明不了的**（`write_out`
的回读走文本模式，CRLF 能骗过它；`ATTEMPTS`/`PAUSE` 两个数字没人判）。假绿与假红是同一枚硬币的两面：
前者让坏实现过关，后者让好改动被冤枉。所以每条新判据一律先发一遍变异确认「改坏确实会红」，
再发一遍等价写法确认「不改语义的写法不会假红」。

文件名保留 `mutate_replay_r9.py`（第九轮建的），**内容已含第十、十一轮的处置**：另起一个文件就等于让
两份电池各自漂移。两轮各自对着电池自己提的东西，逐条落在这里：
- 第十轮：① 它原先只比 rc ⇒ **基线不绿也会让每一发变异都报 OK**（实测：注入一条无关的红之后十发全 OK）
  ⇒ N-00 先跑一次未变异的副本，不绿就整批判 INCONCLUSIVE（rc=2）；② 每发 RED 还要红在**该红的判据组**；
  ③ `N-iso` 原先只是 print ⇒ 隔离探测器自己被反证一次（三种世界）；④ 它自己没有编码 guard ⇒
  标签里出现 `⇒` 就整段崩在 cp936 输出流上 ⇒ 补 `_ensure_utf8_stdout()` 并按 K 段那套做三发。
- 第十一轮：① 它把 `rc≠0` 一律折成 RED ⇒ rc=2（判据压根没跑）与崩栈都会伪装成「这一发变异打中了」，
  现在三档分开读，非 0 非 1、或 1 却一条可读裁决都没有的，都判 INCONCLUSIVE；② 末句「每条判据都有能
  把它打红的变异」当时是**形容词**（判据条数早已多于变异发数，而这两个数都没人报）⇒ 现在先跑
  `--list-checks` 拿驱动自报的判据全清单当分母，再按每一发红出来的 `[组] 判据名` 记账，末尾报
  「覆盖 n / m 条」并点名列出没有变异的判据；③ 编码三发全绿时原先一声不出（等于悄悄注销）⇒
  现在三发各自把实得读数打出来，绿档也留得下读数。
- 第十二轮：驱动那一版把「段体里有三类读数」写进留档头部却没有号数，而 ② 那一类在留档里一处都没有；
  同一批还撞起另一起事故——复核时把打了变异的驱动副本放进本包直接跑，`OUT` 跟着指到在库留档，
  整份 `out_s213.txt` 被变异版重写（N 段标题当场变成 M 段），而 `N-iso` 只 glob `_tmp_*`，那份
  `_v12_a2d.py` 在它眼里不存在。所以这里给归一化 / 段末裁决 / 落盘权三组新判据各配了变异，并把探测器的
  形状口径从 `_tmp_*` 改成「以 `_` 开头的文件」（`__pycache__` 是目录，不算残留——见 `residues`）。
- 第十三轮：S2.1.4/S2.1.5 进包，驱动多了 `af_ids()`/`af_headline()`/`o_ledger()` 与 O 段三条命令。
  「头部现算」那组从前只担保 BD 一台，第二台的条数如果只加读数不加反证，就是第十轮 10-1 那条纪律
  第五次欠账 ⇒ 新增 `锚定台现算` 一组（15 发 RED + 1 发 GREEN）。这一组的由来很难写轻：本轮驱动
  **真的**以 `ValueError: invalid literal for int() with base 10: 'P0'` 崩过一次（AF 的 id 是
  三段形状 `AF-<面字母><号数>`，从前那支 `int(s.split("-")[1])` 只适用于 BD 的两段形状），
  崩栈没有裁决 ⇒ 现在 `af_ids()` 不抛、形状不符由判据变红，且这一发形状本身有靶（形状档）。
  同批再加 `真库指针` 一组：本轮把 P-4 连库用例从 `test_kb_longlink_ingest.py` 搬到卡面点名的
  `test_kb_multisource_anchor.py`，而「真库那条走 某文件::某用例」这句话从前只写在 harness 的
  print 与 O 段注释里——搬一次就烂掉、没人核对磁盘上确有其事。现在名字集中在驱动的
  `REAL_DB_TARGETS`，G 段落盘前逐条按 AST 核对（grep 会放过「文件在、函数已改名」这种形状）。

三条老纪律不变：
1. **锚点失效即失败**：变异锚 `old` 若在 `replay_s213.py` 里找不到，这一发直接 FAIL 而不是跳过——
   锚点漂了就说明判据被改过而电池没跟上，跳过等于把这条反证悄悄注销。
2. **期望分三档**：`RED` 的变异必须让副本给出**可读裁决**且红在指定判据组；`GREEN` 的等价写法必须 `rc=0`；
   其余（rc=2、rc≠0 却无裁决）一律 INCONCLUSIVE，算电池不合格，而不是算打中。
3. **临时副本一律在系统临时目录**，跑完即删，仓库里不留任何以 `_` 开头的文件；`OUT` 由副本自己指着
   副本目录，所以变异出来的驱动**不会**重写仓库里的 `out_s213.txt`——这一条由探测器自证，而驱动自己
   另有一条「落盘权」判据（`stray_copy()`）：不在册的那一份连写盘的资格都没有。
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

EV = pathlib.Path(__file__).resolve().parent
DRIVER = EV / "replay_s213.py"
BATTERY = pathlib.Path(__file__).resolve()
REPO_OUT = EV / "out_s213.txt"
RC_INCONCLUSIVE = 2
FAIL_PREFIX = "FAIL 重放器自证："


def _ensure_utf8_stdout() -> None:
    """win32 默认 cp936 输出流编不出标签里的 `⇒`：裸跑不许崩（崩掉不等于裁决，见 10-7）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


_ensure_utf8_stdout()

# (标签, 变异锚, 替换成, 期望, 红/绿该落在哪个判据组)
# 组名取自 `replay_s213.py` 里 `check(组, …)` 的第一参数；写组名而不是写判据全文，是为了让
# 「合法重构新增了判据」不会把电池变成假红——但崩在别的组仍然算没堵住。
# **这张表要铺满 M 段的每一条判据**：覆盖率由 `main()` 拿驱动自报的 `--list-checks` 清单现算，
# 少一条就 rc≠0 并点名是哪几条——所以往驱动里加判据而忘记配变异，红的是那几条的名字，
# 不是我文档里那句「每条都配了」。
SHOTS: list[tuple[str, str, str, str, str]] = [
    # ↓ 取命令。这一组在第十一轮之前**没有任何变异**，判定力只由第八轮的实测兜着。
    ("把手不再剥 ⇒ 有把手的那段取到的是 `$ cmd`（取命令/把手在位取对）",
     r'lines[start] = re.sub(r"^\$ ", "", lines[start])', "pass  # 把手不再剥", "RED", "取命令"),
    ("把手改用切片硬剥 ⇒ 丢了把手就把命令切掉两字符（取命令/把手丢了仍取到同一条）",
     r'lines[start] = re.sub(r"^\$ ", "", lines[start])', "lines[start] = lines[start][2:]",
     "RED", "取命令"),
    ("heredoc 只取首行 ⇒ 配对白接（取命令/heredoc 接配对到 PY）",
     'cmd = "\\n".join(lines[start:end + 1])', "cmd = lines[start]", "RED", "取命令"),
    ("整段无命令改成交空串（取命令/整段只剩注释与空行必须 raise）",
     'raise ValueError("段里只剩注释与空行，取不到命令——拒绝用旧读数填空") from None',
     'return ""', "RED", "取命令"),
    ("heredoc 无配对改成交空串（取命令/heredoc 没有配对 PY 必须 raise）",
     'raise ValueError(f"heredoc 没有配对的 `PY` 结束行：{lines[start]!r}") from None',
     'return ""', "RED", "取命令"),
    ("读数形状不再拒绝 ⇒ 旧驱动抄旧输出就死在这一步（取命令/第一条非注释行是读数必须 raise）",
     'raise ValueError(f"第一条非注释行读起来像留档读数而不像命令：{cmd!r}——拒绝把它当命令跑")',
     "pass  # 读数照跑", "RED", "取命令"),
    # ↓ 写入判据
    ("字节相同也说不对 ⇒「逐位相同才算成」这条判据唯一的变异（写入判据/字节逐位相同才算成）",
     "if raw == want:", "if raw == want and False:", "RED", "写入判据"),
    ("删掉半成品分支", "if PLACEHOLDER in text and PLACEHOLDER not in intent:", "if False:",
     "RED", "写入判据"),
    ("半成品判据丢掉「意图里没有」那一半 ⇒ 塌回 10-4",
     "if PLACEHOLDER in text and PLACEHOLDER not in intent:", "if PLACEHOLDER in text:",
     "RED", "写入判据"),
    ("删掉 CRLF 分支", 'if raw.replace(CRLF, b"\\n") == want:', "if False:", "RED", "写入判据"),
    ("删掉 BOM 分支", "if raw.startswith(BOM):", "if False:", "RED", "写入判据"),
    ("字节比对永远算成", "if raw == want:", "if True:", "RED", "写入判据"),
    ("截断原因只说「长度不同」不给号数（10-9）",
     'return f"回读与写入不是同一份字节（写 {len(want)} 字节，读回 {len(raw)} 字节）"',
     'return "回读与写入不是同一份字节（长度不同）"', "RED", "写入判据"),
    ("删掉通用分支（10-10 的第 ① 档）",
     'return f"回读与写入不是同一份字节（写 {len(want)} 字节，读回 {len(raw)} 字节）"',
     'return ""', "RED", "写入判据"),
    # ↓ 写入通道
    ("默认落盘多写一个换行 ⇒ 磁盘上不是那一份（写入通道/临时目录里真写成＋磁盘上的字节就是这一份）",
     'OUT.write_text(text, encoding="utf-8", newline="\\n")',
     'OUT.write_text(text + "\\n", encoding="utf-8", newline="\\n")', "RED", "写入通道"),
    ("落盘异常被当成成功 ⇒ 目标是目录也照过（写入通道/目标是目录时必须报原因）",
     'last = f"落盘或回读抛异常：{type(exc).__name__}: {exc}"', 'last = ""', "RED", "写入通道"),
    ("ATTEMPTS 5→1：重试其实是装饰", "ATTEMPTS = 5", "ATTEMPTS = 1", "RED", "写入通道"),
    ("PAUSE 0.3→0：失败之间不等待", "PAUSE = 0.3", "PAUSE = 0", "RED", "写入通道"),
    ("根本不回读（write_ok 结果丢掉）", "last = write_ok(text, read())", 'last = ""', "RED", "写入通道"),
    ("失败之间不再调用 sleep", "            sleep(pause)", "            pass", "RED", "写入通道"),
    ("循环写成只跑一遍", "for i in range(attempts):", "for i in range(1):", "RED", "写入通道"),
    ("原因里不带异常类名", 'last = f"落盘或回读抛异常：{type(exc).__name__}: {exc}"',
     'last = "落盘或回读抛异常"', "RED", "写入通道"),
    ("把 OSError 换成别的类 ⇒ 异常逃出 write_out（10-10 的第 ② 档）",
     "except OSError as exc:", "except ZeroDivisionError as exc:", "RED", "写入通道"),
    ("默认 sleep 换成空函数（10-3：注入通道全绿也照样能骗过）",
     "read=_disk_read, sleep=time.sleep,", "read=_disk_read, sleep=lambda _s: None,",
     "RED", "写入通道"),
    ("默认 attempts/pause 写死成别的数 ⇒ 生产默认值与模块常量脱钩（10-3 的第二档）",
     "attempts: int = ATTEMPTS, pause: float = PAUSE", "attempts: int = 3, pause: float = 0.1",
     "RED", "写入通道"),
    ("默认 read 退回文本模式（=第九轮那条 MAJOR 的原样，10-12）",
     "return OUT.read_bytes()", 'return OUT.read_text(encoding="utf-8").encode("utf-8")',
     "RED", "写入通道"),
    # ↓ 头部现算
    ("bd_ids 写成常量 ⇒ 头部那句「判据条数」又开始撒谎（10-1）",
     "return sorted(beh, key=key), sorted(strct, key=key)",
     'return (["BD-1", "BD-2", "BD-3", "BD-4", "BD-5", "BD-6"],\n'
     '            ["BD-7", "BD-8", "BD-9", "BD-10", "BD-11", "BD-12", "BD-13", "BD-14", "BD-15", "BD-16"])',
     "RED", "头部现算"),
    ("行为面清单重复一条 ⇒ 头部那个「连续」是拼出来的（头部现算/行为面 id 从 BD-1 起连续）",
     "return sorted(beh, key=key), sorted(strct, key=key)",
     "return sorted(beh, key=key) + sorted(beh, key=key)[:1], sorted(strct, key=key)",
     "RED", "头部现算"),
    ("结构面回写成行为面 ⇒「与行为面不相交」没人判（头部现算/结构面非空、与行为面不相交）",
     "return sorted(beh, key=key), sorted(strct, key=key)",
     "return sorted(beh, key=key), sorted(beh, key=key)", "RED", "头部现算"),
    # ↓ 锚定台现算（第十三轮：S2.1.4/S2.1.5 的 O 段与 `af_headline()`/`o_ledger()` 进驱动，
    #   判据面从一台变两台。上一轮「头部现算」只担保 BD，本轮若只加读数不加反证，
    #   就是第十轮 10-1 那条纪律在第二台上第五次欠账。这一组也是本轮那发
    #   `ValueError: invalid literal for int() with base 10: 'P0'` 的靶子来源。）
    ("AF 清单按字符串排序 ⇒ AF-S10 排到 AF-S2 前（面内连续与形状档一起塌）",
     "    return {k: [i for _, i in sorted(set(v))] for k, v in groups.items()}",
     "    return {k: [i for _, i in sorted(set(v), key=lambda t: str(t[1]))] for k, v in groups.items()}",
     "RED", "锚定台现算"),
    ("登记表少登记一个面 ⇒「四个面没齐」这道门形同虚设",
     'AF_GROUP_NAME = {"P": "前提面", "B": "锚定行为面", "A": "片段行为面", "S": "结构面"}',
     'AF_GROUP_NAME = {"B": "锚定行为面", "A": "片段行为面", "S": "结构面"}',
     "RED", "锚定台现算"),
    ("af_ids 认死在库那一份 ⇒ 删一行、换形状都不跟着变",
     '    src = (path or EV / "prove_anchor_fallback.py").read_text(encoding="utf-8-sig")',
     '    src = (EV / "prove_anchor_fallback.py").read_text(encoding="utf-8-sig")',
     "RED", "锚定台现算"),
    ("头部那句把「面的个数」当判据条数 ⇒ 18 条与 4 个面混为一谈",
     'f"# **AF 判据条数：{sum(len(v) for v in groups.values())} 条——{parts}"',
     'f"# **AF 判据条数：{len(groups)} 条——{parts}"',
     "RED", "锚定台现算"),
    ("af_headline 忽略 path ⇒ 删了判据它照样报原条数（「不是写死的数」这句没被证）",
     "    groups = af_ids(path)",
     "    groups = af_ids()",
     "RED", "锚定台现算"),
    ("o_ledger 永远沉默 ⇒ O 段三条读数可以各说各话",
     "def o_ledger(af: dict[str, list[str]], o1: str, o2: str, o3: str) -> list[str]:",
     "def o_ledger(af: dict[str, list[str]], o1: str, o2: str, o3: str) -> list[str]:\n"
     "    return []  # 变异：对账永远沉默",
     "RED", "锚定台现算"),
    ("o_ledger 见人就报 ⇒「自洽时不给缺陷」那一档绿不可证",
     "    defects: list[str] = []\n    flat = [i for k in sorted(af) for i in af[k]]",
     '    defects: list[str] = ["注入：这道核对见人就报"]\n    flat = [i for k in sorted(af) for i in af[k]]',
     "RED", "锚定台现算"),
    ("O.1 只判 FAIL、不比 PASS 与登记条数",
     "        if f_ or p != n_:",
     "        if f_:",
     "RED", "锚定台现算"),
    ("登记条数与表条数不再对账 ⇒ 头部那句的分母可以是虚的",
     "        if n_ != total:",
     "        if False:",
     "RED", "锚定台现算"),
    ("O.3 退回只比条数 ⇒ 清单少一条换一条照样绿（那种读数才最像绿的）",
     "    if total and sorted(set(listed)) != sorted(set(flat)):",
     "    if total and len(listed) != total:",
     "RED", "锚定台现算"),
    ("重复行不再单独判 ⇒ 同一 id 数两行没人管",
     "    if total and len(listed) != len(set(listed)):",
     "    if False:",
     "RED", "锚定台现算"),
    ("「没有分母」那句改成别的措辞 ⇒ 探针点不到它的名（缺陷还在，但名字不可假这条没了）",
     'defects.append(f"O 段没有分母：',
     'defects.append(f"O 段空了：',
     "RED", "锚定台现算"),
    ("对账结果被丢掉 ⇒ o_section 不再把三条读数交给 o_ledger",
     "    return chunks, o_ledger(af_ids(), chunks[0], chunks[1], chunks[2])",
     "    return chunks, []",
     "RED", "锚定台现算"),
    ("锚定台没进 EV_PY ⇒ 它既不过 G 段门禁，也不算被检清单",
     '         "prove_anchor_fallback.py", "prove_article_identity.py", "prove_biz_delegation.py",',
     '         "prove_article_identity.py", "prove_biz_delegation.py",',
     "RED", "锚定台现算"),
    ("等价：AF 清单显式按 (号数, id) 排（与默认元组排序同一结果）",
     "    return {k: [i for _, i in sorted(set(v))] for k, v in groups.items()}",
     "    return {k: [i for _, i in sorted(set(v), key=lambda t: (t[0], t[1]))] for k, v in groups.items()}",
     "GREEN", ""),
    # ↓ 真库指针（第十三轮：P-4 用例按卡面换了文件，「那条走 某文件::某用例」从前只是注释）
    ("用例存在性检查被关掉 ⇒ 改名没人报",
     "        if fn not in names:",
     "        if False:",
     "RED", "真库指针"),
    ("存在性改用 grep 文本而不是 AST ⇒ 类里的方法、注释里的名字都算「确有其事」",
     "        if fn not in names:",
     '        if fn not in path.read_text(encoding="utf-8"):',
     "RED", "真库指针"),
    ("指针核对永远绿（函数一进门就返回空缺陷）⇒ 文件不存在也不报",
     "    bad: list[str] = []\n    for rel, fn in targets:",
     "    return []  # 变异：核对永远绿\n    bad: list[str] = []\n    for rel, fn in targets:",
     "RED", "真库指针"),
    ("指针核对见人就报 ⇒「文件在、用例在 ⇒ 静默」那一档绿不可证",
     "    bad: list[str] = []\n    for rel, fn in targets:",
     '    bad: list[str] = ["注入：这道核对见人就报"]\n    for rel, fn in targets:',
     "RED", "真库指针"),
    ("g_section 不再核对指针表 ⇒ G 段这条门禁只是注释",
     "    defects += db_pointer_defects(REAL_DB_TARGETS)",
     "    pass  # 变异：丢掉那次核对",
     "RED", "真库指针"),
    ("登记表清空 ⇒ 「真表非空」「两份新文件都在表里」「用例级点名」必须一起出声（空表 = 注销门禁）",
     'REAL_DB_TARGETS = (\n'
     '    ("apps/api/tests/test_kb_multisource_anchor.py", "test_multi_source_no_crash"),\n'
     '    ("apps/api/tests/test_kb_multisource_anchor.py", "test_biz_anchor_wins_when_both_anchors_exist"),\n'
     '    ("apps/api/tests/test_asset_fragment_guard.py", "test_url_fragment_short_returns_none_and_zero_query"),\n'
     '    ("apps/api/tests/test_asset_fragment_guard.py", "test_url_fragment_empty_returns_none_without_warning"),\n'
     '    ("apps/api/tests/test_asset_fragment_guard.py", "test_url_fragment_boundary_is_exactly_min_len"),\n'
     '    ("apps/api/tests/test_asset_fragment_guard.py", "test_url_fragment_query_is_source_scoped_like"),\n'
     '    ("apps/api/tests/test_kb_longlink_ingest.py", "test_long_link_yields_non_empty_biz"),\n'
     ")",
     "REAL_DB_TARGETS = ()",
     "RED", "真库指针"),
    ("登记表漏掉 S2.1.5 那份新用例文件 ⇒ 「本步两份新文件都在表里」失去对象",
     '    ("apps/api/tests/test_asset_fragment_guard.py", "test_url_fragment_short_returns_none_and_zero_query"),\n'
     '    ("apps/api/tests/test_asset_fragment_guard.py", "test_url_fragment_empty_returns_none_without_warning"),\n'
     '    ("apps/api/tests/test_asset_fragment_guard.py", "test_url_fragment_boundary_is_exactly_min_len"),\n'
     '    ("apps/api/tests/test_asset_fragment_guard.py", "test_url_fragment_query_is_source_scoped_like"),\n',
     "",
     "RED", "真库指针"),
    ("用例级判据永远静默 ⇒ 少登记一条 `test_*` 没人报（A 组 NI-2 的那一格）",
     "def db_pointer_missing(targets: tuple[tuple[str, str], ...],",
     "def db_pointer_missing(targets: tuple[tuple[str, str], ...],\n"
     "                       root: pathlib.Path = ROOT,\n"
     "                       must_files: tuple[str, ...] = STEP_NEW_TEST_FILES) -> list[str]:\n"
     "    return []  # 变异：用例级核对永远绿\n"
     "def _unused_missing(targets: tuple[tuple[str, str], ...],",
     "RED", "真库指针"),
    ("用例级判据见人就报 ⇒ 「两条都登记时给静默」那档绿不可证",
     "    bad: list[str] = []\n    listed = {f\"{f}::{fn}\" for f, fn in targets}",
     "    bad: list[str] = [\"注入：见人就报\"]\n    listed = {f\"{f}::{fn}\" for f, fn in targets}",
     "RED", "真库指针"),
    ("核对根目录被换成 `ROOT / \"docs\"` ⇒ 按 AST 取实参那条必须出声（grep 版抓不到，MI-4 的漏检档）",
     "    defects += db_pointer_defects(REAL_DB_TARGETS)",
     '    defects += db_pointer_defects(REAL_DB_TARGETS, ROOT / "docs")',
     "RED", "真库指针"),
    ("改成 `targets=REAL_DB_TARGETS` 的关键字写法 ⇒ AST 版不许把它判红（MI-4 的假红档）",
     "    defects += db_pointer_defects(REAL_DB_TARGETS)",
     "    defects += db_pointer_defects(targets=REAL_DB_TARGETS)",
     "GREEN", ""),
    ("g_section 不再调用用例级核对",
     "    defects += db_pointer_missing(REAL_DB_TARGETS)",
     "    pass  # 变异：用例级核对没接进来",
     "RED", "真库指针"),
    ("g_section 返回空缺陷表 ⇒ 它自己算出来的一切都进不了交付判据",
     "    return text, defects\n",
     "    return text, []\n",
     "RED", "真库指针"),
    ("孤儿编译件核对见人就报 ⇒「正常编译件不该被咬」那半口径失去对照"
     "（注：改 `if True` 那种写法在本电池里测不出——`stage()` 拷副本时 ignore 了 `__pycache__`，"
     "那份世界里根本没有 `.pyc`，判据照样绿；所以这一发直接把结果写成非空，逼出绿档那一判）",
     "    out = []\n    for pyc in sorted((ev / \"__pycache__\").glob(\"*.pyc\")):",
     "    out = [\"注入：见谁都咬\"]\n    for pyc in sorted((ev / \"__pycache__\").glob(\"*.pyc\")):",
     "RED", "真库指针"),
    ("指针表里的文件被从 G 段门禁名单里摘掉 ⇒ 交代去哪儿跑的文件自己不过静态自检",
     '                "apps/api/tests/test_kb_multisource_anchor.py", '
     '"apps/api/tests/test_asset_fragment_guard.py",',
     '                "apps/api/tests/test_asset_fragment_guard.py",',
     "RED", "真库指针"),
    ("等价：指针表换成 frozenset 式的写法（逐条核对的结果不变）",
     '    ("apps/api/tests/test_kb_longlink_ingest.py", "test_long_link_yields_non_empty_biz"),\n)',
     '    ("apps/api/tests/test_kb_longlink_ingest.py", "test_long_link_yields_non_empty_biz"),\n)\n'
     "REAL_DB_TARGETS = tuple(REAL_DB_TARGETS)",
     "GREEN", ""),
    # ↓ 交付门（第十三轮 A 组 MA-3：G/K/O 的缺陷最后由 main 那两道 `if` 拒收，而「门在不在」
    #   从前没有任何判据——把合并语句改成 `pass`、把死门写成 `if False and defects:`，
    #   M 段与电池全部照样绿。下面每一发都只对上一组判据里的某一条有效，逐条点名。）
    ("拒收门改成永假条件 ⇒ 「直接把名字当条件」那条必须认出来（`if False and defects:` 不是门）",
     "    if defects:\n        # 崩栈不是裁决",
     "    if False and defects:  # 变异：死门\n        # 崩栈不是裁决",
     "RED", "交付门"),
    ("收尾门同样改成永假条件",
     "    if late:\n        for d in late:",
     "    if False and late:  # 变异：死门\n        for d in late:",
     "RED", "交付门"),
    ("K 段缺陷不再并入 defects ⇒ 临时件没删干净也能交付",
     "    defects += k_defects",
     "    pass  # 变异：K 段的缺陷被丢掉",
     "RED", "交付门"),
    ("G 段缺陷不再并入 defects ⇒ 静态门禁报了红也照发",
     "            defects += g_defects",
     "            pass  # 变异：G 段的缺陷被丢掉",
     "RED", "交付门"),
    ("O 段对账缺陷不再进 late ⇒ o_ledger 白写",
     "    late = rc_gate(sections_text) + norm_bad + o_defects",
     "    late = rc_gate(sections_text) + norm_bad",
     "RED", "交付门"),
    ("把落盘挪到拒收门之前 ⇒ 「门必须排在第一次写盘之前」那条按行号认出来",
     "    k_chunks, k_defects = k_sections()",
     '    write_out("")  # 变异：先落盘再判\n    k_chunks, k_defects = k_sections()',
     "RED", "交付门"),
    # ↓ 归一化（第十二轮复审 B3：头部那句「三类读数都处理了」从前是模板字面量）
    ("墙钟阈值放宽一位 ⇒ 正样本（带小数）不再被改写",
     '("墙钟", r"\\bin \\d+\\.\\d+s\\b", "in <redacted>s", "in 12.34s", "in 5s"),',
     '("墙钟", r"\\bin \\d+s\\b", "in <redacted>s", "in 12.34s", "in 5s"),', "RED", "归一化"),
    ("墙钟正则去掉「必须有小数」⇒ 反样本 in 5s 也被吞（阈值不是装饰）",
     '("墙钟", r"\\bin \\d+\\.\\d+s\\b", "in <redacted>s", "in 12.34s", "in 5s"),',
     '("墙钟", r"\\bin \\d+\\.?\\d*s\\b", "in <redacted>s", "in 12.34s", "in 5s"),', "RED", "归一化"),
    ("地址位数下限抬到 20 ⇒ 真实对象表示不再命中",
     '("内存地址", r"\\b0x[0-9a-fA-F]{5,}\\b", "0x<redacted>",',
     '("内存地址", r"\\b0x[0-9a-fA-F]{20,}\\b", "0x<redacted>",', "RED", "归一化"),
    ("地址位数下限降到 2 ⇒ `0x12` 那种短串也被当成地址",
     '("内存地址", r"\\b0x[0-9a-fA-F]{5,}\\b", "0x<redacted>",',
     '("内存地址", r"\\b0x[0-9a-fA-F]{2,}\\b", "0x<redacted>",', "RED", "归一化"),
    ("rc=2 那一档改成 rc=3 ⇒ 没测到的段落再没有标注",
     "    if rc == 2:\n        text += ", "    if rc == 3:\n        text += ", "RED", "归一化"),
    ("rc != 0 就补标注 ⇒ 真红与没测到塌成一档",
     "    if rc == 2:\n        text += ", "    if rc >= 0:\n        text += ", "RED", "归一化"),
    ("计数写到空字典里 ⇒ 头部那句「命中 N 处」永远是 0（登记了却没人记账）",
     "out = apply_norm(raw, rc, NORM_HITS)", "out = apply_norm(raw, rc, {})", "RED", "归一化"),
    ("账的两条通道永远算相符 ⇒ 这道对账不可假",
     "if counts.get(name, 0) != again:", "if True:", "RED", "归一化"),
    ("账的原因里丢掉类名 ⇒ 少算了也不点名是哪一类",
     'defects.append(f"归一化「{name}」两条通道不符：`apply_norm` 累加 {counts.get(name, 0)} 处，"',
     'defects.append(f"归一化两条通道不符：累加 {counts.get(name, 0)} 处，"', "RED", "归一化"),
    ("头部那句只点第一类 ⇒ 又变成一句不带全号数的漂亮话",
     '+ "｜".join(f"{name} {counts.get(name, 0)} 处" for name in NORM_CLASSES)',
     '+ "｜".join(f"{name} {counts.get(name, 0)} 处" for name in NORM_CLASSES[:1])', "RED", "归一化"),
    # ↓ 段末裁决（第十一轮只修了 G 段那条红线，M/N 报红照样整趟 rc=0 交付）
    ("每段一律预期 rc=0 ⇒ A 段（改前红重放）那条登记被抹平",
     "got, want = int(tail.group(1)), EXPECTED_RC.get(letter, 0)",
     "got, want = int(tail.group(1)), 0", "RED", "段末裁决"),
    ("末行 rc 与预期不符也不管 ⇒ 红段能无声交付",
     "        got, want = int(tail.group(1)), EXPECTED_RC.get(letter, 0)\n        if got != want:",
     "        got, want = int(tail.group(1)), EXPECTED_RC.get(letter, 0)\n        if False:",
     "RED", "段末裁决"),
    ("rc=2 少了那句标注也不报 ⇒ 没测到会被读成真红",
     "if got == 2 and INCON_MARK not in body:", "if False:", "RED", "段末裁决"),
    ("末行根本不是 rc=N 的段被静默跳过（不留崩栈，只留沉默）",
     "        if not tail:\n"
     '            defects.append(f"{letter} 段末行不是 `rc=N` 形状（{lines[-1][:40]!r}）——这一段的裁决读不出来")\n'
     "            continue",
     "        if not tail:\n            continue", "RED", "段末裁决"),
    ("登记表里空挂一条 Q ⇒ 那条登记从没被探针走过",
     'EXPECTED_RC = {"A": 1, "D": 2}', 'EXPECTED_RC = {"A": 1, "D": 2, "Q": 1}', "RED", "段末裁决"),
    # ↓ 落盘权（第十二轮实测：本包里那份变异副本 `_v12_a2d.py` 跑起来就把在库留档重写了）
    ("落盘权判定反过来 ⇒ 在册件被拒、变异副本有权写盘",
     'return "" if here.resolve() == reg else (', 'return "" if here.resolve() != reg else (',
     "RED", "落盘权"),
    ("在册件的路径锚到上一层 ⇒ 临时目录那份同名件也被当成有权者",
     'reg = (ev / "replay_s213.py").resolve()', 'reg = (ev.parent / "replay_s213.py").resolve()',
     "RED", "落盘权"),
    # 等价写法：语义不变，判据必须照样全绿——假红同样是缺陷（它会把好改动挡在门外）
    ("等价：CRLF 常量写成字面量", 'if raw.replace(CRLF, b"\\n") == want:',
     'if raw.replace(b"\\r\\n", b"\\n") == want:', "GREEN", ""),
    ("等价：字节比较把两边对调", "if raw == want:", "if want == raw:", "GREEN", ""),
    ("等价：BOM 前缀用切片比", "if raw.startswith(BOM):", "if raw[:3] == BOM:", "GREEN", ""),
    ("等价：把手改用 removeprefix 剥", r'lines[start] = re.sub(r"^\$ ", "", lines[start])',
     'lines[start] = lines[start].removeprefix("$ ")', "GREEN", ""),
    ("等价：落盘改走 write_bytes（落下去的是同一份字节）",
     'OUT.write_text(text, encoding="utf-8", newline="\\n")',
     'OUT.write_bytes(text.encode("utf-8"))', "GREEN", ""),
    ("等价：归一化计数换个写法（累加顺序不影响和）",
     "hits[name] = hits.get(name, 0) + n", "hits[name] = n + hits.get(name, 0)", "GREEN", ""),
]


def norm(label: str) -> str:
    """把判据名里的**数字**统一塌成 `N` 再比：有几条判据的名字里带着 `ATTEMPTS`/`PAUSE`/字节号数，
    被变异改掉的正是这些数字——拿全文比对就会把「同一条判据」读成两条，覆盖率于是虚高。"""
    return re.sub(r"\d+", "N", label)


def stage(old: str, new: str) -> tuple[pathlib.Path, pathlib.Path, bool]:
    """把整个证据包拷进系统临时目录（保住 `parents[3]` 的层级），打上这一发变异。

    返回 `(临时根, 副本路径, 锚点命中)`：命中与否必须在**替换之前**判——替换成功后锚点当然就
    不在了，拿「替换后找不到锚」当「锚点漂了」会把每一发红报成失效。
    """
    base = pathlib.Path(tempfile.mkdtemp(prefix="n_r9_"))
    ev = base / "a" / "b" / "c" / "EVD-V2-02"
    shutil.copytree(EV, ev, ignore=shutil.ignore_patterns("__pycache__"))
    py = ev / "replay_s213.py"
    text = py.read_text(encoding="utf-8")
    hit = old in text
    if hit:
        py.write_text(text.replace(old, new, 1), encoding="utf-8")
    return base, py, hit


def spawn(py: pathlib.Path, flag: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(py), flag], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def run_selftest(py: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return spawn(py, "--self-test")


def fail_lines(proc: subprocess.CompletedProcess[str]) -> list[str]:
    """副本给出的**可读裁决**行。`rc≠0` 而这里为空 = 崩栈，按项目纪律不算堵住了任何判据。"""
    return [ln for ln in (proc.stdout or "").splitlines() if ln.startswith(FAIL_PREFIX)]


def verdict(proc: subprocess.CompletedProcess[str]) -> str:
    """三档分开读（第十一轮复审 ①）：上一版写成 `got = "RED" if rc else "GREEN"`，于是 rc=2
    （判据压根没跑）与崩栈都被折成「这一发变异打中了」——那是假绿换了个马甲。"""
    if proc.returncode == 0:
        return "GREEN"
    if proc.returncode == 1 and fail_lines(proc):
        return "RED"
    return "INCONCLUSIVE"


def baseline_checks() -> list[tuple[str, str]]:
    """判据全清单：跑驱动自己的 `--list-checks`（每行 `组｜判据名`），电池里不抄名单。

    这一档是「覆盖率」的**分母**。分母由被测件自己报，所以往驱动里加一条判据而忘记配变异，
    报红的是没覆盖的那条的名字，而不是文档里那句「每条都配了」。
    """
    proc = spawn(DRIVER, "--list-checks")
    pairs: list[tuple[str, str]] = []
    for ln in (proc.stdout or "").splitlines():
        if "｜" in ln:
            group, label = ln.split("｜", 1)
            pairs.append((group, norm(label)))
    return pairs


def hits_of(proc: subprocess.CompletedProcess[str],
            baseline: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """把这一发红出来的 `[组] 判据名` 对回登记表。对不上的不硬算命中——判据名改了而电池没跟上，
    应当表现为「那条判据没人覆盖」，而不是悄悄算成已覆盖。"""
    hit: list[tuple[str, str]] = []
    for ln in fail_lines(proc):
        body = ln[len(FAIL_PREFIX):]
        if not body.startswith("["):
            continue
        group, _, rest = body[1:].partition("] ")
        nrest = norm(rest)
        hit.extend([(g, lab) for g, lab in baseline if g == group and nrest.startswith(lab + "：")])
    return hit


#: 临时件的形状：以 `_` 开头的**文件**（`_tmp_ng.py`、K 段的 `_tmp_noarrow.py`、J 段的
#: `_harness_prefix_r7.py`，以及第十二轮复核时丢进本包的 `_v12_a2d.py`）。
#: 从前这里只 glob `_tmp_*`，于是同一批里那份 `_v12_*` 就在包里待着而探测器一声不出（第十二轮实测）。
#: 目录不算：`__pycache__` 也是 `_` 开头，把它算成残留会让每一发真电池都假红。
def residues(dir_: pathlib.Path) -> list[str]:
    return sorted(p.name for p in dir_.iterdir() if p.is_file() and p.name.startswith("_"))


def isolate(before: bytes, path: pathlib.Path) -> tuple[str, str]:
    """两条隔离判据：留档字节没变、同目录不留临时件。返回 (原因, 读数)，空原因才算绿。"""
    now = path.read_bytes() if path.exists() else b""
    why = "" if now == before else f"运行期间 `{path.name}` 字节变了：{len(before)} → {len(now)}"
    left = residues(path.parent)
    if left:
        why = f"{why}；同目录留下临时副本：{left}" if why else f"同目录留下临时副本：{left}"
    return why, f"字节 {len(now)}、临时件 {left or '无'}"


def isolate_selfcheck() -> tuple[str, int]:
    """反证探测器自己（第十轮复审 10-6：`N-iso` 原先只是 print，没有任何形状能把它打红）。

    在临时目录里造五种世界：① 留档字节变了 / ② 留下 `_tmp_*` / ③ 留下 `_v12_*`（第十二轮那种非
    `_tmp` 前缀的变异副本）/ ④ 只有**正常命名**的在库件与 `__pycache__` 目录 / ⑤ 什么都没有。
    前三次必须报红，后两次必须报绿——只会在坏消息上吱一声、永远沉默、或见文件就咬的探测器
    都不算判据（G-23）。返回 `(原因, 走过的世界数)`：那句「几种都判对」的号数由现场数出来，
    不是我抄进 print 的（第十轮抄的是「三种」，这一版加到五种，抄的话现在正说着谎）。
    """
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="iso_r10_"))
    worlds = 0
    try:
        doc = tmp / "out_s213.txt"
        doc.write_bytes(b"abc")

        def one(want_why: bool, shape: str, before: bytes = b"abc") -> str:
            nonlocal worlds
            worlds += 1
            why, _ = isolate(before, doc)
            if want_why and not why:
                return f"探测器对「{shape}」报绿——`N-iso` 不可假"
            if not want_why and why:
                return f"探测器对「{shape}」报红（{why}）——见什么都咬的探测器等于没判"
            return ""

        def swap(old: str, new: str) -> None:
            if (tmp / old).exists():
                (tmp / old).unlink()
            (tmp / new).write_text("", encoding="utf-8")

        (tmp / "_tmp_evil.py").write_text("", encoding="utf-8")
        for want, shape, before in ((True, "留档字节变了", b"xyz"),
                                    (True, "同目录留下 _tmp_*", b"abc")):
            why = one(want, shape, before)
            if why:
                return why, worlds
        swap("_tmp_evil.py", "_v12_a2d.py")
        why = one(True, "同目录留下 _v12_*")
        if why:
            return why, worlds
        swap("_v12_a2d.py", "prove_something.py")
        (tmp / "__pycache__").mkdir()
        why = one(False, "只有正常命名件与 `__pycache__` 目录")
        if why:
            return why, worlds
        (tmp / "prove_something.py").unlink()
        why = one(False, "两种坏形状都没有")
        if why:
            return why, worlds
        return "", worlds
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def print_labels() -> int:
    """`--print-labels`：把全部标签往**当前输出流**上原样打一遍，供编码三发用（不跑电池本体）。"""
    for shot in SHOTS:
        print(shot[0])
    print("N-enc 标签行数（上面每一行都要能编得出去）")
    return 0


def stage_battery(transform) -> tuple[pathlib.Path, pathlib.Path]:
    """把**本电池**拷成一份临时副本再打靶——编码这一档判的是电池自己的打印流。"""
    base = pathlib.Path(tempfile.mkdtemp(prefix="n_r9_enc_"))
    dst = base / "mutate_replay_r9.py"
    dst.write_text(transform(BATTERY.read_text(encoding="utf-8-sig")), encoding="utf-8")
    return base, dst


def encoding_probe() -> list[str]:
    """三发（裸跑 / 关 guard / 抽靶），照 K.1–K.3 的形状判电池自己的 cp936 打印流。

    第十轮复审 10-7 的实测：往驱动里加一条标签含 `⇒` 的判据后，本电池崩在
    `UnicodeEncodeError: 'gbk' codec can't encode character '\\u21d2'`——零裁决，
    正是 K 段存在理由里那个「第三种形态」。所以这里既补 guard，也给 guard 配反证。

    **绿档也要出声**（第十一轮复审 ③）：上一版三发全按时只 return 空清单、一行读数都不打，
    于是「编码自证」在留档里长得像一段没跑过的判据。现在每发各自打印实得 rc、traceback 行数与
    stdout 行数——绿的时候也留得下读数。
    """
    reasons: list[str] = []
    env = {k: v for k, v in os.environ.items() if k != "PYTHONIOENCODING"}
    label = " | ".join(s[0] for s in SHOTS)
    target_in_labels = "⇒" in label

    def run(dst: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(dst), "--print-labels"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=env)

    bases = []
    try:
        for name, transform in (("裸跑", lambda t: t),
                                ("关 guard", lambda t: re.sub(r"(?m)^_ensure_utf8_stdout\(\)\r?$",
                                                              "pass  # guard disabled", t)),
                                ("抽靶（⇒ 全换成 ->）", lambda t: t.replace("⇒", "->"))):
            base, dst = stage_battery(transform)
            bases.append(base)
            staged = dst.read_text(encoding="utf-8")
            if name.startswith("关 guard") and "guard disabled" not in staged:
                reasons.append("编码/关 guard：靶没打上（副本里那句 guard 调用行没被替换掉），"
                               "这一档等于没跑")
            if name.startswith("抽靶") and "⇒" in staged:
                reasons.append("编码/抽靶：靶字没抽干净，这一档等于没跑")
            proc = run(dst)
            tb = (proc.stderr or "").count("Traceback")
            print(f"N-enc 编码/{name}：rc={proc.returncode}、stderr 里 traceback 行数={tb}、"
                  f"stdout 行数={len((proc.stdout or '').splitlines())}（标签里 `⇒` 在场={target_in_labels}）")
            if name == "裸跑":
                if proc.returncode or tb:
                    reasons.append(f"编码/裸跑：guard 在位却崩了（rc={proc.returncode}、traceback {tb} 行）")
            elif name.startswith("关 guard"):
                if target_in_labels and not (proc.returncode or tb):
                    reasons.append("编码/关 guard：靶字在、关掉 guard 也没崩 ⇒ 这一档没有靶，"
                                   "「编码自证」是装饰（或 guard 根本没承重）")
                if not target_in_labels:
                    reasons.append("编码/关 guard：标签里一个 `⇒` 都没有 ⇒ 这档不构成证据，"
                                   "要么把靶加回来，要么把这档删掉（G-23）")
            else:  # 抽靶
                if proc.returncode or tb:
                    reasons.append(f"编码/抽靶：靶字抽掉后仍崩（rc={proc.returncode}、traceback {tb} 行）"
                                   "⇒ 崩的不是 `⇒`，前面那发「关 guard 会崩」不能归因给编码这档")
    finally:
        for base in bases:
            shutil.rmtree(base, ignore_errors=True)
    return reasons


def main() -> int:
    if "--print-labels" in sys.argv[1:]:
        return print_labels()
    if not DRIVER.exists():
        print(f"FAIL 电池：驱动不在 {DRIVER}")
        return 1
    bad: list[str] = []

    # 分母先取：判据清单由驱动自己报，电池不抄名单。报不出分母 ⇒ 整批判 INCONCLUSIVE，
    # 而不是「覆盖 0/0」那种看起来像满分的东西。
    baseline = baseline_checks()
    if not baseline:
        print("FAIL 电池：`--list-checks` 一条判据都没列出来 ⇒ 覆盖率没有分母，整批判 INCONCLUSIVE"
              "（别把这一档读成「全都覆盖了」）")
        return RC_INCONCLUSIVE
    tally: dict[str, int] = {}
    for g, _ in baseline:
        tally[g] = tally.get(g, 0) + 1
    print(f"N-0 清单：驱动自报 {len(baseline)} 条判据（"
          + "、".join(f"{k} {v} 条" for k, v in tally.items()) + "）——下面按判据名记账覆盖")

    # N-00 基线：**未变异**的副本必须先绿。没有这一发时，「变异全报 OK」可以在一条无关的红上成立
    # （第十轮复审 10-6 的实测形状）——那些 OK 什么都没证明。
    # 「未变异」用一次自身替换表达（锚 = 替换值），省得给 `stage()` 开一条「空锚」的特殊分支。
    base, py, _ = stage("ATTEMPTS = 5", "ATTEMPTS = 5")
    proc = run_selftest(py)
    shutil.rmtree(base, ignore_errors=True)
    if proc.returncode:
        why = fail_lines(proc)
        print(f"N-00 INCONCLUSIVE 基线副本不绿（rc={proc.returncode}）："
              f"{(why[0][:120] if why else '一条可读裁决都没有，是崩栈不是红')}")
        print("INCONCLUSIVE 电池：下面每一发的「红」都可能来自这条无关的红，整批不作数")
        return RC_INCONCLUSIVE
    print("N-00 基线 GREEN 未变异副本 rc=0（后面每一发的红才只可能来自那一发变异）")

    # 探测器自证：`N-iso` 那两行必须有能红起来的形状（10-6）
    bad += encoding_probe()
    iso_why, iso_worlds = isolate_selfcheck()
    if iso_why:
        bad.append(f"隔离探测器不可假：{iso_why}")
    print(f"N-iso 探测器自证（{iso_worlds} 种世界：字节变 / `_tmp_*` / `_v12_*` / 只有正常命名件与目录 /"
          f" 都干净）：{'OK ' + str(iso_worlds) + ' 种都判对' if not iso_why else 'BAD ' + iso_why}")

    snapshot = REPO_OUT.read_bytes() if REPO_OUT.exists() else b""
    covered: set[tuple[str, str]] = set()
    red_n = green_n = incon_n = 0
    for i, (label, old, new, want, group) in enumerate(SHOTS, 1):
        base, py, hit = stage(old, new)
        if not hit:
            bad.append(f"{label}：变异锚在驱动里找不到（锚点漂了，这条反证已注销）——{old!r}")
            print(f"N-{i:02d} FAIL {label}｜锚点失效")
            shutil.rmtree(base, ignore_errors=True)
            continue
        proc = run_selftest(py)
        got = verdict(proc)
        why = fail_lines(proc)
        hit_labels = hits_of(proc, baseline)
        if got != want:
            bad.append(f"{label}：期望 {want}，实得 {got}（rc={proc.returncode}）"
                       + ("——rc 不是 0、也不是「1 加可读裁决」：崩栈或没跑都不算打中"
                          if got == "INCONCLUSIVE" else ""))
        elif want == "RED" and group and not any(f"[{group}]" in ln for ln in why):
            # 「红」还得红得对：红在别的判据组，不算堵住这条判据
            bad.append(f"{label}：红了，但没有一条落在『{group}』组"
                       f"（首行 {why[0][:80]!r}）——可能只是别处崩了")
        if want == "RED":
            red_n += got == "RED"
            incon_n += got == "INCONCLUSIVE"
            covered.update(hit_labels)
        else:
            green_n += got == "GREEN"
        tag = "OK  " if got == want else "BAD "
        print(f"N-{i:02d} 应 {want:5} 实 {got:5} {tag}{label}"
              + (f"｜应红在『{group}』组" if want == "RED" else ""))
        if got == "RED" and hit_labels:
            uniq = list(dict.fromkeys(hit_labels))
            print(f"      └─ 命中 {len(hit_labels)} 条："
                  + "、".join(f"[{g}] {lab}" for g, lab in uniq)[:260])
        elif got == "RED":
            print(f"      └─ 一条 FAIL 行都没对回登记表（判据名改了而电池没跟上？"
                  f"首行 {why[0][:80]!r}）")
        shutil.rmtree(base, ignore_errors=True)

    # 副本隔离回读：电池只碰临时目录，仓库留档必须一个字节都没动、本包不留 `_tmp_*`
    iso_reason, iso_read = isolate(snapshot, REPO_OUT)
    print(f"N-iso 仓库 `out_s213.txt` 与临时件残留：{'未改动、无残留' if not iso_reason else iso_reason}"
          f"（{iso_read}）")
    if iso_reason:
        bad.append(f"隔离被破坏：{iso_reason}")

    # 覆盖率：分母 = 驱动自报的判据清单（按 `norm()` 塌数去重），分子 = 全部 RED 变异命中的判据并集。
    # 少了就点名列出并判红——这一档把末句「每条判据都有能把它打红的变异」从形容词改成读数。
    # 去重是必需的（第十二轮实测）：`rc=0 不许补…` 与 `rc=1 不许补…` 塌数后同名，一发变异同时堵住两条，
    # 当时报的是「覆盖 49 / 共 50 条」却又写着「每条都配到了变异」——两个读数当场互相矛盾。
    uniq = list(dict.fromkeys(baseline))
    uncovered = [f"[{g}] {lab}" for g, lab in uniq if (g, lab) not in covered]
    dup = len(baseline) - len(uniq)
    print(f"N-覆 覆盖率：{len(covered)} / {len(uniq)} 条判据各有一发「改坏会红」的变异"
          f"（清单 {len(baseline)} 行，塌数后同名 {dup} 行——那一发同时堵住它们）"
          + (f"；未覆盖 {len(uncovered)} 条：{uncovered}" if uncovered else "——每条都配到了变异"))
    if uncovered:
        bad.append(f"{len(uncovered)} 条判据至今没有任何变异能把它打红：{uncovered}")

    for b in bad:
        print(f"FAIL 电池：{b}")
    want_red = sum(1 for s in SHOTS if s[3] == "RED")
    want_green = len(SHOTS) - want_red
    if bad:
        print(f"N-总 电池判红：{len(bad)} 处不符"
              f"（应红 {want_red} 发实红 {red_n} 发、其中 INCONCLUSIVE {incon_n} 发 / "
              f"等价不许假红 {want_green} 发实绿 {green_n} 发 / 覆盖 {len(covered)}/{len(uniq)}）")
        return 1
    print(f"N-总 电池全符合：{len(SHOTS)} 发全部落在期望档上"
          f"（{want_red} 发「改坏必须红、且红在该红的判据组」全红，INCONCLUSIVE {incon_n} 发 / "
          f"{want_green} 发「等价写法不许假红」全绿）＋ N-00 基线 ＋ N-iso 探测器自证 ＋ 编码三发；"
          f"覆盖面 {len(covered)}/{len(uniq)} 条判据由 `--list-checks` 现算后按 `norm()` 塌数去重，非手抄"
          f"（发数由 `len(SHOTS)` 现算）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
