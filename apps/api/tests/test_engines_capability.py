"""STEP-13：引擎能力面三态（+ 未开放）如实回报，且"回报的原因"与"切换被拒的原因"是同一个函数给的。

D-V3-03（签 A）本轮不实接四家引擎，所以本卡要防的是**说不清**：改前 `GET /engines` 只给一组布尔，
前端要自己拼"为什么不可用"，而切换接口的拒绝顺序写在另一处——两处一旦分家，UI 说"缺 Key"、
后端却因为"未实接"拒绝，管理员登记完 Key 仍然切不过去。

不连库：`_engine_status` / `assert_engine_switchable` 都接受显式 settings 与登记表，直接喂。
"""
from __future__ import annotations

import itertools
import json
import re
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from app.api.v1 import engines as engines_api
from app.contracts.engine import EngineReason
from app.core.config import get_settings
from app.core.errors import ForbiddenError
from app.providers import engine_port

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads((REPO_ROOT / "packages" / "contracts" / "schemas" / "engine.schema.json").read_text("utf-8"))
_CAPABILITY = Draft202012Validator({**SCHEMA, "$ref": "#/$defs/EngineCapability"})

_PLACEHOLDER = "s13-registered-placeholder"


def _settings(allow: str) -> Any:
    return get_settings().model_copy(
        update={
            "kb_engine_allowlist": allow,
            "coze_api_key": "",
            "dify_api_key": "",
            "fastgpt_api_key": "",
            "main_kb_api_key": "",
            "main_kb_api_base": "",
        }
    )


def _status(engine: str, *, allowlisted: bool, configured: bool) -> dict[str, Any]:
    allow = "builtin," + engine if allowlisted else "builtin"
    registered = {engine: _PLACEHOLDER} if configured else {}
    settings = _settings(allow)
    if engine == "main" and configured:
        settings = settings.model_copy(update={"main_kb_api_base": "https://example.invalid"})
    return engines_api._engine_status(engine, settings, registered)


SKELETONS = [e for e in engine_port.ENGINE_ORDER if not engine_port.ENGINE_IMPLEMENTED.get(e, False)]
COMBOS = list(itertools.product(SKELETONS, (False, True), (False, True)))


@pytest.mark.parametrize(("engine", "allowlisted", "configured"), COMBOS)
def test_reason_follows_the_fixed_precedence(engine: str, allowlisted: bool, configured: bool) -> None:
    """S13.1.1：未开放 → 缺 Key → 未实接，只报最先该处理的那一个。"""
    st = _status(engine, allowlisted=allowlisted, configured=configured)
    expected = (
        EngineReason.not_allowlisted if not allowlisted
        else EngineReason.key_missing if not configured
        else EngineReason.not_implemented
    )
    assert st["reason"] == expected.value, st
    assert st["available"] is (st["reason"] == "ok"), "不变量：available ⇔ reason=ok"


def test_builtin_is_always_ok_even_when_the_allowlist_forgets_it() -> None:
    st = engines_api._engine_status("builtin", _settings("coze"), {})
    assert (st["available"], st["reason"]) == (True, "ok")


def test_not_implemented_comes_from_the_registry_not_from_route_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """S13.1.2.1：取值必须来自 `ENGINE_IMPLEMENTED`。把 coze 标成已实接 ⇒ 同样条件下变成 ok。"""
    assert _status("coze", allowlisted=True, configured=True)["reason"] == "not_implemented"
    monkeypatch.setitem(engine_port.ENGINE_IMPLEMENTED, "coze", True)
    st = _status("coze", allowlisted=True, configured=True)
    assert (st["reason"], st["available"]) == ("ok", True)


def test_route_module_hardcodes_no_engine_names_in_the_reason_logic() -> None:
    src = Path(engines_api.__file__).read_text("utf-8")
    body = src[src.index("def _engine_reason") : src.index("def _engine_status")]
    assert not re.search(r"\"(main|coze|dify|fastgpt)\"", body), "原因判定里出现了写死的引擎名"


