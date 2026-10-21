"""文章来源 Provider 基类与协议。

每个平台实现 ArticleSourceProvider 协议，提供两种能力：
1. **发现**（清单）：STEP-08 S8.3.1 起主端口是 `query_work_list_page`（游标进、游标出，
   产物 `WorkListPage`）；旧端口 `query_work_list(identifier, page)` **保留一个版本**，
   由各 provider 适配到新端口上——直接删它会把 STEP-03 的契约测试一起删掉（那些文件不在
   本卡所有权内），而"上游游标不能由页号预构"这件事本来就该由旧端口的空页如实说出来。
2. **详情兜底**（fetch_article_detail）：付费获取文章正文，直抓失败时触发

统一产物 ArticleDetail 汇入 extractor → normalizer → ContentAsset 同一入库链。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import structlog
from pydantic import ValidationError

from app.contracts.collection import WorkListPage, WorkListRow

#: 上游页宽（`redfox.client.PAGE_SIZE` 同值）。它同时是 S8.3.2 的末页判据宽度：
#: 「本页少于 page_size」= 上游没有下一页了，比等一个可能永远不来的空页便宜。
WORK_LIST_PAGE_SIZE = 20

_logger = structlog.get_logger(__name__)


def _epoch_to_aware(value: Any) -> datetime | None:
    """纯 epoch 秒/毫秒（数值或数字串）→ 带时区值；别的形状一律 `None`。

    刻意只认数值形状：四家付费渠道的清单实测就是 `str(CreateTime)`（`test_provider_contract.py:903`
    钉着 `publishTime == str(_EPOCH)`），而 `1e11` 以上的毫秒判定与 `tz=UTC` 这两条口径
    与消费端 `manifest._from_epoch` 逐字相同——**不是**在这里另立一套时间解释。
    RSS 的 `pubDate`（RFC 822）不在这里解：那套解析留在 `_parse_rfc822` 一份，
    provider 层再抄一遍就是 P-28 那一族"同一个字符串在两条路径上解出不同瞬间"。
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        seconds = float(value)
    elif isinstance(value, str) and value.strip().isdigit():
        seconds = float(value.strip())
    else:
        return None
    if seconds <= 0:
        return None
    if seconds > 1e11:  # 毫秒级
        seconds /= 1000.0
    try:
        return datetime.fromtimestamp(seconds, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def build_work_list_page(
    raw_rows: list[dict[str, Any]],
    *,
    next_cursor: str | None,
    page_size: int,
    total: int | None = None,
    channel: str = "",
) -> WorkListPage:
    """把各家原始行收成契约页——**行级策略只写在这一处**。

    存在理由：`WorkListRow` 有硬约束（`url` 8~512、`id` 非空、时间必须带时区），
    五个渠道各写一遍"不合约束的行怎么办"就会有五种答案——其中至少一种是直接抛
    （一条脏项打挂整页，P-17 的原形状），另一种是静默消失（P0-3 的原形状）。
    这里选第三种并让它出声：约束不过 → `warning` + 丢这一行，其余行照收。

    时间字段的处理是**加一格而不是换一格**：原键（`publishTime`）连同原值一起留在行里
    （`WorkListRow` 是 `extra="allow"`），typed 的 `publish_time` 只在数值形状上填。
    这样消费端 `_map_row` 的别名优先序与升级前逐字一致，不会因为"provider 开始讲类型"
    而把 RFC 822 那一支的时间解成 `None`——那种失败长得像"上游没时间"，不是"接线错了"。

    代价如实写在这里：迁移后的 provider 里"被丢掉几行"只在这两条日志里可见，
    `ManifestSyncReport.skipped` 计的是消费端解不出身份的行，两者不是同一件事（读数见 EVD-V17-08 §9）。
    """
    rows: list[WorkListRow] = []
    dropped = 0
    for raw in raw_rows:
        payload = dict(raw)
        typed = _epoch_to_aware(payload.get("publishTime", payload.get("publish_time")))
        if typed is not None:
            payload["publish_time"] = typed
        try:
            rows.append(WorkListRow.model_validate(payload))
        except ValidationError:
            dropped += 1
            _logger.warning(
                "discovery.row_unrepresentable",
                channel=channel,
                url=str(raw.get("url", ""))[:80],
                keys=sorted(raw)[:6],
            )
    if dropped:
        _logger.warning("discovery.page_rows_dropped", channel=channel, dropped=dropped, kept=len(rows))
    if raw_rows and not rows:
        # 整页丢光必须比"丢一行"更响：服务层拿到空页会当"上游没内容"直接止页，
        # 于是 P0-3 那一族（上游正常而本仓零入库）的告警面在这一页上是空的——
        # 本卡没有指标面（`core/metrics.py` 与 `core/alerting.py` 属 STEP-05），
        # 所以这里至少用 error 级把形状留在日志里，缺口登记为 P-69。
        _logger.error("discovery.page_all_dropped", channel=channel, attempted=len(raw_rows))
    return WorkListPage(rows=rows, next_cursor=next_cursor, page_size=page_size, total=total)


def work_list_row_id(url: str) -> str:
    """清单行 id = URL 的规范键（ADR-0011 的 `canonical_article_key`）。

    存在理由（STEP-03 的 P-1）：`manifest._map_row` 在解不出 id 时 `return None`，
    而 dajiala / justoneapi / tikhub / wellbyte 的清单样本里**没有任何 id 形状字段**
    ⇒ 上游返回 N 条、本地落 0 条，而一轮同步读起来像成功。
    生产端先补 `id`、消费端再兜一层（`_map_row` 的 fallback），任一端回退都不会丢整页。

    上游带 id 的渠道（redfox 的 `workUuid`、rss 的 `guid`/`id`）**不**走这里：
    它们的沿用由消费端 `_ID_KEYS` 的优先序负责，本函数只负责"上游没给"的那一侧，
    免得多处判上游 id 而各处判得还不一样。

    `url` 先 `strip()` 再算键：消费端兜底走的是 `_first_str`（它会 strip），
    生产端若用未 strip 的原串，同一个 ` https://x/a ` 会算出**另一个**哈希键——
    那就是 STEP-02 刚消灭的那族"两处各说各话的冒名键"，只是换了入口。
    """
    from app.services.article_identity import canonical_article_key

    cleaned = url.strip()
    return canonical_article_key(cleaned) if cleaned else ""


@dataclass(frozen=True, slots=True)
class ArticleDetail:
    """付费详情 API 的归一化产物。

    各平台响应字段不同，防腐层统一到此结构后汇入入库链。
    """

    url: str
    title: str
    content_html: str  # 原始 HTML 正文（extractor 可直接消费）
    content_text: str  # 纯文本正文（兜底用，extractor 优先用 html）
    author: str = ""
    biz: str = ""  # 公众号 __biz（base64）
    ghid: str = ""  # 公众号 gh_ ID
    publish_time: datetime | None = None
    source: str = ""  # 来源平台名（dajiala/justoneapi/...）


@dataclass(frozen=True, slots=True)
class ArticleSearchResult:
    """关键词搜索结果（Wellbyte/TikHub/Dajiala 支持）。"""

    url: str
    title: str
    digest: str = ""
    author: str = ""
    publish_time: datetime | None = None
    source: str = ""


class ArticleSourceProvider(Protocol):
    """文章来源 Provider 协议：发现 + 详情兜底。

    query_work_list / query_work_list_page 的 identifier 参数：
    - RedFox：biz（base64 __biz）
    - Dajiala/JustOneAPI/TikHub：ghid（gh_xxx）
    - Wellbyte：文章 URL（account_history）或关键词（search）
    - RSS：feed URL

    各 Provider 内部按自身 API 契约解释 identifier。
    """

    name: str
    description: str

    async def query_work_list_page(
        self, identity: str, cursor: str | None = None, *, page_size: int = WORK_LIST_PAGE_SIZE
    ) -> WorkListPage:
        """取一页清单（S8.3.1 主端口）。

        `cursor` 是**上游给的**、不透明：`None` 表示首页，其余值必须是上一次响应里
        `WorkListPage.next_cursor` 的原样回传——本层不翻译、不递增、不猜。
        上游没有可续游标时 `next_cursor` 恒为 `None`（= 这就是末页），
        拿页号拼一个假游标等于让上层以为"还有下一页"而反复打付费接口。
        """
        ...

    async def query_work_list(self, identifier: str, page: int) -> tuple[list[dict[str, Any]], int | None]:
        """旧签名（保留一个版本）：page 从 1 起，返回 `(原始行, 上游 total)`。

        行字段经 `manifest._map_row` 的别名消化；上游缺失 total 时为 None。
        这一版**只在页号能等价换成游标的渠道上继续翻页**：四家付费渠道的游标由上页响应
        产生，无法从页号预构 ⇒ 它们的旧入口 page>1 如实返回空页（与升级前逐字相同），
        要翻页就走 `query_work_list_page`。
        """
        ...

    async def fetch_article_detail(self, url: str) -> ArticleDetail | None:
        """付费获取文章详情（正文 + 元数据）。

        直抓失败且非图集类时由 fallback coordinator 调用。
        返回 None 表示该平台不支持详情或获取失败（不抛异常，由 coordinator 降级）。
        """
        ...

    async def search_articles(
        self, keyword: str, *, sort: str = "latest", time_range: str = ""
    ) -> list[ArticleSearchResult]:
        """关键词搜索文章（可选能力，不支持的平台返回空列表）。"""
        ...

    async def aclose(self) -> None:
        """释放 HTTP 连接。"""
        ...
