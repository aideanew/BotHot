"use client";

import { useEffect, useState } from "react";
import { listPublicSpaces, listSpaces, type PublicSpace, type Space } from "@/lib/api";
import { useAuth, tierLabel } from "@/components/AuthContext";
import { usePageTitle } from "@/components/usePageTitle";

/**
 * 首页落地页（C-T1 建，C-T2 接入会话态；AB-P004 P5 工作台改造）
 * 两态由 AuthContext 驱动：登录态 → 欢迎语 + 空间列表缩略 + 公共库推荐位；
 * 未登录 → 登录引导卡。任何失败均回落，禁止白屏。
 * P5（SPEC §六 6.2「/ 工作台（改造）」）：空态 CTA「创建第一个知识库」；公共库推荐位；三入口心智统一。
 */
export default function HomePage() {
  const { status, me, login, reload } = useAuth();
  usePageTitle("首页");
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [publicSpaces, setPublicSpaces] = useState<PublicSpace[]>([]);
  const [spacesError, setSpacesError] = useState(false);

  // 空间列表仅登录态加载（C-T3 将做完整列表页与创建流程）
  useEffect(() => {
    if (status !== "authed") return;
    let cancelled = false;
    setSpacesError(false);
    listSpaces()
      .then((list) => {
        if (!cancelled) setSpaces(list);
      })
      .catch(() => {
        if (!cancelled) setSpacesError(true);
      });
    // AB-P004 P5：公共库推荐位（加载失败不阻塞工作台）
    listPublicSpaces()
      .then((list) => {
        if (!cancelled) setPublicSpaces(list);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [status]);

  return (
    <main className="page-shell">
      {status === "loading" && (
        <div className="card mx-auto max-w-2xl p-10 text-center text-neutral-500">正在加载你的知识空间…</div>
      )}

      {status === "guest" && (
        <section className="mx-auto mt-10 grid max-w-4xl overflow-hidden rounded-[20px] border border-neutral-200 bg-white shadow-popover md:grid-cols-[1.05fr_0.95fr] md:mt-16">
          <div className="bg-brand-50 p-8 sm:p-12">
            <p className="eyebrow">PERSONAL KNOWLEDGE HUB</p>
            <h1 className="mt-4 max-w-md text-3xl font-bold tracking-tight text-neutral-900 sm:text-4xl">
              把好文章，变成真正能回答问题的知识。
            </h1>
            <p className="mt-5 max-w-md text-base leading-7 text-neutral-600">
              从公众号链接开始，建立你的专属知识空间，让每一次提问都有来源、有依据。
            </p>
            <div className="mt-8 grid gap-3 text-base text-neutral-700 sm:grid-cols-3 md:grid-cols-1">
              <span>01　收藏优质内容</span>
              <span>02　自动整理入库</span>
              <span>03　基于来源问答</span>
            </div>
          </div>
          <div className="flex flex-col justify-center p-8 sm:p-12">
            <p className="text-caption font-medium text-neutral-400">欢迎回来</p>
            <h2 className="mt-2 text-2xl font-semibold text-neutral-900">登录开始构建</h2>
            <p className="mt-3 text-base leading-6 text-neutral-500">
              使用主平台账号登录，空间和文章会安全地保存在你的账户中。
            </p>
            <button
              onClick={login}
              className="mt-8 w-full rounded-input bg-brand-500 py-3 font-medium text-white shadow-[0_8px_18px_rgba(47,128,237,0.2)] transition hover:bg-brand-600"
            >
              使用主平台账号登录
            </button>
            <p className="mt-4 text-center text-caption text-neutral-400">统一认证，完成后自动返回 BotHot</p>
          </div>
        </section>
      )}

      {status === "authed" && me && (
        <>
          <section className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
            <div>
              <p className="eyebrow">YOUR KNOWLEDGE SPACES</p>
              <h1 className="mt-2 section-title">你好，{me.nickname}</h1>
              <p className="mt-2 muted-copy">从最近的空间继续，或打开全部空间管理内容。</p>
            </div>
            <div className="flex gap-2 text-caption text-neutral-500">
              <span className="rounded-full bg-white px-3 py-1.5 shadow-card">{tierLabel(me.tier)}</span>
              <span className="rounded-full bg-white px-3 py-1.5 shadow-card">
                {me.providerUnreachable ? "余额暂不可查" : `余额 ${me.wallet}`}
              </span>
            </div>
          </section>

          {spacesError ? (
            <div className="status-panel status-panel-error mt-7">
              <p className="font-medium">知识空间加载失败</p>
              <p className="mt-1 text-base">请检查连接后重试。</p>
              <button onClick={reload} className="mt-4 rounded-input bg-white px-4 py-2 text-base font-medium text-red-700 shadow-card hover:bg-red-50">
                重新加载
              </button>
            </div>
          ) : (
            <section className="mt-7">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-title-sm font-semibold text-neutral-900">最近空间</h2>
                <a href="/spaces" className="text-base font-medium text-brand-600 hover:text-brand-700">查看全部 →</a>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {spaces.slice(0, 6).map((s) => (
                  <a key={s.id} href={`/spaces/${s.id}`} className="card group block p-5 transition hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-popover">
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="truncate text-title-sm font-semibold text-neutral-900">{s.name}</h3>
                      <span className="text-brand-500 transition group-hover:translate-x-0.5" aria-hidden="true">↗</span>
                    </div>
                    <p className="mt-3 line-clamp-2 min-h-12 text-base leading-6 text-neutral-500">{s.description || "暂无简介"}</p>
                    <p className="mt-5 text-caption text-neutral-400">{s.docCount} 篇文章</p>
                  </a>
                ))}
                {spaces.length === 0 && (
                  <div className="card col-span-full p-10 text-center">
                    <p className="text-title-sm font-medium text-neutral-900">还没有知识空间</p>
                    <p className="mt-2 text-base text-neutral-500">
                      创建第一个知识库：粘贴一篇公众号文章，或一键引入公共 AI 库。
                    </p>
                    <div className="mt-5 flex justify-center gap-3">
                      <a href="/spaces" className="rounded-input bg-brand-500 px-5 py-2 font-medium text-white hover:bg-brand-600">
                        创建第一个知识库
                      </a>
                      <a href="/subscriptions" className="rounded-input border border-neutral-300 px-5 py-2 font-medium text-neutral-700 hover:bg-neutral-50">
                        订阅公众号
                      </a>
                    </div>
                  </div>
                )}
              </div>
            </section>
          )}
        {/* AB-P004 P5：公共库推荐位（AI前沿库卡 + 去引入引导；SPEC §六 J3 旅程） */}
        {publicSpaces.length > 0 && (
          <section className="mt-6">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-title-sm font-semibold text-neutral-900">公共库推荐</h2>
              <span className="text-caption text-neutral-400">一键引入到你的空间</span>
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {publicSpaces.map((ps) => (
                <a
                  key={ps.id}
                  href={spaces.length > 0 ? `/spaces/${spaces[0].id}` : "/spaces"}
                  className="card block p-5 transition hover:border-brand-200 hover:shadow-popover"
                >
                  <div className="flex items-start justify-between">
                    <p className="text-base font-medium text-neutral-900">📚 {ps.name}</p>
                    <span className="text-caption text-neutral-400">{ps.engine === "builtin" ? "内置引擎" : ps.engine}</span>
                  </div>
                  <p className="mt-2 line-clamp-2 text-base text-neutral-500">{ps.description}</p>
                  <p className="mt-4 text-caption text-neutral-400">
                    {ps.docCount} 篇 · 更新于 {new Date(ps.updatedAt).toLocaleDateString("zh-CN")}
                  </p>
                </a>
              ))}
            </div>
          </section>
        )}
        </>
      )}

      <footer className="mt-14 pb-6 text-center text-caption text-neutral-400">数据来自 {status === "authed" ? "真实后端" : "BotHot"}</footer>
    </main>
  );
}
