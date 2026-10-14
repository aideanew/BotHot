"""STEP-02 / S2.1.5：`AssetRepository.get_by_url_fragment` 的片段长度守卫。

根因链（与 S2.1.4 同源）：长链的 article_key 是 URL 末段 `s`（`kb._article_key`），
而 `get_by_url_fragment` 拿它做 `ContentAsset.url LIKE '%s%'` 兜底——几乎所有 https URL
都含字母 s，于是「该源下 URL 含该片段」这条兜底退化成「随便给我一行资产」，
缓存命中会复用错文章、版本管理会比对错 hash。卡面口径：片段长度 < 8 直接返回 None 并记 WARNING。

本机跑不起来（与 `test_kb_longlink_ingest.py` 同一原因：模块级 import `sqlalchemy`/`structlog`，
本机皆无）⇒ 有依赖环境的执行命令是卡面验收命令
`cd apps/api && uv run pytest tests -q -k url_fragment`；
本机侧等价证明在 `docs/06_validation/evidence/EVD-V2-02/prove_anchor_fallback.py`
（AST 取磁盘 asset.py 的当前函数体真实执行，带改坏必须红 / 等价不假红 / 判据能假三通道）。

这里刻意用假会话而不是连库会话：守卫的判据是「有没有把 SQL 发出去」，
连库夹具会把"发出去了什么"糊成一层 commit/rollback 噪声，且 8/7 边界只需数查询次数。
"""

from __future__ import annotations

import pytest

from app.models.entities import ContentAsset
from app.repositories import asset as asset_module
from app.repositories.asset import MIN_FRAGMENT_LEN, AssetRepository


class _RecordingSession:
    """只实现 `scalar`：记录每次下发的语句，返回可辨识的假资产。

    守卫失效（旧实现直接放行 `"s"`）时 `calls` 会多出一条 ⇒ 断言红；
    守卫过严（把合法片段也挡掉）时 `calls` 会少一条 ⇒ 同样红。两个方向都能被抓住。
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def scalar(self, stmt):  # noqa: ANN202
        self.calls.append(str(stmt.compile()))
        return _asset()


def _asset() -> ContentAsset:
    return ContentAsset(
        id="asset-1",
        source_id="src-1",
        external_id="k",
        url="https://mp.weixin.qq.com/s/other",
        content_hash="h",
        content_markdown="x",
    )


class _Recorder:
    """替换模块级 logger，抓住 `logger.warning(event, **kw)` 的调用现场。"""

    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict[str, object]]] = []

    def warning(self, event: str, **kw: object) -> None:
        self.warnings.append((event, kw))

    def info(self, event: str, **kw: object) -> None:  # 其余级别静默
        pass


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    rec = _Recorder()
    monkeypatch.setattr(asset_module, "logger", rec)
    return rec


async def test_url_fragment_short_returns_none_and_zero_query(recorder: _Recorder) -> None:
    """机器门①：`"s"`（长链 article_key 的真实退化形）不发 SQL、返回 None、留 WARNING。"""
    sess = _RecordingSession()
    got = await AssetRepository(sess).get_by_url_fragment("src-1", "s")  # type: ignore[arg-type]
    assert got is None, f"短片段仍返回了资产：{got!r}"
    assert sess.calls == [], f"短片段仍下发了 {len(sess.calls)} 条 SQL：守卫没生效"
    assert [w[0] for w in recorder.warnings] == ["asset_url_fragment_too_short"], (
        f"WARNING 缺失或事件名漂移：{recorder.warnings!r}"
    )


async def test_url_fragment_empty_returns_none_without_warning(recorder: _Recorder) -> None:
    """空串维持旧语义（不发 SQL），但不该刷 WARNING——空串是调用方没给值，不是命中风险。"""
    sess = _RecordingSession()
    assert await AssetRepository(sess).get_by_url_fragment("src-1", "") is None  # type: ignore[arg-type]
    assert sess.calls == []
    assert recorder.warnings == [], f"空串被当成短片段告警：{recorder.warnings!r}"


@pytest.mark.parametrize(("fragment", "queries"), [("abcdefg", 0), ("abcdefgh", 1), ("p0-cache-001", 1)])
async def test_url_fragment_boundary_is_exactly_min_len(
    fragment: str, queries: int, recorder: _Recorder
) -> None:
    """机器门②：阈值边界卡在 MIN_FRAGMENT_LEN=8（7 挡、8 放），合法片段必须仍查得到。

    这条同时反证两件事：阈值被悄悄改成 1（守卫形同虚设）⇒ 7 那一行红；
    阈值被悄悄改成 12（把存量兼容路径也挡了）⇒ 8 那一行红。
    """
    assert MIN_FRAGMENT_LEN == 8, f"卡面阈值是 8，代码里是 {MIN_FRAGMENT_LEN}"
    sess = _RecordingSession()
    got = await AssetRepository(sess).get_by_url_fragment("src-1", fragment)  # type: ignore[arg-type]
    assert len(sess.calls) == queries, f"{fragment!r}（{len(fragment)} 字符）下发了 {len(sess.calls)} 条，期望 {queries}"
    assert (got is None) is (queries == 0), f"{fragment!r} → {got!r}，与下发条数不自洽"


async def test_url_fragment_query_is_source_scoped_like(recorder: _Recorder) -> None:
    """机器门③：放行的片段仍按 (source_id, url LIKE %片段%) + limit(1) 下发。

    守卫不是把兜底整个关掉的理由——存量兼容路径（biz 锚源 + article_key 资产）还得走通，
    只是不再拿单字符去撞全表。
    """
    sess = _RecordingSession()
    await AssetRepository(sess).get_by_url_fragment("src-1", "aaaa1111")  # type: ignore[arg-type]
    assert len(sess.calls) == 1
    sql = sess.calls[0].upper()
    assert "LIKE" in sql and "LIMIT" in sql, f"兜底语句形态漂移：{sess.calls[0]!r}"
