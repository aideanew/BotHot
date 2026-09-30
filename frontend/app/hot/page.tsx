"use client";

/**
 * 热点信息流页面。
 *
 * 展示热点事件、文章、日报的 Feed 流。
 * 支持按类型筛选（热点/文章/日报）和分类筛选。
 */

import { useCallback, useEffect, useState } from "react";
import {
  getFeed,
  listHotTopics,
  triggerCluster,
  type FeedItem,
  type HotTopic,
} from "@/lib/api/hot";
import { usePageTitle } from "@/components/usePageTitle";
import { useAuth } from "@/components/AuthContext";

const ITEM_TYPE_LABELS: Record<string, string> = {
  article: "文章",
  hot_topic: "热点",
  daily_report: "日报",
  system: "系统",
};

const STATUS_COLORS: Record<string, string> = {
  rising: "bg-yellow-100 text-yellow-700",
  hot: "bg-red-100 text-red-700",
  cooling: "bg-blue-100 text-blue-700",
  archived: "bg-gray-100 text-gray-500",
};

const STATUS_LABELS: Record<string, string> = {
  rising: "上升中",
  hot: "热门",
  cooling: "降温中",
  archived: "已归档",
};

/** 状态过滤候选（4.4c）：与 STATUS_LABELS 同集。 */
const STATUS_FILTERS = ["rising", "hot", "cooling", "archived"] as const;

