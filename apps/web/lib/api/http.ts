/**
 * lib/api/http —— 请求基础设施：MOCK 开关 + 错误文案映射 + 统一信封请求器（T1.2.5 分域拆分）
 *
 * 公开面（barrel 转出）：MOCK_ENABLED / MOCK_LABEL / isAuthError / request。
 * 内部面（供各域模块 import，不经 barrel 转出）：ERROR_MESSAGES / friendlyMessage /
 * delay / mockRequest —— 保持与拆分前「模块私有」等价的可见性。
 */

import { ApiError, ERROR_MESSAGES, friendlyMessage, type Envelope } from "./types";
import {
  UNREGISTERED_MOCK_MODE,
  buildMockContext,
  matchMockRoute,
  unregisteredMockRoute,
} from "./mock-routes";

// ---------- MOCK 开关 ----------

/**
 * MOCK 开关：true 时请求走本地契约样例数据。
 * **默认关闭**（STEP-15b S15b.1.1，D-V10-03 代选：翻默认值而不是删开关）——
 * 只有显式 `NEXT_PUBLIC_API_MOCK=true` 才回到样例数据。
 * 翻之前的形状是 `(process.env.NEXT_PUBLIC_API_MOCK ?? "true") !== "false"`，
 * 那条 `?? "true"` 让"没配"被读成"要 mock"，于是开发者打开页面看到的是演示数据，
 * 而真后端在同一时刻正在给同一个接口回 404/500（STEP-22 证据 3 的 `/bots/tasks` 就是实例）。
 * 生产不受影响：`package.json` 的 `prebuild` 仍要求显式 `=false`，`Dockerfile` 仍 ARG 成 false，
 * 纯 UI 开发与 e2e 数据面走显式 `=true`（`ci.yml` 的 mock UI e2e 早已显式设置，不依赖这条默认值）。
 */
export const MOCK_ENABLED: boolean = process.env.NEXT_PUBLIC_API_MOCK === "true";

/** 供顶栏状态徽标等 UI 展示当前数据来源（mock 数据 / 真实后端） */
export const MOCK_LABEL = MOCK_ENABLED ? "演示数据" : "真实后端";

/**
 * 数据来源谓词的**唯一读取口**：非 HTTP 的演示态行为（整页跳转登录、SSE 不建连、
 * 伪流式分片）用它判断，而不是各自再写一次开关表达式。
 * HTTP 形状的数据**不走这个谓词**——那些进 `mock-routes` 的表，由 `request()` 统一分发。
 */
export function isMockMode(): boolean {
  return MOCK_ENABLED;
}

// ---------- 错误文案映射 ----------
// 表本体搬到 `types.ts`（`mock-routes` 要按同码同文抛错，又不能 import 本模块 ⇒ 见那里的注释）。
// 这里只做转出，`auth/ask/ingest` 等既有 `from "./http"` 的 import 面一字不变。
export { ERROR_MESSAGES, friendlyMessage } from "./types";

/** 未登录类错误码：调用方据此回落未登录态 */
export function isAuthError(code: number): boolean {
  return code === 10001 || code === 10101;
}

// ---------- MOCK 延迟与样例请求 ----------

const MOCK_LATENCY_MS = 400;

/** mock 延迟（默认 400ms；供各域 mock 分支与伪流式复用） */
export function delay(ms = MOCK_LATENCY_MS): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/** mock 请求：模拟延迟 + 契约样例数据 */
export async function mockRequest<T>(data: T, failRate = 0): Promise<T> {
  await delay();
  if (failRate > 0 && Math.random() < failRate) {
    throw new ApiError(50101, ERROR_MESSAGES[50101], `mock-${Date.now()}`);
  }
  return data;
}

// ---------- 内部请求器 ----------

/**
 * mock 分发：查 `mock-routes` 的表。
 * 未命中时按 `UNREGISTERED_MOCK_MODE` 决定——迁移期交给真实 fetch（等价于"这个域还没有 mock 分支"
 * 的迁移前行为），收尾期必须翻成抛 50101：一张表成为唯一来源之后，"漏登记"若静默返回
 * `undefined`，页面会渲染成一份看起来正常的空态（与真实的"今天就是没有"同形），
 * 那是本仓最贵的那一族缺陷。
 */
async function mockDispatch<T>(
  path: string,
  init?: RequestInit
): Promise<{ handled: boolean; value?: T }> {
  const [pure, search = ""] = path.split("?");
  const method = (init?.method ?? "GET").toUpperCase();
  const hit = matchMockRoute(method, pure);
  if (!hit) {
    if (UNREGISTERED_MOCK_MODE === "error") {
      throw unregisteredMockRoute(method, pure);
    }
    return { handled: false };
  }
  await delay();
  return {
    handled: true,
    value: hit.route.handle(
      buildMockContext(method, pure, search, hit.params, init?.body)
    ) as T,
  };
}

/**
 * 请求器：**mock 与真实共用同一条管道**（STEP-15b S15b.2.1）。
 * 非零 code → 抛 ApiError；HTTP 层异常 → 归一为 50101 语义。
 * 导出说明：SSO 回调页等需要原始信封语义（非域函数）的场景复用。
 *
 * `MOCK_ENABLED` 为真时不再各域自己造数，而是查 `mock-routes` 的表拿**线上 `data` 形状**的样例：
 * 表命中即过 `delay()` 后返回，未命中**抛 50101**（不是回 undefined——
 * 那会让"漏登记"长得像"今天就是没有数据"）。
 */
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (MOCK_ENABLED) {
    const got = await mockDispatch<T>(path, init);
    if (got.handled) return got.value as T;
  }
  let res: Response;
  try {
    res = await fetch(path, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...init?.headers },
      ...init,
    });
  } catch {
    throw new ApiError(50101, "网络异常，请检查连接后重试");
  }

  // 401 语义：未登录/会话失效，统一转认证错误
  if (res.status === 401) {
    throw new ApiError(10001, ERROR_MESSAGES[10001]);
  }

  // W7 429 预留：RATE_LIMITED（20005 / HTTP 429）未落地前，
  // 此处先按 429 拦截并转 20005 语义，供调用方统一 toast。
  // W7 落地后后端会直接回 20005 错误码，此处变为冗余保护。
  if (res.status === 429) {
    throw new ApiError(20005, "请求过于频繁，请稍后再试");
  }

  let body: Envelope<T>;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    throw new Error("响应格式异常，请稍后重试");
  }

  if (body.code !== 0) {
    throw new ApiError(
      body.code,
      friendlyMessage(body.code, body.message),
      body.requestId
    );
  }
  return body.data as T;
}
