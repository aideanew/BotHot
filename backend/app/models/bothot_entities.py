"""BotHot 扩展模型：多渠道机器人、推送任务、热点聚簇、日报、Feed 流。

设计原则：
- 高性能：关键字段建索引，热查询路径覆盖索引
- 高拓展：channel 字段用 String(32) 不枚举，新增渠道零迁移
- 层次明确：BotChannel(配置) → PushTask(调度) → PushLog(投递记录)
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, gen_uuid

# ── 1. 多渠道机器人配置 ──────────────────────────────────────────────

class BotChannel(TimestampMixin, Base):
    """机器人渠道配置：飞书/钉钉/微信ClawBot/企业微信/Webhook 等。

    一条记录 = 一个可投递的机器人入口。webhook_url 和 secret 由管理员在后台填写，
    AES-256-GCM 加密落库（secret_enc 字段，AAD 绑定 channel id），webhook_url 可明文（相当于门牌号）。
    """

    __tablename__ = "bot_channels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 渠道类型：feishu | dingtalk | wechat_clawbot | wechat_work | webhook | web
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 投递目标：飞书 webhook、钉钉 webhook、企业微信 webhook、自定义 webhook URL
    webhook_url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    # 签名密钥（飞书/钉钉加签模式）；AES-256-GCM 加密后落库（b64(nonce).b64(ct+tag)）
    secret_enc: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 额外配置 JSON（如飞书 app_id/app_secret、钉钉 access_token 等）
    extra_config: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    # 状态：active | disabled
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    # 绑定用户（可选：某些渠道绑定到特定用户，如微信 ClawBot）
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 统计：累计推送次数 / 成功次数
    total_push_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_push_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("name", name="uq_bot_channel_name"),)


# ── 2. 推送任务 ──────────────────────────────────────────────────────

class PushTask(TimestampMixin, Base):
    """推送任务：定时推送或事件触发推送。

    - 定时推送：cron_expr 驱动，scheduler 每轮扫描到期任务
    - 事件触发：trigger_event 驱动（如"新文章入库"、"热点更新"）
    - 手动触发：admin 手动点击"立即推送"
    """

    __tablename__ = "push_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 目标渠道（bot_channel.id）
    bot_channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bot_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 触发类型：cron | event | manual
    trigger_type: Mapped[str] = mapped_column(String(16), default="manual", nullable=False, index=True)
    # cron 表达式（trigger_type=cron 时有效）
    cron_expr: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # 事件类型（trigger_type=event 时有效）：new_article | hot_topic_update | daily_report
    trigger_event: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    # 推送内容模板：支持变量替换 {space_name} {doc_title} {hot_topic} {date}
    content_template: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 关联空间（可选：限定推送某个空间的新文章）
    space_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_spaces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 下次执行时间（cron 类型由 scheduler 计算）
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 状态：active | paused | deleted | failed（重试超限终态）
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    # 创建者
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 投递重试（WB，审查补完）：失败可重试时的已重试次数与下次重投时点；
    # 挂在任务而非日志——日志（PushLog）只记事实，调度语义归任务。
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


# ── 3. 推送日志 ──────────────────────────────────────────────────────

class PushLog(TimestampMixin, Base):
    """单次推送投递记录：成功/失败/内容摘要。

    高性能查询：按 bot_channel_id + created_at 建联合索引，管理端"某渠道最近推送"
    直接走索引扫描。
    """

    __tablename__ = "push_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    bot_channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bot_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    push_task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("push_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 投递状态：success | failed | dead（重试超限死信） | pending
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    # 推送内容摘要（前 200 字）
    content_preview: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    # 错误信息（失败时）
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 响应数据（渠道返回的原始响应摘要）
    response_summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)


# ── 4. 热点聚簇（融合 AIHOT） ────────────────────────────────────────

class HotTopic(TimestampMixin, Base):
    """热点事件：多篇文章聚簇为一个事件，按热度排序。

    融合 AIHOT 的聚簇与热度算法：
    - 聚簇：同主题文章归为一个事件
    - 热度：48h 内独立来源数加权，24h 减半
    """

    __tablename__ = "hot_topics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    # 事件标题（LLM 生成或取最高分文章标题）
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    # 事件摘要（LLM 生成）
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 聚簇中心文章 ID
    center_asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("content_assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 热度分数
    hot_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    # 独立来源数
    source_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # 关联文章数
    article_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # 状态：rising | hot | cooling | archived
    status: Mapped[str] = mapped_column(String(16), default="rising", nullable=False, index=True)
    # 事件日期（用于日报归档）
    topic_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    # 分类标签
    category: Mapped[str] = mapped_column(String(32), default="", nullable=False, index=True)


class HotTopicArticle(TimestampMixin, Base):
    """热点事件 ↔ 文章的多对多关联。"""

    __tablename__ = "hot_topic_articles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    hot_topic_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hot_topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 该文章在此事件中的相关度分数
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    __table_args__ = (
        UniqueConstraint("hot_topic_id", "asset_id", name="uq_hot_topic_asset"),
    )


# ── 5. 日报（融合 AIHOT） ────────────────────────────────────────────

class DailyReport(TimestampMixin, Base):
    """每日热点日报：自动生成或手动触发。

    融合 AIHOT 的日报机制：每天定时从 hot_topics 取当日 TOP N 热点，
    用 LLM 生成中文标题和摘要，组成日报。
    """

    __tablename__ = "daily_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    # 报告日期 YYYY-MM-DD
    report_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    # 报告标题
    title: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    # 报告内容（Markdown 格式）
    content_markdown: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 包含的热点数量
    topic_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 状态：draft | published | archived
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False, index=True)
    # 生成方式：auto | manual
    generated_by: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)

    __table_args__ = (
        UniqueConstraint("report_date", name="uq_daily_report_date"),
    )


# ── 6. Feed 流（融合 AIHOT） ─────────────────────────────────────────

class FeedItem(TimestampMixin, Base):
    """Feed 流条目：供前端展示的信息流。

    高性能：按 created_at 倒序索引，分页查询直接走索引。
    """

    __tablename__ = "feed_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    # 条目类型：article | hot_topic | daily_report | system
    item_type: Mapped[str] = mapped_column(String(16), default="article", nullable=False, index=True)
    # 关联 ID（asset_id / hot_topic_id / daily_report_id）
    ref_id: Mapped[str] = mapped_column(String(36), default="", nullable=False, index=True)
    # 标题
    title: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    # 摘要
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 来源名称
    source_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # 热度分数（用于排序）
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    # 分类
    category: Mapped[str] = mapped_column(String(32), default="", nullable=False, index=True)
    # 原始 URL
    url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    # 是否置顶
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # upsert 语义的基础：同类型同引用只允许一行（feed_service 按此冲突覆盖更新；
    # 迁移 ab1004w2a 在 DB 侧同建，模型与迁移必须一致）
    __table_args__ = (
        UniqueConstraint("item_type", "ref_id", name="uq_feed_item_type_ref"),
    )


# ── 7. 事件 outbox ────────────────────────────────────────────────────

class PushEvent(TimestampMixin, Base):
    """事件 outbox 表：W2 落库，push_scheduler 轮询消费。

    outbox 模式保证 at-least-once 语义：事件与业务事务同库落库，
    调度器 claim 后标记 consumed_at，崩溃恢复后未消费事件重新投递。
    """

    __tablename__ = "push_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, default="", nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


# ── 8. 站内通知持久化（离线补投底座 R1.2a） ──────────────────

class Notification(TimestampMixin, Base):
    """站内通知落库记录：web provider 离线补投的存储底座。

    现状：providers/push/web.py 走 Redis pub/sub 是 fire-and-forget——用户不在线
    （无 SSE 订阅者）时通知即永久丢失。本表把每条站内通知同时落库，配合待建的
    GET /system/notifications/history（R1.2b）让前端重连时补投离线期间的通知；
    SSE 实时侧不变，本表只做「离线兜底 + 已读回执」。

    收件人锚 = sub（SSO 身份锚点，与 get_current_sub / 主频道 bothot:notifications:{sub} 一致）。
    广播投递（发布侧无 external_user_id → broadcast 频道）落库时 sub="" 且 is_broadcast=True，
    历史查询按 (sub == 当前用户 OR is_broadcast) 过滤即可覆盖定向 + 广播两类。

    高性能：(sub, created_at) 复合索引支撑「按用户取最近 N 条倒序」热查询走索引。
    拓展：channel_type 用 String(32) 不枚举，未来落其他渠道历史零迁移。
    """

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    # 收件人 SSO 锚（users.sub）；广播通知存 ""
    sub: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # 广播标记（True 时对所有人可见，sub 不参与过滤）
    is_broadcast: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 渠道类型快照：web（预留多渠道历史扩展位）
    channel_type: Mapped[str] = mapped_column(String(32), default="web", nullable=False)
    # 以下五字段与 web provider 发布载荷一一对应
    title: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    space_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    doc_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # 已读回执（NULL=未读）
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 历史查询热路：按用户 + 时间倒序（与迁移 ab1005w5a 同建，模型与迁移一致）
    __table_args__ = (
        Index("ix_notifications_sub_created", "sub", "created_at"),
    )
