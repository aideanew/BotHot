"""用户与知识空间域模型。

SSO 铁律（ADR-0002 / 主平台接入指南）：
- 身份锚点 = users.sub（主平台 User.id）；
- 余额/tier 不落库（实时查询主平台）。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, gen_uuid


class User(TimestampMixin, Base):
    """主平台账号快照（sub 唯一锚点）。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    sub: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)
    # SPEC-M3 批次 1（D9=a 终底）：授权主判据；默认最小权限，升权须显式写库
    role: Mapped[str] = mapped_column(String(32), default="user", nullable=False, index=True)


class KnowledgeSpace(TimestampMixin, Base):
    """知识空间：用户的多源知识聚合单元，1:1 映射 LangBot KB（ADR-0001）。"""

    __tablename__ = "knowledge_spaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # R0.5.1（F-4）：可空表示「从未填写」，不设默认值以与「显式清空」区分
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    langbot_kb_uuid: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)
    doc_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # AB-P004 P1：公共库标记 + 引擎位（ADR-0004 双写；与 langbot_kb_uuid 并存）
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    owner_type: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    engine: Mapped[str] = mapped_column(String(32), default="builtin", nullable=False)
    engine_kb_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_space_user_name"),)


class Source(TimestampMixin, Base):
    """信息源（当前仅 wechat_oa 公众号）。"""

    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # wechat_oa | web(M4)
    external_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)  # 公众号 biz
    name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)

    __table_args__ = (UniqueConstraint("type", "external_id", name="uq_source_type_external"),)


class SourceSubscription(TimestampMixin, Base):
    """订阅：整库导入的增量同步生命周期（Manifest Diff 水位）。"""

    __tablename__ = "source_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    space_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_spaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sync_policy: Mapped[str] = mapped_column(String(32), default="auto", nullable=False)
    sync_interval_minutes: Mapped[int] = mapped_column(Integer, default=360, nullable=False)
    # 固定时点锚：每天 HH 点触发（0..23，调度器时区口径）。NULL = 滑动窗口
    # （now + interval × 退避），即历史行为；非 NULL 时调度器按下一次该时点的自然日
    # 对齐排程，空轮询退避按整天往后跳（见 scheduler.next_run_at）。
    sync_anchor_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_empty_syncs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "source_id", "space_id", name="uq_sub_user_source_space"),)


class ArticleManifest(TimestampMixin, Base):
    """发现快照：Redfox 清单行，Diff 同步基准（幂等键 = source_id + external_id）。"""

    __tablename__ = "article_manifests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)  # workUuid
    url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    publish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="DISCOVERED", nullable=False)

    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_manifest_source_external"),)


class ContentAsset(TimestampMixin, Base):
    """内容资产：标准化 Markdown 与元数据（幂等键 = source_id + external_id + content_hash）。"""

    __tablename__ = "content_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)  # article_key
    url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    author: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_type: Mapped[str] = mapped_column(String(16), default="article", nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_uri: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    quality_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="READY", nullable=False)
    # AB-P004 P0：素材复用命中计数——同 (source,external) 命中 READY 资产时 +1（0 微信请求）
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # T3.2.1（C-8/G6）：规则版分类标签（categorizer.categorize 赋值；站内筛选用）
    category: Mapped[str] = mapped_column(String(32), default="", nullable=False, index=True)

    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_asset_source_external"),)


class ShortLinkMap(TimestampMixin, Base):
    """AB-P004 D-04/L-01：短链 key → 长链 article_key 映射（同文两形态二次入库 0 请求）。

    短链直抓一次得长链后落库；后续任一模态入库先查映射，命中即用长链 article_key 锚，
    不重复抓取。"""

    __tablename__ = "short_link_maps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    short_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    article_key: Mapped[str] = mapped_column(String(128), nullable=False)
    biz: Mapped[str] = mapped_column(String(128), default="", nullable=False)

    __table_args__ = (UniqueConstraint("short_key", name="uq_shortlink_key"),)


