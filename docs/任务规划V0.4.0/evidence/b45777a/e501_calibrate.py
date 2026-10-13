"""E501 口径标定：把 ruff 0.12.12 的 `line-too-long` 用 stdlib 复现一遍，验证「改宽度计数」够不够。

结论（本机实测，见同目录 `e501_width_calibration.txt`）：
  `ruff check app tests` 在 b45777a 只报 **1** 条 E501（`test_env_isolation.py:68`，134 > 120），
  而**按显示宽度**裸判 `width > 120` 在这棵树上会命中 **27** 行。多出来的 26 行全部落在
  ruff 的两条豁免里：25 行的超长尾巴是 pragma 注释（`# noqa` / `# type: ignore[...]`）、
  1 行以 URL 结尾。⇒ 只把 `g24_static_check.py` 的 `len()` 换成显示宽度，会让本地门禁
  **反向假红**（报 26 条 ruff 不报的违规），比现在的假绿更难收拾。

复跑：`python docs/任务规划V0.4.0/evidence/b45777a/e501_calibrate.py`
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

LIMIT = 120
URL = re.compile(r"https?://\S+")


def repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "apps" / "api" / "pyproject.toml").is_file():
            return parent
    raise SystemExit("找不到 apps/api/pyproject.toml，无法定位仓库根")


def width(s: str) -> int:
    n = 0
    for ch in s:
        if unicodedata.combining(ch):
            continue
        n += 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
    return n


def classify(line: str) -> str:
    """返回 'over'（ruff 会报）、'pragma'、'url-tail'、'single-word'（后三者 ruff 豁免）。"""
    if re.search(r"#\s*(noqa\b|type:\s*ignore)", line):
        return "pragma"
    body = line.lstrip(" \t\f")
    if " " not in body and "\t" not in body:
        return "single-word"
    found = list(URL.finditer(body))
    if found and width(body[: found[-1].start()]) <= LIMIT:
        return "url-tail"
    return "over"


def main() -> int:
    api = repo_root() / "apps" / "api"
    files = sorted(api.glob("app/**/*.py")) + sorted(api.glob("tests/**/*.py"))
    buckets: dict[str, list[str]] = {}
    for path in files:
        rel = str(path.relative_to(api))
        for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.rstrip()
            w = width(line)
            if w <= LIMIT:
                continue
            buckets.setdefault(classify(line), []).append(f"{rel}:{i} 宽={w}")
    order = ["over", "pragma", "url-tail", "single-word"]
    for k in order:
        v = buckets.get(k, [])
        print(f"[{k}] {len(v)} 条")
        for s in v[:3]:
            print(f"    {s}")
        if len(v) > 3:
            print(f"    …（其余 {len(v) - 3} 条同类）")
    other = buckets.get("over", [])
    ok = len(other) == 1 and other[0].startswith("tests\\test_env_isolation.py:68") or \
        len(other) == 1 and other[0].startswith("tests/test_env_isolation.py:68")
    print(f"裸宽度命中 {sum(len(v) for v in buckets.values())} 行；"
          f"其中 ruff 真报的 {len(other)} 行 = {other}")
    print(f"标定{'成立' if ok else '不成立'}：与 ruff_0.12.12_b45777a.txt 的唯一一条 E501 "
          f"{'一致' if ok else '不一致（模型需要重做，不能据此改 g24）'}")
    if not ok:
        return 1
    print("处置口径：g24 若要对齐 ruff，必须同时建模 pragma/url/单词三条豁免；"
          "否则豁免项会被当违规报出来（本地假红）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
