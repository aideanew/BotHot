"""落库前置扫描：把 `docs/任务规划V0.4.0/`（或任意 pathspec）当成「即将入库的文件」逐行过一遍
`.gitleaks.toml` 里那条 `connection-string-embedded-password` 规则，量出「提交它会新增几条告警」。

为什么需要这个脚本（本机实测，非推断）：
  CI 的 Security 走 gitleaks 8.21.2 历史模式，而执行机（win32）**没有 gitleaks 二进制**（用户约束：
  本项目不装开发环境与外部依赖）。于是「V0.4.0 包能不能落库」这个问题原先只能靠人回忆补丁里写了什么
  ——本卡上一轮就是这么判的（F-30/D-12），回忆会漂移。这里把判定交给代码：正则与白名单**从
  `.gitleaks.toml` 现读**（`tomllib`），不在脚本里手抄第二份，规则改了脚本自动跟着变。

三档退出码（「崩栈不是裁决」纪律）：
  0 = 无命中，提交该 pathspec 不会新增 gitleaks 告警；
  1 = 有命中，逐条打印 `文件:行号 片段`，落库前必须先处置；
  2 = INCONCLUSIVE，`.gitleaks.toml` 不在 / 解析失败 / pathspec 为空 ⇒ 没有裁决可读。

诚实局限（三条，都影响判读）：
  · 方言：真·gitleaks 用 RE2，本脚本用 Python `re`。这三条正则不含 lookahead / `\p{...}`，
    只用了 RE2 与 Python 共有的 `(?:…)`、字符类与量词 ⇒ 对本规则等价；改规则若引入 lookahead 就失效。
  · 口径：CI 历史模式只扫**每个提交的新增行**，本脚本按**文件全文**逐行判 ⇒ 对「新增文件」两档一致
    （本用例正是整包新增），对「改已有文件」本脚本偏严（未动的旧行也会被算进来）。
  · 白名单：`.gitleaks.toml` 的 `[[rules.allowlists]]` 有 `regexes` 与 `paths` 两类，本脚本两类都读；
    命中 `paths` 豁免的文件会记为「豁免」而不是「安全」——豁免范围是路径子串搜索，比想象的宽。
  · 自指：读数文件也在待判集合里，逐字打印命中片段会让**证据本身**带回告警（本轮实测到，5 条）。
    所以片段一律经 `mask()` 掩码（口令段与 `@` 一起删），跑 3 就是拿本脚本扫自己的读数，
    要求 rc=0 —— 这条不是客套，是防止「修门禁的工具变成新的门禁红」。
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve()
for _p in ROOT.parents:
    if (_p / ".gitleaks.toml").is_file():
        ROOT = _p
        break
else:
    raise SystemExit("找不到 .gitleaks.toml")

CONFIG = ROOT / ".gitleaks.toml"


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # ty: ignore[unresolved-attribute]
        except (OSError, ValueError):
            pass


def load_rule() -> tuple[str, re.Pattern[str], list[re.Pattern[str]], list[re.Pattern[str]]]:
    """从配置文件现读规则本体 + 两类 allowlist，返回 (规则 id, 主正则, 白名单正则, 白名单路径)。"""
    data = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    for rule in data.get("rules", []):
        if rule.get("id") != "connection-string-embedded-password":
            continue
        main = re.compile(rule["regex"])
        al_regexes, al_paths = [], []
        for al in rule.get("allowlists", []):
            al_regexes += [re.compile(x) for x in al.get("regexes", [])]
            al_paths += [re.compile(x) for x in al.get("paths", [])]
        return str(rule["id"]), main, al_regexes, al_paths
    raise KeyError(".gitleaks.toml 里没有 connection-string-embedded-password 这条规则")


def mask(line: str, main: re.Pattern[str]) -> str:
    """把命中段压成 `scheme+账号:‹口令已掩码›`（**连 `@` 一起去掉**）。

    为什么必须掩码而不是原样打印（本轮实测出来的自指问题）：
      读数文件本身也在待判 pathspec 里。上一版逐字打印命中片段，
      于是 `precommit_gitleaks_scan.txt` 自己带回了 5 条告警——「报告漏洞的信本身是漏洞」，
      这份证据一入库就给 Security 添新指纹，落库判读反而被它自己污染。
    """
    return main.sub(lambda m: m.group(0).rsplit(":", 1)[0] + ":‹口令已掩码›", line).strip()[:120]


def scan_file(path: Path, main: re.Pattern[str], al_regexes: list[re.Pattern[str]],
              al_paths: list[re.Pattern[str]]) -> tuple[list[tuple[int, str]], bool]:
    """返回 (命中行片段（已掩码）, 该文件是否被 paths 豁免)。"""
    rel = path.relative_to(ROOT).as_posix()
    if any(p.search(rel) for p in al_paths):
        return [], True
    hits: list[tuple[int, str]] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for lineno, line in enumerate(text.splitlines(), 1):
        m = main.search(line)
        if not m:
            continue
        if any(a.search(line) for a in al_regexes):
            continue
        hits.append((lineno, mask(line, main)))
    return hits, False


def main_run(argv: list[str]) -> int:
    _ensure_utf8_stdout()
    specs, excludes = [], []
    it = iter(argv)
    for a in it:
        if a == "--exclude":
            excludes += [next(it)]
        else:
            specs.append(a)
    try:
        rule_id, main, al_regexes, al_paths = load_rule()
    except (OSError, KeyError, tomllib.TOMLDecodeError, re.error) as exc:
        print(f"INCONCLUSIVE 读不到规则本体：{type(exc).__name__}: {exc}")
        return 2
    files: list[Path] = []
    for spec in specs:
        p = Path(spec)
        if not p.is_absolute():
            p = ROOT / p
        if p.is_dir():
            files += [f for f in sorted(p.rglob("*"))
                      if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc"]
        elif p.is_file():
            files.append(p)
        else:
            print(f"INCONCLUSIVE pathspec 不存在：{spec}")
            return 2
    files = sorted(set(files))
    # `--exclude` 用来量「这一批打算提交的文件」的告警数，被排除的件单独列出来，
    # 免得读表的人以为它「已经干净」。
    kept, skipped_by_flag = [], []
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        (skipped_by_flag if any(x in rel for x in excludes) else kept).append(f)
    files = kept
    if not files:
        print("INCONCLUSIVE pathspec 下一个文件都没有，无裁决可读。")
        return 2

    print(f"规则 `{rule_id}` 现读自 {CONFIG.name}："
          f"主正则 1 条、口令白名单正则 {len(al_regexes)} 条、路径豁免 {len(al_paths)} 条；"
          f"待判文件 {len(files)} 个。")
    if skipped_by_flag:
        print(f"按 --exclude 暂不判定（**不等于干净**）：{[f.relative_to(ROOT).as_posix() for f in skipped_by_flag]}")
    total = 0
    exempt = [f.relative_to(ROOT).as_posix() for f in files
              if any(p.search(f.relative_to(ROOT).as_posix()) for p in al_paths)]
    if exempt:
        print(f"被 paths 豁免（不计入安全，只计入豁免）：{exempt}")
    for f in files:
        hits, skipped = scan_file(f, main, al_regexes, al_paths)
        if skipped or not hits:
            continue
        total += len(hits)
        print(f"\n[FLAG] {f.relative_to(ROOT).as_posix()}  {len(hits)} 条")
        for lineno, snippet in hits:
            print(f"    :{lineno}  {snippet}")
    print(f"\n合计待新增告警 {total} 条（已按口令白名单放行 {len(al_regexes)} 类占位串）。")
    if total:
        print("⇒ 落库判读：这些行入库即成为**新提交**里的新指纹，`git apply` 的补丁正文整份都是新增行，"
              "连它引用的 `-` 行也会被当成内容扫到。要么改字面量，要么走 D-12 的登记方式，不能直接提交。")
        return 1
    print("⇒ 落库判读：提交该 pathspec 不会给 Security 添新指纹。")
    return 0


if __name__ == "__main__":
    sys.exit(main_run(sys.argv[1:] or ["docs/任务规划V0.4.0"]))
