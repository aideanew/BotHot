"""STEP-08 S8.2.1：标识补全（`identifier_resolver`）。

判据分三层：**推导规则**（与解析层恒等、ghid 只在带键名的位置取值）、
**库里到底落了什么**（origin 的两种值、幂等、被别的源占住时的行为）、
**接线证明**（AST：生产里只有一处调用它，且那一处把已在手的页面原文传进来）。
只测前两层的话，"resolver 算得对但入库时没人叫它"这种失败没人看见。

先红读数（改前形状，scratch 探针，EVD-V17-08 §3/§7b）：新建一个源、给它一条带 `__biz` 的样例链接
⇒ `source_identifiers` 行数 **0**（迁移里的回填是一次性的，之后新建的源没人补）。
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from app.models.entities import Source, SourceIdentifier
from app.services import identifier_resolver as resolver_module
from app.services.article_identity import parse_wechat_url
from app.services.identifier_resolver import (
    GHID_MAPPING_CHANNELS,
    ORIGIN_RESOLVER,
    ORIGIN_SOURCE,
    IdentifierResolver,
    biz_from_sample_url,
    ghid_from_html,
)

BIZ = "MzA5NzIwNTQ1Mg=="
BIZ_URL = f"https://mp.weixin.qq.com/s?__biz={BIZ.replace('=', '%3D')}&mid=264&idx=1&sn=aa"
GHID = "gh_b9465228558d"
_APP = Path(__file__).resolve().parents[1] / "app"


@contextmanager
def _logged() -> Iterator[list[dict[str, Any]]]:
    """`capture_logs()` + 换一个新代理。

    `core/logging.py` 以 `cache_logger_on_first_use=True` 装配，模块级 logger 在第一次被用时
    就绑死当时的全局配置 ⇒ 全量跑时窗外的首次使用会让捕获读不到东西（同一形状登记在 P-63）。
    """
    with capture_logs() as logs:
        original = resolver_module.logger
        resolver_module.logger = structlog.get_logger("app.services.identifier_resolver")
        try:
            yield logs
        finally:
            resolver_module.logger = original


def _blob(logs: list[dict[str, Any]]) -> str:
    return " ".join(f"{e.get('event')} {e}" for e in logs)


# ------------------------------------------------------------------ 推导规则（不连库）


def test_biz_derivation_is_the_parsing_layer_not_a_second_copy() -> None:
    """委托判据取**两种书写**：只比"与解析层恒等"不够——两处各写一份同样的代码时它也成立。"""
    assert biz_from_sample_url(BIZ_URL) == parse_wechat_url(BIZ_URL).biz == BIZ
    assert biz_from_sample_url(BIZ_URL.replace("%3D", "=")) == BIZ, (
        "同一条链接的两种 `__biz` 书写必须解出同一个值，否则同一个号主会裂成两个标识"
    )
    assert biz_from_sample_url("https://mp.weixin.qq.com/s/no-biz-here") == ""
    assert biz_from_sample_url(None) == ""  # type: ignore[arg-type]


def test_no_channel_claims_the_biz_to_ghid_mapping() -> None:
    """卡面说"有渠道支持时"从 biz 补 ghid——现读是**没有**（各渠道以 ghid 为入参，Wellbyte 是 URL→gh_）。

    这条钉的是"没有就不许造"。将来 `GHID_MAPPING_CHANNELS` 被填上时本条会红，
    逼来人把推导分支与它的用例一起补上，而不是让凭空推导悄悄发生。
    """
    assert GHID_MAPPING_CHANNELS == ()


def test_ghid_parsed_from_the_two_measured_page_shapes() -> None:
    """键名家族照 `source_resolver._BIZ_RE` 的两支实证形态镜像（值在前 / `"" ||` 兜底写法）。"""
    assert ghid_from_html(f'<script>var user_name = "{GHID}";</script>') == GHID
    assert ghid_from_html(f'<script>var user_name = ""||"{GHID}";</script>') == GHID, "M0 样本的 || 写法"
    assert ghid_from_html(f'<span class="profile_weixin">{GHID}</span>') == GHID


def test_body_text_mentioning_a_gh_id_is_not_read_as_an_identifier() -> None:
    """窄化的理由不是风格：`(kind,value)` 全局唯一，把正文里随口一提的 gh_ 写进去 ⇒
    真号主后来入库时撞约束，只能告警不能覆盖，这一格的标识从此永久错挂。"""
    assert ghid_from_html(f"<div id='js_content'><p>加我微信号 {GHID} 聊</p></div>") == ""
    assert ghid_from_html(f"<p>var user_name = '{GHID}'</p>") == "", "单引号写法不在实证形态里"
    assert ghid_from_html("") == ""
    assert ghid_from_html('var user_name = "gh_b9465"') == "", "短于 6 位下限的 token 不认"


# ------------------------------------------------------------------ 落库（连库）


async def _source(db_session: AsyncSession, *, external_id: str, url: str = "") -> Source:
    src = Source(type="wechat_oa", external_id=external_id, name=f"s08-{id(db_session)}", url=url)
    db_session.add(src)
    await db_session.flush()
    return src


async def _rows(db_session: AsyncSession, source_id: str) -> dict[str, str]:
    return {
        kind: origin
        for kind, origin in (
            await db_session.execute(
                select(SourceIdentifier.kind, SourceIdentifier.origin).where(
                    SourceIdentifier.source_id == source_id
                )
            )
        ).all()
    }


async def test_external_id_becomes_a_biz_identifier_of_origin_source(db_session: AsyncSession) -> None:
    src = await _source(db_session, external_id="BIZ-FROM-COLUMN")
    got = await IdentifierResolver(db_session).ensure_identifiers(src)
    assert got["biz"] == "BIZ-FROM-COLUMN"
    assert await _rows(db_session, src.id) == {"biz": ORIGIN_SOURCE}


async def test_biz_is_derived_from_the_sample_url_when_the_column_is_empty(db_session: AsyncSession) -> None:
    """回填之后新建的源，external_id 为空时样例链接就是唯一线索，且 origin 要说清是推出来的。"""
    src = await _source(db_session, external_id="", url=BIZ_URL)
    got = await IdentifierResolver(db_session).ensure_identifiers(src)
    assert got["biz"] == BIZ
    assert await _rows(db_session, src.id) == {"biz": ORIGIN_RESOLVER, "sample_url": ORIGIN_SOURCE}


async def test_ensure_is_idempotent(db_session: AsyncSession) -> None:
    src = await _source(db_session, external_id="BIZ-IDEM", url=BIZ_URL)
    resolver = IdentifierResolver(db_session)
    first = dict(await resolver.ensure_identifiers(src))
    after_first = (await db_session.execute(select(func.count()).select_from(SourceIdentifier))).scalar_one()
    second = dict(await resolver.ensure_identifiers(src))
    after_second = (await db_session.execute(select(func.count()).select_from(SourceIdentifier))).scalar_one()
    assert first == second
    assert after_first == after_second, "每次读取都新增一行 = 把幂等写成了追加"


async def test_a_biz_already_owned_by_another_source_is_not_taken(db_session: AsyncSession) -> None:
    """两个源声称同一个号主 ⇒ 第二个不覆盖、不崩，且如实告警。

    形状是真的：A 用 `external_id` 列登记 biz，B 的列是空、但样例链接指向**同一个** `__biz`
    ——`sources` 那对 `(type, external_id)` 唯一约束拦不住它，拦得住的是本表的 `(kind, value)`。
    这正是那条唯一约束要抓的事：号主身份共用不会报错，而是清单串到别人的资产上（P0-1 那一族）。
    """
    owner = await _source(db_session, external_id=BIZ)
    other = await _source(db_session, external_id="", url=BIZ_URL)
    resolver = IdentifierResolver(db_session)
    await resolver.ensure_identifiers(owner)
    with _logged() as logs:
        got = await resolver.ensure_identifiers(other)
    assert got.get("biz") is None, "第二个源不该拿到别人的 biz 行"
    assert BIZ in _blob(logs), logs
    assert await _rows(db_session, other.id) == {"sample_url": ORIGIN_SOURCE}


async def test_unknown_kind_rows_are_not_trusted_by_the_reader(db_session: AsyncSession) -> None:
    """ADR-0014 不变量 2：库里出现没登记的 kind ⇒ 读侧忽略并告警，不参与渠道选择。"""
    src = await _source(db_session, external_id="BIZ-KINDS")
    resolver = IdentifierResolver(db_session)
    await resolver.ensure_identifiers(src)
    db_session.add(SourceIdentifier(source_id=src.id, kind="telegram_id", value="t-1", origin=ORIGIN_SOURCE))
    await db_session.flush()
    with _logged() as logs:
        got = await resolver.identifiers(src.id)
    assert got == {"biz": "BIZ-KINDS"}
    assert "telegram_id" in _blob(logs)


async def test_reverse_lookup_by_identifier_and_unknown_kind(db_session: AsyncSession) -> None:
    src = await _source(db_session, external_id="BIZ-FIND")
    resolver = IdentifierResolver(db_session)
    await resolver.ensure_identifiers(src)
    assert await resolver.find_source_id("biz", "BIZ-FIND") == src.id
    assert await resolver.find_source_id("biz", "NOPE") is None
    assert await resolver.find_source_id("telegram_id", "BIZ-FIND") is None, "未知 kind 不允许被反查"


async def test_without_page_html_the_ghid_slot_stays_empty(db_session: AsyncSession) -> None:
    """biz 推不出 ghid（`GHID_MAPPING_CHANNELS` 为空）⇒ 没有页面原文时这一格就是空，不报错、不猜。"""
    src = await _source(db_session, external_id="BIZ-NO-GHID")
    resolver = IdentifierResolver(db_session)
    await resolver.ensure_identifiers(src)
    assert await resolver.ghid_for(src) is None
    assert "ghid" not in await resolver.identifiers(src.id)


async def test_ghid_from_the_page_already_in_hand_is_written_as_derived(db_session: AsyncSession) -> None:
    """入库时那篇页面的原文本来就在手 ⇒ 顺带读出的 ghid 要落库，且 origin 说清是推出来的。

    这条是"卡面交付物真的落地"的唯一计数证据：只测 `ghid_from_html` 的话，
    解析函数写成死代码它也绿。
    """
    src = await _source(db_session, external_id="BIZ-GHID")
    page = 'var user_name = "' + GHID + '";'
    got = await IdentifierResolver(db_session).ensure_identifiers(src, html=page)
    assert got["ghid"] == GHID
    assert await _rows(db_session, src.id) == {"biz": ORIGIN_SOURCE, "ghid": ORIGIN_RESOLVER}


# ── 接线证明（AST）：解析函数存在 ≠ 有人在入库时叫它 ─────────────────────────────


def _callee_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _ensure_calls(tree: ast.AST) -> list[ast.Call]:
    return [
        item
        for item in ast.walk(tree)
        if isinstance(item, ast.Call) and _callee_name(item.func) == "ensure_identifiers"
    ]


def test_the_resolver_has_exactly_three_claimed_production_callers() -> None:
    """标识补全在生产代码里只许有**三处**调用，且三处各自的角色写死。

    - `services/kb.py` 1 处 = 入库落库那一步（卡面 S8.2.1 的"入库成功时写"）；
    - `services/scheduler.py` 1 处 = 每轮调度按源取渠道之前的"读侧补行"
      （S8.4.1 要用标识筛渠道；不补的话，迁移回填之后建出来、又没再入库的源没有标识行，
      路由会把"我们没读过它"读成"这一源哪一家都去不了" ⇒ 整轮静默不发现）。
    - `services/subscription.py` 1 处 = 注册 RSS 源的那一刻（STEP-09 S9.1.1：feed_url 只在
      这一支被写，别无第二处；`register_source` 的公众号分支不补，保持 S8.2.1 的两处形状）。

    判"N 处各一次"而不是判"存在"：多出的一处 = 出现了没人认领的写入口（迁移回填之外的分裂），
    正是 ADR-0014 要防的；零处 = 本模块退化成只有测试在用的死代码。
    """
    hits: list[tuple[str, int]] = []
    for path in sorted(p for p in _APP.rglob("*.py") if "__pycache__" not in p.parts):
        count = len(_ensure_calls(ast.parse(path.read_text(encoding="utf-8"))))
        if count:
            hits.append((path.relative_to(_APP).as_posix(), count))
    assert hits == [
        ("services/kb.py", 1),
        ("services/scheduler.py", 1),
        ("services/subscription.py", 1),
    ], f"标识补全的调用面={hits}"


def test_that_one_call_hands_it_the_page_it_already_fetched() -> None:
    """卡面的"零额外请求"落在参数上：不传 `html=` 的话，ghid 那一格今天在生产里永远空着。"""
    tree = ast.parse((_APP / "services" / "kb.py").read_text(encoding="utf-8"))
    func = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_persist_document"
    )
    calls = _ensure_calls(func)
    assert len(calls) == 1, "_persist_document 没有调用标识补全"
    assert any(kw.arg == "html" for kw in calls[0].keywords), "调用未把已在手的页面原文传进来"
