/**
 * lib/api/mock-routes —— 演示数据的**唯一**来源表（STEP-15b S15b.2.1）。
 *
 * 为什么要一张表而不是九个文件各写各的演示分支：
 * 分支散在各域时，"mock 态返回什么"与"真后端返回什么"是**两份各自维护的形状**——
 * 域函数在 mock 分支里直接返回它自己想要的对象，于是同一条 `d.items` 解包逻辑
 * 只在真实路径上被执行过。演示态看起来永远正确，恰恰因为它绕过了自己要展示的东西。
 * 收进 `request()` 之后，mock 与真实走**同一条解包与归一化管道**：表里存的是
 * 线上 `data` 字段的形状，域函数不再知道自己拿到的是样例还是后端。
 *
 * 未登记路由的行为（这条是本文件存在的另一半年）：**抛错，不静默返回 undefined**。
 * 表一旦成为唯一来源，"漏登记"就会表现为"这个页面今天是空的"——与真实的空态同形，
 * 那正是本仓反复登记过的那族静默失败（P0-3、P-9、外链过滤那一族）。
 * 所以漏登记必须是 50101 一条会响的错误，而不是一份看起来正常的空数据。
 *
 * 形状来源（S48 起步、S52 铺满）：本表 22 条路由的样例与 handler 返回值**全部**
 * `satisfies` 契约类型（`packages/contracts`，由 `apps/api/app/contracts/**` 生成），
 * 路由 pattern → 契约类型名的对照只有一份：`mock-contract-map.ts`（镜像后端
 * `app/contracts/shapes.py` 的 `MOCK_ROUTE_CONTRACTS`）。三道机器红：
 * ① 有路由没登记契约 ⇒ `s52-mock-contract-coverage` 红；② 登记了但 mock 里没有这条路由，
 * 或表里的类型名与后端权威串不一致 ⇒ 同文件红；③ 样例少一个契约键 ⇒ tsc 红。
 * P-82 收口前的"演示态形状与线上不同形"这一族就此关闭（satisfies 与表之间的绑定
 * 仍靠人工对账，洞已登记为 P-124）。
 */

import { ApiError, CATEGORIES, ERROR_MESSAGES, UNCATEGORIZED } from "./types";
import { MOCK_DOCS, MOCK_SPACE_DETAILS, MOCK_SPACES } from "./mock-data";
import type {
  BatchDocFailure,
  DocCategoryList,
  DocCategoryPatch,
  DocDeleteResult,
  DocIngestState,
  DocsBatchDeleteResult,
  DocsRecategorizeResult,
  EngineCapability,
  EngineList,
  ExtractedArticleView,
  IngestAccepted,
  LinkResult,
  LogoutResult,
  MeView,
  NotificationHistoryPage,
  NotificationReadResult,
  PublicSpacePage,
  PublicSpaceView,
  ResolvedArticleView,
  SpaceDeleteResult,
  SpaceDetail,
  SpaceDocPage,
  SpaceEngineBinding,
  SpacePage,
} from "@bothot/contracts";

/** 一次 mock 分发拿到的上下文——与真实那次 fetch 能拿到的信息同集。 */
export interface MockContext {
  method: string;
  /** 请求路径（不含 query） */
  path: string;
  /** 原始 query 串 */
  search: string;
  query: URLSearchParams;
  /** `pattern` 命名捕获组解出来的路径参数 */
  params: Record<string, string>;
  /** 已 `JSON.parse` 的请求体；无体或非 JSON ⇒ undefined */
  body: unknown;
}

export type MockHandler = (ctx: MockContext) => unknown;

export interface MockRoute {
  method: string;
  /**
   * 路径模式。**用位置捕获组 + `paramNames` 而不是命名捕获组**：
   * `tsconfig.json` 的 `target` 是 ES2017，`(?<name>…)` 会直接 TS1503 编译失败。
   */
  pattern: RegExp;
  paramNames?: string[];
  handle: MockHandler;
}

/**
 * 路由表：按声明顺序**首个命中**生效，所以具体路径要写在模式路径之前。
 * 每条的值就是真后端 `data` 字段该长的形状。
 */
export const MOCK_ROUTES: MockRoute[] = [];

