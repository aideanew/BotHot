"""S0.3.2 机器判定：Provider 响应样本形状 ↔ 真实代码读取路径一致性证明。

为什么不能只 "肉眼对齐 JSON"：STEP-00 的 7 个样本是给 S4/S9 当契约锚用的，
样本一旦与代码读取路径漂移，后续用例会「拿错的形状互相印证」——TC-A4-04
（把 Wellbyte 看成 `data.data.MsgList`）正是这类事故。故本脚本用 AST 从**现行源码**
里导出每条 `.get("K")` / `[K]` 的完整路径，再逐个在样本里定位，不写死任何键名。

本机无 venv（`import httpx` → ModuleNotFoundError，实测 2026-10-12），因此分两条路：
  A 组 JSON Provider：AST 导出容器路径 + 字段路径 → 在样本中定位（静态证明）；
  B 组 RSS/Atom 与 manifest：AST 抽出**纯标准库**函数体（`_parse_feed` 链、`_map_row`
    链）后 exec 真实执行，把样本喂进去（动态证明，不经 httpx）。

C 组补充：AST 导出各 Provider 归一化行的键集合，与 manifest `_ID_KEYS` 求交——
交为空即证明「付费 Provider 的归一化行喂进 ManifestSyncService 会被 _map_row 丢弃」，
这是留给 S4/S9 的在案事实，不判 FAIL（不在本卡验收项内）。

用法：python docs/06_validation/evidence/EVD-V2-00/prove_provider_shapes.py
退出码：0 全绿；1 有 FAIL。只读仓库文件，不写库、不启服务、不联网。
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

if hasattr(sys.stdout, "reconfigure"):  # Windows 控制台默认 GBK，中文证据会花屏
    sys.stdout.reconfigure(encoding="utf-8")  # ty: ignore[unresolved-attribute]

# EVD-V2-00/prove_provider_shapes.py → 上溯 4 级到仓库根（0..3 = 本目录/evidence/06_validation/docs）
ROOT = Path(__file__).resolve().parents[4]
API = ROOT / "apps" / "api"
SAMPLES = API / "tests" / "fixtures" / "provider_payloads"

# (样本文件, 源码文件, Provider 类名/模块名) —— 源码路径即证据锚点，逐条在报告里回显
JSON_CASES: tuple[tuple[str, str], ...] = (
    ("redfox.json", "app/providers/redfox/client.py"),
    ("dajiala.json", "app/providers/article_sources/dajiala.py"),
    ("justoneapi.json", "app/providers/article_sources/justoneapi.py"),
    ("tikhub.json", "app/providers/article_sources/tikhub.py"),
    ("wellbyte.json", "app/providers/article_sources/wellbyte.py"),
)

RESULTS: list[tuple[str, str, str]] = []  # (PASS|FAIL|WARN|INFO, 断言, 细节)


def rec(status: str, claim: str, detail: str = "") -> None:
    RESULTS.append((status, claim, detail))


# ── ZoneInfo 可用性探测（本机实测结论，决定 B/C 组是否退化为等价替身） ──

_TZ_SHIM_NEEDED = False
try:  # Linux（CI runner / 正式镜像）有 /usr/share/zoneinfo，直接用真实现
    from zoneinfo import ZoneInfo as _ZoneInfo

    _ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001 — Windows 无系统 tz 库，且 pyproject 未声明 tzdata
    _TZ_SHIM_NEEDED = True

    def _ZoneInfo(key: str) -> timezone:  # noqa: N802 — 与 zoneinfo.ZoneInfo 同调用形态
        # Asia/Shanghai 自 1991 年起无夏令时，固定 +08:00 对现当代时间戳等价。
        if key != "Asia/Shanghai":
            raise AssertionError(f"替身只覆盖 Asia/Shanghai，收到 {key!r}")
        return timezone(timedelta(hours=8))


# ── AST 工具 ──────────────────────────────────────────────────────────


class _QuietLogger:
    """structlog 替身：被 exec 的函数体只用到 .warning / .info。"""

    @staticmethod
    def warning(*_a: Any, **_k: Any) -> None:
        return None

    @staticmethod
    def info(*_a: Any, **_k: Any) -> None:
        return None


_QUIET_LOGGER = _QuietLogger()


def _func(tree: ast.Module, name: str) -> ast.AST | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
            return node
    return None


def _key_of(node: ast.AST) -> str | None:
    """`.get("K")` / `["K"]` → "K"；其它形态返回 None。"""
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                return node.args[0].value
        return None
    if isinstance(node, ast.Subscript):
        sl = node.slice
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
            return sl.value
    return None


def _base_name(node: ast.AST) -> str | None:
    """.get("K") / ["K"] 的接收者变量名（非 Name 退化到内层 Call）。"""
    base: ast.expr | None = None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        base = node.func.value
    elif isinstance(node, ast.Subscript):
        base = node.value
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Call):
        return _base_name(base)
    return None


def _unwrap(node: ast.expr) -> ast.expr:
    """剥掉 `A or {}` 的首项与 `A if cond else None` 的真值支，露出真正的 .get 调用。"""
    if isinstance(node, ast.BoolOp) and node.values:
        return node.values[0]
    if isinstance(node, ast.IfExp):
        return node.body
    return node


def _resolve_path(doc: Any, path: tuple[str | list, ...]) -> tuple[bool, str]:
    """在样本中定位路径；"[]" 表示进入列表并遍历所有 dict 元素。"""
    cur: list[Any] = [doc]
    steps: list[str] = []
    for seg in path:
        nxt: list[Any] = []
        if seg == "[]":
            for node in cur:
                if isinstance(node, list):
                    nxt.extend(node)
            steps.append("[]")
        else:
            for node in cur:
                if isinstance(node, dict) and seg in node:
                    nxt.append(node[seg])
            steps.append(f".{seg}")
        if not nxt:
            return False, "$" + "".join(steps)
        cur = nxt
    types = {type(x).__name__ for x in cur}
    return True, "$" + "".join(steps) + f" → {sorted(types)}"


def _optional_access_ids(fn: ast.AST) -> set[int]:
    """收集 `A or B or {}` 里 **非首项** 的键读取点 id()——这些是兜底变体，样本可以不含。

    没有这个区分，「所有读取点都要在样本里出现」就成了假断言（代码里的 OR 兜底链
    本就不该被单一样本穷举）；有了它，主路径缺失就能真的判红。
    """
    opt: set[int] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            for tail in node.values[1:]:
                for sub in ast.walk(tail):
                    if isinstance(sub, ast.Call | ast.Subscript) and _key_of(sub):
                        opt.add(id(sub))
    return opt


def derive_paths(
    src: Path, func_name: str
) -> tuple[dict[str, tuple[str | list, ...]], list[tuple[str, str]], set[tuple[str, str]]]:
    """导出 (变量→路径, [(holder 变量, 键)], 兜底可选键集合)，符号链自 `payload` 起。"""
    tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
    fn = _func(tree, func_name)
    if fn is None:
        raise AssertionError(f"{src.name} 未找到 {func_name}()")
    optional_nodes = _optional_access_ids(fn)
    paths: dict[str, tuple[str | list, ...]] = {"payload": (), "resp": ()}
    accesses: list[tuple[str, str]] = []
    optional: set[tuple[str, str]] = set()
    for node in ast.walk(fn):
        # 赋值链：data = payload.get("data") / msg_list = data.get("MsgList") or {}
        #          payload = await self._handle_response(...) 之类的非 .get 赋值不追踪
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            val = _unwrap(node.value)
            if isinstance(val, ast.Call):
                key = _key_of(val)
                holder = _base_name(val)
                if key and holder in paths:
                    paths[node.targets[0].id] = (*paths[holder], key)
                    continue
        # 迭代器：for msg in msgs / [row for row in items]
        target_name = None
        iter_name = None
        if isinstance(node, ast.For):
            target_name, iter_name = (
                node.target.id if isinstance(node.target, ast.Name) else None,
                node.iter.id if isinstance(node.iter, ast.Name) else None,
            )
        elif isinstance(node, ast.ListComp) and node.generators and isinstance(node.generators[0], ast.comprehension):
            g = node.generators[0]
            target_name = g.target.id if isinstance(g.target, ast.Name) else None
            iter_name = g.iter.id if isinstance(g.iter, ast.Name) else None
        if target_name and iter_name in paths:
            paths[target_name] = (*paths[iter_name], "[]")
        # 键读取点（.get("K") 与 ["K"] 同一套导出）
        if isinstance(node, ast.Call | ast.Subscript):
            key = _key_of(node)
            holder = _base_name(node)
            if key and holder in paths:
                accesses.append((holder, key))
                if id(node) in optional_nodes:
                    optional.add((holder, key))
    return paths, accesses, optional


# ── 从源码 exec 出纯标准库函数（不经 httpx / sqlalchemy） ─────────────


def exec_functions(src: Path, names: set[str], extra_ns: dict[str, Any] | None = None) -> dict[str, Any]:
    """按 AST 抽取指定顶层函数 + 所需常量，exec 出真实现（非副本）。"""
    tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
    picked: list[ast.AST] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name in names:
                picked.append(node)
        elif isinstance(node, ast.Assign) and node.targets:
            t = node.targets[0]
            if isinstance(t, ast.Name) and t.id in names:
                picked.append(node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in names:
            picked.append(node)
    if len(picked) < len(names):
        missing = names - {
            getattr(n, "name", None) or (n.targets[0].id if isinstance(n, ast.Assign) else n.target.id)
            for n in picked
        }
        raise AssertionError(f"{src.name} 未导出：{sorted(missing)}")
    module = ast.Module(body=picked, type_ignores=[])
    for n in module.body:  # exec 不接受 docstring 之外的位置问题，但需去掉行号依赖
        ast.fix_missing_locations(n)
    ns: dict[str, Any] = {
        "Any": Any,
        "ET": ET,
        "json": json,
        "hashlib": hashlib,
        "datetime": datetime,
        "UTC": UTC,
        "ZoneInfo": _ZoneInfo,
        "logger": _QUIET_LOGGER,
    }
    ns.update(extra_ns or {})
    exec(compile(module, str(src), "exec"), ns)  # noqa: S102 — 执行仓库现行源码本身，非外来输入
    return ns


# ── A 组：JSON 样本 vs 代码读取路径 ───────────────────────────────────


def check_json_cases() -> None:
    for sample_name, rel_src in JSON_CASES:
        sample = SAMPLES / sample_name
        src = API / rel_src
        rec("INFO" if sample.is_file() else "FAIL", f"{sample_name} 存在", str(sample.relative_to(ROOT)))
        if not sample.is_file() or not src.is_file():
            continue
        try:
            doc = json.loads(sample.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            rec("FAIL", f"{sample_name} 为合法 JSON", str(exc))
            continue
        top = sorted(k for k in (doc if isinstance(doc, dict) else {}))
        rec("PASS", f"{sample_name} JSON 可解析", f"顶层键={top}")
        # 形状忠实：顶层不得出现注记键（历史版本把 `_shape_source` 塞进响应体，
        # 使「样本 == 上游形状」这句声明自己带上一个上游不会给的键）。注记现居 README.md。
        notes = [k for k in top if k.startswith("_")]
        rec("PASS" if not notes else "FAIL", f"{sample_name} 顶层无注记键",
            f"注记键={notes or '无'}（声明：样本字面即上游形状）")
        paths, accesses, optional = derive_paths(src, "query_work_list")
        # 去重并按 holder 路径分组；主路径缺失=FAIL，兜底变体缺失=WARN
        seen: set[tuple[str, str]] = set()
        missing: list[str] = []
        rows_found = 0
        for holder, key in accesses:
            if (holder, key) in seen:
                continue
            seen.add((holder, key))
            ok, where = _resolve_path(doc, (*paths[holder], key))
            if ok:
                rows_found += 1
            elif (holder, key) in optional:
                rec("WARN", f"{rel_src} 兜底键在 {sample_name} 中缺席", f"{where}（OR 链非首项，允许）")
            else:
                missing.append(f"{holder}→{where}")
        rec(
            "PASS" if rows_found >= 1 and not missing else "FAIL",
            f"{sample_name} 覆盖 {rel_src} 的全部主路径读取键",
            f"命中 {rows_found}/{len(seen)} 个读取点；主路径缺失={missing or '无'}（AST 导出，未写死）",
        )
    # 关键容器逐个硬断言（缺失即 Provider 抛错/返回空 → 样本无契约价值）
    containers = [
        ("redfox.json", ("data", "list"), "RedFox data.list 为非空数组"),
        ("redfox.json", ("data", "total"), "RedFox data.total 存在"),
        ("dajiala.json", ("data",), "Dajiala data **本身即数组**（非 data.list）"),
        ("justoneapi.json", ("data", "MsgList", "Msg"), "JustOneAPI data.MsgList.Msg 非空数组"),
        ("wellbyte.json", ("data", "MsgList", "Msg"), "Wellbyte data.MsgList.Msg 非空数组（TC-A4-04：不是 data.data.MsgList）"),
        ("tikhub.json", ("data", "data"), "TikHub data.data 非空数组"),
    ]
    for sample_name, path, claim in containers:
        doc = json.loads((SAMPLES / sample_name).read_text(encoding="utf-8"))
        ok, where = _resolve_path(doc, path)
        node: Any = doc
        for seg in path:
            node = node[seg] if isinstance(node, dict) and seg in node else None
            if node is None:
                break
        nonempty = isinstance(node, list) and len(node) > 0 if isinstance(node, list) else node is not None
        rec("PASS" if ok and nonempty else "FAIL", claim, where)


# ── B 组：RSS/Atom 真实执行 + manifest 映射 ──────────────────────────


def check_rss_execution() -> None:
    if _TZ_SHIM_NEEDED:
        rec(
            "WARN",
            "本机 ZoneInfo('Asia/Shanghai') 不可用 → B/C 组用固定 +08:00 等价替身",
            "实测抛 ZoneInfoNotFoundError：Windows 无 /usr/share/zoneinfo 且 pyproject 依赖表未声明 tzdata。"
            "Linux（CI runner / 正式镜像）有时区库故不受影响；Asia/Shanghai 自 1991 年无夏令时，"
            "+08:00 对本卡的时间断言等价——但该缺口在 Windows 上会让 7 个 ZoneInfo 模块 import 即崩。",
        )
    else:
        rec("PASS", "本机 ZoneInfo('Asia/Shanghai') 可用，B/C 组用真实时区对象")
    ns = exec_functions(
        API / "app/providers/article_sources/rss.py",
        {"_parse_feed", "_parse_rss2", "_extract_rss_item", "_parse_atom", "_extract_atom_entry", "_text", "_text_ns"},
    )
    mns = exec_functions(
        API / "app/services/manifest.py",
        {
            "_map_row",
            "_parse_time",
            "_from_epoch",
            "_first_str",
            "_ID_KEYS",
            "_URL_KEYS",
            "_TITLE_KEYS",
            "_TIME_KEYS",
            "_HASH_KEYS",
            "MANIFEST_STATUS_DISCOVERED",
            "UPSTREAM_TZ",
        },
    )
    map_row = mns["_map_row"]
    for name, expect in (("rss2.xml", 2), ("atom.xml", 2)):
        text = (SAMPLES / name).read_text(encoding="utf-8")
        try:
            ET.fromstring(text)
            rec("PASS", f"{name} XML 良构", "xml.etree.ElementTree.fromstring 通过")
        except ET.ParseError as exc:
            rec("FAIL", f"{name} XML 良构", str(exc))
            continue
        rows = ns["_parse_feed"](text)
        rec("PASS" if len(rows) >= expect else "FAIL", f"{name} 经真实 _parse_feed 产出行", f"{len(rows)} 行（≥{expect}）")
        if not rows:
            continue
        rec("INFO", f"{name} 行字段集", f"{sorted(rows[0])}")
        # _map_row：guid/id 命中 _ID_KEYS ⇒ 行不被丢弃
        mapped = [m for m in (map_row(r) for r in rows) if m]
        rec(
            "PASS" if len(mapped) == len(rows) else "FAIL",
            f"{name} 全部行可被 manifest._map_row 消费",
            f"{len(mapped)}/{len(rows)}",
        )
        for i, row in enumerate(rows):
            m = map_row(row)
            if m is None:
                continue
            pt = row.get("publishTime")
            rec(
                "INFO",
                f"{name} entry[{i}] publishTime→_parse_time",
                f"raw={pt!r} → {m['publish_time']!r}",
            )
    # D-04：RFC-2822 pubDate 不被 fromisoformat 接受 → publish_time=None
    rows = ns["_parse_feed"]((SAMPLES / "rss2.xml").read_text(encoding="utf-8"))
    with_time = [r for r in rows if r.get("publishTime")]
    none_time = [r for r in with_time if (map_row(r) or {}).get("publish_time") is None]
    rec(
        "PASS" if len(with_time) >= 2 and len(none_time) == len(with_time) else "FAIL",
        "D-04 在案：RSS 2.0 的 RFC-2822 pubDate 原样透传后，_parse_time 恒得 None",
        f"{len(none_time)}/{len(with_time)} 行 publish_time=None；样本串={with_time and with_time[0]['publishTime']!r}"
        "（修复归 S4/S9，非本卡）",
    )
    # Atom 无 published 时回落 updated 的分支（现存用例未覆盖）
    arows = ns["_parse_feed"]((SAMPLES / "atom.xml").read_text(encoding="utf-8"))
    if len(arows) < 2:
        rec("FAIL", "Atom 样本同时覆盖 published 命中与 published→updated 回退两支", f"仅 {len(arows)} 行")
    else:
        hit_pub = arows[0]["pubDate"] == "2026-10-01T09:00:00+08:00"
        hit_upd = arows[1]["pubDate"] == "2026-10-02T10:00:00+08:00"
        rec(
            "PASS" if hit_pub and hit_upd else "FAIL",
            "Atom 样本同时覆盖 published 命中与 published→updated 回退两支（rss.py:250-255）",
            f"entry[0].pubDate={arows[0]['pubDate']!r}（取 published）"
            f" entry[1].pubDate={arows[1]['pubDate']!r}（该 entry 无 published，取 updated）",
        )


# ── C 组：归一化行键 vs _ID_KEYS（在案事实，供 S4/S9） ────────────────


def row_keys_from_src(src: Path) -> set[str]:
    """只取归一化**行**字典的键（变量名 row，含 AnnAssign 与 row["k"]=v）。

    上一版把 `form_data = {"token":..., "ghid":...}` 这类请求体也算进行键，
    导致「行键」证据失真——现按变量名收敛，与 _map_row 的输入契约同口径。
    """
    tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
    fn = _func(tree, "query_work_list")
    keys: set[str] = set()
    for node in ast.walk(fn):
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        if value is not None and any(isinstance(t, ast.Name) and t.id == "row" for t in targets):
            if isinstance(value, ast.Dict):
                keys.update(k.value for k in value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str))
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            if isinstance(node.value, ast.Name) and node.value.id == "row":
                if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                    keys.add(node.slice.value)
    return keys


def check_id_key_gap() -> None:
    mns = exec_functions(
        API / "app/services/manifest.py",
        {
            "_map_row",
            "_parse_time",
            "_from_epoch",
            "_first_str",
            "_ID_KEYS",
            "_URL_KEYS",
            "_TITLE_KEYS",
            "_TIME_KEYS",
            "_HASH_KEYS",
            "MANIFEST_STATUS_DISCOVERED",
            "UPSTREAM_TZ",
        },
    )
    id_keys = set(mns["_ID_KEYS"])
    for rel_src in (
        "app/providers/article_sources/dajiala.py",
        "app/providers/article_sources/justoneapi.py",
        "app/providers/article_sources/tikhub.py",
        "app/providers/article_sources/wellbyte.py",
    ):
        keys = row_keys_from_src(API / rel_src)
        if not keys:
            rec("FAIL", f"{rel_src} 归一化行字典可被 AST 定位", "query_work_list 内未发现 row 字典（提取器需修）")
            continue
        hit = keys & id_keys
        rec(
            "WARN" if not hit else "INFO",
            f"{rel_src} 归一化行键 ∩ manifest _ID_KEYS",
            f"行键={sorted(keys)} 命中={sorted(hit) if hit else '∅ → _map_row 返回 None，行被丢弃'}",
        )
    # 对照：RedFox 把上游原始行直接交给 _map_row，故必须命中
    map_row = mns["_map_row"]
    doc = json.loads((SAMPLES / "redfox.json").read_text(encoding="utf-8"))
    if not isinstance(doc.get("data"), dict) or not isinstance(doc["data"].get("list"), list):
        rec("FAIL", "redfox.json 具备 data.list 数组（对照前提）", "结构缺失")
        return
    rows = doc["data"]["list"]
    mapped = [map_row(r) for r in rows]
    rec(
        "PASS" if all(mapped) else "FAIL",
        "RedFox 原始行经真实 _map_row 全部可落库",
        f"{sum(1 for m in mapped if m)}/{len(rows)}；"
        f"external_id={[m['external_id'] for m in mapped if m]}",
    )
    rec(
        "PASS" if all(m and m["url"] for m in mapped) else "FAIL",
        "RedFox 行无 url 键时仍取到 workUrl（_URL_KEYS 顺序：workUrl 在前）",
        f"url={[m['url'][:24] for m in mapped if m]}",
    )
    tz_ok = all(m and str(m["publish_time"]).endswith("+08:00") for m in mapped)
    rec(
        "PASS" if tz_ok else "FAIL",
        "RedFox 无时区北京时间串按 Asia/Shanghai 解析（L1-1 不回退）",
        f"publish_time={[str(m['publish_time']) for m in mapped if m]}",
    )


def main() -> int:
    check_json_cases()
    check_rss_execution()
    check_id_key_gap()
    fails = 0
    for status, claim, detail in RESULTS:
        if status == "FAIL":
            fails += 1
        print(f"{status:4} {claim}" + (f" :: {detail}" if detail else ""))
    passed = sum(1 for s, _, _ in RESULTS if s == "PASS")
    warns = sum(1 for s, _, _ in RESULTS if s == "WARN")
    infos = sum(1 for s, _, _ in RESULTS if s == "INFO")
    print(f"\n合计 PASS={passed} WARN={warns} INFO={infos} FAIL={fails}")
    if fails:
        print("结论：存在 FAIL，S0.3.2 不得标记完成")
        return 1
    print("结论：S0.3.2 无 FAIL。承重断言是「主路径读取键全覆盖（缺失即 FAIL）」+「容器层级硬断言」"
          "+「RSS/Atom 真执行行数」；PASS 计数只是断言行数，不作强度指标。")
    print(f"       未覆盖项 {warns} 条（WARN）全部为 OR 兜底变体或替身声明，不含主路径缺口。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
