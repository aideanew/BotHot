"use client";

import { useSubscriptions } from "@/components/useSubscriptions";
import SubscriptionCard from "@/components/SubscriptionCard";
import { POLL_NET_FAIL_THRESHOLD, networkPauseMessage } from "@/lib/api";
import { usePageTitle } from "@/components/usePageTitle";
import AuthGate from "@/components/AuthGate";

export default function SubscriptionPage() {
  const {
    status,
    spaces, selectedSpaceId, setSelectedSpaceId,
    bizInput, setBizInput,
    registering, actionError,
    subscriptions, jobs, loading, netFailCount,
    loadAll, handleRegisterAndSubscribe, handleRetry, applySubscriptionView,
  } = useSubscriptions();
  usePageTitle("订阅管理");

  // G2.1：guest 态由 AuthGate 统一渲染提示卡（原 `return null` 整页白屏已废除）；
  // hook 层 status 门保证 guest 不发请求。
  return (
    <AuthGate>
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6">
        <p className="eyebrow">SUBSCRIPTIONS</p>
        <h1 className="text-title-lg font-semibold text-neutral-900">订阅管理</h1>
      </div>

      <section className="card p-5">
        <label className="mb-1 block text-caption text-neutral-500">目标空间</label>
        <select
          value={selectedSpaceId}
          onChange={(e) => setSelectedSpaceId(e.target.value)}
          className="mb-3 w-full rounded-input border border-neutral-300 px-3 py-2 text-base outline-none focus:border-brand-500"
        >
          {spaces.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}（{s.docCount} 篇）
            </option>
          ))}
        </select>
        <label className="mb-1 block text-caption text-neutral-500">
          公众号 biz 或 profile URL
        </label>
        <div className="flex gap-2">
          <input
            value={bizInput}
            onChange={(e) => setBizInput(e.target.value)}
            placeholder="Mz…（biz）或 https://redfox.hk/…"
            className="flex-1 rounded-input border border-neutral-300 px-3 py-2 text-base outline-none focus:border-brand-500"
          />
          <button
            type="button"
            onClick={handleRegisterAndSubscribe}
            disabled={registering}
            className="shrink-0 rounded bg-brand-600 px-4 py-2 text-base font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {registering ? "订阅中…" : "订阅公众号"}
          </button>
        </div>
        {actionError && <p className="mt-2 text-caption text-red-600">{actionError}</p>}
      </section>

      {netFailCount >= POLL_NET_FAIL_THRESHOLD && (
        <div className="mt-6 rounded-card border border-red-200 bg-red-50 p-4">
          <p className="text-base text-red-700">
            {networkPauseMessage(netFailCount)}
          </p>
          <button
            onClick={() => void loadAll()}
            className="mt-2 rounded-input border border-red-400 px-3 py-1 text-base text-red-700 hover:bg-red-100"
          >
            重新加载
          </button>
        </div>
      )}

      <section className="mt-6">
        <h2 className="mb-3 text-title-sm font-semibold text-neutral-900">当前订阅</h2>
        {subscriptions.length === 0 ? (
          <div className="card p-8 text-center text-neutral-500">
            暂无订阅，上方填写公众号 biz 即可开始整号入库。
          </div>
        ) : (
          <ul className="space-y-3">
            {subscriptions.map((sub) => (
              <SubscriptionCard
                key={sub.subscriptionId}
                sub={sub}
                job={sub.latestJobId ? jobs[sub.latestJobId] : undefined}
                spaceId={selectedSpaceId}
                onRetry={(jobId) => void handleRetry(jobId)}
                onSubscriptionChange={applySubscriptionView}
              />
            ))}
          </ul>
        )}
      </section>
    </main>
    </AuthGate>
  );
}
