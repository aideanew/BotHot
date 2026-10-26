/**
 * lib/api/types —— 契约类型单一出处（T1.2.5 分域拆分）
 *
 * 与 .docs/03_solution/interfaces/API接口文档.md 一一对应；只放**类型 + 纯归一化函数**，零副作用、零网络。
 * 原 lib/api.ts 的「类型定义（契约一一对应）」段原样迁入，公开符号零变更。
 */

import type { Envelope } from "@bothot/contracts";
import type * as Shapes from "@bothot/contracts";

export type { Envelope };

/**
 * GET /api/v1/auth/me → data（C-T7 真实态适配）。
 * 真实后端载荷为嵌套形态：{ user: {sub,email,nickname,tier,role}, wallet: {balanceYuan,...,currency} }；
 * mock/旧契约为扁平形态：{ sub,email,nickname,tier, wallet: "¥128.50" }。
 * 对外统一归一化为 MeData（wallet 已格式化为展示字符串），调用方零适配。
 */
export interface MeData {
  sub: string;
  email: string;
  nickname: string;
  tier: string;
  /** 归一化后的余额展示串（如 "¥0.00"） */
  wallet: string;
  /**
   * SPEC-M3 批次 2：是否具备 admin 秩（后端本地 users.role 判定的同源回显）。
   * 这是 admin 面的唯一门禁依据——真实载荷里的 `user.role` 是**主平台** userinfo
   * 的大写枚举（如 "USER"），与本地授权阶梯（user/operator/admin）不同源不同形，
   * 拿它门禁会与后端 10004 双向分歧。字段名保持 wire 形态 `is_admin`。
   */
  is_admin: boolean;
  /**
   * 主平台 userinfo/wallet 不可达、后端已用本地 users 行降级回填资料。
   * 会话本身有效（其余域接口不受影响）——UI 据此提示「余额暂不可查」，
   * 而非渲染成 ¥0.00 让用户误以为余额清零。
   */
  providerUnreachable: boolean;
}

/**
 * 真实 /me 的钱包对象（B-T5 契约：金额为字符串保留两位）。
 * STEP-52：改为契约别名——形状唯一来源是 `app/contracts/shapes.py` 的 `MeWallet`，
 * 本地不再留一份可漂移的手写副本。
 * 降级语义仍然读这一条：`available === false` 时不得渲染成 ¥0.00（旧后端不返回，故可选）。
 */
export type MeWalletInfo = Shapes.MeWallet;

/** 布尔归一化：wire 上是真布尔，兼容 "true"/"1" 等历史形态。缺失一律 false（fail closed）。 */
function isTrue(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") return value === "true" || value === "1";
  if (typeof value === "number") return value === 1;
  return false;
}

/**
 * 归一化 /auth/me 载荷：兼容嵌套（真实）与扁平（mock/旧）两种形态。
 * 字段缺失时回空串，wallet 无法解析时回 "—"，杜绝渲染期崩溃。
 */
export function normalizeMeData(
  raw: Record<string, unknown> | null | undefined
): MeData {
  const obj = (raw ?? {}) as Record<string, unknown>;
  // 真实形态取 data.user；扁平形态直接取自身
  const user = (obj.user ?? obj) as Record<string, unknown>;
  const w = obj.wallet as string | MeWalletInfo | undefined;
  // 降级态：主平台 userinfo/wallet 不可达，后端已用本地 users 行回填资料。
  // 此时 wallet 不可查，须展示「余额暂不可查」而非 ¥0.00。
  const providerUnreachable = isTrue(obj.providerUnreachable);
  let wallet = "—";
  if (providerUnreachable || (w && typeof w === "object" && w.available === false)) {
    wallet = "余额暂不可查";
  } else if (typeof w === "string") {
    wallet = w;
  } else if (w && typeof w === "object") {
    const cur =
      w.currency === "CNY" ? "¥" : w.currency ? `${w.currency} ` : "";
    wallet = `${cur}${Number(w.balanceYuan ?? 0).toFixed(2)}`;
  }
  return {
    sub: String(user.sub ?? ""),
    email: String(user.email ?? ""),
    nickname: String(user.nickname ?? ""),
    tier: String(user.tier ?? ""),
    wallet,
    is_admin: isTrue(user.is_admin),
    providerUnreachable,
  };
}

/**
 * GET/POST /api/v1/spaces → data.items（B-T4 契约 v0.2：camelCase）。
 * STEP-52 收紧：`engine`/`engineKbId`/`isPublic` 线上恒有 ⇒ 改为契约别名后不再可选。
 * 留可选的代价不是"少写三个键"，是 mock 样例可以整片不写它们，
 * 于是"引擎位漂移"这类形状差在演示态永远看不见（P-122 盘出的第七处即此族）。
 */