@pytest.mark.parametrize(("engine", "allowlisted", "configured"), COMBOS)
def test_switch_refusal_says_the_same_reason_as_the_listing(engine: str, allowlisted: bool, configured: bool) -> None:
    """S13.1.2.2：切换仍是 403/10004，但拒绝文案与列表的 reason 一一对应，不再各说各话。"""
    st = _status(engine, allowlisted=allowlisted, configured=configured)
    allow = "builtin," + engine if allowlisted else "builtin"
    registered = {engine: _PLACEHOLDER} if configured else {}
    settings = _settings(allow)
    if engine == "main" and configured:
        settings = settings.model_copy(update={"main_kb_api_base": "https://example.invalid"})
    with pytest.raises(ForbiddenError) as exc:
        engines_api.assert_engine_switchable(engine, settings, registered)
    assert exc.value.code == 10004 and exc.value.http_status == 403
    marker = engines_api.REFUSAL_MARKERS[EngineReason(st["reason"])]
    assert marker in exc.value.message, (st["reason"], exc.value.message)


def test_refusal_markers_are_pairwise_distinct() -> None:
    markers = [engines_api.REFUSAL_MARKERS[r] for r in EngineReason if r is not EngineReason.ok]
    assert len(set(markers)) == len(markers) == 3
    for a, b in itertools.permutations(markers, 2):
        assert a not in b, "一个原因的标记词包含另一个的 ⇒ 文案无法区分"


@pytest.mark.parametrize("engine", engine_port.ENGINE_ORDER)
def test_every_listing_item_satisfies_the_frozen_contract(engine: str) -> None:
    for allowlisted, configured in itertools.product((False, True), repeat=2):
        st = _status(engine, allowlisted=allowlisted, configured=configured)
        errors = [e.message for e in _CAPABILITY.iter_errors(st)]
        assert not errors, (st, errors)


def test_contract_validator_has_teeth() -> None:
    st = _status("coze", allowlisted=True, configured=False)
    assert not _CAPABILITY.is_valid({**st, "reason": "maybe"})
    assert not _CAPABILITY.is_valid({k: v for k, v in st.items() if k != "reason"})


def test_skeleton_surface_only_shrinks() -> None:
    """S13.1.3：骨架位 `NotImplementedError` 基线 16，只降不升（实接一家就该往下走）。"""
    src = Path(engine_port.__file__).read_text("utf-8")
    assert src.count("NotImplementedError") <= 16


def test_refusal_markers_match_the_frontend_wording() -> None:
    """S37.2（P-90）：后端切换拒绝的标记词与前端 `ENGINE_REASON_TEXT` 逐值一致。

    同一个 `EngineReason` 在列表（前端文案表）与切换拒绝（后端标记词）里必须是同一句话。
    前端表从 `apps/web/lib/api/engines.ts` 原文逐行解析（不复制一份到测试里——
    复制就是第二份真相）。反证：改一侧任一词 ⇒ 本用例红。
    """
    import re
    from pathlib import Path

    engines_ts = (
        Path(__file__).resolve().parents[3] / "apps" / "web" / "lib" / "api" / "engines.ts"
    )
    text = engines_ts.read_text(encoding="utf-8")
    block = re.search(r"export const ENGINE_REASON_TEXT[^{]*\{(.*?)\};", text, re.DOTALL)
    assert block, "engines.ts 里找不到 ENGINE_REASON_TEXT ⇒ 前端单一文案表被挪走了"
    frontend: dict[str, str] = dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", block.group(1)))
    for reason in EngineReason:
        if reason is EngineReason.ok:
            continue
        expected = frontend.get(reason.value)
        assert expected, f"前端文案表缺 {reason.value}：{frontend}"
        assert engines_api.REFUSAL_MARKERS[reason] == expected, (
            f"{reason.value}：后端 {engines_api.REFUSAL_MARKERS[reason]!r} ≠ 前端 {expected!r}"
            "（P-90：同一原因两套词）"
        )
