"""F-14 迁移：`EVD-V2-00/prove_provider_shapes.py` 的判据 pytest 化（STEP-00T S00T.V14.3）。

为什么必须迁而不是修（`docs/06_validation/evidence/EVD-V14-00T/s00t_v14_gates.md` §2 现跑实测）：
原脚本用「AST 抽顶层函数 + 手写命名空间 exec」复刻被测代码。同一份代码里同时存在三处
独立断裂——`ManifestStatus`（模块级赋值，注入表里没有）、`_row_identity`（STEP-03 新增的
同文件辅助函数，pick 名单里没有）、`_parse_rfc822`（`b84dc53` 新增，同样不在名单里）——
外加两条**已经被实现推翻却还在报 PASS/WARN 的在案事实**：

- **B 组 D-04**：脚本断言 RSS 2.0 的 RFC-2822 `pubDate` 恒得 `publish_time=None`；
  现值是能解析成 aware UTC（`10:00:00 +0800` → `02:00:00+00:00`）。
- **C 组**：脚本断言四家付费源行键 ∩ `_ID_KEYS` = ∅ ⇒ 行被 `_map_row` 丢弃。
  这条因果链现在**两处都断了**：四家行键都含 `id`（交集非空），而且 `_row_identity` 在
  id 解不出时改用 URL 规范键兜底——「交集为空」本身已不等于「行被丢弃」。
- 两条翻案同源：`b84dc53`（STEP-03 S3.1-S3.3「清单行不再因缺 id 被整页静默丢掉」）。

⇒ 一个既不会红、也不会翻案的取证形态，比没有取证更糟：它让「CI 绿」与「证据有效」
可以同时不成立，而这一门当时还不在 CI 里（F-V14-05）。本文件把这些判据改成
**真 import、真调用**的 pytest 用例，并随 `pytest tests/` 自动进 CI（Linux 与 Windows 两侧）。

三条迁移纪律（都对着上面那张表）：
1. 已经翻案的断言按**现在的真值**重写，不保留旧结论（保留就是给下一位设绊线）；
2. 旧脚本里的 WARN（不参与门禁的事实陈述）不迁成用例——要么是可断言的行为，要么进文档；
3. 每一条判据都配**反向可测性**：能说出「生产代码怎么改它会红」。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pytest

from app.providers.article_sources.rss import _parse_feed
from app.services.manifest import _ID_KEYS, _URL_KEYS, _map_row

API = Path(__file__).resolve().parents[2]
SAMPLES = API / "tests" / "fixtures" / "provider_payloads"

# 样本 ↔ 源码：路径即证据锚点（承原脚本 JSON_CASES，逐条在断言消息里回显）
JSON_CASES: tuple[tuple[str, str], ...] = (
    ("redfox.json", "app/providers/redfox/client.py"),
    ("dajiala.json", "app/providers/article_sources/dajiala.py"),
    ("justoneapi.json", "app/providers/article_sources/justoneapi.py"),
    ("tikhub.json", "app/providers/article_sources/tikhub.py"),
    ("wellbyte.json", "app/providers/article_sources/wellbyte.py"),
)

PAID_SOURCES: tuple[str, ...] = (
    "app/providers/article_sources/dajiala.py",
    "app/providers/article_sources/justoneapi.py",
    "app/providers/article_sources/tikhub.py",
    "app/providers/article_sources/wellbyte.py",
)

# ── AST 工具（承原脚本；这里只保留判据需要的部分，且**不再 exec 任何被测代码**） ──


def _func(tree: ast.Module, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"未找到函数 {name}()")


def _key_of(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                return node.args[0].value
        return None
    if isinstance(node, ast.Subscript):
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            return node.slice.value
    return None


def _base_name(node: ast.AST) -> str | None:
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
    return True, "$" + "".join(steps) + f" → {sorted({type(x).__name__ for x in cur})}"


def _optional_access_ids(fn: ast.AST) -> set[int]:
    """`A or B or {}` 里**非首项**的读取点：兜底变体不要求样本穷举，否则断言是假的。"""
    opt: set[int] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            for tail in node.values[1:]:
                for sub in ast.walk(tail):
                    if isinstance(sub, ast.Call | ast.Subscript) and _key_of(sub):
                        opt.add(id(sub))
    return opt


def derive_paths(src: Path, func_name: str) -> tuple[dict[str, tuple], list[tuple[str, str]], set]:
    tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
    fn = _func(tree, func_name)
    optional_nodes = _optional_access_ids(fn)
    paths: dict[str, tuple] = {"payload": (), "resp": ()}
    accesses: list[tuple[str, str]] = []
    optional: set[tuple[str, str]] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            val = _unwrap(node.value)
            if isinstance(val, ast.Call):
                key, holder = _key_of(val), _base_name(val)
                if key and holder in paths:
                    paths[node.targets[0].id] = (*paths[holder], key)
                    continue
        target_name = iter_name = None
        if isinstance(node, ast.For):
            target_name = node.target.id if isinstance(node.target, ast.Name) else None
            iter_name = node.iter.id if isinstance(node.iter, ast.Name) else None
        elif isinstance(node, ast.ListComp) and node.generators:
            gen = node.generators[0]
            target_name = gen.target.id if isinstance(gen.target, ast.Name) else None
            iter_name = gen.iter.id if isinstance(gen.iter, ast.Name) else None
        if target_name and iter_name in paths:
            paths[target_name] = (*paths[iter_name], "[]")
        if isinstance(node, ast.Call | ast.Subscript):
            key, holder = _key_of(node), _base_name(node)
            if key and holder in paths:
                accesses.append((holder, key))
                if id(node) in optional_nodes:
                    optional.add((holder, key))
    return paths, accesses, optional


def row_keys_from_src(rel_src: str) -> set[str]:
    """只取归一化**行**字典的键（变量名 row）。

    承原脚本的收敛理由：把 `form_data = {...}` 这类请求体也算进行键会让证据失真。
    """
    tree = ast.parse((API / rel_src).read_text(encoding="utf-8"), filename=str(API / rel_src))
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
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.ctx, ast.Store)
            and isinstance(node.value, ast.Name)
            and node.value.id == "row"
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            keys.add(node.slice.value)
    return keys


# ═══════════════════════════════ A 组：样本形状 ↔ 现行读取路径（静态，不执行被测代码）


@pytest.mark.parametrize(("sample_name", "rel_src"), JSON_CASES)
def test_provider_sample_is_valid_json_without_annotation_keys(sample_name: str, rel_src: str) -> None:
    doc = json.loads((SAMPLES / sample_name).read_text(encoding="utf-8"))
    notes = [k for k in (doc if isinstance(doc, dict) else {}) if str(k).startswith("_")]
    assert not notes, (
        f"{sample_name} 顶层带注记键 {notes}：样本必须字面等于上游形状，"
        "注记写进 fixtures/provider_payloads/README.md（历史版本把 _shape_source 塞进响应体，"
        "使「样本 == 上游形状」这句声明自己带上一个上游不会给的键）"
    )


@pytest.mark.parametrize(("sample_name", "rel_src"), JSON_CASES)
def test_sample_covers_every_main_path_read_key(sample_name: str, rel_src: str) -> None:
    """主路径读取键必须在样本里定位得到；OR 兜底链的非首项不要求（那才是真判据）。"""
    doc = json.loads((SAMPLES / sample_name).read_text(encoding="utf-8"))
    paths, accesses, optional = derive_paths(API / rel_src, "query_work_list")
    assert accesses, f"{rel_src}::query_work_list 一个 `.get()`/`[]` 读取点都没导出 ⇒ 提取器失效，证据为空"
    seen: set[tuple[str, str]] = set()
    missing: list[str] = []
    hits = 0
    for holder, key in accesses:
        if (holder, key) in seen:
            continue
        seen.add((holder, key))
        ok, where = _resolve_path(doc, (*paths[holder], key))
        if ok:
            hits += 1
        elif (holder, key) not in optional:
            missing.append(f"{holder}→{where}")
    assert hits >= 1, f"{rel_src} 的读取点在 {sample_name} 里一个都定位不到（键链已漂移）：{sorted(seen)}"
    assert not missing, f"{sample_name} 覆盖不了 {rel_src} 的主路径读取键：{missing}"


@pytest.mark.parametrize(
    ("sample_name", "path"),
    [
        ("redfox.json", ("data", "list")),
        ("redfox.json", ("data", "total")),
        ("dajiala.json", ("data",)),
        ("justoneapi.json", ("data", "MsgList", "Msg")),
        ("wellbyte.json", ("data", "MsgList", "Msg")),
        ("tikhub.json", ("data", "data")),
    ],
)
def test_upstream_container_levels_are_where_the_code_thinks_they_are(sample_name: str, path: tuple) -> None:
    """容器层级硬断言（TC-A4-04 那一类事故的常驻版）。

    `wellbyte` 写这条是因为历史上有过把它当成 `data.data.MsgList` 的读法；
    `dajiala` 写这条是因为它的 `data` **本身即数组**，不是 `data.list`。
    """
    doc = json.loads((SAMPLES / sample_name).read_text(encoding="utf-8"))
    ok, where = _resolve_path(doc, path)
    assert ok, f"{sample_name} 里找不到容器路径 {path}（停在 {where}）⇒ 代码的读取层级与上游形状不一致"


# ═══════════════════════════════ B 组：RSS/Atom 真执行（真 import，不再 exec）


@pytest.mark.parametrize(("sample_name", "expect_rows"), [("rss2.xml", 2), ("atom.xml", 2)])
def test_feed_sample_is_wellformed_and_produces_rows(sample_name: str, expect_rows: int) -> None:
    text = (SAMPLES / sample_name).read_text(encoding="utf-8")
    ET.fromstring(text)  # 良构性：抛 ParseError 即红
    rows = _parse_feed(text)
    assert len(rows) >= expect_rows, f"{sample_name} 经真实 `_parse_feed` 只产出 {len(rows)} 行（≥{expect_rows}）"
    assert all(isinstance(r, dict) and r for r in rows), f"{sample_name} 存在空行或非 dict 行：{rows}"


@pytest.mark.parametrize("sample_name", ["rss2.xml", "atom.xml"])
def test_every_feed_row_is_consumable_by_map_row(sample_name: str) -> None:
    """行必须能被 `manifest._map_row` 消费——`_map_row` 返回 None 等于整行静默丢弃。"""
    rows = _parse_feed((SAMPLES / sample_name).read_text(encoding="utf-8"))
    dropped = [i for i, r in enumerate(rows) if _map_row(r) is None]
    assert not dropped, f"{sample_name} 第 {dropped} 行被 `_map_row` 丢弃（返回 None ⇒ 不落库、不报错）"


def test_rss2_rfc2822_pubdate_is_parsed_into_an_aware_datetime() -> None:
    """D-04 已修：RFC-2822 `pubDate` 不再恒得 None，而是按自带的偏移解析成 aware。

    这条**取代**原脚本的「恒 None」在案事实（`b84dc53` 加 `_parse_rfc822` 之后翻案）。
    判据故意写成瞬间等价而不是字符串相等：`10:00:00 +0800` 与 `02:00:00+00:00` 是同一个瞬间，
    只有把 tz 丢掉（退回 naive 或 UTC 误读）才会红——那正是 P-15 那一族缺陷的形状。
    """
    rows = _parse_feed((SAMPLES / "rss2.xml").read_text(encoding="utf-8"))
    with_time = [r for r in rows if r.get("publishTime")]
    assert len(with_time) >= 2, f"rss2 样本里可解析时间的行不足 2：{len(with_time)}"
    for row in with_time:
        mapped = _map_row(row)
        assert mapped is not None and mapped["publish_time"] is not None, (
            f"RSS 2.0 的 pubDate {row['publishTime']!r} 又解成 None 了：`_parse_rfc822` 那条支路失效"
        )
        parsed = mapped["publish_time"]
        assert parsed.tzinfo is not None, f"pubDate {row['publishTime']!r} 解析成 naive datetime：{parsed!r}"
    stamps = [str(_map_row(r)["publish_time"]) for r in with_time]
    assert all(s.endswith("+00:00") for s in stamps), (
        f"RFC-2822 带偏移的串应归一到 UTC 存储，实读 {stamps}"
    )


def test_atom_sample_covers_both_published_and_updated_fallback() -> None:
    """Atom 两条支都要有样本：`published` 命中，以及 `published` 缺席时回落 `updated`。

    反向可测性：若 `_parse_atom` 不再回落 `updated`，entry[1] 的 `pubDate` 会变空 ⇒ 本条红。
    """
    rows = _parse_feed((SAMPLES / "atom.xml").read_text(encoding="utf-8"))
    assert len(rows) >= 2, f"atom 样本不足 2 行，无法同时覆盖两支：{len(rows)}"
    assert rows[0]["pubDate"] == "2026-10-01T09:00:00+08:00", (
        f"entry[0] 应取 published，实读 {rows[0]['pubDate']!r}"
    )
    assert rows[1]["pubDate"] == "2026-10-02T10:00:00+08:00", (
        f"entry[1] 无 published，应回落 updated，实读 {rows[1]['pubDate']!r}"
    )


# ═══════════════════════════════ C 组：归一化行键 ↔ `_map_row` 输入契约


@pytest.mark.parametrize("rel_src", PAID_SOURCES)
def test_paid_provider_rows_reach_a_manifest_identity_source(rel_src: str) -> None:
    """归一化行必须携带 `_map_row` 能解出身分的键——`_ID_KEYS` **或** `_URL_KEYS` 任一命中。

    这条取代原脚本 C 组的 WARN（"交集为空 ⇒ 行被丢弃"）。那个结论已经翻案两次：
    先由 `b84dc53` 给四家补上 `id` 键，再由同一提交的 `_row_identity` 把"缺 id 丢整行"
    改成「id 解不出就用 URL 规范键兜底」⇒ 交集为空**今天不再等于**行被丢弃。
    判据因此按现行的两条真源写，而不是照抄旧 WARN：照抄会得到一条打不中的守卫
    （本文件首次跑这条反证时就是这样被打回原形的，见 `test_polarity_…`）。
    """
    keys = row_keys_from_src(rel_src)
    assert keys, (
        f"{rel_src}::query_work_list 里定位不到 row 字典 ⇒ 提取器失效。"
        "请修本文件，不要删掉本用例（提取器静默失效正是 F-14 的形态）"
    )
    hit_id = keys & set(_ID_KEYS)
    hit_url = keys & set(_URL_KEYS)
    assert hit_id or hit_url, (
        f"{rel_src} 的归一化行键 {sorted(keys)} 既不含 `_ID_KEYS` 也不含 `_URL_KEYS`："
        "`_row_identity` 两条真源都解不出 ⇒ 整行 skipped，发现结果静默消失"
    )


def test_map_row_drops_only_rows_with_neither_id_nor_url() -> None:
    """行为判据：`_map_row` 返回 None 的唯一条件是 id 与 URL **都**没有。

    这是 C 组交集判据的落地端——交集只是"看起来能解"，真正决定丢不丢的是这里。
    三条子判据都对应对话里出现过的错：静默丢行（旧 P-1）、只有 id 的行被误丢、
    无 id 行没走 URL 兜底。
    """
    assert _map_row({"title": "既无 id 也无 url"}) is None, (
        "id 与 URL 都没有的行必须 skipped；落库等于把脏数据固化"
    )
    only_id = _map_row({"workUuid": "d" * 32, "title": "只有渠道身份"})
    assert only_id is not None and only_id["external_id"] == "d" * 32, (
        "只有 id、没有 URL 的行仍要收（它是「见过这篇」的真实记录）"
    )
    assert only_id["article_key"] is None, (
        "无 URL 时 article_key 必须是 None 而不是空串：`\"\"` 不是合法 ArticleKey，"
        "且会让所有无键行在 Diff 里撞成同一个键（D-V9-04）"
    )
    only_url = _map_row({"url": "https://mp.weixin.qq.com/s/AbC123", "title": "只有链接"})
    assert only_url is not None and only_url["external_id"], "URL 兜底建键那条支路失效了"
    assert only_url["article_key"], "有 URL 的行必须带规范键，否则 Diff 永远不通它入列"


def test_redfox_raw_rows_map_with_workurl_and_beijing_offset() -> None:
    """对照支：RedFox 把上游原始行直接交给 `_map_row`（不组装 `row` 变量），故必须全行可落。

    三条子判据都是历史上真出过的错：
    - 全部行被丢弃（缺 id）；
    - `url=""`（上游只有 `workUrl`，没有 `url` 键，早期实现取了 `url`）；
    - 8 小时时差（`publishTime` 是**无时区的北京时间串**，必须按 `Asia/Shanghai` 解释）。
    """
    doc = json.loads((SAMPLES / "redfox.json").read_text(encoding="utf-8"))
    rows = doc["data"]["list"]
    assert isinstance(rows, list) and rows, "redfox.json 的 data.list 必须是非空数组（对照前提）"
    mapped = [_map_row(r) for r in rows]
    assert all(mapped), f"有行被丢弃：{sum(1 for m in mapped if m)}/{len(rows)}"
    assert all(m["url"] for m in mapped), f"存在空 url（`_URL_KEYS` 里 workUrl 必须在前）：{[m['url'] for m in mapped]}"
    offsets = [str(m["publish_time"]) for m in mapped]
    assert all(o.endswith("+08:00") for o in offsets), (
        f"无时区的北京时间串必须按 Asia/Shanghai 贴标，实读 {offsets}（退回 UTC 就是 8 小时时差）"
    )


# ═══════════════════════════════ 极性自证：每条判据都要能被"摘掉支路"打回原形
#
# 写这三条的理由是本会话已经为此返工过一次：`re.search(r"fromtimestamp\([^)]*tz=None")`
# 那条"常驻守卫"因为在嵌套括号处提前遇到 `)` 而**永远 0 命中**，改前改后都绿。
# 只证"现在绿"不证"错时会红"的判据，等于没有判据。


def test_polarity_rfc2822_branch_is_what_makes_the_aware_claim_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """把 `_parse_rfc822` 退回 `return None`，`publish_time` 必须立刻变成 None。

    若不是这样，上面那条 aware 判据就不是靠这条支路成立的（可能是别的路径在兜），
    那么它既挡不住回归，也不该被写成"防复发"。
    """
    import app.services.manifest as manifest

    monkeypatch.setattr(manifest, "_parse_rfc822", lambda raw: None)
    rows = [r for r in _parse_feed((SAMPLES / "rss2.xml").read_text(encoding="utf-8")) if r.get("publishTime")]
    assert rows, "rss2 样本里已无带 pubDate 的行，本反证失去前提"
    assert all(manifest._map_row(r)["publish_time"] is None for r in rows), (
        "摘掉 RFC-2822 支路后 publish_time 仍非 None ⇒ aware 判据不是靠它成立的，须重查数据来源"
    )


def test_polarity_row_survival_needs_both_identity_sources_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """极性反证：只摘 `_ID_KEYS` 时行**仍应存活**（URL 兜底），两条都摘才必须全丢。

    这条第一次跑就失败了，而失败正是它的价值：我原本照脚本旧结论写的是
    「拿掉 `id` ⇒ 行被丢弃」，实测却发现行仍落库——因为 `b84dc53` 之后
    `_row_identity` 有 URL 规范键兜底。判据若不配这条反证，就会带着一个
    已经翻案的因果链常驻绿（F-14 的原始病灶换了个说法复发）。
    """
    import app.services.manifest as manifest

    rows = _parse_feed((SAMPLES / "atom.xml").read_text(encoding="utf-8"))
    assert rows, "atom 样本为空，本反证失去前提"

    monkeypatch.setattr(manifest, "_ID_KEYS", ())
    assert all(manifest._map_row(r) is not None for r in rows), (
        "只去掉 id 源就把行全丢了 ⇒ URL 兜底那支不存在或已失效"
    )
    monkeypatch.setattr(manifest, "_URL_KEYS", ())
    assert all(manifest._map_row(r) is None for r in rows), (
        "两条真源都摘掉后行仍能落库 ⇒ C 组的交集判据根本没有门在落库路径上"
    )


def test_polarity_main_path_extractor_finds_a_drifted_key(tmp_path: Path) -> None:
    """A 组提取器的反证：造一个读 `MISSING_TODAY` 的假 Provider，样本里没有它 ⇒ 必须报缺失。

    若提取器只会返回"全部命中"，`test_sample_covers_every_main_path_read_key` 就是空守卫。
    """
    fake = tmp_path / "fake_provider.py"
    fake.write_text(
        "def query_work_list(payload):\n"
        "    data = payload.get(\"data\") or {}\n"
        "    return [row for row in data.get(\"MISSING_TODAY\", [])]\n",
        encoding="utf-8",
    )
    doc = json.loads((SAMPLES / "dajiala.json").read_text(encoding="utf-8"))
    paths, accesses, optional = derive_paths(fake, "query_work_list")
    assert accesses, "提取器在合成就面上一个读取点都没导出 ⇒ 真文件的判据同样是空守卫"
    missing = []
    for holder, key in accesses:
        ok, where = _resolve_path(doc, (*paths[holder], key))
        if not ok and (holder, key) not in optional:
            missing.append(f"{holder}→{where}")
    assert missing, f"漂移的键没被判据抓住（提取器永远绿）：{accesses}"