export type Space = Shapes.SpaceView;

/**
 * GET /api/v1/admin/spaces → data.items（SPEC-M3 批次 2 读面）。
 * 与 Space 同形，增量三字段表示归属账号；owner 三字段可能整体缺失
 * （后端 users 行缺失的孤儿空间），按空串回落而非渲染 undefined。
 */
export interface AdminSpace extends Space {
  ownerId: string;
  ownerSub: string;
  ownerNickname: string;
}

/**
 * GET /api/v1/spaces/{id} → data（详情含统计）。
 * `stats.chunks` 为 null 表示「该指标不可得」（数据源未接线），不是 0。
 * 展示侧须隐藏该指标，不得渲成「0 个知识分块」——那会把指标缺失谎报成空数据。
 */
export type SpaceDetail = Shapes.SpaceDetail;

/** 文档状态：pending 采集中 | ready 可用 | failed 失败（契约 `SpaceDocStatus`） */
export type DocStatus = Shapes.SpaceDocStatus;

/**
 * GET /api/v1/spaces/{id}/docs → data.items。
 * STEP-52：`category` 线上恒有（空串 = 未分类），改为契约别名后不再可选（P-122）。
 */
export type SpaceDoc = Shapes.SpaceDocItem;

/** R0.2.1：DELETE /spaces/{id}/docs/{docId} → data（assets=被连带清理的孤儿资产数） */
export type DeleteDocResult = Shapes.DocDeleteResult;

/** M3 批次 2：PATCH /api/v1/admin/spaces/{id} → data（description 为空串 = 清空简介） */
export interface PatchAdminSpaceResult {
  ok: boolean;
  id: string;
  description: string;
}

/** R0.2.2：PATCH /spaces/{id}/docs/{docId} → data（空串回默认口径「其他」） */
export type PatchDocResult = Shapes.DocCategoryPatch;

/**
 * R0.2.6：单次批量请求的 ids **业务**上限（后端 `batch_docs_max_ids` = 50）。
 * pydantic 层另有 1..500 的体量硬闸，超出业务上限走 10005/422，故前端须先切片。
 */
export const BATCH_DOCS_MAX_IDS = 50;

/** R0.2.6：批量删除的篇级失败明细（后端 `_failure_entry`；非 AppError 回落 50001） */
export type BatchDocFailure = Shapes.BatchDocFailure;

/**
 * R0.2.6：POST /spaces/{id}/docs:delete → data（**篇级部分成功**）。
 * failed 为空即全成功；已生效篇立即落库，失败篇的 PG 行完整保留、可原样重试。
 */
export type DeleteDocsBatchResult = Shapes.DocsBatchDeleteResult;

/** R0.2.6：POST /spaces/{id}/docs:recategorize → data（**整批原子**，无中间态） */
export type RecategorizeDocsBatchResult = Shapes.DocsRecategorizeResult;

/**
 * 篇级失败的可展示文案。后端 `failed[].error` 只回错误码登记表标签，此处登记
 * **逐篇路径**可达的码位（30004/10005 在引擎调用前整体拒绝，走错误信封不进此表）。
 * 未收录码走调用方回落，避免把英文标签直接展示给用户。
 */
export const BATCH_FAILURE_MESSAGES: Record<number, string> = {
  30002: "该篇未能处理：引擎服务异常",
  30003: "该篇未能处理：入库链路异常",
  50001: "该篇未能处理：服务端异常",
  50002: "该篇未能处理：依赖服务暂不可用",
};

/** 规则版分类词表（与后端 `categorizer.CATEGORIES` 同序；空串 = 清空人工标签） */
export const CATEGORIES: readonly string[] = [
  "AI·技术",
  "产品·商业",
  "行业·动态",
  "观点·评论",
  "教程·实践",
  "其他",
] as const;

/**
 * 分类过滤哨兵（与后端 `categorizer.UNCATEGORIZED` 同值）：契约层表达「未分类」
 * （资产无分类标签；库里存空串、不存哨兵值）。
 * 只出现在查询入参与 `:categories` 出参；列表响应的 category 保持空串，不回填哨兵。
 */
export const UNCATEGORIZED = "__uncategorized__" as const;

/**
 * GET /api/v1/spaces/{id}/docs → data（T1.5.7 分页 + R0.1.1 分类过滤）。
 * `total` 与 `items` 同谓词（过滤后总数，分页窗口不虚高）。
 */