/**
 * 没有样例、**明确**交给真实后端的端点前缀。
 *
 * 这条清单是"passthrough 是决定，不是缺席"的载体：七个域（bots / hot / jobs /
 * subscriptions / admin / admin-ops / batch）从设计上就没有演示态样例——
 * 任务状态、整号订阅、后台跨用户读面都必须来自真后端，造一份假 Job 会让"Job 在排队"
 * 这种状态在演示里永远看不出问题。把它们写成声明而不是"表里恰好没有"，
 * 才让"表里没登记又不在豁免清单 ⇒ 抛 50101"这条硬规则可以立刻生效（新端点一进来就必须表态）。
 *
 * 配套判据在 `tests/mock-routes.spec.ts`：扫 `lib/api/*.ts` 里出现的每一条字面
 * `/api/v1/...`，断言"要么命中表、要么命中本清单"——清单的完整性由机器守，不靠人记。
 */
export const MOCK_PASSTHROUGH: ReadonlyArray<{ path: RegExp; reason: string }> = [
  { path: /^\/api\/v1\/bots\b/, reason: "渠道与推送任务态必须来自真后端（STEP-22 起 /bots/tasks 才被后端接住）" },
  { path: /^\/api\/v1\/channels\b/, reason: "同上：渠道列表与密钥状态不造样例" },
  { path: /^\/api\/v1\/push\b/, reason: "推送日志与投递回执不造样例" },
  { path: /^\/api\/v1\/hot\b/, reason: "热点域读面来自真聚簇结果" },
  { path: /^\/api\/v1\/jobs\b/, reason: "Job 状态机（QUEUED→RUNNING→终态）造样例会遮蔽积压与失败" },
  { path: /^\/api\/v1\/sources\b/, reason: "整号采集依赖真实清单链路（r024 同口径）" },
  { path: /^\/api\/v1\/spaces\/[^/]+\/subscriptions\b/, reason: "订阅生命周期与 Job 水位不造样例" },
  { path: /^\/api\/v1\/system\/notifications$/, reason: "SSE 流由 EventSource 自己开、不经信封表；演示态在 connectNotifications 里由唯一谓词门短路" },
  { path: /^\/api\/v1\/spaces\/[^/]+\/docs:batch$/, reason: "批量入库必须真打：演示态跑的是同一套轮询与部分成功语义（T2.6.2）" },
  { path: /^\/api\/v1\/admin\b/, reason: "后台跨用户读面与批量运维不造样例" },
  { path: /^\/api\/v1\/chat\b/, reason: "问答由 ask.ts 的伪流式与真流式两支自己处理，不走信封表" },
  { path: /^\/api\/v1\/auth\/login\b/, reason: "整页跳转端点（302），不是 fetch 目标" },
  { path: /^\/api\/v1\/auth\/callback\b/, reason: "SSO 回调页直取原始信封语义，不经 request()" },
  {
    path: /^\/api\/v1\/system\/ready$/,
    reason:
      "就绪探针回显的是**部署事实**（ALERTING_ENABLED、PG/Redis/schema 当下可达性），给它造一份样例等于向运维宣布一个不存在的服务栈的状态；演示态真打失败后由 AlertBanner 降级为「未知」",
  },
];

export function isMockPassthrough(path: string): boolean {
  return MOCK_PASSTHROUGH.some((entry) => entry.path.test(path));
}

export function registerMockRoutes(...routes: MockRoute[]): void {
  MOCK_ROUTES.push(...routes);
}

/** 供 `http.ts` 查询：命中则返回 (route, params)。 */
export function matchMockRoute(
  method: string,
  path: string
): { route: MockRoute; params: Record<string, string> } | null {
  for (const route of MOCK_ROUTES) {
    if (route.method !== method) continue;
    const got = route.pattern.exec(path);
    if (!got) continue;
    const params: Record<string, string> = {};
    (route.paramNames ?? []).forEach((name, index) => {
      const value = got[index + 1];
      if (value !== undefined) params[name] = decodeURIComponent(value);
    });
    return { route, params };
  }
  return null;
}

export function buildMockContext(
  method: string,
  path: string,
  search: string,
  params: Record<string, string>,
  rawBody: BodyInit | null | undefined
): MockContext {
  let body: unknown;
  if (typeof rawBody === "string") {
    try {
      body = JSON.parse(rawBody);
    } catch {
      body = undefined; // 非 JSON 体（FormData 等）在 mock 态不参与判断，如实给 undefined
    }
  }
  return { method, path, search, query: new URLSearchParams(search), params, body };
}

