"""W2 热点聚簇：TF-IDF 标题相似度 + 单链接凝聚聚类，零 schema 变更。

设计口径（任务 2.1/2.2）：
- 窗口取近 N 天 content_assets（published_at 为锚，缺失回落 created_at），N 参数化默认 1；
- 标题规范化（NFKC 全半角统一 + 小写）后**按字 bigram 分词**——不引入 jieba/numpy/sklearn
  重依赖。理由：公众号标题以中文为主，字 bigram 对"同义改写/转载"这类字面高度重叠的
  场景命中率高；日增量百~千篇量级纯内存实现足够。拉丁字母段按词切分补足；
- TF-IDF 向量 + 余弦相似度，阈值 τ 单链接凝聚聚类。单链接在阈值 τ 下的凝聚聚类等价于
  「相似度 ≥ τ 的边的连通分量」，实现取连通分量（与 sklearn AgglomerativeClustering
  linkage=single + distance_threshold 同语义，零依赖）；
- 簇内 quality_score 最高者为 center_asset；relevance_score = 该文与中心的余弦相似度
  （中心自身 = 1.0）。

幂等策略（任务 2.2b）：重跑某日先删除该日 HotTopic（CASCADE 及 HotTopicArticle）+
对应 FeedItem(item_type=hot_topic) 再重建。选择「按 topic_date 整日 wipe」而非逐簇
diff，因聚簇结果随窗口漂移（同日不同窗口成员可能变化），逐簇合并会留下半旧簇，整日
重建语义清晰且可重复。簇标题取中心文章标题（去公众号后缀类噪声），summary 初版留空
（由日报阶段 LLM 填充）。

只持久化成员数 ≥ 2 的簇为 HotTopic（单篇不构成「事件」）；孤立文章不入热点表。
"""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bothot_entities import FeedItem, HotTopic, HotTopicArticle
from app.models.entities import ContentAsset

logger = logging.getLogger(__name__)

# 热点业务日界 = Asia/Shanghai；如改口径只动此常量（与 hot.py BUSINESS_TZ 同口径）。
BUSINESS_TZ = ZoneInfo("Asia/Shanghai")

# 余弦相似度凝聚阈值 τ（可调：调低→更易合并、簇更大；调高→更保守、簇更多）。
# 0.35 在公众号同义改写语料上经验命中（标题 bigram 重叠约 35% 即视为同主题）。
SIM_THRESHOLD = 0.35

# 公众号标题常见后缀噪声（去后缀让簇标题更干净；不影响分词相似度计算）。
_TITLE_NOISE = re.compile(r"[|｜\-—–].*$")


@dataclass(frozen=True)
class AssetDoc:
    """聚簇纯函数输入：仅需 id / title / quality_score。"""

    id: str
    title: str
    quality_score: float


# ── 分词 ──────────────────────────────────────────────────────────────

_CJK_RUN = re.compile(r"[一-鿿]+")
_LATIN_RUN = re.compile(r"[a-z0-9]+")
# 单字停用词（仅对单字 unigram 有效；bigram 不在此集，由 IDF 自然降权）
_STOPWORDS = {"的", "了", "是", "在", "与", "和", "及", "为", "对", "这", "那", "一", "有"}


def _normalize(title: str) -> str:
    """NFKC 全半角统一 + 小写。"""
    return unicodedata.normalize("NFKC", title or "").lower()


def _tokenize(title: str) -> list[str]:
    """中文按字 bigram（单字回退 unigram）+ 拉丁按词，去停用词。"""
    s = _normalize(title)
    toks: list[str] = []
    for run in _CJK_RUN.findall(s):
        if len(run) == 1:
            toks.append(run)
        else:
            toks.extend(run[i : i + 2] for i in range(len(run) - 1))
    toks.extend(_LATIN_RUN.findall(s))
    return [t for t in toks if t not in _STOPWORDS]


def _tfidf_vectors(docs: Sequence[AssetDoc]) -> list[dict[str, float]]:
    """逐文档 TF-IDF 向量（dict token→权重）；IDF 平滑：ln((1+N)/(1+df))+1。"""
    n = len(docs)
    if n == 0:
        return []
    token_seqs = [_tokenize(d.title) for d in docs]  # 带重复序列（算 TF）
    token_sets = [set(s) for s in token_seqs]  # 集合（算 df）
    df: Counter[str] = Counter()
    for ts in token_sets:
        df.update(ts)
    idf = {t: math.log((1 + n) / (1 + df_t)) + 1.0 for t, df_t in df.items()}
    vectors: list[dict[str, float]] = []
    for seq in token_seqs:
        total = len(seq) or 1
        tf = Counter(seq)
        vectors.append({t: (c / total) * idf[t] for t, c in tf.items()})
    return vectors


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    shared = a.keys() & b.keys()
    dot = sum(a[k] * b[k] for k in shared)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def cluster(docs: Sequence[AssetDoc], *, tau: float = SIM_THRESHOLD) -> list[list[int]]:
    """单链接凝聚聚类 = 相似度 ≥ τ 的连通分量。返回各簇的成员下标列表（含单成员簇）。"""
    n = len(docs)
    vectors = _tfidf_vectors(docs)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            if _cosine(vectors[i], vectors[j]) >= tau:
                union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    return list(groups.values())


