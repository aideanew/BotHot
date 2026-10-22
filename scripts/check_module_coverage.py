#!/usr/bin/env python3
"""模块覆盖率门（STEP-06 S6.3.1）：按模块判，不再只看那个全局数。

为什么全局门不够：`pytest --cov-fail-under` 只有一个总分，于是「四个付费 provider 里有两个
掉到 55%」可以被「另一个域涨了 3 个点」正好抵掉——总分不动，采集链却空了。本卡的四家 provider
与三个采集服务是 M1 的承重墙，它们各自的最低线必须逐条钉住，抵不掉。

三个契约（写在代码里，不靠人记）：
- 阈值表里的每一个 key 必须在 coverage.json 里**恰好命中一个文件**。命中 0 个（改名/删文件）
  不是「这条没要求了」，而是判据失去作用面 ⇒ rc=2 并点名是哪个 key（`scanned==0` 不等于通过）。
- 读不到 / 解析不了 / 形状不对 ⇒ rc=2，且必须打印 NOT-PASS。缺输入与达标是两件事。
- 反证通道 `--set KEY=PCT` 只用于把阈值**调高**以证明门禁真的会拦（S6.3.1.1），CI 不使用它；
  它存在的理由是「判据必须能被证伪」，不是给运营开的后门——真要改基线就改这张表并提 PR。

退出码：0 全部达标 / 1 有模块或全局未达标 / 2 输入缺失、形状不符或阈值失配。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

RC_OK, RC_FAIL, RC_NOT_PASS = 0, 1, 2

#: 默认读数位置：`pytest --cov=app --cov-report=json` 在 apps/api 下产出的文件。
DEFAULT_JSON = Path("apps/api/coverage.json")

#: 全局线（卡面 §1「全局保持 ≥79%」）。
GLOBAL_MIN = 79.0

#: 模块线：键是 coverage.json 里的文件路径（相对 `--cov=app` 的运行目录），值是最低行覆盖率。
THRESHOLDS: dict[str, float] = {
    # 文章身份键：一支键错就是两篇并成一篇（P-3），所以 100% 是它的合格线，不是理想线。
    "app/services/article_identity.py": 100.0,
    # 发现→清单→入列→入库三段服务层。
    "app/services/manifest.py": 85.0,
    "app/services/kb.py": 85.0,
    "app/services/subscription.py": 85.0,
    # 四家付费 provider 适配器（S3.4.1 / P-14 的落点）。
    "app/providers/article_sources/dajiala.py": 80.0,
    "app/providers/article_sources/justoneapi.py": 80.0,
    "app/providers/article_sources/tikhub.py": 80.0,
    "app/providers/article_sources/wellbyte.py": 80.0,
}


def _fail(msg: str) -> int:
    print(f"NOT-PASS {msg}")
    return RC_NOT_PASS


def _resolve(json_path: Path) -> Any:
    """读 coverage.json 并校验最小形状：成功返回 (files, totals)，任何不合规返回一个 rc（由调用方透传）。"""
    if not json_path.exists():
        return _fail(
            f"读不到 {json_path}——覆盖率门**未执行**。请先在 apps/api 下跑："
            f"`pytest tests/ -q --cov=app --cov-report=json`（缺输入不等于达标）"
        )
    try:
        raw = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _fail(f"{json_path} 解析失败：{type(exc).__name__}: {exc}")
    files, totals = raw.get("files"), raw.get("totals")
    if not isinstance(files, dict) or not isinstance(totals, dict):
        return _fail(f"{json_path} 形状不符：需要顶层 files/totals 两个对象，实得 keys={sorted(raw)[:6]}")
    return files, totals


def _match(key: str, files: dict[str, dict[str, dict[str, float]]]) -> list[str]:
    """阈值键 → coverage.json 里的文件路径：精确命中优先，否则按后缀唯一命中。

    后缀匹配是为了让门在「运行目录深度变了」（CI 里 `--cov=app` 的相对根与本机不同）时仍然
    只命中那一个文件。命中多于一个必须报错而不是取第一个：取第一个就等于让别的文件替它受审。
    """
    if key in files:
        return [key]
    needle = "/" + key.replace("\\", "/")
    return [p for p in files if p.replace("\\", "/").endswith(needle)]


def _percent(summary: dict[str, float]) -> float:
    return float(summary["percent_covered"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按模块阈值判定覆盖率（输入：coverage.json）")
    parser.add_argument("--json", dest="json_path", default=str(DEFAULT_JSON), help="coverage.json 路径")
    parser.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="KEY=PCT",
        help="反证通道：临时抬高某模块阈值（CI 不使用）",
    )
    args = parser.parse_args(argv)

    thresholds = dict(THRESHOLDS)
    for item in args.overrides:
        key, _, value = item.partition("=")
        if key not in thresholds:
            return _fail(f"--set 的 KEY 必须已在阈值表里，收到未知模块 {key!r}（表内：{sorted(thresholds)}）")
        try:
            thresholds[key] = float(value)
        except ValueError:
            return _fail(f"--set 的阈值必须是数字，收到 {value!r}")

    loaded = _resolve(Path(args.json_path))
    if isinstance(loaded, int):
        return loaded
    files, totals = loaded

    rc = RC_OK
    print(f"模块覆盖率门（全局线 {GLOBAL_MIN:g}%）")
    print("-" * 78)
    for key in sorted(thresholds):
        hits = _match(key, files)
        if len(hits) != 1:
            print(f"  失配  {key}  —— coverage.json 里命中 {len(hits)} 个文件（需要恰好 1 个）")
            rc = RC_NOT_PASS
            continue
        summary = files[hits[0]].get("summary") or {}
        if "percent_covered" not in summary:
            print(f"  失配  {key}  —— 该文件没有 summary.percent_covered")
            rc = RC_NOT_PASS
            continue
        pct = _percent(summary)
        need = thresholds[key]
        ok = pct >= need
        covered = int(summary.get("num_statements", 0) or 0) - int(summary.get("missing_lines", 0) or 0)
        total = int(summary.get("num_statements", 0) or 0)
        print(f"  {'达标' if ok else '未达标'}  {pct:6.2f}%  ≥{need:5.1f}%  {covered}/{total} 行  {hits[0]}")
        if not ok:
            rc = RC_FAIL

    if "percent_covered" not in totals:
        print("  失配  全局 totals 缺 percent_covered")
        return RC_NOT_PASS
    global_pct = _percent(totals)
    ok = global_pct >= GLOBAL_MIN
    print("-" * 78)
    print(f"  {'达标' if ok else '未达标'}  {global_pct:6.2f}%  ≥{GLOBAL_MIN:5.1f}%  TOTAL")
    if not ok:
        rc = RC_FAIL
    if rc == RC_OK:
        print("✅ 全部模块与全局达标")
    else:
        print("❌ 覆盖率门判红/判 NOT-PASS（rc=%d）" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