/** 未登记路由的错误文案：把"缺哪一条"写在脸上，方便下一轮直接补表。 */
export function unregisteredMockRoute(method: string, path: string): ApiError {
  return new ApiError(
    50101,
    `mock 路由未登记：${method} ${path}（请在 lib/api/mock-routes.ts 补一条，而不是让它返回空数据）`,
    "mock-unregistered"
  );
}

// ── engines 域（S15b.2.2 第一个迁入的域）───────────────────────────────

/**
 * 演示态引擎位：builtin 恒可用，其余未配 Key（置灰 + 提示找管理员）。
 * 与真实后端"零 Key 部署"的回报一致——这条样例存在的理由不是"要有数据可看"，
 * 而是 EngineSwitcher 在空间详情页**无条件挂载**，mock 产物里让它真打 /api/v1/engines
 * 会被 rewrite 代理到不存在的后端（ECONNREFUSED :3300 → 500 → console 门禁红，
 * CI run 37749239965 实证）。
 */
const MOCK_ENGINES = [
  {
    engine: "builtin",
    configured: true,
    available: true,
    allowlisted: true,
    reason: "ok",
    implemented: true,
    keyEnv: "",
    activeSource: "env",
    decryptFailed: false,
    description: "内置关键词检索引擎（演示数据）",
  } satisfies EngineCapability,
  {
    engine: "main-platform",
    configured: false,
    available: false,
    allowlisted: true,
    reason: "key_missing",
    implemented: false,
    keyEnv: "MAIN_PLATFORM_API_KEY",
    activeSource: null,
    decryptFailed: false,
    description: "主平台知识引擎",
  } satisfies EngineCapability,
  {
    engine: "coze",
    configured: false,
    available: false,
    allowlisted: true,
    reason: "key_missing",
    implemented: false,
    keyEnv: "COZE_API_KEY",
    activeSource: null,
    decryptFailed: false,
    description: "Coze 知识引擎",
  } satisfies EngineCapability,
  {
    engine: "dify",
    configured: false,
    available: false,
    allowlisted: true,
    reason: "key_missing",
    implemented: false,
    keyEnv: "DIFY_API_KEY",
    activeSource: null,
    decryptFailed: false,
    description: "Dify 知识引擎",
  } satisfies EngineCapability,
  {
    engine: "fastgpt",
    configured: false,
    available: false,
    allowlisted: true,
    reason: "key_missing",
    implemented: false,
    keyEnv: "FASTGPT_API_KEY",
    activeSource: null,
    decryptFailed: false,
    description: "FastGPT 知识引擎",
  } satisfies EngineCapability,
];

registerMockRoutes(
  {
    method: "GET",
    pattern: /^\/api\/v1\/engines$/,
    handle: () => ({ items: MOCK_ENGINES, defaultEngine: "builtin" }) satisfies EngineList,
  },
  {
    // 演示态切换：只放行 available 的引擎位，其余按真后端口径拒 10004（不是拒 500、也不是静默成功）
    method: "PATCH",
    pattern: /^\/api\/v1\/spaces\/([^/]+)\/engine$/,
    paramNames: ["spaceId"],
    handle: ({ params, body }) => {
      const engine = String((body as { engine?: string } | undefined)?.engine ?? "");
      const target = MOCK_ENGINES.find((e) => e.engine === engine);
      if (!target || !target.available) {
        throw new ApiError(
          10004,
          "引擎未开放 / 未配置 Key / 尚未实接，请联系管理员"
        );
      }
      return { engine, engineKbId: `mock-kb-${engine}`, spaceId: params.spaceId } satisfies SpaceEngineBinding;
    },
  }
);

// ── auth 域（第二个迁入的域）─────────────────────────────────────────

/**
 * 演示态的登录标记。**key 与读写只在这里有一份**：`authLogin` 写、`authMe` 读、`authLogout` 清，
 * 三处若各自持有一个字符串，改名时就会出现"登录了但 /me 说没登录"这种最难读的现象。
 */
const MOCK_LOGIN_KEY = "bothot_mock_login";

function loginStore(): Storage | null {
  return typeof window === "undefined" ? null : window.localStorage;
}

