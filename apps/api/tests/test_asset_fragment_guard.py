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
        # 渲染必须带 `literal_binds`：默认方言把值渲染成绑定参数
        # （`source_id = :source_id_1 … LIKE :url_1 LIMIT :param_1`），下面那条
        # 「断言渲染文本里有字面值」的机器门在 CI 上就恒红。这条红由 V0.8.0 的
        # `docs/任务规划V0.8.0/evidence/61358c3/pytest_local_noPG.txt` 抓到，
        # 修法照 V0.8.0 STEP-00C 卡 S0C.1.2 那一条；本包另有一条静态判据
        # （`replay_s213.py` 的 `sql_render_defects`）防止再犯。
        self.calls.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
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
    """机器门①：`"s"`（长链 article_key 的真实退化形）不发 SQL、返回 None、留一条**说清参数的** WARNING。

    告警载荷也判（A 组 MI-3）：只比事件名时，把 `source_id=…/fragment=…/min_len=…` 三个 kw 全删掉
    这一条照样绿——「显式放弃兜底并留痕」里的「痕」就只剩下一个词，拿到它不知道是谁的哪个片段、
    被哪条阈值挡的。
    """
    sess = _RecordingSession()
    got = await AssetRepository(sess).get_by_url_fragment("src-1", "s")  # type: ignore[arg-type]
    assert got is None, f"短片段仍返回了资产：{got!r}"
    assert sess.calls == [], f"短片段仍下发了 {len(sess.calls)} 条 SQL：守卫没生效"
    assert [w[0] for w in recorder.warnings] == ["asset_url_fragment_too_short"], (
        f"WARNING 缺失或事件名漂移：{recorder.warnings!r}"
    )
    event, kw = recorder.warnings[0]
    assert kw.get("source_id") == "src-1", f"告警没带 source_id：{event} {kw!r}"
    assert kw.get("fragment") == "s", f"告警没带被挡的片段：{event} {kw!r}"
    assert kw.get("min_len") == MIN_FRAGMENT_LEN, f"告警里的阈值与常量不符：{event} {kw!r}"


async def test_url_fragment_empty_returns_none_without_warning(recorder: _Recorder) -> None:
    """空串维持旧语义（不发 SQL），但不该刷 WARNING——空串是调用方没给值，不是命中风险。"""
    sess = _RecordingSession()
    assert await AssetRepository(sess).get_by_url_fragment("src-1", "") is None  # type: ignore[arg-type]
    assert sess.calls == []
    assert recorder.warnings == [], f"空串被当成短片段告警：{recorder.warnings!r}"


@pytest.mark.parametrize(
    ("fragment", "queries"),
    [("abcdefg", 0), ("abcdefgh", 1), ("p0-cache-001", 1), ("热点热", 0), ("1234567", 0),
     ("ab-1234", 0), ("ab-12345", 1), ("p0-st_01", 1), ("a--b", 0)],
)
async def test_url_fragment_boundary_is_exactly_min_len(
    fragment: str, queries: int, recorder: _Recorder
) -> None:
    """机器门②：阈值边界卡在 MIN_FRAGMENT_LEN=8 个**字符**（7 挡、8 放），合法片段必须仍查得到。

    这条同时反证两件事：阈值被悄悄改成 1（守卫形同虚设）⇒ 7 那一行红；
    阈值被悄悄改成 12（把存量兼容路径也挡了）⇒ 8 那一行红。
    `热点热` 那一行钉的是**计数单位**（A 组 MI-2）：3 个字符 = 9 个 UTF-8 字节，
    守卫若被改成按字节数长度就会把它放行——三个样本全是 ASCII 时字符数与字节数谁也分不开。
    `1234567` 那一行钉的是**守卫的返回必须无条件**（第十四轮 C 组 C-14-02）：
    把 `return None` 嵌进 `if fragment.isalpha():` 那种写法，四个字母/汉字样本全都照旧，
    只有纯数字的短片段（缓存键、纯数字 mid）会被放出去发 LIKE——没有这一行，那条旁路无人可证。
    """
    assert MIN_FRAGMENT_LEN == 8, f"卡面阈值是 8，代码里是 {MIN_FRAGMENT_LEN}"
    sess = _RecordingSession()
    got = await AssetRepository(sess).get_by_url_fragment("src-1", fragment)  # type: ignore[arg-type]
    assert len(sess.calls) == queries, (
        f"{fragment!r}（{len(fragment)} 字符）下发了 {len(sess.calls)} 条，期望 {queries}"
    )
    assert (got is None) is (queries == 0), f"{fragment!r} → {got!r}，与下发条数不自洽"


async def test_url_fragment_query_is_source_scoped_like(recorder: _Recorder) -> None:
    """机器门③：放行的片段仍按 (source_id 等值 + url LIKE `%片段%` + LIMIT 1) 下发。

    守卫不是把兜底整个关掉的理由——存量兼容路径（biz 锚源 + article_key 资产）还得走通，
    只是不再拿单字符去撞全表。

    断言写的是**形状与参数值**而不是「串里有 LIKE 这个词」：从前那版只判
    `"LIKE" in sql and "LIMIT" in sql`，于是 `.limit(5)`、或把 `source_id` 谓词整条删掉都判不动
    （A 组 MI-7：那句话比用例能证的强）。现在三个条件各有一句：跨源不得命中、只取一行、模式含通配。
    """
    sess = _RecordingSession()
    await AssetRepository(sess).get_by_url_fragment("src-1", "aaaa1111")  # type: ignore[arg-type]
    assert len(sess.calls) == 1, f"应恰好下发一条，实得 {len(sess.calls)} 条"
    sql = sess.calls[0]
    flat = " ".join(sql.split())
    assert "source_id = 'src-1'" in flat, f"没有按源过滤（跨源命中就是拿别人的资产当缓存）：{sql!r}"
    assert "LIMIT 1" in flat.upper(), f"兜底语句不再是单行：{sql!r}"
    assert "%aaaa1111%" in sql, f"LIKE 模式丢了通配或丢了片段本身：{sql!r}"