export default function HotPage() {
  const { status, me } = useAuth();
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [topics, setTopics] = useState<HotTopic[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filterType, setFilterType] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  // 4.4 热点区：状态过滤 + 聚簇触发提示
  const [topicStatus, setTopicStatus] = useState("");
  const [clustering, setClustering] = useState(false);
  const [clusterMsg, setClusterMsg] = useState("");
  // admin 面唯一门禁信号是 is_admin（后端 require_roles("admin","operator")，
  // 但 /auth/me 契约只回显 is_admin，operator 秩无法在纯前端区分——见交付说明）。
  const canCluster = status === "authed" && me?.is_admin === true;

  const fetchFeed = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await getFeed({
        item_type: filterType || undefined,
        page,
        page_size: 20,
      });
      setFeed(res.items || []);
      setTotal(res.total || 0);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载 Feed 失败");
    } finally {
      setLoading(false);
    }
  }, [filterType, page]);

  const fetchTopics = useCallback(async () => {
    try {
      const res = await listHotTopics({
        status: topicStatus || undefined,
        page: 1,
        page_size: 10,
      });
      setTopics(res.items || []);
    } catch {
      // 静默失败，Feed 是主内容
    }
  }, [topicStatus]);

  useEffect(() => {
    fetchFeed();
  }, [fetchFeed]);

  useEffect(() => {
    fetchTopics();
  }, [fetchTopics]);

  // 初次挂载读 URL query（status 参数可选同步，刷新/分享链接保留过滤态）
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("status");
    if (q && (STATUS_FILTERS as readonly string[]).includes(q)) {
      setTopicStatus(q);
    }
  }, []);

  // 状态徒章点击切换过滤，并同步 URL query（replaceState 不触发路由重渲染）
  const handleTopicStatusFilter = (next: string) => {
    const value = topicStatus === next ? "" : next;
    setTopicStatus(value);
    const sp = new URLSearchParams(window.location.search);
    if (value) sp.set("status", value);
    else sp.delete("status");
    const query = sp.toString();
    window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
  };

  const handleCluster = async () => {
    setClustering(true);
    setClusterMsg("");
    try {
      const res = await triggerCluster();
      // W2 异步语义：响应 {queued:true} → 提示「已入队」而非「已完成」
      setClusterMsg(
        res.queued === false
          ? `⚠️ 聚簇未能入队：${res.message || "请稍后重试"}`
          : `✅ 聚簇任务已入队（${res.message || "完成后自动更新热点"}）`,
      );
    } catch (e: unknown) {
      setClusterMsg(`❌ 触发聚簇失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setClustering(false);
    }
  };

  usePageTitle("热点中心");

  // 热度条形可视化基准（4.4b）：以当前展示集的最高分为满格，纯 CSS 宽度比例
  const maxScore = topics.reduce((m, t) => Math.max(m, t.hot_score), 0);

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">热点中心</h1>
          <p className="mt-1 text-sm text-gray-600">
            实时热点聚簇、信息流与每日日报
          </p>
        </div>
        {/* 4.4a admin/operator 可见的触发聚簇按钮（入队语义提示） */}
        {canCluster && (
          <button
            onClick={handleCluster}
            disabled={clustering}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {clustering ? "入队中..." : "触发聚簇"}
          </button>
        )}
      </div>

      {clusterMsg && (
        <div className="mb-4 rounded border border-blue-300 bg-blue-50 p-3 text-sm text-blue-700">
          {clusterMsg}
        </div>
      )}

      {error && (
        <div className="mb-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* TOP 热点卡片 */}
      {topics.length > 0 && (
        <div className="mb-6">
          <h2 className="mb-3 text-sm font-semibold text-gray-700">🔥 今日热点 TOP 10</h2>
          {/* 4.4c 状态徽章点击过滤 */}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <button
              onClick={() => handleTopicStatusFilter("")}
              className={`rounded px-2.5 py-1 text-xs ${
                topicStatus === ""
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              全部
            </button>
            {STATUS_FILTERS.map((s) => (
              <button
                key={s}
                onClick={() => handleTopicStatusFilter(s)}
                aria-pressed={topicStatus === s}
                className={`rounded px-2.5 py-1 text-xs ring-1 ring-transparent ${
                  STATUS_COLORS[s]
                } ${topicStatus === s ? "ring-blue-400" : "hover:opacity-80"}`}
              >
                {STATUS_LABELS[s]}
              </button>
            ))}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {topics.map((t, i) => {
              const heatPct = maxScore > 0 ? Math.round((t.hot_score / maxScore) * 100) : 0;
              return (
              <div
                key={t.id}
                className="rounded-lg border border-gray-200 p-4 hover:shadow-md"
              >
                <div className="flex items-start justify-between">
                  <span className="mr-2 text-lg font-bold text-gray-400">#{i + 1}</span>
                  <div className="flex-1">
                    <h3 className="font-medium text-gray-900">{t.title}</h3>
                    {t.summary && (
                      <p className="mt-1 line-clamp-2 text-sm text-gray-600">{t.summary}</p>
                    )}
                    <div className="mt-2 flex items-center gap-3 text-xs text-gray-500">
                      <span
                        className={`rounded px-1.5 py-0.5 ${
                          STATUS_COLORS[t.status] || "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {STATUS_LABELS[t.status] || t.status}
                      </span>
                      <span>🔥 {t.hot_score.toFixed(1)}</span>
                      <span>来源 {t.source_count}</span>
                      <span>文章 {t.article_count}</span>
                      {t.category && <span>· {t.category}</span>}
                    </div>
                    {/* 热度比例条（无图表库，纯 CSS 宽度） */}
                    <div
                      className="mt-2 h-1.5 w-full rounded bg-gray-100"
                      role="progressbar"
                      aria-label="热度"
                      aria-valuenow={heatPct}
                      aria-valuemin={0}
                      aria-valuemax={100}
                    >
                      <div
                        className="h-1.5 rounded bg-gradient-to-r from-orange-400 to-red-500"
                        style={{ width: `${heatPct}%` }}
                      />
                    </div>
                  </div>
                </div>
              </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 类型筛选 */}
      <div className="mb-4 flex gap-2">
        <button
          onClick={() => {
            setFilterType("");
            setPage(1);
          }}
          className={`rounded px-3 py-1.5 text-sm ${
            !filterType ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
          }`}
        >
          全部
        </button>
        {Object.entries(ITEM_TYPE_LABELS).map(([key, label]) => (
          <button
            key={key}
            onClick={() => {
              setFilterType(key);
              setPage(1);
            }}
            className={`rounded px-3 py-1.5 text-sm ${
              filterType === key
                ? "bg-blue-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Feed 列表 */}
      {loading ? (
        <div className="py-12 text-center text-gray-500">加载中...</div>
      ) : feed.length === 0 ? (
        <div className="py-12 text-center text-gray-500">
          暂无内容。触发聚簇或生成日报后，内容会出现在这里。
        </div>
      ) : (
        <div className="space-y-3">
          {feed.map((item) => (
            <div
              key={item.id}
              className={`rounded-lg border p-4 hover:shadow-md ${
                item.is_pinned ? "border-blue-300 bg-blue-50/30" : "border-gray-200"
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  {item.is_pinned && (
                    <span className="mr-2 rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-700">
                      📌 置顶
                    </span>
                  )}
                  <span className="mr-2 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
                    {ITEM_TYPE_LABELS[item.item_type] || item.item_type}
                  </span>
                  {item.category && (
                    <span className="text-xs text-gray-500">· {item.category}</span>
                  )}
                  <h3 className="mt-1 font-medium text-gray-900">{item.title}</h3>
                  {item.summary && (
                    <p className="mt-1 line-clamp-2 text-sm text-gray-600">{item.summary}</p>
                  )}
                  <div className="mt-2 flex items-center gap-3 text-xs text-gray-500">
                    {item.source_name && <span>来源: {item.source_name}</span>}
                    {item.score > 0 && <span>🔥 {item.score.toFixed(1)}</span>}
                    {item.created_at && (
                      <span>{item.created_at.slice(0, 19).replace("T", " ")}</span>
                    )}
                  </div>
                </div>
                {item.url && (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-4 flex-shrink-0 text-sm text-blue-600 hover:text-blue-800"
                  >
                    查看原文 →
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 分页 */}
      {total > 20 && (
        <div className="mt-4 flex items-center justify-between">
          <span className="text-sm text-gray-600">共 {total} 条</span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="rounded border px-3 py-1 text-sm disabled:opacity-50"
            >
              上一页
            </button>
            <span className="px-3 py-1 text-sm">第 {page} 页</span>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={page * 20 >= total}
              className="rounded border px-3 py-1 text-sm disabled:opacity-50"
            >
              下一页
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