export function mockMarkLoggedIn(): void {
  loginStore()?.setItem(MOCK_LOGIN_KEY, "1");
}

export function mockClearLoggedIn(): void {
  loginStore()?.removeItem(MOCK_LOGIN_KEY);
}

export function mockLoggedIn(): boolean {
  return loginStore()?.getItem(MOCK_LOGIN_KEY) === "1";
}

/**
 * 演示态 `/me`：**线上嵌套形态** `{user:{…}, wallet:{…}}`（契约 `MeView`）。
 * 此前这里是扁平形（`{sub,…,wallet:"¥128.50"}`）——`normalizeMeData` 两种形态都吃，
 * 于是页面在演示态永远走"扁平分支"，真实的嵌套解包路径只有接上后端才第一次执行（P-122 第一处）。
 */
const MOCK_ME = {
  user: {
    sub: "mock-user-001",
    email: "admin@bothot.local",
    nickname: "演示用户",
    tier: "pro",
    /** 主平台 userinfo 的大写枚举，与本地授权秩（`is_admin`）不同源（SPEC-M3 批次 2） */
    role: "USER",
    is_admin: false,
  },
  wallet: { balanceYuan: "128.50", currency: "CNY" },
  providerUnreachable: false,
} satisfies MeView;

registerMockRoutes(
  {
    method: "GET",
    pattern: /^\/api\/v1\/auth\/me$/,
    handle: () => {
      // 未登录态必须与真后端同码同文（10001），否则 AuthContext 的回落分支在演示态永不执行
      if (!mockLoggedIn()) {
        throw new ApiError(10001, ERROR_MESSAGES[10001], `mock-${Date.now()}`);
      }
      return MOCK_ME;
    },
  },
  {
    method: "POST",
    pattern: /^\/api\/v1\/auth\/logout$/,
    handle: () => {
      mockClearLoggedIn();
      // 真后端回 `{logged_out:true}`；此前返回 null，于是"登出回执"这条消费路径在演示态永不执行（P-122）
      return { logged_out: true } satisfies LogoutResult;
    },
  }
);

// ── public-library 域（第三个迁入的域）───────────────────────────────

/**
 * 注册顺序即匹配顺序（首个命中生效）：`GET /spaces/public` 必须写在将来那条
 * `GET /spaces/{id}` 之前，否则 "public" 会被当成一个空间 id 吃掉——这条不是风格问题，
 * 是这张表唯一会产生**错数据**的顺序陷阱，所以在这里写明并要求 spaces 迁入时遵守。
 */
const MOCK_PUBLIC_SPACES = [
  {
    id: "mock-public-ai-001",
    name: "AI前沿库",
    description: "AI前沿库（采自公众号，系统空间）",
    docCount: 50,
    engine: "builtin",
    isPublic: true,
    updatedAt: "2026-09-14T00:00:00",
  },
] satisfies PublicSpaceView[];

const MOCK_LINK_RESULT = { copied: 50, skipped: 0, total: 50 } satisfies LinkResult;

/** 后端 `limit_offset_query` 的缺省页宽（`app/api/deps.py:41` = 50）；请求带值时一律回显请求值 */
const MOCK_PAGE_LIMIT = 50;

registerMockRoutes(
  {
    // 契约 `PublicSpacePage` 是整页（items+total+limit+offset），此前样例只给 `{items}`：
    // 分页窗口在演示态拿到的是"没有总数的半张响应"，与线上不同形（P-122 第三处）
    method: "GET",
    pattern: /^\/api\/v1\/spaces\/public$/,
    handle: ({ query }) =>
      ({
        items: MOCK_PUBLIC_SPACES,
        total: MOCK_PUBLIC_SPACES.length,
        limit: Number(query.get("limit") ?? MOCK_PAGE_LIMIT),
        offset: Number(query.get("offset") ?? 0),
      }) satisfies PublicSpacePage,
  },
  {
    // 幂等 copy：演示态固定给"全部新增、零跳过"，与真后端的 {copied, skipped, total} 同形
    method: "POST",
    pattern: /^\/api\/v1\/spaces\/[^/]+\/links$/,
    handle: () => MOCK_LINK_RESULT,
  }
);

// ── ingest 域（第四个迁入的域：解析 / 抽取 / 提交 / 状态轮询）──────────

