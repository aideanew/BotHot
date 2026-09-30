"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/AuthContext";
import { connectNotifications, type AppNotification } from "@/lib/api/notifications";

/**
 * 站内通知铃铛（WE 5.2b）
 *
 * - 顶栏铃铛 + 未读计数徽标 + 下拉最近列表；风格对齐 TopBar（neutral/brand 配色、
 *   text-caption、rounded），不引入新 UI 库。
 * - 数据源：EventSource（SSE）订阅后端 /api/v1/system/notifications（见 notifications.ts）。
 * - 生命周期：登录态（status==="authed"）才连接；登出（→guest）或卸载即断连
 *   （effect 依赖 status，cleanup 关闭 EventSource）。
 * - 未读：新通知入列时计数 +1（最新在前，上限 MAX_ITEMS）；展开下拉清零。
 * - 降级：后端回报 Redis 不可用时，下拉顶部提示「通知服务暂不可用」，不崩渲染。
 */

const MAX_ITEMS = 20;

interface BellItem extends AppNotification {
  id: number;
  receivedAt: number;
}

export default function NotificationBell() {
  const { status } = useAuth();
  const authed = status === "authed";

  const [items, setItems] = useState<BellItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const idRef = useRef(0);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!authed) {
      // 未登录/登出：断开订阅并清空视图（下次登录重新连接）
      setItems([]);
      setUnread(0);
      setUnavailable(false);
      setOpen(false);
      return;
    }
    const disconnect = connectNotifications({
      onNotification: (n) => {
        idRef.current += 1;
        const entry: BellItem = { ...n, id: idRef.current, receivedAt: Date.now() };
        setItems((prev) => [entry, ...prev].slice(0, MAX_ITEMS));
        setUnread((u) => u + 1);
      },
      onUnavailable: () => setUnavailable(true),
      // EventSource readyState CLOSED（CONNECTING/OPEN 浏览器会自动重连，故不主动干预）
      onError: (es) => {
        if (es.readyState === EventSource.CLOSED) setUnavailable(true);
      },
    });
    return disconnect;
  }, [authed]);

  // 点击外部收起下拉（轻量，不引第三方 hook）
  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const toggle = useCallback(() => {
    setOpen((o) => {
      const next = !o;
      if (next) setUnread(0); // 展开即视为已读
      return next;
    });
  }, []);

  if (!authed) return null;

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={toggle}
        aria-label={unread > 0 ? `通知，${unread} 条未读` : "通知"}
        aria-expanded={open}
        className="relative flex h-9 w-9 items-center justify-center rounded-full text-neutral-500 transition hover:bg-neutral-100 hover:text-neutral-700"
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unread > 0 && (
          <span
            className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand-500 px-1 text-[10px] font-semibold leading-none text-white"
            aria-hidden="true"
          >
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-[0_8px_28px_rgba(15,23,42,0.12)]">
          <div className="flex items-center justify-between border-b border-neutral-100 px-3 py-2">
            <span className="text-caption font-semibold text-neutral-700">通知</span>
            <span className="text-caption text-neutral-400">{items.length} 条</span>
          </div>
          {unavailable && (
            <div className="border-b border-amber-100 bg-amber-50 px-3 py-2 text-caption text-amber-700">
              通知服务暂不可用，请稍后重试
            </div>
          )}
          {items.length === 0 ? (
            <div className="px-3 py-8 text-center text-caption text-neutral-400">暂无通知</div>
          ) : (
            <ul className="max-h-80 divide-y divide-neutral-100 overflow-y-auto">
              {items.map((it) => (
                <li key={it.id} className="px-3 py-2.5 hover:bg-neutral-50">
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="truncate text-base font-medium text-neutral-900">{it.title}</p>
                    <span className="shrink-0 text-[11px] text-neutral-400">
                      {formatTime(it.receivedAt)}
                    </span>
                  </div>
                  <p className="mt-0.5 line-clamp-2 text-caption text-neutral-500">{it.message}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/** 展示用时刻：HH:MM（24h）。仅在客户端下拉展开时渲染，无 SSR 水合风险。 */
function formatTime(epochMs: number): string {
  const d = new Date(epochMs);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}