export type SpaceDocsPage = Shapes.SpaceDocPage;

/** listSpaceDocs 入参（limit 上限 200 由后端校验；默认 100/0） */
export interface ListSpaceDocsOptions {
  limit?: number;
  offset?: number;
  /** 省略或空串 = 全部；`UNCATEGORIZED` = 未分类；其余按精确匹配 */
  category?: string;
}

// ---------- AB-P004 P1 公共库（v0.4b，契约 §六 v0.5 草案） ----------

/** GET /api/v1/spaces/public → data.items（公共库卡） */
export type PublicSpace = Shapes.PublicSpaceView;

/** POST /api/v1/spaces/{id}/links → data（批量 copy 结果） */
export type LinkResult = Shapes.LinkResult;

// ---------- AB-P004 P2 整号订阅（v0.5 契约） ----------

/** POST /api/v1/sources → data */
export interface RegisterSourceResult {
  sourceId: string;
  biz: string;
  name: string;
  url: string;
}

/** POST /api/v1/spaces/{id}/subscriptions → data */
export interface SubscribeResult {
  subscriptionId: string;
  jobIds: string[];
  created: boolean;
}

/** GET /api/v1/spaces/{id}/subscriptions → data.items */
export interface SubscriptionItem {
  subscriptionId: string;
  sourceId: string;
  biz: string;
  sourceName: string;
  syncPolicy: string;
  /** R0.2.3：同步间隔（分钟）；5~4320 */
  syncIntervalMinutes?: number;
  /** 固定时点锚（每天 HH 点触发，0~23，北京时间）；null/缺省 = 按间隔滑动 */
  syncAnchorHour?: number | null;
  nextRunAt: string;
  status: string;
  /** 最近一次同步任务 id（无则空串） */
  latestJobId?: string;
  /** T1.4.4（N11）：上次成功同步时间（worker 未建成前为空串，诚实缺口） */
  lastSuccessAt?: string;
  /** T1.4.4（N11）：连续空轮询次数（退避展示用） */
  consecutiveEmptySyncs?: number;
  /** T1.4.3（N11）：该源 DISCOVERED 清单计数 = U6「预计篇数」 */
  discoveredCount?: number;
}

/** 单篇失败明细（GET /api/v1/jobs/{id}.data.failedItems[]） */
export interface JobFailedItem {
  itemId: string;
  /** 原文链接；空串表示入库时未取到 */
  url: string;
  /** 后端格式 `原因标识: 中文说明`，用 `jobErrorText` 取后半段展示 */
  error: string;
  /** 已重试次数（0 = 尚未重试过） */
  retryCount: number;
}

/** GET /api/v1/jobs/{id} → data */
export interface JobView {
  jobId: string;
  type: string;
  status: string;
  progress: number;
  error: string;
  counts: {
    total: number;
    succeeded: number;
    failed: number;
    pending: number;
  };
  /** 失败篇目明细；无失败项时为空数组。
   *
   * 可选：当前后端恒返该字段，但前后端镜像可能不同步（已实际发生过），
   * 缺字段时按「无明细」降级而非抛错——用 `?? []` 消费。
   */
  failedItems?: JobFailedItem[];
  createdAt: string;
}

/** POST /api/v1/jobs/{id}/retry → data */
export interface RetryResult {
  jobId: string;
  retried: number;
  status: string;
}

/** GET /api/v1/jobs → data.items[]（R0.4.1 清单条目）
 *
 * 刻意**不含 counts**：JobItem 计数要按 Job 逐条查（N+1），单篇钻取走 `GET /jobs/{id}`。
 * 改带 `workerHeartbeatAt` + `updatedAt`——STALL 判定的两个输入。
 */
export interface JobListItem {
  jobId: string;
  type: string;
  status: string;
  progress: number;
  error: string;
  /** 空串 = 从未被 worker 认领 */
  workerHeartbeatAt: string;
  createdAt: string;
  updatedAt: string;
}

/** GET /api/v1/jobs → data（`total` 与 `items` 同谓词，过滤后不虚高） */
export interface JobsPage {
  items: JobListItem[];
  total: number;
  limit: number;
  offset: number;
}

/** listJobs 入参（`type`/`status` 省略或空串 = 不过滤；limit 上限 100 由后端校验） */
export interface ListJobsOptions {
  limit?: number;
  offset?: number;
  type?: string;
  status?: string;
}