/** 正常文章（高质量） */
const MOCK_RESOLVE_OK = {
  title: "深度解析：大模型知识库落地的三个关键环节",
  author: "技术前沿周刊",
  publishTime: "2026-09-05 08:30",
  content:
    "知识库的质量决定了问答效果的上限。\n采集、清洗、评分是入库前的三道关口。\n本文逐一拆解每个环节的最佳实践。",
  url: "https://mp.weixin.qq.com/s/mock-ok-001",
  biz: "mock-biz-001",
} satisfies ResolvedArticleView;

const MOCK_EXTRACT_OK = {
  title: "深度解析：大模型知识库落地的三个关键环节",
  author: "技术前沿周刊",
  publishTime: "2026-09-05 08:30",
  paragraphs: [
    "知识库的质量决定了问答效果的上限。",
    "采集、清洗、评分是入库前的三道关口。",
    "本文逐一拆解每个环节的最佳实践，并给出可落地的操作建议。",
  ],
  images: [{ src: "https://mock.example/fig-1.png", caption: "图 1：入库流程" }],
  wordCount: 2860,
  langbotFormat: "markdown-v1",
  qualityScore: 86,
  qualityPassed: true,
  qualityReasons: [],
} satisfies ExtractedArticleView;

/** 低质样例：URL 含"低质"时命中，用于演示后端 20003 的同步拦截 */
const MOCK_LOW_QUALITY = {
  title: "（低质样例）标题党短文",
  author: "营销号日报",
  publishTime: "2026-09-06 12:00",
  paragraphs: ["点关注不迷路。"],
  images: [],
  wordCount: 7,
  langbotFormat: "markdown-v1",
  qualityPassed: false,
  qualityScore: 12,
  qualityReasons: ["正文过短（少于 200 字）", "无有效配图"],
} satisfies ExtractedArticleView;

function bodyUrl(ctx: MockContext): string {
  return String((ctx.body as { url?: string } | undefined)?.url ?? "");
}

registerMockRoutes(
  {
    // 非 http(s) 链接在演示态也必须现 10006：否则"链接校验"这条前端路径永不执行
    method: "POST",
    pattern: /^\/api\/v1\/resolve$/,
    handle: (ctx) => {
      if (!bodyUrl(ctx).startsWith("http")) {
        throw new ApiError(10006, ERROR_MESSAGES[10006], `mock-${Date.now()}`);
      }
      return MOCK_RESOLVE_OK;
    },
  },
  {
    method: "POST",
    pattern: /^\/api\/v1\/extract$/,
    handle: (ctx) => (bodyUrl(ctx).includes("低质") ? MOCK_LOW_QUALITY : MOCK_EXTRACT_OK),
  },
  {
    method: "POST",
    pattern: /^\/api\/v1\/spaces\/[^/]+\/docs$/,
    handle: () => ({
      docId: `doc-mock-${Date.now()}`,
      title: "深度解析：大模型知识库落地的三个关键环节",
      status: "INDEXED",
      langbotFileId: `file-mock-${Date.now()}`,
      taskId: "",
      hitCache: false,
      hitCount: 0,
    }) satisfies IngestAccepted,
  },
  {
    // 演示态"3s 后即 READY"的演练路径：轮询循环照跑，只是第一跳就返回终态
    method: "GET",
    pattern: /^\/api\/v1\/spaces\/[^/]+\/docs\/([^/]+)\/status$/,
    paramNames: ["docId"],
    handle: ({ params }) => ({
      docId: params.docId ?? "",
      status: "READY",
      langbotFileId: "file-mock",
    }) satisfies DocIngestState,
  }
);

// ── notifications 域（第五个迁入的域：历史与已读回执）─────────────────

registerMockRoutes(
  {
    // 演示数据没有真实通知历史 ⇒ 空页；但 limit/offset 必须**回显请求里的值**，
    // 否则前端分页窗口（"这一页拿满 ⇒ 还有下一页"）在演示态永远算错。
    // 缺省页宽取后端 `limit_offset_query` 的 50（`app/api/deps.py:41`）——原来写死 20，
    // 只在"不带 query 直接打这条路由"时露出来，属同一族回显口径。
    method: "GET",
    pattern: /^\/api\/v1\/system\/notifications\/history$/,
    handle: ({ query }) => ({
      items: [],
      total: 0,
      limit: Number(query.get("limit") ?? MOCK_PAGE_LIMIT),
      offset: Number(query.get("offset") ?? 0),
      unread_total: 0,
    }) satisfies NotificationHistoryPage,
  },
  {
    method: "PUT",
    pattern: /^\/api\/v1\/system\/notifications\/read$/,
    handle: () => ({ updated: 0 }) satisfies NotificationReadResult,
  }
);

