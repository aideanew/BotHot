"use client";

/**
 * 热点信息流页面。
 *
 * 展示热点事件、文章、日报的 Feed 流。
 * 支持按类型筛选（热点/文章/日报）和分类筛选。
 */

import { useCallback, useEffect, useState } from "react";
import { getFeed, listHotTopics, type FeedItem, type HotTopic } from "@/lib/api/hot";

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

export default function HotPage() {
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [topics, setTopics] = useState<HotTopic[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filterType, setFilterType] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

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
      const res = await listHotTopics({ page: 1, page_size: 10 });
      setTopics(res.items || []);
    } catch {
      // 静默失败，Feed 是主内容
    }
  }, []);

  useEffect(() => {
    fetchFeed();
  }, [fetchFeed]);

  useEffect(() => {
    fetchTopics();
  }, [fetchTopics]);

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">热点中心</h1>
        <p className="mt-1 text-sm text-gray-600">
          实时热点聚簇、信息流与每日日报
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* TOP 热点卡片 */}
      {topics.length > 0 && (
        <div className="mb-6">
          <h2 className="mb-3 text-sm font-semibold text-gray-700">🔥 今日热点 TOP 10</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {topics.map((t, i) => (
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
                  </div>
                </div>
              </div>
            ))}
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