# ── 落库 ──────────────────────────────────────────────────────────────


def _clean_title(title: str) -> str:
    """去公众号后缀噪声（标题首个分隔符后截断），簇标题用。"""
    return _TITLE_NOISE.split(title or "", 1)[0].strip() or (title or "").strip()


def _business_date(dt: datetime | None, *, fallback: datetime) -> str:
    """把时刻转 Asia/Shanghai 业务日期串；dt 为空回落 fallback。"""
    moment = dt if dt is not None else fallback
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BUSINESS_TZ)
    return moment.astimezone(BUSINESS_TZ).strftime("%Y-%m-%d")


async def _delete_day_topics(session: AsyncSession, topic_date: str) -> None:
    """幂等：删除该日全部 HotTopic（CASCADE 及 HotTopicArticle）+ 对应 FeedItem。

    HotTopicArticle.hot_topic_id ondelete=CASCADE，删 HotTopic 自动级联删关联行；
    FeedItem(item_type=hot_topic, ref_id=topic_id) 无外键，需显式按 ref_id 删。
    """
    topic_ids = [
        row[0]
        for row in (
            await session.execute(select(HotTopic.id).where(HotTopic.topic_date == topic_date))
        ).all()
    ]
    if topic_ids:
        await session.execute(
            delete(FeedItem).where(
                FeedItem.item_type == "hot_topic", FeedItem.ref_id.in_(topic_ids)
            )
        )
    await session.execute(delete(HotTopic).where(HotTopic.topic_date == topic_date))


async def run_clustering(
    session: AsyncSession,
    *,
    days: int = 1,
    now: datetime | None = None,
) -> dict[str, Any]:
    """取近 N 天 content_assets → 聚簇 → 写 HotTopic/HotTopicArticle/FeedItem。

    事务边界由调用方（job_worker / API）持有；本方法只 flush 不 commit。
    返回摘要供 Job 结果与日志观测。
    """
    from app.services.feed_service import add_hot_topic_feed

    moment = now or datetime.now(BUSINESS_TZ)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BUSINESS_TZ)
    cutoff = moment - timedelta(days=max(days, 1))

    rows = (
        await session.execute(
            select(ContentAsset).where(
                or_(
                    ContentAsset.published_at >= cutoff,
                    and_(
                        ContentAsset.published_at.is_(None),
                        ContentAsset.created_at >= cutoff,
                    ),
                )
            )
        )
    ).scalars().all()

    docs = [AssetDoc(id=a.id, title=a.title, quality_score=float(a.quality_score or 0.0)) for a in rows]
    vectors = _tfidf_vectors(docs)  # 语料级 IDF 向量，与 cluster() 同口径算 relevance
    groups = cluster(docs)

    # 业务日期取窗口当日（moment 的业务日）；同窗口所有簇共享一个 topic_date，
    # 整日 wipe 重建保证幂等。
    topic_date = moment.astimezone(BUSINESS_TZ).strftime("%Y-%m-%d")
    await _delete_day_topics(session, topic_date)

    by_id = {a.id: a for a in rows}
    id_to_idx = {d.id: i for i, d in enumerate(docs)}
    persisted = 0
    for group in groups:
        if len(group) < 2:
            continue  # 单篇不构成事件
        members = [by_id[docs[i].id] for i in group]
        center = max(members, key=lambda a: float(a.quality_score or 0.0))
        center_idx = id_to_idx[center.id]
        center_vec = vectors[center_idx]
        category = center.category or ""
        topic = HotTopic(
            title=_clean_title(center.title),
            summary="",  # 初版留空，日报阶段 LLM 填充
            center_asset_id=center.id,
            hot_score=0.0,  # 评分由 hot_scorer 回填
            source_count=1,
            article_count=len(members),
            status="rising",
            topic_date=topic_date,
            category=category,
        )
        session.add(topic)
        await session.flush()  # 取 topic.id

        for m in members:
            rel = 1.0 if m.id == center.id else _cosine(vectors[id_to_idx[m.id]], center_vec)
            session.add(
                HotTopicArticle(
                    hot_topic_id=topic.id,
                    asset_id=m.id,
                    relevance_score=float(rel),
                )
            )
        await add_hot_topic_feed(session, topic)
        persisted += 1

    logger.info("hot_cluster: 窗口 %d 天 / 候选 %d 篇 / 簇 %d / 落库话题 %d", days, len(docs), len(groups), persisted)
    return {
        "topic_date": topic_date,
        "candidates": len(docs),
        "clusters": len(groups),
        "topics_persisted": persisted,
    }
