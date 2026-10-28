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
   这条判据要红一次逼人回去重跑 S64.0，而不是让 B 悄悄变成"没人说得清为什么是 B"。
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

