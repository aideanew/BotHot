/**
 * `@bothot/contracts` —— BotHot 前后端共享契约包（**纯类型**）。
 *
 * 纪律：
 * 1. 零运行时依赖、零副作用：本包**只导出类型**，`tsc` 配置为 `emitDeclarationOnly`，
 *    产物仅 `dist/*.d.ts`（见 `tsconfig.json`）。因此消费侧必须用 `import type`。
 * 2. **每个类型都在其源文件里标注了“单一来源”**（后端/前端的具体 `文件:行号`）。
 *    新增类型前先确认后端形状，**禁止按想象定义**（本仓库最大的病史是文档/契约虚报）。
 * 3. 行号锚点取自**提交态**（`git show HEAD:<path>`）。上游文件被改动后行号会漂移，
 *    校准方式见 README「维护契约」。
 *
 * 当前已冻结（W5）：
 * - 通用：分页 `PageResult<T>` / 响应信封 `ApiResponse<T>` / 错误码 `ApiErrorCode`
 *
 * 域 DTO（S3.4 接线，2026-10-08 起 index.ts 导出）：
 * - 已导出：bot / hot / ingest / knowledge / push_event / subscription（6 域，模型内省生成）
 * - 保持骨架：chat（`.gitkeep`）。identity 已在 STEP-66 出实体镜像 `identity/dto.ts`（`User`）；
 *   chat 仍缺不是"忘了接"，而是它的载荷是 SSE 聚合形、没有任何端点把它当信封 `data` 整体吐出，
 *   而孤儿守卫不收「无真端点反向核」的 def（实测红字见 `EVD-V23-66/s66_chat_defs_orphan_red.txt`）
 *   ⇒ 口径问题交回台账 P-144，不由本包自行放宽。
 *
 * API 响应形状（STEP-46 起，D-V21-01，解 P-82）：从 `app/contracts/<域>.py` → schema → TS
 * 一条链派生，**是**线上 `data` 形状，可直接用于 `satisfies`：
 * - 已导出：engine（EngineList / EngineCapability / EngineReason / SpaceEngineBinding）
 * - 已导出：shapes（STEP-47：mock 表其余 20 条路由的 data 形状，路由→契约名见 app/contracts/shapes.py 的 MOCK_ROUTE_CONTRACTS）
 *
 * ⚠️ 口径限定（重要）：域 dto 是**持久层实体镜像**（SQLAlchemy 列内省），
 * 不是 API 响应形状——序列化器会隐藏字段（如 BotChannel 的 `secret_enc` →
 * `has_secret`，bots.py:134 `_serialize_log` 只输出 8 字段且 `created_at` 可空）。
 * 前端消费线上形状时以序列化器为准；实体镜像用于「确认后端真实列形状」的
 * 单一来源（见下条纪律）。响应形状 DTO 的生成器扩展已登记 backlog。
 */
export type { PageQuery, PageResult } from "./common/pagination";
export type { ApiFailure, ApiResponse, ApiSuccess, Envelope } from "./common/response";
export type {
  ApiErrorCode,
  ApiErrorHttpStatus,
  ApiErrorName,
  AuthErrorCode,
} from "./common/errors";

// ── bot 域（实体 + 请求模型）──
export type {
  BotChannel,
  PushTask,
  PushLog,
  ChannelCreateRequest,
  ChannelUpdateRequest,
  PushTaskCreateRequest,
  PushTaskUpdateRequest,
} from "./bot/dto";

// ── hot 域 ──
export type { HotTopic, HotTopicArticle, DailyReport, FeedItem } from "./hot/dto";

// ── ingest 域 ──
export type { Job, JobItem } from "./ingest/dto";

// ── knowledge 域 ──
export type { KnowledgeSpace } from "./knowledge/dto";

// ── push_event 域 ──
export type { PushEvent } from "./push_event/dto";

// ── subscription 域 ──
export type { Source, SourceSubscription, SourceIdentifier } from "./subscription/dto";

// ── engine 域（API 响应形状，契约模块派生，STEP-46）──
export type { EngineCapability, EngineList, EngineReason, SpaceEngineBinding } from "./engine/dto";

// ── shapes 域（其余 mock 域的 API 响应形状，契约模块派生，STEP-47）──
export type {
  BatchDocFailure,
  DocCategoryList,
  DocCategoryPatch,
  DocDeleteResult,
  DocIngestState,
  DocIngestStatus,
  DocsBatchDeleteResult,
  DocsRecategorizeResult,
  ExtractedArticleView,
  ExtractedImageView,
  IngestAccepted,
  LinkResult,
  LogoutResult,
  MeUser,
  MeView,
  MeWallet,
  NotificationHistoryPage,
  NotificationItem,
  NotificationReadResult,
  PublicSpacePage,
  PublicSpaceView,
  ResolvedArticleView,
  SpaceDeleteResult,
  SpaceDetail,
  SpaceDocItem,
  SpaceDocPage,
  SpaceDocStatus,
  SpacePage,
  SpaceStats,
  SpaceView,
} from "./shapes/dto";

// ── ux 域（STEP-64 方案 B）──
// `UxState` 来自手写的 `src/ux/states.ts`，**不是** `app/contracts/ux.py` 的生成物：
// 域一旦进生成器就会被逐 def 比对器要求与冻结稿对齐，而冻结稿带比对器不认识的 `note` 关键词
// （两侧都不许改）⇒ 依卡面第 13 格 ① 转 B。八值与冻结稿逐值同序，由
// `apps/api/tests/test_ux_states_contract.py` 钉住。
export type { UxState } from "./ux/states";
export type { UxViewStates } from "./ux/states";

// ── identity 域（STEP-66，P-82 余项 / U6）──
// **两类产物要分清**（这是 identity↔shapes 的分工，也是本行注释存在的理由）：
// - `identity/dto.ts` 的 `User` 是**持久层实体镜像**（SQLAlchemy 内省 `app/models/entities.py`），
//   用来看"库里的 users 行长什么样"，不是任何一个端点的响应形；
// - 线上 `GET /auth/me` 的 `data` 形状在 **shapes** 域（`MeView` / `MeUser` / `MeWallet`），
//   前端要"这个端点吐什么"时读那一侧，不要把 `User` 当响应形用。
export type { User } from "./identity/dto";
