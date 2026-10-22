/**
 * lib/api/mock-routes —— 演示数据的**唯一**来源表（STEP-15b S15b.2.1）。
 *
 * 为什么要一张表而不是九个文件各写各的 `if (MOCK_ENABLED)`：
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
 * 形状来源（如实声明）：本表的值类型取 `lib/api/types.ts` 与各域自己声明的**线上响应类型**，
 * 不是 `packages/contracts` 的生成物——那个包目前只冻结了 6 个域的**持久层实体镜像**
 * （`src/index.ts:33-38` 的口径限定写明"域 dto 是 SQLAlchemy 列内省，不是 API 响应形状"，
 * 而 identity / chat / engine 三域还是 `.gitkeep` 骨架）。卡面 S15b.2.1 要的
 * `satisfies 生成类型` 在现行契约包下**不可满足**，已按升级条件登记 P-82 交 Contract 列，
 * 而不是在这里手写一批新类型冒充契约。
 */

import { ApiError, ERROR_MESSAGES } from "./types";
import type { EngineItem } from "./engines";
import type { LinkResult, MeData, PublicSpace } from "./types";

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
 * 未登记路径的口径。两档，**迁移期与收尾期不同**：
 *
 * - `"passthrough"`（S15b.2.2 期间）：交给真实 fetch。这等价于"这个域还没有 mock 分支"的
 *   迁移前行为（`r024-lifecycle-api` 甚至专门钉住"订阅域整域无 mock 分支，写函数仍走真实 fetch"），
 *   所以逐文件删分支的过程中 CI 的 mock e2e 不会被误伤；
 * - `"error"`（S15b.2.3 收尾必须翻到这一档）：表成为唯一来源后，漏登记必须抛 50101。
 *
 * 留在 `"passthrough"` 的后果写在注释里而不是藏在代码里：漏登记的接口会在演示态
 * 真打后端、被 rewrite 代理到不存在的 3300，得到一条 500——那条引擎位的老病（CI run 37749239965）。
 */
export const UNREGISTERED_MOCK_MODE: "passthrough" | "error" = "passthrough";

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
const MOCK_ENGINES: EngineItem[] = [
  {
    engine: "builtin",
    configured: true,
    available: true,
    allowlisted: true,
    implemented: true,
    keyEnv: "",
    activeSource: "env",
    description: "内置关键词检索引擎（演示数据）",
  },
  {
    engine: "main-platform",
    configured: false,
    available: false,
    allowlisted: true,
    implemented: false,
    keyEnv: "MAIN_PLATFORM_API_KEY",
    description: "主平台知识引擎",
  },
  {
    engine: "coze",
    configured: false,
    available: false,
    allowlisted: true,
    implemented: false,
    keyEnv: "COZE_API_KEY",
    description: "Coze 知识引擎",
  },
  {
    engine: "dify",
    configured: false,
    available: false,
    allowlisted: true,
    implemented: false,
    keyEnv: "DIFY_API_KEY",
    description: "Dify 知识引擎",
  },
  {
    engine: "fastgpt",
    configured: false,
    available: false,
    allowlisted: true,
    implemented: false,
    keyEnv: "FASTGPT_API_KEY",
    description: "FastGPT 知识引擎",
  },
];

registerMockRoutes(
  {
    method: "GET",
    pattern: /^\/api\/v1\/engines$/,
    handle: () => ({ items: MOCK_ENGINES, defaultEngine: "builtin" }),
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
      return { engine, engineKbId: `mock-kb-${engine}`, spaceId: params.spaceId };
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

/** 演示态 `/me`：扁平形态（`normalizeMeData` 两种形态都吃，见 types.ts 的注释） */
const MOCK_ME: MeData = {
  sub: "mock-user-001",
  email: "admin@bothot.local",
  nickname: "演示用户",
  tier: "pro",
  wallet: "¥128.50",
  is_admin: false,
  providerUnreachable: false,
};

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
      return null;
    },
  }
);

// ── public-library 域（第三个迁入的域）───────────────────────────────

/**
 * 注册顺序即匹配顺序（首个命中生效）：`GET /spaces/public` 必须写在将来那条
 * `GET /spaces/{id}` 之前，否则 "public" 会被当成一个空间 id 吃掉——这条不是风格问题，
 * 是这张表唯一会产生**错数据**的顺序陷阱，所以在这里写明并要求 spaces 迁入时遵守。
 */
const MOCK_PUBLIC_SPACES: PublicSpace[] = [
  {
    id: "mock-public-ai-001",
    name: "AI前沿库",
    description: "AI前沿库（采自公众号，系统空间）",
    docCount: 50,
    engine: "builtin",
    isPublic: true,
    updatedAt: "2026-09-14T00:00:00",
  },
];

const MOCK_LINK_RESULT: LinkResult = { copied: 50, skipped: 0, total: 50 };

registerMockRoutes(
  {
    method: "GET",
    pattern: /^\/api\/v1\/spaces\/public$/,
    handle: () => ({ items: MOCK_PUBLIC_SPACES }),
  },
  {
    // 幂等 copy：演示态固定给"全部新增、零跳过"，与真后端的 {copied, skipped, total} 同形
    method: "POST",
    pattern: /^\/api\/v1\/spaces\/[^/]+\/links$/,
    handle: () => MOCK_LINK_RESULT,
  }
);
