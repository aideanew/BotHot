"""J 段驱动：拿**两版 harness**（改前 = `git show de78125:…`，改后 = 工作区/本包这一版）对同一批
攻击体各跑一遍，逐发打印 `改前 rc/红/traceback` 与 `改后 rc/红/traceback`。
「第七轮那四条空过在改前确实空过」这句话的证据就是它的输出，不是叙述。

临时件只有两处：探针 harness 写在本包目录（脚本用 `parents[4]` 反推仓库根，放在别处会指错），
kb 攻击副本写在 `tempfile.mkdtemp`，跑完各自删掉——J-11 是这条清理的回读。
"""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[4]
EV = ROOT / "docs/06_validation/evidence/EVD-V2-02"


def _ensure_utf8_stdout() -> None:
    """win32 默认 cp936 输出流编不出本文件的 `⇒`：裸跑不许崩（崩掉不等于裁决）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


_ensure_utf8_stdout()

NEW = (EV / "prove_biz_delegation.py").read_text(encoding="utf-8")
OLD = subprocess.run(["git", "show", "de78125:docs/06_validation/evidence/EVD-V2-02/prove_biz_delegation.py"],
                     capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
# 第十轮复审 10-8：这一处原先是裸 `assert`。两个坏处——`python -O` 下整条被剥掉，脚本会拿空串当
# 「改前版 harness」继续跑，把「取不到基准」演成「两版都绿」；而真跑起来时它以 traceback 收场，
# 崩栈在本项目里不等于裁决。所以改成立即下 FAIL 并退出 1。
if not OLD.startswith("#!/usr/bin/env python"):
    print("FAIL J 段：取不到改前版 harness（`git show de78125:…` 没返回可执行的正文，"
          "没有基准就没有「改前空过」这句话的证据）")
    raise SystemExit(1)
KB = (ROOT / "apps/api/app/services/kb.py").read_text(encoding="utf-8")

CALL = "        for anchor in (a for a in (_biz_from_url(url), article_key) if a):"
TAIL = "        ).scalar_one_or_none()\n        return row\n"
SECOND = ("\n\ndef _r7_local_biz(url: str) -> str:\n"
          "    from urllib.parse import parse_qs, urlparse\n\n"
          "    return (parse_qs(urlparse(url).query).get('__biz') or [''])[0]\n")

# 一发攻击 = (源码, 期望改后至少红哪些)。期望写成「至少」而非「恰好」：
# 判据本来就该多处报警，把恰好值写死会让合法重构变成假红。
ATTACKS = {
    "J-1 属性形态重绑 sys.modules[__name__].目标名 = lambda": (
        KB + "\nimport sys\n\nsys.modules[__name__]._biz_from_url = lambda url: ''\n", {"BD-13", "BD-16"}),
    "J-2 属性形态解绑 del sys.modules[__name__].目标名": (
        KB + "\nimport sys\n\ndel sys.modules[__name__]._biz_from_url\n", {"BD-13", "BD-16"}),
    "J-3 del + 模块级 __getattr__ 造同名假实现（PEP 562）": (
        KB + "\nimport sys\n\ndel sys.modules[__name__]._biz_from_url\n\n\n"
        "def __getattr__(name):\n    if name == '_biz_from_url':\n        return lambda url: ''\n"
        "    raise AttributeError(name)\n", {"BD-13", "BD-16"}),
    "J-4 星号导入把目标名从别处带进来": (
        KB + "\nfrom app.services.kb_legacy import *\n", {"BD-13", "BD-16"}),
    "J-5 委托结果被丢弃（调用还在，锚里没它）": (
        KB.replace(CALL, "        _biz_from_url(url)\n        for anchor in (a for a in (article_key,) if a):", 1),
        {"BD-14"}),
    "J-6 结果丢弃 + kb 内第二份解析器当真锚": (
        KB.replace(CALL, "        _biz_from_url(url)\n"
                         "        for anchor in (a for a in (_r7_local_biz(url), article_key) if a):", 1) + SECOND,
        {"BD-14"}),
    "J-7 传错实参 _biz_from_url(article_key)": (
        KB.replace(CALL, CALL.replace("_biz_from_url(url)", "_biz_from_url(article_key)"), 1), {"BD-14"}),
    "J-8 宿主同名重复定义、活的那份不用委托结果（合法可解析构造）": (
        KB.replace(TAIL, TAIL +
                   "    async def _find_source_by_anchor(self, article_key: str, url: str):\n"
                   "        for anchor in (a for a in (_r7_local_biz(url), article_key) if a):\n"
                   "            return None\n        return None\n" + SECOND, 1), {"BD-14"}),
}
CRASHES = {
    "J-9 攻击体本身解析不了（原构造把顶层 def 塞进类体）": KB.replace(
        "async def _find_source_by_anchor",
        "def _r7_local_biz(url: str) -> str:\n    return ''\n\n\nasync def _find_source_by_anchor", 1),
    "J-10 文件带 BOM 开头（CPython 自己接受，判据不许因此崩）": "\ufeff" + KB,
}
tmp = pathlib.Path(tempfile.mkdtemp(prefix="j_r7_"))
probe = EV / "_harness_prefix_r7.py"


def run_with(harness_text, kb_text, tag):
    probe.write_text(harness_text, encoding="utf-8")
    copy = tmp / f"kb_{tag}.py"
    copy.write_text(kb_text, encoding="utf-8", newline="\n")
    r = subprocess.run([sys.executable, str(probe), f"--kb={copy}"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    lines = (r.stdout or "").splitlines()
    red = {ln.split()[1] for ln in lines if ln.startswith("FAIL BD")}
    # 判据条数=这一版 harness **真的下过裁决**的条数，不是文件里数出来的行数
    judged = red | {ln.split()[1] for ln in lines if ln.startswith("PASS BD")}
    crash = "Traceback (most recent call last)" in (r.stderr or "")
    incon = "INCONCLUSIVE" in (r.stdout or "")
    return r.returncode, red, crash, incon, judged


# 第八轮复审 id 5：这一版之前这里印的是硬编码的「改前 15 条 / 改后 16 条」，加一条判据它也不会变红，
# 于是「基准」这件事随时会烂掉。现在测量，并且与登记值不符就 rc=1——下一个人必须更新这个数。
EXPECT = {"改前": 15, "改后": 16}
bad = []
print("J-0 两版 harness 在真实 kb.py 上各自下过多少条裁决（实测，不是抄的）：")
for tag, text in (("改前", OLD), ("改后", NEW)):
    rc, red, crash, incon, judged = run_with(text, KB, f"base_{tag}")
    print(f"    {tag}：rc = {rc} | 判据条数 = {len(judged)} | 红条数 = {len(red)}"
          f" | INCONCLUSIVE = {incon} | traceback = {crash}")
    if len(judged) != EXPECT[tag]:
        bad.append(f"{tag}版实测 {len(judged)} 条，登记的是 {EXPECT[tag]} 条")
    elif rc != 0 or crash:
        bad.append(f"{tag}版基准不该红或崩（rc={rc}）")
for label, (body, must) in ATTACKS.items():
    rc_new, red_new, crash_new, _, _ = run_with(NEW, body, "new")
    rc_old, red_old, crash_old, _, _ = run_with(OLD, body, "old")
    gap = sorted(must - red_new)
    if gap:
        bad.append(f"{label} 应红未红 {gap}")
    if red_old:
        bad.append(f"{label} 改前并不空过（红 {sorted(red_old)}）——对照失效")
    print(f"{label}")
    print(f"    改前 rc={rc_old} 红={sorted(red_old) or '（全绿=空过）'} traceback={crash_old}")
    print(f"    改后 rc={rc_new} 红={sorted(red_new)} traceback={crash_new}"
          f"｜应红未红={gap or '无'}")
for label, body in CRASHES.items():
    rc_new, red_new, crash_new, incon_new, _ = run_with(NEW, body, "crashnew")
    rc_old, red_old, crash_old, incon_old, _ = run_with(OLD, body, "crashold")
    if crash_new:
        bad.append(f"{label} 改后仍以 traceback 收场")
    print(f"{label}")
    print(f"    改前 rc={rc_old} 红={sorted(red_old) or '（无裁决）'} traceback={crash_old} INCONCLUSIVE={incon_old}")
    print(f"    改后 rc={rc_new} 红={sorted(red_new) or '（无裁决）'} traceback={crash_new} INCONCLUSIVE={incon_new}")
probe.unlink()
print("J-11 临时 harness 副本已删除：", not probe.exists())
shutil.rmtree(tmp, ignore_errors=True)
print("J-12 临时 kb 副本目录已删除：", not tmp.exists())
for b in bad:
    print("FAIL 攻击对照：", b)
verdict = (f"通过（{len(ATTACKS)} 发攻击 + {len(CRASHES)} 发崩栈，改前/改后两侧都符合预期）"
           if not bad else f"{len(bad)} 处不符")
print(f"J-13 对照自洽性：{verdict}｜发数由 len(ATTACKS)/len(CRASHES) 现算"
      f"（第九轮复审 id 7：先前这里写死「10 发攻击」，实际是 {len(ATTACKS)}+{len(CRASHES)}，"
      f"与 J-0 写死条数同一类缺陷）")
raise SystemExit(0 if not bad else 1)
