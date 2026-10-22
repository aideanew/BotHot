/**
 * lib/api/http —— 请求基础设施：MOCK 开关 + 错误文案映射 + 统一信封请求器（T1.2.5 分域拆分）
 *
 * 公开面（barrel 转出）：MOCK_ENABLED / MOCK_LABEL / isAuthError / request。
 * 内部面（供各域模块 import，不经 barrel 转出）：ERROR_MESSAGES / friendlyMessage /
 * delay / mockRequest —— 保持与拆分前「模块私有」等价的可见性。
 */

import { ApiError, type Envelope } from "./types";

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

// ---------- 错误文案映射 ----------

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
  30101: "知识空间不存在或已删除",
  30102: "知识空间数量已达上限",
  50002: "依赖服务暂不可用，请稍后重试",
  50101: "服务暂不可用，请稍后重试",
};

/** 未登录类错误码：调用方据此回落未登录态 */
export function isAuthError(code: number): boolean {
  return code === 10001 || code === 10101;
}

/** 错误码 → 可展示中文文案（未收录码回落原文案，再回落通用文案） */
export function friendlyMessage(code: number, raw: string): string {
  return ERROR_MESSAGES[code] ?? raw ?? "请求失败，请稍后重试";
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
 * 真实请求：fetch + 信封解包。
 * 非零 code → 抛 ApiError；HTTP 层异常 → 归一为 50101 语义。
 * 导出说明：SSO 回调页等需要原始信封语义（非域函数）的场景复用。
 */
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
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
