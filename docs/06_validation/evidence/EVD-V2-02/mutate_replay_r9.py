"""第九轮处置的反证电池：M 段新添的每一条判据，都必须「改坏能红」；等价写法必须不假红。

跑法（仓库根）：`PYTHONIOENCODING=utf-8 python docs/06_validation/evidence/EVD-V2-02/mutate_replay_r9.py`
它由 `replay_s213.py` 作为 **N 段**逐字重跑，读数落在 `out_s213.txt` N 段——于是「每一条新判据都真的
能假」这句话不再是我的一句叙述，而是一条谁都能重跑的命令。

为什么需要它：第九轮复审报回的两条 MAJOR，本身就是**上一版反证电池的读数证明不了的**——
`write_out` 的回读走文本模式（CRLF 能骗过它），`ATTEMPTS`/`PAUSE` 两个数字没人判。
所以本轮处置新加的判据，一律先发一遍变异确认「改坏确实会红」，再发一遍等价写法确认「不改语义的
写法不会假红」。假绿与假红是同一枚硬币的两面：前者让坏实现过关，后者让好改动被冤枉。

三条纪律：
1. **锚点失效即失败**：变异锚 `old` 若在 `replay_s213.py` 里找不到，本脚本报 FAIL 而不是跳过——
   锚点漂了就说明判据被改过而电池没跟上，跳过等于把这条反证悄悄注销（`replay_s213.py` 的 M 段
   对「取不到命令」用的是同一套 raise-first 口径）。
2. **期望分两档**：`RED` 的变异必须让被变异副本 `rc≠0`；`GREEN` 的等价写法必须 `rc=0`。
3. **临时副本一律在系统临时目录**，跑完即删，仓库里不留任何 `_tmp_*`；`OUT` 由副本自己指着副本目录，
   所以变异出来的驱动**不会**重写仓库里的 `out_s213.txt`（这一点由 `J-11/J-12` 式的回读兜住：
   跑完后核对仓库留档的字节数没变）。
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

EV = pathlib.Path(__file__).resolve().parent
DRIVER = EV / "replay_s213.py"
REPO_OUT = EV / "out_s213.txt"

# (标签, 变异锚, 替换成, 期望)
SHOTS: list[tuple[str, str, str, str]] = [
    ("ATTEMPTS 5→1：重试其实是装饰", "ATTEMPTS = 5", "ATTEMPTS = 1", "RED"),
    ("PAUSE 0.3→0：失败之间不等待", "PAUSE = 0.3", "PAUSE = 0", "RED"),
    ("删掉半成品分支", "if PLACEHOLDER in text:", "if False:", "RED"),
    ("删掉 CRLF 分支", 'if raw.replace(CRLF, b"\\n") == want:', "if False:", "RED"),
    ("删掉 BOM 分支", "if raw.startswith(BOM):", "if False:", "RED"),
    ("字节比对永远算成", "if raw == want:", "if True:", "RED"),
    ("根本不回读（write_ok 结果丢掉）", "last = write_ok(text, read())", 'last = ""', "RED"),
    ("失败之间不再调用 sleep", "            sleep(pause)", "            pass", "RED"),
    ("循环写成只跑一遍", "for i in range(attempts):", "for i in range(1):", "RED"),
    ("原因里不带异常类名", 'last = f"落盘或回读抛异常：{type(exc).__name__}: {exc}"',
     'last = "落盘或回读抛异常"', "RED"),
    # 等价写法：语义不变，判据必须照样全绿——假红同样是缺陷（它会把好改动挡在门外）
    ("等价：CRLF 常量写成字面量", 'if raw.replace(CRLF, b"\\n") == want:',
     'if raw.replace(b"\\r\\n", b"\\n") == want:', "GREEN"),
    ("等价：read_bytes 换成读文本再编码", "return OUT.read_bytes()",
     'return OUT.read_text(encoding="utf-8").encode("utf-8")', "GREEN"),
]


def stage(old: str, new: str) -> tuple[pathlib.Path, pathlib.Path, bool]:
    """把整个证据包拷进系统临时目录（保住 `parents[3]` 的层级），打上这一发变异。

    返回 `(临时根, 副本路径, 锚点命中)`：命中与否必须在**替换之前**判——替换成功后锚点当然就
    不在了，拿「替换后找不到锚」当「锚点漂了」会把每一发红报成失效。
    """
    base = pathlib.Path(tempfile.mkdtemp(prefix="n_r9_"))
    ev = base / "a" / "b" / "c" / "EVD-V2-02"
    shutil.copytree(EV, ev)
    py = ev / "replay_s213.py"
    text = py.read_text(encoding="utf-8")
    hit = old in text
    if hit:
        py.write_text(text.replace(old, new, 1), encoding="utf-8")
    return base, py, hit


def main() -> int:
    if not DRIVER.exists():
        print(f"FAIL 电池：驱动不在 {DRIVER}")
        return 1
    out_bytes = REPO_OUT.read_bytes() if REPO_OUT.exists() else b""
    bad: list[str] = []
    red_n = green_n = 0
    for i, (label, old, new, want) in enumerate(SHOTS, 1):
        base, py, hit = stage(old, new)
        if not hit:
            bad.append(f"{label}：变异锚在驱动里找不到（锚点漂了，这条反证已注销）——{old!r}")
            print(f"N-{i:02d} FAIL {label}｜锚点失效")
            shutil.rmtree(base, ignore_errors=True)
            continue
        r = subprocess.run([sys.executable, str(py), "--self-test"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        got = "RED" if r.returncode else "GREEN"
        first = next((ln for ln in (r.stdout or "").splitlines() if ln.startswith("FAIL")), "")
        if got != want:
            bad.append(f"{label}：期望 {want}，实得 {got}（rc={r.returncode}）")
        if want == "RED":
            red_n += got == "RED"
        else:
            green_n += got == "GREEN"
        print(f"N-{i:02d} 应 {want:5} 实 {got:5} {'OK  ' if got == want else 'BAD '}{label}")
        if got == "RED" and first:
            print(f"      └─ {first[:120]}")
        shutil.rmtree(base, ignore_errors=True)

    # 副本隔离回读：电池只碰临时目录，仓库留档必须一个字节都没动
    untouched = (REPO_OUT.read_bytes() if REPO_OUT.exists() else b"") == out_bytes
    print(f"N-iso 仓库 `out_s213.txt` 在电池运行期间未被改动：{untouched}")
    leftovers = sorted(p.name for p in EV.glob("_tmp_*"))
    print(f"N-iso 本包目录里的临时副本残留：{leftovers or '无'}")

    for b in bad:
        print(f"FAIL 电池：{b}")
    want_red = sum(1 for s in SHOTS if s[3] == "RED")
    want_green = len(SHOTS) - want_red
    if bad or not untouched or leftovers:
        print(f"N-总 电池判红：{len(bad)} 处不符"
              f"（应红 {want_red} 发实红 {red_n} 发 / 等价不许假红 {want_green} 发实绿 {green_n} 发）")
        return 1
    print(f"N-总 电池全符合：{len(SHOTS)} 发全部落在期望档上"
          f"（{want_red} 发「改坏必须红」全红 / {want_green} 发「等价写法不许假红」全绿）"
          f"——M 段每条新判据都有能把它打红的变异")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
