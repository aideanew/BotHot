"""应用配置：环境变量唯一入口（密钥不入库不入码）。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "BotHot"

    # 数据库
    database_url: str = "postgresql+psycopg://bothot:bothot@localhost:5432/bothot"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Aidean 主平台（SSO IdP / 钱包）
    # 双 base_url（管理者裁决 B，2026-09-11）：aidean_public_url 签发给宿主浏览器（须浏览器
    # 可达，如 http://localhost:3000）；aidean_issuer 供容器内 token/userinfo/wallet 直连
    # （须容器可达宿主，如 host.docker.internal）。空串 = 未配置，回落 aidean_issuer
    # （单值语义，生产与既有部署零变更）。
    aidean_issuer: str = "http://localhost:3000"
    aidean_public_url: str = ""
    oidc_client_id: str = "wechat-rag"
    oidc_client_secret: str = "change-me"
    # 授权回调：必须与主平台 oidc_clients 白名单精确匹配（协议+域名+端口+路径）
    oidc_redirect_uri: str = "https://wechat-rag.aidean.local/auth/aidean/callback"
    oidc_scopes: str = "openid profile wallet:read"
    # state 单次消费有效期（秒）：覆盖用户在主平台登录页停留时间
    oidc_state_ttl_seconds: int = 600
    # R5.1.1：userinfo iss/aud 期望值（空 = 跳过校验，向后兼容；主平台 userinfo 若未返回这些字段则自动跳过）
    oidc_issuer_expected: str = ""
    oidc_audience_expected: str = ""
    # R9 back-channel logout：logout_token 的 |now - iat| 有界窗（秒）。
    # 主平台签发的 logout_token **不含 exp/nbf**（backchannel.ts:30-40），RP 必须自建时间窗，
    # 否则该 token 可无限重放（只能删会话，但足以反复摧毁受害者会话，构成可用 DoS 向量）。
    # 取 300 与主平台 JWKS 的 `cache-control: max-age=300` 对齐。
    # 注意 abs() 同时容忍双向时钟偏移，故窗口两侧各宽 300s。
    oidc_logout_token_max_age_seconds: int = 300

    # 服务端会话（HttpOnly cookie 承载不透明 session_id，令牌只存服务端）
    session_cookie_name: str = "bothot_session"
    session_ttl_seconds: int = 7 * 24 * 3600
    session_cookie_secure: bool = False  # 生产 HTTPS 环境置 true（compose 注入）
    # 会话/state 存储后端（A 裁决 2026-09-07）：memory|redis；M1 开发期默认 memory，
    # M2 发布前切 redis 实测（redis_url 复用下方 Redis 段）
    session_store_backend: str = "memory"

    # LangBot（机器人运行时 / RAG 引擎）
    langbot_base_url: str = "http://localhost:5300"
    langbot_api_key: str = ""
    # 管理员登录（lbk_ API Key 创建端点 400 未解，M0 §四遗留——M1 用 JWT；
    # 凭据经 compose env 注入，不入库不入码）
    langbot_admin_username: str = "admin@bothot.local"
    langbot_admin_password: str = ""
    # ingest 轮询上限（秒）：超时 → 30003 INGEST_FAILED（防挂死）
    langbot_ingest_timeout_seconds: int = 120

    # 嵌入服务（OpenAI 兼容协议；LangBot 建库需注册 embedding 模型，见 M0 报告 §四）
    # 默认值与 docker/compose.yml 的 ${EMBEDDING_*} 兜底保持一致
    embedding_api_base: str = "https://api.siliconflow.cn/v1"
    embedding_api_key: str = ""
    embedding_model: str = "BAAI/bge-m3"

    # 生成 LLM（B-T10R 方案 A：OpenAI 兼容直连流式通道，A 批复 2026-09-08；
    # Key 只走 env 不入码；模型默认 A 裁决，实测不可用时报备替换）
    llm_api_base: str = "https://api.siliconflow.cn/v1"
    llm_api_key: str = ""
    llm_model: str = "Qwen/Qwen2.5-7B-Instruct"

    # 阶段 3.2 检索重排（可选增强；base/key 留空回落 embedding_* 同供应商口径）
    rerank_enabled: bool = True
    rerank_api_base: str = ""
    rerank_api_key: str = ""
    rerank_model: str = "BAAI/bge-reranker-v2-m3"

    # Redfox（公众号 Discovery Provider）
    redfox_base_url: str = "https://redfox.hk"
    redfox_api_key: str = ""

    # ── 文章来源平台（providers/article_sources/）──────────────────
    # 4 个第三方 API 平台作为文章发现 + 详情兜底渠道（ADR-0008）。
    # 未配置 key 的平台自动跳过注册，不影响启动。
    # Dajiala 极致了（发现 + HTML 详情兜底）
    dajiala_base_url: str = "https://www.dajiala.com/fbmain/monitor/v3"
    dajiala_api_key: str = ""
    # JustOneAPI（历史文章发现 + 带正文详情兜底）
    justoneapi_base_url: str = "https://api.justoneapi.com"
    justoneapi_api_key: str = ""
    # TikHub（发现 + 搜索，需付费余额）
    tikhub_base_url: str = "https://api.tikhub.io"
    tikhub_api_key: str = ""
    # Wellbyte 数井（关键词搜索 + URL 驱动的文章发现）
    wellbyte_base_url: str = "https://api.wellbyte.net"
    wellbyte_api_key: str = ""
    # 详情兜底总开关：直抓失败时是否尝试付费详情 API（默认关，按需开）
    article_detail_fallback_enabled: bool = False

    # AB-P004 P4 引擎可插拔（ADR-0004 §五：全走 env 占位，.env 写真实值，代码零明文）
    kb_default_engine: str = "builtin"  # 默认引擎位
    # R1 修复：默认仅 builtin；main 待 Ragflow 实接+Key 轮换后显式开，SaaS 按 Key 到位逐个开
    kb_engine_allowlist: str = "builtin"
    coze_api_key: str = ""
    dify_api_key: str = ""
    fastgpt_api_key: str = ""
    main_kb_api_base: str = ""
    main_kb_api_key: str = ""

    # W1：渠道密钥 AES-256-GCM 落库加密主密钥。
    # 32 字节原始密钥的 base64（44 字符）。空串 = 未配置 → 加解密操作 50002 拒绝，
    # **绝不回落明文**。与 engine_key_master_key 同纪律。
    push_secret_master_key: str = ""

    # SPEC-M3 批次 3 / T5.4：engine_key_registrations 的 AES-256-GCM 落库加密主密钥。
    # 32 字节原始密钥的 base64（44 字符）。空串 = 未配置 → 登记/轮换操作 50002 拒绝，
    # **绝不回落明文**（回落等于把加密伪装成已生效，比明文更难发现）。
    # 轮换：改本值后存量密文不可解——先导出/重录，不静默降级。
    engine_key_master_key: str = ""

    # 公共库发布双闸之一（T1.4.1，D9=c 过渡裁决 2026-09-22）：逗号分隔的本地 user_id
    # （users.id）白名单；空串 = 无人可发布。双闸之二在服务层：目标空间须 owner_type=system。
    # SPEC-M3 批次 3 双闸收敛（2026-09-23 裁「按角色分通道」）：本字段语义**不变**——
    # 仍是发布闸①，不进 require_role。role 升权走 users.role 显式写库。
    public_admin_allowlist: str = ""

    # BE-02 资产原文存储：raw_uri 后端（url 透传默认 / local 本地卷），不强上 S3
    raw_store_backend: str = "url"
    raw_store_dir: str = ""  # local 后端落盘目录；空则回落 backend/data/raw

    # T2.3 Job 执行器（整号采集消费端）：逐篇限速 + 失败退避 + 崩溃自愈窗口
    job_worker_item_interval_seconds: float = 2.0  # 逐篇间隔（per-source 串行=并发 1）
    job_worker_max_retries: int = 3  # 单篇最大重试次数（超限 → FAILED → 进 PARTIAL 分母）
    job_worker_stale_seconds: int = 300  # RUNNING 心跳超时阈值（超时 → 自愈回退 QUEUED）
    job_worker_idle_sleep_seconds: float = 5.0  # 无活空转间隔

    # T2.4 增量调度器（整号采集触发端）：next_run_at 驱动 + consecutiveEmpty 退避
    scheduler_max_backoff_multiplier: int = 8  # 空轮询退避上限倍数（2^n 截断；首次空即 2×）
    scheduler_batch_limit: int = 100  # 单轮最多处理的到期订阅数（防单轮长尾）
    scheduler_idle_sleep_seconds: float = 10.0  # 无到期订阅时的空转间隔
    # 到期订阅的并发执行度：多号同时到期时并行同步（claim_due 用 FOR UPDATE SKIP LOCKED，
    # 并发认领不会重复取同一条）。1 = 历史串行行为。
    scheduler_concurrency: int = 4
    # 固定时点锚的时区口径（sync_anchor_hour 按此时区解读；10 = 每天 10:00）。
    scheduler_timezone: str = "Asia/Shanghai"
    # 新建订阅的默认固定时点锚（0-23，按 scheduler_timezone 解读）。
    # 显式锚定的订阅恒为「每天一次」；而 `sync_anchor_hour=None` 是每 360 分钟滑动窗口
    # ——一天 4 次，RedFox 清单调用量是每日一次的 3.2 倍。故新建订阅默认自动锚定，
    # 而不是默认滑动。设为 None 关闭自动锚定，回退历史滑动行为。
    # 取 12 的依据：R8 活体实测（2026-09-28 14:00 Asia/Shanghai）广域库清单最新一篇
    # 距今 30.3 小时、当日零篇——上游入库本身滞后真实发布数小时至一天以上，12:00 比
    # 10:00 多留 2 小时余量以覆盖上午发布的号。前端表单的建议值须与本项保持一致。
    default_sync_anchor_hour: int | None = 12

    # T2.2 Manifest 同步（清单发现落库）：单源单轮最大翻页数（防上游异常时无限翻页）
    manifest_sync_max_pages: int = 20

    # R7.6 发现渠道（后台配置）：逗号分隔的启用白名单。空串 = 不过滤（所有已注册渠道
    # 参与选择），此时行为与渠道硬编码时代逐字一致。渠道就绪度可查
    # GET /api/v1/admin/discovery/channels（implemented / enabled / available 三者分离回报）
    discovery_channels: str = ""
    # 默认渠道名（须为已注册渠道名）：在可用集内即取之，否则回落注册序首个可用渠道。
    # 「只配置了 redfox、没配其他」时 redfox 即唯一且默认的渠道。
    discovery_default_channel: str = "redfox"

    # T2.6 批量粘贴 Job 化：单次批量提交上限（同步阶段零抓取，逐篇交 JobWorker 消费）
    batch_ingest_max_urls: int = 50

    # R0.2.5 批量文档操作（:delete / :recategorize）：单次批量条数上限
    batch_docs_max_ids: int = 50


    def production_guard_violations(self) -> list[str]:
        """生产配置守卫：返回致命项描述列表（空 = 通过）。

        只在 `app_env == "production"` 时生效——开发期的占位值（`change-me` / `memory` /
        非 secure cookie）是设计内默认，拿生产红线去卡本地开发会让本地直接起不来。
        返回描述而非直接抛错：调用方决定在何处 fail fast，也让守卫结果可被断言。
        """
        if self.app_env.strip().lower() != "production":
            return []
        bad: list[str] = []
        if not self.oidc_client_secret or self.oidc_client_secret == "change-me":
            bad.append("OIDC_CLIENT_SECRET 仍是占位值（主平台 SSO 密钥未配置）")
        if not self.session_cookie_secure:
            bad.append("SESSION_COOKIE_SECURE=False（会话 cookie 会以明文传输）")
        if self.session_store_backend == "memory":
            bad.append("SESSION_STORE_BACKEND=memory（会话无法跨实例与重启存活）")
        if not self.oidc_issuer_expected:
            bad.append("OIDC_ISSUER_EXPECTED 未配置（生产环境须校验 userinfo iss 声明）")
        if not self.oidc_audience_expected:
            bad.append("OIDC_AUDIENCE_EXPECTED 未配置（生产环境须校验 userinfo aud 声明）")
        return bad


def assert_production_ready(settings: Settings) -> None:
    """启动期配置守卫：生产配置不合格即拒启（fail fast，错误显式可见）。

    三进程（Web / scheduler / worker）共用，任一处配错都不该带着病上线。
    """
    violations = settings.production_guard_violations()
    if violations:
        raise RuntimeError("生产配置守卫未通过: " + "; ".join(violations))


@lru_cache
def get_settings() -> Settings:
    return Settings()
