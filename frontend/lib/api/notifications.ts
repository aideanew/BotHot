/**
 * lib/api/notifications —— 站内通知订阅（WE 5.2a）
 *
 * 传输：EventSource（SSE）。EventSource 不支持自定义 header，身份靠同源会话
 * cookie 随请求走——`withCredentials: true` 与 http.ts `request` 的
 * `credentials: "include"` 同口径（SSO 锚点 = users.sub，服务端 HttpOnly cookie）。
 * 端点：GET /api/v1/system/notifications（须登录；Redis 不可达时后端转发
 * {"type":"service_unavailable"} 控制帧优雅降级，不 500）。
 *
 * 载荷契约（与 providers/push/web.py 发布体一一对应）：
 *   通知帧 {title, message, url, space_id, doc_id}；
 *   （mock 态不建连——connectNotifications 的 MOCK_ENABLED 门）
 *   控制帧 {type: "service_unavailable" | ...}（含 type 键即控制帧，非通知）。
 * 心跳（": ping" 注释行）由 EventSource 自动忽略，不经 onmessage。
 */

import { MOCK_ENABLED } from "./http";

/** 后端 web provider 发布的站内通知载荷 */
export interface AppNotification {
  title: string;
  message: string;
  url?: string;
  space_id?: string;
  doc_id?: string;
}

/** SSE 端点路径（同源相对，EventSource 依 document base 解析） */
export const NOTIFICATIONS_ENDPOINT = "/api/v1/system/notifications";

/**
 * 解析一条 SSE data 帧。返回：
 *  - {kind:"notification", notification}：正常站内通知；
 *  - {kind:"control", type, message}：后端控制帧（如 service_unavailable）；
 *  - {kind:"ignore"}：非 JSON / 无法识别的帧（安全忽略，绝不抛穿渲染期）。
 */
export function parseNotificationFrame(
  raw: string
):
  | { kind: "notification"; notification: AppNotification }
  | { kind: "control"; type: string; message: string }
  | { kind: "ignore" } {
  let obj: unknown;
  try {
    obj = JSON.parse(raw);
  } catch {
    return { kind: "ignore" };
  }
  if (obj === null || typeof obj !== "object") {
    return { kind: "ignore" };
  }
  const rec = obj as Record<string, unknown>;
  // 含 type 键 → 控制帧（web provider 通知载荷无 type 字段）
  if (typeof rec.type === "string") {
    return {
      kind: "control",
      type: rec.type,
      message: typeof rec.message === "string" ? rec.message : "",
    };
  }
  if (typeof rec.title === "string" || typeof rec.message === "string") {
    return {
      kind: "notification",
      notification: {
        title: typeof rec.title === "string" ? rec.title : "BotHot 通知",
        message: typeof rec.message === "string" ? rec.message : "",
        url: typeof rec.url === "string" ? rec.url : undefined,
        space_id: typeof rec.space_id === "string" ? rec.space_id : undefined,
        doc_id: typeof rec.doc_id === "string" ? rec.doc_id : undefined,
      },
    };
  }
  return { kind: "ignore" };
}

export interface NotificationHandlers {
  /** 收到一条站内通知 */
  onNotification: (n: AppNotification) => void;
  /** 后端回报服务不可用（Redis 未配置/不可达）——用于展示降级提示 */
  onUnavailable?: (message: string) => void;
  /** EventSource 连接错误（浏览器会在可恢复时自动重连；CLOSED 为致命，如 401） */
  onError?: (es: EventSource) => void;
  /** 连接建立（readyState → OPEN） */
  onOpen?: () => void;
}

/**
 * 建立站内通知订阅，返回一个关闭函数（幂等）。
 * 仅在浏览器环境调用（SSR 下 typeof EventSource === "undefined" → no-op）。
 * 调用方（组件）负责在登出/卸载时执行返回的 close。
 */
export function connectNotifications(handlers: NotificationHandlers): () => void {
  if (typeof window === "undefined" || typeof EventSource === "undefined") {
    return () => {};
  }
  // mock 态（演示数据，next build 产物内联 NEXT_PUBLIC_API_MOCK=true）不建 SSE：
  // EventSource 绕开 http.ts 的 MOCK 网关，会真打 /api/v1 被 rewrite 代理到
  // 不存在的后端（2026-09-30 CI mock e2e 实证 → console error → trunk.spec 红）。
  // vitest（NODE_ENV=test）豁免本门：W9 的 SSE 行为测试以 stub EventSource
  // 验证连接生命周期，门短路会让 stub 永不被触达（2026-10-08 本地回归实证，
  // w9-notification-enhance.spec 4 例全红）；mock e2e 跑 build 产物
  // （NODE_ENV=production），门在该场景保持生效。
  if (MOCK_ENABLED && process.env.NODE_ENV !== "test") {
    return () => {};
  }
  const es = new EventSource(NOTIFICATIONS_ENDPOINT, { withCredentials: true });

  es.onopen = () => handlers.onOpen?.();
  es.onmessage = (ev: MessageEvent<string>) => {
    const parsed = parseNotificationFrame(ev.data);
    if (parsed.kind === "notification") {
      handlers.onNotification(parsed.notification);
    } else if (parsed.kind === "control") {
      if (parsed.type === "service_unavailable") {
        handlers.onUnavailable?.(parsed.message);
      }
    }
  };
  es.onerror = () => handlers.onError?.(es);

  return () => {
    try {
      es.close();
    } catch {
      /* 已关闭则忽略 */
    }
  };
}