// ── spaces 域（第六个迁入的域，也是最后一个带演示态分支的域）──────────
//
// 样例数据本身留在 `mock-data.ts`（跨域共享：ask 域也按空间名取样例），
// 但**改写它们的动作**（删除/改分类就地生效）跟着路由走，仍只在这一处发生。
// 注意注册顺序：本段的通用 `/spaces/{id}` 模式一律排在 `public`、`docs`、
// `docs:categories`、`docs/{docId}/status` 之后——先命中的生效，反了就会把
// "public" 当成一个空间 id 返回详情样例。

/** 按 category 过滤后切片（口径与后端 `_docs_stmt` 一致）。返回整页契约形状。 */
function sliceMockDocs(id: string, query: URLSearchParams): SpaceDocPage {
  const all = MOCK_DOCS[id] ?? [];
  const category = query.get("category") ?? "";
  const filtered = category
    ? category === UNCATEGORIZED
      ? all.filter((d) => !d.category)
      : all.filter((d) => (d.category ?? "") === category)
    : all;
  const limit = Number(query.get("limit") ?? 100);
  const offset = Number(query.get("offset") ?? 0);
  return { items: filtered.slice(offset, offset + limit), total: filtered.length, limit, offset };
}

/** 复刻后端 `order_categories`（声明序、未登记取值置后、未分类哨兵置末）。 */
function orderMockCategories(id: string): string[] {
  const all = MOCK_DOCS[id] ?? [];
  const present = new Set(all.map((d) => d.category ?? "").filter((c) => c !== ""));
  const ordered = CATEGORIES.filter((c) => present.has(c));
  ordered.push(...all.map((d) => d.category ?? "").filter((c) => c && !CATEGORIES.includes(c)));
  if (all.some((d) => !d.category)) ordered.push(UNCATEGORIZED);
  return ordered;
}

