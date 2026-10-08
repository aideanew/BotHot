"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { MOCK_LABEL, MOCK_ENABLED } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import NotificationBell from "@/components/NotificationBell";

/**
 * 顶栏（C-T1 建，C-T2 接入会话态）
 * 界面铁律：全页唯一搜索框，全局常驻；对齐主平台的顶部布局。
 * 用户区：未登录显示"未登录"；登录态显示昵称 + 退出按钮。
 */
export default function TopBar() {
  const router = useRouter();
  const { status, me, logout } = useAuth();
  const [keyword, setKeyword] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);

  function handleSearch(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const q = keyword.trim();
    if (!q) return;
    // 统一进聊天流：顶栏搜索框与聊天输入框行为一致（C-T4 落地交互细节）
    router.push(`/chat?q=${encodeURIComponent(q)}`);
  }

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logout();
    } finally {
      setLoggingOut(false);
    }
  }

  return (
    <header className="sticky top-0 z-40 border-b border-neutral-200/80 bg-white/90 shadow-[0_1px_12px_rgba(15,23,42,0.04)] backdrop-blur">
      <div className="mx-auto flex min-h-16 max-w-6xl flex-wrap items-center gap-3 px-4 py-2 sm:flex-nowrap sm:px-6">
        <Link href="/" className="group flex shrink-0 items-center gap-2.5" aria-label="返回 BotHot 首页">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-500 text-white text-title-sm font-bold shadow-[0_5px_12px_rgba(47,128,237,0.28)] transition group-hover:bg-brand-600">
            A
          </span>
          <span className="text-title-sm font-bold tracking-tight text-neutral-900">
            BotHot
          </span>
        </Link>

        {/* AB-P004 P5：主导航（T1.3.2 收口五入口统一心智：空间/订阅/公共库/问答/引擎；
            R0.4.3 增「任务」——任务中心是用户级（跨空间）观测面，不进订阅页） */}
        <nav className="hidden shrink-0 items-center gap-1 sm:flex" aria-label="主导航">
          <Link
            href="/spaces"
            className="rounded px-2 py-1 text-caption text-neutral-500 transition hover:bg-neutral-100 hover:text-neutral-900"
          >
            空间
          </Link>
          <Link
            href="/subscriptions"
            className="rounded px-2 py-1 text-caption text-neutral-500 transition hover:bg-neutral-100 hover:text-neutral-900"
          >
            订阅
          </Link>
          <Link
            href="/jobs"
            className="rounded px-2 py-1 text-caption text-neutral-500 transition hover:bg-neutral-100 hover:text-neutral-900"
          >
            任务
          </Link>
          <Link
            href="/public"
            className="rounded px-2 py-1 text-caption text-neutral-500 transition hover:bg-neutral-100 hover:text-neutral-900"
          >
            公共库
          </Link>
          <Link
            href="/chat"
            className="rounded px-2 py-1 text-caption text-neutral-500 transition hover:bg-neutral-100 hover:text-neutral-900"
          >
            问答
          </Link>
          <Link
            href="/engines"
            className="rounded px-2 py-1 text-caption text-neutral-500 transition hover:bg-neutral-100 hover:text-neutral-900"
          >
            引擎
          </Link>
          <Link
            href="/bots"
            className="rounded px-2 py-1 text-caption text-neutral-500 transition hover:bg-neutral-100 hover:text-neutral-900"
          >
            机器人
          </Link>
          <Link
            href="/hot"
            className="rounded px-2 py-1 text-caption text-neutral-500 transition hover:bg-neutral-100 hover:text-neutral-900"
          >
            热点
          </Link>
          {/* SPEC-M3 批次 2：admin 入口只按 is_admin 门禁——user.role 是主平台
              userinfo 的大写枚举，与本地授权阶梯不同源，拿它门禁会与后端 10004 分歧 */}
          {status === "authed" && me?.is_admin && (
            <Link
              href="/admin"
              className="rounded px-2 py-1 text-caption text-neutral-500 transition hover:bg-neutral-100 hover:text-neutral-900"
            >
              管理
            </Link>
          )}
        </nav>

        <form onSubmit={handleSearch} className="order-3 w-full sm:order-none sm:flex-1">
          <label className="sr-only" htmlFor="global-search">全局搜索</label>
          <div className="relative">
            <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-neutral-400" aria-hidden="true">⌕</span>
            <input
              id="global-search"
              type="search"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="搜索或提问，例如：如何导入文章？"
              aria-label="全局搜索"
              className="w-full rounded-input border border-neutral-200 bg-neutral-50 py-2 pl-9 pr-4 text-base text-neutral-700 outline-none transition placeholder:text-neutral-400 hover:border-neutral-300 focus:border-brand-400 focus:bg-white"
            />
          </div>
        </form>

        <div className="ml-auto flex min-h-9 shrink-0 items-center justify-end gap-2">
          {status === "loading" && (
            <span className="text-caption text-neutral-400">判定中…</span>
          )}
          {status === "guest" && (
            <span className="text-caption text-neutral-400">未登录</span>
          )}
          {status === "authed" && me && (
            <>
              {/* WE 5.2c：站内通知铃铛（仅登录态挂载；登出即卸载并断连 SSE） */}
              <NotificationBell />
              <span
                className="truncate text-base text-neutral-700"
                title={me.email}
              >
                {me.nickname}
              </span>
              <button
                onClick={handleLogout}
                disabled={loggingOut}
                className="shrink-0 rounded-input border border-neutral-300 px-2.5 py-1 text-caption text-neutral-500 transition hover:border-neutral-400 hover:text-neutral-700 disabled:opacity-50"
              >
                {loggingOut ? "退出中…" : "退出"}
              </button>
            </>
          )}
          {/* 数据来源徽标：验收用，确认 mock 开关状态 */}
          <span className="shrink-0 rounded-full bg-neutral-100 px-2 py-0.5 text-caption text-neutral-400">
            {MOCK_ENABLED ? MOCK_LABEL : "真实后端"}
          </span>
        </div>
      </div>
    </header>
  );
}
