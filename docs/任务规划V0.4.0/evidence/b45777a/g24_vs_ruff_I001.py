"""S0C.1.1 的落地前置证明：ruff 的 I001 终序与本地门禁 g24 的段序模型**互斥**。

为什么需要这个脚本（本机实测，非推断）：
  CI 的红要用 `ruff --fix` 产出的 import 段序来修（`STEP-00C_proposed.patch` 里那三处），
  但把修好的文本喂回 `docs/06_validation/evidence/EVD-V2-00/g24_static_check.py`，g24 会反过来
  报 I001（它认为 `from conftest` 该排在 `from fastapi.testclient` 之后）。
  ⇒ 只看本地门禁的人有充分动机把 import 再改回去，而改回去就是 CI 红。这条互斥必须留档，
     并把 S0C.3.1 的「I001 建模 order-by-type 或从 g24 下线」从可选项升成必做项。

同一跑里顺手测出 g24 自身的一条缺陷：给它一个**仓库外**的绝对路径（`tempfile` 里那种），它在
`g24_static_check.py:275` 的 `path.relative_to(ROOT)` 上以 `ValueError` 收场——stdout 空、rc=1、
一条裁决都没下。所以本脚本把探针落在仓库内已被 `.gitignore` 挡住的 `_workspace/` 下（用完即删），
并且**先验 traceback 再读计数**（本项目纪律：崩栈不是裁决）。

退出码：0 = 互斥复现成立（且折行后无超长行）；1 = 与预期不符（ruff 修复稿或 g24 模型变了，须重判）；
2 = INCONCLUSIVE（g24 不在 / 补丁锚点找不到 / g24 这一跑崩成 traceback）。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve()
for _p in ROOT.parents:
    if (_p / "apps" / "api" / "pyproject.toml").is_file():
        ROOT = _p
        break
else:
    raise SystemExit("找不到 apps/api/pyproject.toml")

G24 = ROOT / "docs/06_validation/evidence/EVD-V2-00/g24_static_check.py"
PROBE = ROOT / "_workspace" / "s0c_g24_probe"
LIMIT = 120
FOLD_PREFIX = "    assert result.retryable is True, f"
FOLD_MARK = "__FOLD_RETRYABLE__"

# 真实 ruff 0.12.12 `--fix` 的产出（逐字取自 STEP-00C_proposed.patch 的 + 行）。
HUNKS: dict[str, list[tuple[str, str]]] = {
    "test_chat_sse.py": [
        ("from conftest import PG_URL, SKIP_UNSET_REASON, _PG_URL_SOURCE",
         "from conftest import _PG_URL_SOURCE, PG_URL, SKIP_UNSET_REASON"),
    ],
    "test_env_isolation.py": [
        ("from conftest import NO_PROXY_ISOLATION_VALUE, _PROXY_ENV_VARS",
         "from conftest import _PROXY_ENV_VARS, NO_PROXY_ISOLATION_VALUE"),
        (FOLD_MARK, ""),
    ],
    "test_kb_longlink_ingest.py": [
        ("import pytest\n\nfrom fixtures.wechat_urls import (",
         "import pytest\nfrom fixtures.wechat_urls import ("),
    ],
}


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def width(s: str) -> int:
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in "WF" else 1
               for c in s)


def fixed_text(name: str) -> str:
    text = (ROOT / "apps/api/tests" / name).read_text(encoding="utf-8")
    for old, new in HUNKS[name]:
        if old == FOLD_MARK:
            target = next((line for line in text.splitlines() if line.startswith(FOLD_PREFIX)), "")
            if not target:
                raise SystemExit(f"2 {name}: 找不到待折行的 E501 那行（ruff 修复稿与当前文件不符）")
            text = text.replace(target, "    assert result.retryable is True, (\n        "
                                        + target.split(", ", 1)[1] + "\n    )")
        elif old not in text:
            raise SystemExit(f"2 {name}: 补丁锚点不在当前文件里（{old[:40]!r}）")
        else:
            text = text.replace(old, new)
    return text


def main() -> int:
    _ensure_utf8_stdout()
    if not G24.is_file():
        print(f"INCONCLUSIVE g24 脚本不在：{G24}")
        return 2
    PROBE.mkdir(parents=True, exist_ok=True)
    try:
        paths = []
        for name in HUNKS:
            p = PROBE / name
            p.write_text(fixed_text(name), encoding="utf-8", newline="\n")
            paths.append(p)
        over = [(p.name, i, width(line))
                for p in paths for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                if width(line.rstrip()) > LIMIT]
        print(f"E501 口径：ruff 修复后的三份文件里显示宽度 >{LIMIT} 的行 = {over if over else '0 行'}")
        proc = subprocess.run([sys.executable, str(G24),
                               *(str(p.relative_to(ROOT)) for p in paths)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              cwd=str(ROOT))
        out = (proc.stdout or "") + (proc.stderr or "")
    finally:
        shutil.rmtree(PROBE, ignore_errors=True)
        print(f"清理：探针目录已删除 = {not PROBE.exists()}（`_workspace/` 本就 gitignore）")

    if "Traceback (most recent call last)" in out:
        print("INCONCLUSIVE：g24 这一跑崩成 traceback，没有裁决可读（缺陷另记 S0C.3.1）")
        return 2
    i001 = re.findall(r"^\s*\S+\.py:\d+ I001.*$", out, flags=re.M)
    print(f"g24 对「已按 ruff 修好」的文件报 I001 {len(i001)} 条（rc={proc.returncode}）：")
    for line in i001:
        print(f"    {line.strip()}")
    if over:
        print("结论不符：折行后仍有超长行，S0C.1.2 的修复稿需要重做。")
        return 1
    if not i001:
        print("结论不符：g24 与 ruff 已一致（g24 被改过？）——S0C.3.1 的互斥项可下线，但要重判一次。")
        return 1
    print(f"互斥复现成立：按 ruff 终序改完后，本地 g24 反而报 I001 {len(i001)} 条。")
    print("⇒ 陷阱：为了「本地绿」把 import 改回原序 = CI 红。S0C.1.1 只能以 ruff 为准，"
          "且 S0C.3.1 必须把 g24 的 I001 预检建模 order-by-type 或直接下线。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