/** R0.2.3：PATCH 订阅 / DELETE 退订 → data（视图与列表 items 同口径，退订多 `cancelled`） */
export interface SubscriptionView {
  subscriptionId: string;
  syncPolicy: string;
  syncIntervalMinutes: number;
  /** 固定时点锚（每天 HH 点）；null = 按间隔滑动 */
  syncAnchorHour?: number | null;
  nextRunAt: string;
  status: string;
  /** 仅退订响应携带：本次是否真的由 ACTIVE 转为 CANCELLED */
  cancelled?: boolean;
}

/** R0.2.3：PATCH 订阅请求体（部分更新，省略 = 不改；sync_anchor_hour 显式传 null = 清除锚定） */
export interface UpdateSubscriptionPayload {
  sync_policy?: string;
  sync_interval_minutes?: number;
  sync_anchor_hour?: number | null;
}

// ---------- 问答域（C-T4，契约 v0.3+） ----------

/** 回答中附带的来源文章引用 */
export interface ChatCitation {
  title: string;
  spaceName: string;
  /** ADR-0004 P4：引擎位 */
  engine?: string;
}

/** POST /api/v1/chat/ask 完成后的回答载荷（流式分片拼接后的最终形态） */
export interface ChatAnswer {
  content: string;
  citations: ChatCitation[];
  /** v0.4 流中 error 帧：已发 delta 保留展示，错误以气泡叠加（不抛错） */
  error?: { code: number; message: string };
}

// ---------- 链接解析入库域（C-T7，契约 v0.3d/e/f） ----------

/** POST /api/v1/resolve → data（解析预览；content 为轻量行式文本） */
export type ResolvedArticle = Shapes.ResolvedArticleView;

/** extract 响应中的图片项（fmt 为内部字段不进前端契约视图） */
export type ExtractedImage = Shapes.ExtractedImageView;

/** POST /api/v1/extract → data（含 v0.3f 质量分） */
export type ExtractedArticle = Shapes.ExtractedArticleView;

/** 业务错误：code 来自契约错误码段位，msg 为可直接展示的中文文案 */
export class ApiError extends Error {
  code: number;
  requestId: string;

  constructor(code: number, message: string, requestId = "") {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.requestId = requestId;
  }
}

/**
 * 错误码 → 可展示中文文案（STEP-15b 起住在这里，不再住 `http.ts`）。
 *
 * 搬动的原因只有一个：`mock-routes.ts` 的分发器要按真后端同码同文抛错（10001/10004/10006…），
 * 而它不能 import `http.ts`——`http.ts` 已经在 import 它，那是一条模块环。
 * 文案表留在 http 里就等于逼分发器**另抄一份字符串**，那才是真正会被拒绝的那件事：
 * 同一个码在两处各有文案，改一处另一处静默不同源（本仓的 P-28 那一族）。
 * `http.ts` 继续转出这两个符号，既有 import 面零变更。
 */
export const ERROR_MESSAGES: Record<number, string> = {
  10001: "尚未登录或会话已过期",
  10002: "登录状态校验失败，请重新登录",
  10003: "授权码兑换失败，请重新登录",
  10101: "登录状态已失效，请重新登录",
  10102: "无权访问该资源",
  10004: "权限不足",
  10005: "请求参数不合法",
  10006: "链接格式不正确",
  20001: "非公众号文章，请检查链接",
  20002: "网络异常，文章抓取失败",
  20003: "内容质量不足，无法入库",
  30001: "知识空间不存在或已删除",
  30002: "机器人服务异常，请稍后重试",
  30003: "入库失败，请稍后重试",
  30004: "知识空间不存在或已删除",
  // 30101 是**僵尸文案**：后端全仓不产这个码（`grep -rn "30101" apps/api/app apps/api/tests` 零命中），
  // 未找到/越权的线上码是 30004（`apps/api/tests/test_spaces_api.py:239-244` 的断言 `== 30004` 钉着）。
  // 这里保留它只为旧客户端兼容——历史版本可能把 30101 写进过缓存里的判断分支。
  // 删除另排卡（D-V21-14：发版前不动它；组件里并列判这两个码的地方也一并留到那次清）。
  30101: "知识空间不存在或已删除",
  30102: "知识空间数量已达上限",
  50002: "依赖服务暂不可用，请稍后重试",
  50101: "服务暂不可用，请稍后重试",
};

/** 错误码 → 可展示中文文案（未收录码回落原文案，再回落通用文案） */
export function friendlyMessage(code: number, raw: string): string {
  return ERROR_MESSAGES[code] ?? raw ?? "请求失败，请稍后重试";
}
