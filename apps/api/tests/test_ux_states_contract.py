"""STEP-64 方案 B 的活体契约锚（P-80 部分闭合、P-139）。

为什么是 B：见 `packages/contracts/src/ux/states.ts` 的头注与 `docs/06_validation/evidence/
EVD-V23-64/`。一句话——把 `ux` 接进生成器会强制为它建一张「冻结稿 ↔ 产物」逐 def 比对行，
而冻结稿的 `definitions.State` 带比对器不认识的关键词 `note`，改稿（D-V21-20）与改门禁
（D-V23-06）都不在本卡落笔权内。

本文件判四件事，缺一件就不叫"归位"：
① `states.ts` 里 `UX_STATES` 的数组字面量与冻结稿 `definitions.State.enum` **逐值且同序**相等，
   且恰为 8 值（顺序也判：消费侧按枚举顺序生成用例标题，顺序变了报告就对不上）；
② `ux` 域**没有被半接进生成器**——既不在 `CONTRACT_SCHEMA_MODULES` / `CONTRACT_TS_DOMAINS` 里，
   `packages/contracts/schemas/ux.schema.json` 也不存在（将来有人接 A 而不先解决 `note`，
   这里先红，而不是让 CI 的比对器红成一团没人看得懂的形）；
③ 前端/契约包看得见的名字确实在 `index.ts` 导出了（否则消费方 `import type { UxState }` 直接编译失败）；
④ 冻结稿里那两条把 A 堵死的关键词仍在位——它们一旦消失，本文件的选路依据就过期，
   这条判据要红一次逼人回去重跑 S64.0，而不是让 B 悄悄变成"没人说得清为什么是 B"；
⑤ `states.ts` 的逐视图投影与冻结稿 `x-core-views[].states` 的**键与键序**逐视图相等
   （STEP-68）。口径：投影是「本视图要交的态」，词表是「可能的态」——把词表当要求，
   就会给只有 5 个键的视图造出契约里没有的态（`r19` ④ 的退化就是这么来的）。
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
STATES_TS = REPO_ROOT / "packages" / "contracts" / "src" / "ux" / "states.ts"
INDEX_TS = REPO_ROOT / "packages" / "contracts" / "src" / "index.ts"
FROZEN_DRAFT = REPO_ROOT / "docs" / "任务规划V0.12.0" / "contracts" / "ux_states.schema.json"
UX_SCHEMA_PRODUCT = REPO_ROOT / "packages" / "contracts" / "schemas" / "ux.schema.json"
GEN_CONTRACTS_PATH = REPO_ROOT / "scripts" / "gen_contracts.py"

# 一行一条、双引号、`as const` 收尾：字面量一旦换形（改单引号 / 拆多行 / 去掉 as const），
# 这里判红而不是"解析不到就返回空列表"——空列表会让 ① 看起来像"8 值对不上"而不是"锚漂了"。
_UX_STATES_RE = re.compile(r'^export const UX_STATES = \[(?P<body>.*)\] as const;$', re.MULTILINE)
_ITEM_RE = re.compile(r'^"([a-z]+)"$')
_EXPECTED_COUNT = 8


def _ux_states_literal() -> list[str]:
    """从手写的 TS 常量里取八态数组。取不到/取到多条/条目不合形 ⇒ 直接判红并说清是哪一种。"""
    assert STATES_TS.exists(), f"八态活体锚缺失：{STATES_TS} 不存在"
    matches = _UX_STATES_RE.findall(STATES_TS.read_text(encoding="utf-8"))
    assert len(matches) == 1, f"UX_STATES 字面量应恰好一条，实读 {len(matches)} 条 ⇒ 谁是唯一源说不清了"
    items: list[str] = []
    for raw in matches[0].split(","):
        token = raw.strip()
        hit = _ITEM_RE.match(token)
        assert hit is not None, f"UX_STATES 条目不合形（要双引号小写串）：{token!r}"
        items.append(hit.group(1))
    return items


def _frozen_state_enum() -> list[Any]:
    assert FROZEN_DRAFT.exists(), f"冻结稿缺失：{FROZEN_DRAFT}"
    doc: dict[str, Any] = json.loads(FROZEN_DRAFT.read_text(encoding="utf-8"))
    return list(doc["definitions"]["State"]["enum"])


def _gen_contracts() -> Any:
    spec = importlib.util.spec_from_file_location("gen_contracts_for_ux_states", GEN_CONTRACTS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ux_states_literal_equals_frozen_draft_enum() -> None:
    """逐值 + 同序 + 恰 8 值。这是 P-80「归位」的机械凭据：搬完之后冻结稿从"唯一源"降级为"被核对方"。"""
    live = _ux_states_literal()
    draft = _frozen_state_enum()
    # 先判逐值同序（红的时候两侧都打得出来，这是 `08` §2.4 对接红原文的要求），再判"恰为 8 值"
    # ——后一条管的是"两侧被同步削成 7 值"那种等式仍然成立的形，那正是 P-80 不许的形。
    assert live == draft, "八态与冻结稿不同序或不同值：\n  活体 " + repr(live) + "\n  稿   " + repr(draft)
    assert len(live) == _EXPECTED_COUNT, f"活体锚应为 {_EXPECTED_COUNT} 值，实读 {len(live)}：{live}"
    assert len(draft) == _EXPECTED_COUNT, f"冻结稿应为 {_EXPECTED_COUNT} 值，实读 {len(draft)}：{draft}"


def test_ux_domain_is_not_half_wired_into_the_generator() -> None:
    """`ux` 要么完整走 A（域表 + 比对行 + `note` 的处置），要么就停在 B——不许半接。

    半接的两种形都在这条里：① 域进了生成器表但 `test_collection_contract.py` 没有比对行
    （那里 `set(fresh) == set(DOMAINS)` 会红，见 EVD-V23-64 的反证原文）；
    ② 有人手写一份 `schemas/ux.schema.json` 冒充产物放在生成物目录里（那是一份没人核的假产物）。
    A 真要落地，得先由规划方处置冻结稿的 `note`（D-V21-20：那条笔不在执行侧）。
    """
    module = _gen_contracts()
    half_wired = " ⇒ 方案 B 仍在册却半接了 A：台账 P-142 未解，先红在这里而不是让逐 def 比对器红成一团"
    assert "ux" not in module.CONTRACT_SCHEMA_MODULES, f"ux 已进 schema 域表{half_wired}"
    assert "ux" not in module.CONTRACT_TS_DOMAINS, f"ux 已进 TS 域表{half_wired}"
    assert not UX_SCHEMA_PRODUCT.exists(), f"生成物目录里出现了手写的 {UX_SCHEMA_PRODUCT.name} ⇒ 那是没有比对行的假产物"


def test_index_ts_reexports_the_ux_state_type() -> None:
    """消费方看得见的名字必须真的导出：没有这一行，STEP-65 的 `import type { UxState }` 编译不过。"""
    line = 'export type { UxState } from "./ux/states";'
    text = INDEX_TS.read_text(encoding="utf-8")
    assert line in text.splitlines(), "index.ts 未导出 UxState ⇒ 契约包对消费侧等于没接"


def test_frozen_draft_is_read_only_for_this_card() -> None:
    """本卡只核对冻结稿，不改它。这条守卫的意义：若哪天稿被改动，八值对照的"被核对方"就变了形。

    锚的是稿里那两条**关键词本身**（`note` / `x-required-for-every-core-view`）——它们是方案 A
    被堵死的根因，也是 P-142 要点名的对象；它们消失意味着 A 的门被打开，那时这条该红一次，
    提醒重跑 S64.0 选路探针。
    """
    doc = json.loads(FROZEN_DRAFT.read_text(encoding="utf-8"))
    state = doc["definitions"]["State"]
    assert "note" in state, "冻结稿 State 的 `note` 不见了 ⇒ A 的堵点可能已解除，回去重跑 S64.0 选路探针（台账 P-142）"
    assert "x-required-for-every-core-view" in state, "冻结稿 State 的注释键漂移，本卡的选路依据需重读"


# ── 逐视图投影（STEP-68 / D-V24-05）──

# 形态同样钉死：一条 `export const UX_VIEW_STATES = {` 起、`} as const;` 收，中间每行一个
# `<小写键>: ["…", …],`。锚不到就说清是哪一种，而不是"返回空表 ⇒ 看起来像键集对不上"。
_VIEW_BLOCK_RE = re.compile(
    r"^export const UX_VIEW_STATES = \{\n(?P<body>.*?)^\} as const;$", re.MULTILINE | re.DOTALL
)
_VIEW_ROW_RE = re.compile(r'^\s*(?P<key>[a-z0-9]+): \[(?P<items>[^\]]*)\],$')
_ITEM_ONLY_RE = re.compile(r'^"([a-z]+)"$')
_EXPECTED_VIEW_COUNT = 6


def _view_key(view: str) -> str:
    """冻结稿 `view` 标题 → 投影键：首段 → 去前导 `/` → 小写 → 去非字母数字。

    六个视图上都不产生歧义（`/spaces 列表…`→`spaces`、`NotificationBell（站内通知）`→
    `notificationbell`）。**不引别名表**：别名表会变成第二个真源，正是 D-V24-05 明令禁止的。
    """
    tokens = view.split()
    assert tokens, f"冻结稿某视图的 `view` 是空串，归一规则无从下手：{view!r}"
    return re.sub(r"[^a-z0-9]", "", tokens[0].lstrip("/").lower())


def _frozen_view_states() -> list[tuple[str, list[str]]]:
    assert FROZEN_DRAFT.exists(), f"冻结稿缺失：{FROZEN_DRAFT}"
    doc: dict[str, Any] = json.loads(FROZEN_DRAFT.read_text(encoding="utf-8"))
    return [(_view_key(v["view"]), list(v["states"])) for v in doc["x-core-views"]]


def _ux_view_states_literal() -> list[tuple[str, list[str]]]:
    """从手写的 TS 投影对象里取 (键, 值列表) 序列。取不到/多条/条目不合形 ⇒ 判红并说清是哪一种。"""
    assert STATES_TS.exists(), f"逐视图投影锚缺失：{STATES_TS} 不存在"
    blocks = _VIEW_BLOCK_RE.findall(STATES_TS.read_text(encoding="utf-8"))
    assert len(blocks) == 1, f"UX_VIEW_STATES 块应恰好一条，实读 {len(blocks)} 条 ⇒ 谁是唯一源说不清了"
    rows: list[tuple[str, list[str]]] = []
    for line in blocks[0].splitlines():
        if not line.strip():
            continue
        hit = _VIEW_ROW_RE.match(line)
        assert hit is not None, f'UX_VIEW_STATES 条目不合形（要 `<键>: ["…", …],`）：{line!r}'
        items: list[str] = []
        for raw in hit.group("items").split(","):
            token = raw.strip()
            if not token:
                continue
            item = _ITEM_ONLY_RE.match(token)
            assert item is not None, f"UX_VIEW_STATES 值不合形（要双引号小写串）：{token!r}"
            items.append(item.group(1))
        rows.append((hit.group("key"), items))
    return rows


def test_ux_view_states_projection_equals_frozen_draft() -> None:
    """逐视图键集 == 冻结稿 `x-core-views[].states` 的键集，同序，无例外。

    为什么不留例外：例外会腐化，且下一个写卡的人不知道要不要再加一个。STEP-70 已把唯一那一态
    移到 `x-build-mode-notes`（view 对象的兄弟键，不在 `states` 里），所以这里可以无条件逐键比；
    它若回流进 `states`，逐键同序比对立刻红——这就是"无例外分支"的机械凭据。
    """
    live = _ux_view_states_literal()
    draft = _frozen_view_states()
    live_keys = [key for key, _ in live]
    draft_keys = [key for key, _ in draft]
    assert live_keys == draft_keys, (
        "投影的视图键集与冻结稿不同序或不同名：\n  活体 " + repr(live_keys) + "\n  稿   " + repr(draft_keys)
    )
    assert len(live) == _EXPECTED_VIEW_COUNT, f"投影应为 {_EXPECTED_VIEW_COUNT} 个视图，实读 {len(live)}：{live_keys}"
    live_map = dict(live)
    for key, draft_states in draft:
        assert live_map[key] == draft_states, (
            f"视图 {key} 的态与冻结稿不同序或不同键：\n  活体 " + repr(live_map[key]) + "\n  稿   " + repr(draft_states)
        )
    vocab = set(_ux_states_literal())
    for key, states in live:
        extra = [s for s in states if s not in vocab]
        assert not extra, f"视图 {key} 用了词表外的值 {extra}：投影必须是 UX_STATES 的子集"
    chat = live_map["chat"]
    assert chat == ["loading", "success", "error", "unauthenticated", "degraded"], (
        "chat 应为契约的 5 键（不含 initial / empty / forbidden），实读 " + repr(chat)
    )

