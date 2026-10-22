/**
 * lib/api/auth —— 认证域（C-T2：登录跳转 / 会话态 / 登出）
 *
 * 契约：GET /api/v1/auth/me、POST /api/v1/auth/logout、整页跳转 /api/v1/auth/login。
 * 会话由服务端 HttpOnly cookie 承载，前端**不读不存 token**。
 *
 * STEP-15b S15b.2.2：`/me` 与 `/logout` 的演示态载荷、登录标记的 key 与读写全部搬到
 * `mock-routes.ts`（那里是唯一一份），本文件因此不再自己"判开关 + 造对象"，只管发请求——
 * 于是 mock 态也照样跑 `normalizeMeData` 这条真实归一化路径。
 * 唯一保留的分支是 `authLogin`：那不是一次 HTTP 调用（后端回 302 到主平台 authorize，
 * fetch 跟不上跨域授权链，必须整页跳转），路由表表达不了，所以读 `isMockMode()` 这个
 * 唯一谓词口——**开关的表达式仍然只有一处**，这里只是它的消费者。
 */

import { isMockMode, request } from "./http";
import { mockMarkLoggedIn } from "./mock-routes";
import { normalizeMeData, type MeData } from "./types";

/**
 * 登录入口。真实态：整页跳转 /api/v1/auth/login（后端 302 至主平台 authorize，
 * 会话由服务端 cookie 建立，前端不读不存 token）；mock 态：写本地标记后刷新。
 */
export function authLogin(): void {
  if (isMockMode()) {
    mockMarkLoggedIn();
    window.location.reload();
    return;
  }
  // 必须整页跳转：该端点返回 302，fetch 无法跟随跨域授权链
  window.location.href = "/api/v1/auth/login";
}

/**
 * GET /api/v1/auth/me。
 * 未登录（10001/10101）或网络失败均抛 ApiError，由调用方（AuthContext）
 * 统一回落未登录态，禁止白屏。演示态的 10001 由表里那条 handler 抛，同码同文。
 */
export async function authMe(): Promise<MeData> {
  // 载荷按未知形状接收（真实为嵌套 {user,wallet}，mock 为扁平），统一归一化
  return request<Record<string, unknown>>("/api/v1/auth/me").then(normalizeMeData);
}

/** POST /api/v1/auth/logout —— 撤销服务端会话；mock 态由表里的 handler 清本地标记 */
export async function authLogout(): Promise<void> {
  await request<null>("/api/v1/auth/logout", { method: "POST" });
}
