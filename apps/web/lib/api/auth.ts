/**
 * lib/api/auth —— 认证域（C-T2：登录跳转 / 会话态 / 登出）
 *
 * 契约：GET /api/v1/auth/me、POST /api/v1/auth/logout、整页跳转 /api/v1/auth/login。
 * 会话由服务端 HttpOnly cookie 承载，前端**不读不存 token**。
 */

import { ERROR_MESSAGES, MOCK_ENABLED, delay, mockRequest, request } from "./http";
import { ApiError, normalizeMeData, type MeData } from "./types";

const MOCK_ME: MeData = {
  sub: "mock-user-001",
  email: "admin@bothot.local",
  nickname: "演示用户",
  tier: "pro",
  wallet: "¥128.50",
  is_admin: false,
  providerUnreachable: false,
};

/** mock 会话：本地登录态标记（仅 MOCK 模式生效），保证未登录/登录两态可复现 */
const MOCK_LOGIN_KEY = "bothot_mock_login";

function mockIsLoggedIn(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(MOCK_LOGIN_KEY) === "1";
}

/**
 * 登录入口。真实态：整页跳转 /api/v1/auth/login（后端 302 至主平台 authorize，
 * 会话由服务端 cookie 建立，前端不读不存 token）；mock 态：写本地标记后刷新。
 */
export function authLogin(): void {
  if (MOCK_ENABLED) {
    window.localStorage.setItem(MOCK_LOGIN_KEY, "1");
    window.location.reload();
    return;
  }
  // 必须整页跳转：该端点返回 302，fetch 无法跟随跨域授权链
  window.location.href = "/api/v1/auth/login";
}

/**
 * GET /api/v1/auth/me。
 * 未登录（10001/10101）或网络失败均抛 ApiError，由调用方（AuthContext）
 * 统一回落未登录态，禁止白屏。
 */
export async function authMe(): Promise<MeData> {
  if (MOCK_ENABLED) {
    if (!mockIsLoggedIn()) {
      throw new ApiError(10001, ERROR_MESSAGES[10001], `mock-${Date.now()}`);
    }
    return mockRequest(MOCK_ME);
  }
  // 载荷按未知形状接收（真实为嵌套 {user,wallet}，mock 为扁平），统一归一化
  return request<Record<string, unknown>>("/api/v1/auth/me").then(normalizeMeData);
}

/** POST /api/v1/auth/logout —— 撤销服务端会话；mock 态清除本地标记 */
export async function authLogout(): Promise<void> {
  if (MOCK_ENABLED) {
    await delay(200);
    window.localStorage.removeItem(MOCK_LOGIN_KEY);
    return;
  }
  await request<null>("/api/v1/auth/logout", { method: "POST" });
}
