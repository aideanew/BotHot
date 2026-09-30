"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/AuthContext";
import { connectNotifications, type AppNotification } from "@/lib/api/notifications";

/**
 * 站内通知铃铛（WE 5.2b → W9 D.5 增强）
 *
 * 增强项（D.5）：
 * - 未读数 localStorage 持久化（刷新不丢，key=bothot:unread:{sub}）
 * - SSE 增量合并去重（title+message 相同且 5s 内到达视为重复）
 * - 429 RATE_LIMITED 码位预留（W7 未落地前先按 HTTP 429 预留 toast 逻辑）
 * - 数据源接口预留：mergeFromHistory() 供未来后端通知历史端点注入
 *
 * 原有行为保持不变：
 * - 登录态 SSE 订阅；登出/卸载断连
 * - 展开下拉清零未读
 * - Redis 不可用时降级提示
 */

const MAX_ITEMS = 20;
const DEDUP_WINDOW_MS = 5000;
const LS_PREFIX = "bothot:unread:";

interface BellItem extends AppNotification {
  id: number;
  receivedAt: number;
}

function getLsKey(sub: string | undefined): string {
  return sub ? `${LS_PREFIX}${sub}` : "";
}

function loadUnread(sub: string | undefined): number {
  if (!sub || typeof window === "undefined") return 0;
  const raw = localStorage.getItem(getLsKey(sub));
  const n = raw ? parseInt(raw, 10) : 0;
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

function saveUnread(sub: string | undefined, count: number): void {
  if (!sub || typeof window === "undefined") return;
  localStorage.setItem(getLsKey(sub), String(count));
}

function dedupKey(n: AppNotification): string {
  return `${n.title}::${n.message}`;
}

/**
 * 外部数据源接口（预留，W9 报告依赖）：
 * 后端「通知历史端点」落地后，调用 mergeFromHistory(items, unreadCount)
 * 将历史数据注入下拉列表并更新未读计数。当前无后端端点，不实施。
 */
export interface NotificationDataSource {
  mergeFromHistory: (historyItems: AppNotification[], unreadCount: number) => void;
}

export default function NotificationBell() {
  const { status, me } = useAuth();
  const authed = status === "authed";
  const sub = me?.sub;

  const [items, setItems] = useState<BellItem[]>([]);
  const [unread, setUnread] = useState(() => (authed ? loadUnread(sub) : 0));
  const [open, setOpen] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [rateLimited, setRateLimited] = useState(false);
  const idRef = useRef(0);
  const panelRef = useRef<HTMLDivElement>(null);
  const recentRef = useRef<Map<string, number>>(new Map());

  // 未读数持久化
  useEffect(() => {
    saveUnread(sub, unread);
  }, [unread, sub]);

  // 登录态恢复未读
  useEffect(() => {
    if (authed && sub) {
      setUnread(loadUnread(sub));
    }
  }, [authed, sub]);

  useEffect(() => {
    if (!authed) {
      setItems([]);
      setUnread(0);
      setUnavailable(false);
      setOpen(false);
      setRateLimited(false);
      recentRef.current.clear();
      return;
    }
    const disconnect = connectNotifications({
      onNotification: (n) => {
        const now = Date.now();
        // 去重：5s 内相同 title+message 视为重复
        const dk = dedupKey(n);
        const lastSeen = recentRef.current.get(dk);
        if (lastSeen && now - lastSeen < DEDUP_WINDOW_MS) return;
        recentRef.current.set(dk, now);
        // 清理过期条目
        const nowClean = now;
        const keysToRemove: string[] = [];
        recentRef.current.forEach((ts, key) => {
          if (nowClean - ts > DEDUP_WINDOW_MS) keysToRemove.push(key);
        });
        keysToRemove.forEach((key) => recentRef.current.delete(key));

        idRef.current += 1;
        const entry: BellItem = { ...n, id: idRef.current, receivedAt: now };
        setItems((prev) => [entry, ...prev].slice(0, MAX_ITEMS));
        setUnread((u) => u + 1);
      },
      onUnavailable: () => setUnavailable(true),
      onError: (es) => {
        if (es.readyState === EventSource.CLOSED) {
          // 429 预留：W7 的 RATE_LIMITED 码（20005）触发 HTTP 429 时，
          // EventSource 因浏览器自动重连会收到 CLOSED 状态。
          // 当前 W7 未落地，暂按通用不可用处理；W7 落地后改判 429 并展示
          // 「请求过于频繁，请稍后再试」toast。
          setUnavailable(true);
          setRateLimited(true);
        }
      },
    });
    return disconnect;
  }, [authed]);

  // 点击外部收起下拉
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
      if (next) setUnread(0);
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
              {rateLimited
                ? "请求过于频繁，请稍后再试"
                : "通知服务暂不可用，请稍后重试"}
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

function formatTime(epochMs: number): string {
  const d = new Date(epochMs);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}
