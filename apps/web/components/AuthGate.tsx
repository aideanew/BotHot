"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useAuth } from "@/components/AuthContext";

/**
 * AuthGate —— 受保护页统一未登录守卫（G1.1，2026-10-10 裁定落地）
 *
 * 背景（证据链）：未登录处理此前散装六形态并存——subscriptions/jobs 的
 * `return null` 整页白屏、engines/public/bots 无守卫裸调 API（401 后错误壳）、
 * spaces/chat/onboarding/spaces/[id] 的 `router.replace("/")` 跳首页、
 * admin 的 loading/guest 不分（guest 永久显示"正在加载…"）。本组件收敛为
 * 唯一形态：原地渲染统一提示卡，不跳转（保留 URL 上下文，登录后继续原操作）。
 *
 * 三态渲染（对齐 AuthContext 的 loading|guest|authed）：
 * - loading → 骨架占位卡（样式口径取自 spaces/[id] 既有骨架，禁白屏）；
 * - guest   → 统一提示卡：文案锚点"尚未登录或会话已过期" + 登录按钮
 *             （useAuth().login——mock 态写标记后 reload，真实态整页跳 SSO，
 *             与首页引导卡同源）+ "返回首页"出口；
 * - authed  → 原样渲染 children。
 *
 * 会话过期（authed→guest 掉落）由 AuthContext 失败回落路径驱动，本组件
 * 自动切卡，无需页面侧任何额外代码（G3.2 有 vitest 锁定该行为）。
 *
 * 边界说明：本组件只做**渲染层**守卫，页面内数据 hook 若在 mount 即发请求，
 * 需自带 status 门（useSubscriptions/useJobsList/useSpaceDetail 已有；
 * engines/public/bots 接入时已补）——AuthGate 不是请求拦截器。
 */
export default function AuthGate({ children }: { children: ReactNode }) {
  const { status, login } = useAuth();

  if (status === "loading") {
    return (
      <main className="mx-auto max-w-5xl px-4 py-10">
        <div className="card p-8">
          <div className="h-6 w-40 animate-pulse rounded bg-neutral-200" />
          <div className="mt-3 h-4 w-2/3 animate-pulse rounded bg-neutral-100" />
          <div className="mt-5 h-4 w-48 animate-pulse rounded bg-neutral-100" />
        </div>
      </main>
    );
  }

  if (status === "guest") {
    return (
      <main className="mx-auto flex min-h-[60vh] max-w-3xl flex-col items-center justify-center px-4 py-16 text-center">
        <div className="card mx-auto max-w-md p-10">
          <p className="eyebrow">AUTH REQUIRED</p>
          <h1 className="mt-2 text-title-lg font-semibold text-neutral-900">
            尚未登录或会话已过期
          </h1>
          <p className="mt-3 text-base text-neutral-500">
            请登录后查看本页内容，登录后将回到当前页面。
          </p>
          <div className="mt-8 flex flex-col items-center gap-3">
            <button
              type="button"
              onClick={login}
              className="rounded-input bg-brand-500 px-6 py-2 text-base font-medium text-white hover:bg-brand-600"
            >
              使用主平台账号登录
            </button>
            <Link
              href="/"
              className="text-caption text-neutral-400 hover:text-neutral-600"
            >
              返回首页
            </Link>
          </div>
        </div>
      </main>
    );
  }

  return <>{children}</>;
}
