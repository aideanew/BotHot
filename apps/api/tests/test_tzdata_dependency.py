"""STEP-32 S32.3 用例：`tzdata` 必须是后端的**无条件主依赖**，且时区名真的能取到。

为什么要有这道门（P-106 / D-V18-04）：`zoneinfo.ZoneInfo("Asia/Shanghai")` 现在是靠
`psycopg[binary,pool]` 的传递依赖 `tzdata`（`apps/api/uv.lock` 里那条
`{ name = "tzdata", marker = "sys_platform == 'win32'" }`）碰巧带进来的。上游哪天把它剥掉，
后端会在 **import 期整体起不来**——不是某个功能降级，是进程起不来；而 CI 只有 `compose-smoke`
一条路会红。判据必须钉住"我们自己声明了它"。

用例分两侧，缺一侧就是永远绿：
- 声明侧（pyproject + uv.lock）：红在"没声明"，与本机环境无关 ⇒ 这是本卡的**先红**证据。
- 取用侧（TZPATH 置空后仍能构造 Asia/Shanghai）：红在"tzdata 包不在"，与声明无关。
  本机实测（win32 + 已装传递依赖 tzdata）这条在修复前就是绿的，所以它承担的是**防复发**，
  不承担先红——把这句话写在这里，是为了不让后来人以为它证明了什么。
"""

from __future__ import annotations

import tomllib
import zoneinfo
from datetime import datetime
from pathlib import Path

import pytest

_ROOTS = [up for up in Path(__file__).resolve().parents if (up / "apps" / "api" / "pyproject.toml").is_file()]
assert _ROOTS, "向上找不到含 apps/api/pyproject.toml 的仓库根"
_API = _ROOTS[0] / "apps" / "api"


def _pyproject() -> dict:
    with (_API / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def _lock() -> dict:
    with (_API / "uv.lock").open("rb") as handle:
        return tomllib.load(handle)


def _name_and_marker(spec: str) -> tuple[str, str]:
    """把 PEP 508 字符串拆成 (名字, 环境标记)。`pyproject.toml` 的主依赖就是这个形状。"""
    head, _, marker = spec.partition(";")
    name = head
    for cut in ("[", ">", "<", "=", "!", "~", " "):
        name = name.split(cut)[0]
    return name.strip().lower(), marker.strip()


def _table_deps(entries: list[dict]) -> dict[str, str]:
    """锁文件里的依赖表：`{ name = "tzdata", marker = "..." }`。"""
    return {str(item.get("name", "")).lower(): str(item.get("marker", "")) for item in entries}


def test_tzdata_is_a_declared_runtime_dependency() -> None:
    """主依赖里必须有 tzdata，且**不带平台标记**——带 marker 就等于又回到"碰巧带"。"""
    raw = _pyproject()["project"]["dependencies"]
    deps = dict(_name_and_marker(item) for item in raw)
    assert "tzdata" in deps, f"pyproject 主依赖没有 tzdata（现有 {sorted(deps)}）"
    assert deps["tzdata"] == "", f"tzdata 被写成条件依赖：marker={deps['tzdata']!r}"
    # 必须在主依赖，不是 dev/optional：dev 只进 CI 的 `pip install -e .[dev]`，运行镜像不装它
    optional = _pyproject()["project"].get("optional-dependencies", {})
    for group, entries in optional.items():
        names = {_name_and_marker(item)[0] for item in entries}
        assert "tzdata" not in names, f"tzdata 被放进了 optional-dependencies[{group!r}]"


def test_lock_file_agrees_with_the_declaration() -> None:
    """锁文件里 bothot-backend 的直接依赖必须同样是无条件的 tzdata。

    判据落在 `dependencies`（解析结果）与 `package.metadata.requires-dist`（声明回声）两处：
    只改 pyproject 不重锁，前者就不会出现——这正是 D-V18-12「锁文件为唯一依赖真相」要防的形。
    """
    lock = _lock()
    root = next((p for p in lock["package"] if p.get("name") == "bothot-backend"), None)
    assert root is not None, "uv.lock 里没有 bothot-backend 条目"
    direct = _table_deps(root.get("dependencies", []))
    assert direct.get("tzdata") == "", f"uv.lock 的 bothot-backend 直接依赖没有无条件 tzdata：{direct}"
    declared = _table_deps(root.get("metadata", {}).get("requires-dist", []))
    assert declared.get("tzdata") == "", f"requires-dist 里没有 tzdata：{sorted(declared)}"


def test_zoneinfo_shanghai_resolves_from_the_tzdata_package(tmp_path: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """把系统时区目录清空后仍能取到 Asia/Shanghai ⇒ 取到的是 tzdata 包，不是系统库。"""
    assert tmp_path.exists() and list(tmp_path.iterdir()) == [], "空目录前提不成立"
    monkeypatch.setattr(zoneinfo, "TZPATH", (str(tmp_path),))
    tz = zoneinfo.ZoneInfo("Asia/Shanghai")
    assert tz.key == "Asia/Shanghai"
    offset = datetime(2026, 1, 1, 12, 0, tzinfo=tz).utcoffset()
    assert offset is not None and offset.total_seconds() == 8 * 3600, (
        f"不是 UTC+8（实读 {offset}）⇒ 取到的时区是假的"
    )


def test_the_empty_tzpath_patch_itself_is_effective(tmp_path: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """反证：TZPATH 被挪走这件事必须真的可观测，否则上一条用例可能只是从系统库取的。

    一个不存在的时区名在TZPATH 置空后必须抛 ZoneInfoNotFoundError——抛不出来就说明
    `monkeypatch.setattr(zoneinfo, "TZPATH", ...)` 根本没作用到查找路径上。
    """
    monkeypatch.setattr(zoneinfo, "TZPATH", (str(tmp_path),))
    with pytest.raises(zoneinfo.ZoneInfoNotFoundError):
        zoneinfo.ZoneInfo("Nowhere/Fake")