class KnowledgeDocument(TimestampMixin, Base):
    """资产 → 知识空间（LangBot KB）的入库映射与状态机：FETCHED → INDEXED → READY。"""

    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    space_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_spaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    langbot_file_id: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    # R4.4（F-11）：该 doc 入库时对应的资产内容指纹。跨空间 stale 判定按此指纹而非按
    # 空间归属——资产全局共享，号主改文后指纹与资产当前 hash 不符的 doc 即过期（含他人空间）。
    content_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="FETCHED", nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # AB-P004 P1：入库来源（copy=批量引入公共库/单篇默认；link 预留 M4 引用扇出，不启用）
    source: Mapped[str] = mapped_column(String(16), default="copy", nullable=False)

    __table_args__ = (UniqueConstraint("asset_id", "space_id", name="uq_doc_asset_space"),)


class Job(TimestampMixin, Base):
    """任务状态机：QUEUED → RUNNING → SUCCEEDED/PARTIAL_SUCCESS/FAILED；QUEUED → CANCELLED（ADR：不依赖队列存活）。"""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payload: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED", nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    result: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    worker_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobItem(TimestampMixin, Base):
    """整库导入的单篇子任务（支撑 PARTIAL_SUCCESS 与失败重试）。"""

    __tablename__ = "job_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class BotBinding(TimestampMixin, Base):
    """M2：用户 ↔ 机器人通道（clawbot 微信等）的绑定关系。

    ⚠️ F-8 死表（R6.6.9 裁定：保留+如实登记）：全仓仅本文件 + models/__init__.py
    两处导出引用 + 初始迁移 05a5a856c37b，零 service/repo/router/test 消费者。
    消费方待 SPEC-T6.1 微信 Bot 接线时建立；新增通道值零迁移（channel 已 String(32)、
    uq_binding_channel_external 已按 channel 分域建键）。
    """

    __tablename__ = "bot_bindings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)  # clawbot | web
    external_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("channel", "external_user_id", name="uq_binding_channel_external"),)


class EngineKeyRegistration(TimestampMixin, Base):
    """SPEC-M3 批次 3 / T5.4：引擎 API Key 登记（operator 可登记，替代「找管理员改 env」）。

    密文落库、零明文（core.engine_keyring AES-256-GCM，AAD 绑定 engine）；优先级
    登记表 > env，生效来源由 resolve_engine_key().source 显式回报，登记覆盖 env 不静默。
    真实引擎实接仍锁 D10（ENGINE_IMPLEMENTED 全 False 时登记表只影响状态上报）。
    """

    __tablename__ = "engine_key_registrations"

    # 自然键：一引擎位一登记行（轮换走 key_id 换值，不并排多版本）
    engine: Mapped[str] = mapped_column(String(32), primary_key=True)
    # Text 而非 VARCHAR：密文长度随明文线性增长，长度上限会造出静默截断/写入失败路径
    secret_ref: Mapped[str] = mapped_column(Text, nullable=False)  # b64(nonce).b64(ct+tag)
    key_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)  # 轮换/审计句柄
    registered_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


class ProcessHeartbeat(Base):
    """R7.7 常驻进程心跳：scheduler / worker 各自一行，进程键即主键。

    不继承 `TimestampMixin`——本表的行时间戳就是 `last_heartbeat_at` 本身，
    再加一个 `updated_at` 会造出一个只在插入时被写、之后永远停滞的假字段。
    消费方是 `GET /api/v1/admin/ops/liveness` 与容器 `healthcheck`（见
    `services/process_heartbeat.py` 模块文档的根因记录）：后台健康 ≠ 采集在跑。
    """

    __tablename__ = "process_heartbeats"

    process_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa_text("now()"), nullable=False
    )
    # 最近一次回报时携带的上下文（如本轮处理条数）；空串 = 无附加信息，避免 null 语义歧义
    last_detail: Mapped[str] = mapped_column(String(512), server_default=sa_text("''"), nullable=False)