function bodyOf(ctx: MockContext): Record<string, unknown> {
  return (ctx.body as Record<string, unknown> | undefined) ?? {};
}
registerMockRoutes(
  {
    // 创建响应复用详情形状（后端 spaces.py:141 明写），故 satisfies SpaceDetail；
    // 此前样例缺 engine/engineKbId/isPublic 三键，与 `GET /spaces` 的 items 不同形（P-122 第四处）
    method: "POST",
    pattern: /^\/api\/v1\/spaces$/,
    handle: (ctx) => {
      const now = new Date().toISOString();
      const payload = bodyOf(ctx);
      const id = `sp-mock-${Date.now()}`;
      return {
        id,
        name: String(payload.name ?? ""),
        description: String(payload.description ?? ""),
        docCount: 0,
        updatedAt: now,
        createdAt: now,
        engine: "builtin",
        engineKbId: `mock-kb-${id}`,
        isPublic: false,
        stats: { docs: 0, chunks: null },
      } satisfies SpaceDetail;
    },
  },
  {
    // 具体路径先行：`docs:categories` / `docs:delete` / `docs:recategorize` / `docs` 都在前面注册
    method: "GET",
    pattern: /^\/api\/v1\/spaces$/,
    handle: ({ query }) => ({
      items: MOCK_SPACES,
      total: MOCK_SPACES.length,
      limit: Number(query.get("limit") ?? MOCK_PAGE_LIMIT),
      offset: Number(query.get("offset") ?? 0),
    }) satisfies SpacePage,
  },
  {
    method: "GET",
    pattern: /^\/api\/v1\/spaces\/([^/]+)\/docs$/,
    paramNames: ["id"],
    handle: ({ params, query }) => sliceMockDocs(params.id ?? "", query),
  },
  {
    method: "GET",
    pattern: /^\/api\/v1\/spaces\/([^/]+)\/docs:categories$/,
    paramNames: ["id"],
    handle: ({ params }) => ({ items: orderMockCategories(params.id ?? "") }) satisfies DocCategoryList,
  },
  {
    method: "DELETE",
    pattern: /^\/api\/v1\/spaces\/([^/]+)\/docs\/([^/]+)$/,
    paramNames: ["id", "docId"],
    handle: ({ params }) => {
      const list = MOCK_DOCS[params.id ?? ""];
      const docId = params.docId ?? "";
      if (list) {
        const idx = list.findIndex((d) => d.id === docId);
        if (idx >= 0) list.splice(idx, 1);
      }
      return { ok: true, docId, docs: 1, assets: 0 } satisfies DocDeleteResult;
    },
  },
  {
    method: "PATCH",
    pattern: /^\/api\/v1\/spaces\/([^/]+)\/docs\/([^/]+)$/,
    paramNames: ["id", "docId"],
    handle: ({ params, body }) => {
      const list = MOCK_DOCS[params.id ?? ""];
      const doc = (list ?? []).find((d) => d.id === (params.docId ?? ""));
      const category = String((body as { category?: string } | undefined)?.category ?? "");
      if (doc) doc.category = category;
      return { docId: params.docId ?? "", category: category || "其他" } satisfies DocCategoryPatch;
    },
  },
  {
    method: "POST",
    pattern: /^\/api\/v1\/spaces\/([^/]+)\/docs:delete$/,
    paramNames: ["id"],
    handle: ({ params, body }) => {
      const list = MOCK_DOCS[params.id ?? ""];
      const ids = ((body as { ids?: string[] } | undefined)?.ids ?? []);
      const failed: BatchDocFailure[] = [];
      if (list) {
        for (const id of ids) {
          const idx = list.findIndex((d) => d.id === id);
          if (idx < 0) failed.push({ docId: id, code: 30004, error: "RESOURCE_NOT_FOUND" });
          else list.splice(idx, 1);
        }
      }
      return {
        ok: true,
        requested: ids.length,
        docs: Math.max(0, ids.length - failed.length),
        assets: 0,
        failed,
      } satisfies DocsBatchDeleteResult;
    },
  },
  {
    method: "POST",
    pattern: /^\/api\/v1\/spaces\/([^/]+)\/docs:recategorize$/,
    paramNames: ["id"],
    handle: ({ params, body }) => {
      const list = MOCK_DOCS[params.id ?? ""];
      const payload = (body ?? {}) as { ids?: string[]; category?: string };
      const ids = (payload.ids as string[]) ?? [];
      const normalized = String(payload.category ?? "") || "其他";
      (list ?? []).forEach((d) => {
        if (ids.includes(d.id)) d.category = normalized;
      });
      return { ok: true, requested: ids.length, docs: ids.length, category: normalized } satisfies DocsRecategorizeResult;
    },
  },
  {
    method: "GET",
    pattern: /^\/api\/v1\/spaces\/([^/]+)$/,
    paramNames: ["id"],
    handle: ({ params }) => {
      const detail = MOCK_SPACE_DETAILS[params.id ?? ""];
      if (!detail) {
        // 与后端同码：`GET /spaces/{id}` 未命中 → 30004（不泄露存在性，spaces.py:695）。
        // 此前 mock 抛 30101，恰好绕过了前端只认 30101/10102 的那条分支——现改成线上真实会走的那条
        // （该缺口已登记 P-123，本卡不顺手修 useSpaceDetail）。
        throw new ApiError(30004, ERROR_MESSAGES[30004], `mock-${Date.now()}`);
      }
      return detail;
    },
  },
  {
    method: "DELETE",
    pattern: /^\/api\/v1\/spaces\/([^/]+)$/,
    paramNames: ["id"],
    handle: () => ({
      ok: true,
      // 演示态不调引擎 ⇒ 引擎侧不可能有残留；真后端把"KB 没删净"如实回报，样例必须带这个键（P-122 第五处）
      engineResidue: false,
    }) satisfies SpaceDeleteResult,
  }
);

// ── 注册顺序备忘 ────────────────────────────────────────────────────
// 本文件按域分段注册，段内顺序即匹配顺序（首个命中生效）。迁入 spaces 域时务必把
// `GET /spaces/public`、`POST /spaces/{id}/docs`、`GET /spaces/{id}/docs/{docId}/status`
// 这类**具体路径**排在通用 `/spaces/{id}` 之前，否则通用模式会先把具体路径吃掉，
// 表现是"页面拿到一份结构正确但内容错误的样例"——不是异常，是最难查的那类缺陷。
