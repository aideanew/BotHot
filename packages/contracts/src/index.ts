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
 * - 保持骨架：identity / chat / engine（`.gitkeep`，待后端对应模型纳入生成器后接线）
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
export type { Source, SourceSubscription } from "./subscription/dto";
