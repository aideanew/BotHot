/**
 * SubscribeShortcut —— T1.3.1「订阅此号」快捷入口（空间详情页内嵌）。
 *
 * 定位（大纲 §8.2 N6 注记）：采集方式统一入口 = 详情页「订阅此号」快捷入口，
 * 复用订阅页（/subscriptions）既有能力，但**本空间已预选**，无需再挑目标空间：
 *   ① `POST /sources {biz|profile_url}` 注册公众号 Source（幂等）；
 *   ② `POST /spaces/{id}/subscriptions {source_id, sync_policy:"auto"}` 订阅整号（幂等）。
 * 成功后给出跳转订阅页查看进度的入口（进度真相在 /subscriptions 的 Job 轮询，本卡不重复记账）。
 */
"use client";

import { useState } from "react";
import {
  ApiError,
  registerSource,
  subscribeToSource,
  type SubscribeResult,
} from "@/lib/api";

interface Props {
  /** 目标空间 id（详情页当前空间，已预选） */
  spaceId: string;
  /** 订阅成功回调（刷新订阅相关面板等） */
  onSubscribed?: (result: SubscribeResult) => void;
}

export default function SubscribeShortcut({ spaceId, onSubscribed }: Props) {
  const [bizInput, setBizInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<{
    name: string;
    biz: string;
    created: boolean;
  } | null>(null);

  const handleSubscribe = async () => {
    const biz = bizInput.trim();
    if (!biz) {
      setError("请输入公众号 biz 或 profile URL");
      return;
    }
    setBusy(true);
    setError("");
    setDone(null);
    try {
      const src = await registerSource({ biz });
      const r = await subscribeToSource(spaceId, src.sourceId);
      setDone({ name: src.name || src.biz, biz: src.biz, created: r.created });
      setBizInput("");
      onSubscribed?.(r);
    } catch (e) {
      if (e instanceof ApiError && (e.code === 30004 || e.code === 30101)) {
        setError("空间或信息源不存在，请检查后重试");
      } else if (e instanceof ApiError && e.code === 10001) {
        setError("登录已过期，请重新登录");
      } else {
        setError("订阅失败，请稍后重试");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card border border-neutral-200 bg-white p-4">
      <div className="mb-3">
        <p className="eyebrow">订阅此号</p>
        <p className="mt-1 text-caption text-neutral-400">
          输入公众号 biz 或 profile URL，整号订阅到当前空间；新文章由后台调度器按同步间隔增量采集
          （需已配置 REDFOX_API_KEY，未配置时不会有任何产出）。
        </p>
      </div>

      <div className="flex gap-2">
        <input
          value={bizInput}
          onChange={(e) => setBizInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !busy) void handleSubscribe();
          }}
          placeholder="Mz…（biz）或 https://redfox.hk/…"
          aria-label="公众号 biz 或 profile URL"
          className="flex-1 rounded-input border border-neutral-300 px-3 py-2 text-base outline-none focus:border-brand-500"
        />
        <button
          type="button"
          onClick={handleSubscribe}
          disabled={busy}
          className="shrink-0 rounded bg-brand-600 px-4 py-2 text-base font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {busy ? "订阅中…" : "订阅此号"}
        </button>
      </div>

      {error && <p className="mt-2 text-caption text-red-600">{error}</p>}

      {done && (
        <p className="mt-2 text-caption text-green-700">
          {done.created ? "已订阅「" : "「"}
          {done.name}
          {done.created
            ? "」，已登记后台同步计划，按同步间隔增量采集新文章。"
            : "」已在订阅列表中（幂等，未重复创建；重复点击不会重新触发采集，需等下一个同步间隔）。"}
          <a href="/subscriptions" className="ml-2 text-brand-600 hover:underline">
            查看订阅进度 →
          </a>
        </p>
      )}
    </div>
  );
}
