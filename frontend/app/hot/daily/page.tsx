"use client";

/**
 * 每日热点日报页面。
 *
 * 功能：
 * - 日报列表（按日期倒序）
 * - 查看日报详情（Markdown 渲染）
 * - 手动生成日报
 */

import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  generateDailyReport,
  getDailyReport,
  listDailyReports,
  type DailyReport,
  type DailyReportDetail,
} from "@/lib/api/hot";
import { usePageTitle } from "@/components/usePageTitle";

const PAGE_SIZE = 10;

export default function DailyReportPage() {
  const [reports, setReports] = useState<DailyReport[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [detail, setDetail] = useState<DailyReportDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  const fetchReports = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await listDailyReports({ page, page_size: PAGE_SIZE });
      setReports(res.items || []);
      setTotal(res.total || 0);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载日报列表失败");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  usePageTitle("每日热点日报");

  const handleViewReport = async (date: string) => {
    setSelectedDate(date);
    setDetailLoading(true);
    try {
      const d = await getDailyReport(date);
      setDetail(d);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载日报详情失败");
    } finally {
      setDetailLoading(false);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setError("");
    try {
      await generateDailyReport();
      fetchReports();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "生成日报失败（可能今日日报已存在）");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">每日热点日报</h1>
          <p className="mt-1 text-sm text-gray-600">
            自动聚簇当日 TOP 10 热点，生成 Markdown 日报
          </p>
        </div>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {generating ? "生成中..." : "生成今日日报"}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-3">
        {/* 日报列表 */}
        <div className="md:col-span-1">
          <h2 className="mb-3 text-sm font-semibold text-gray-700">历史日报</h2>
          {loading ? (
            <div className="py-8 text-center text-gray-500">加载中...</div>
          ) : reports.length === 0 ? (
            <div className="py-8 text-center text-gray-500">
              暂无日报，点击&ldquo;生成今日日报&rdquo;创建第一份。
            </div>
          ) : (
            <div className="space-y-2">
              {reports.map((r) => (
                <button
                  key={r.id}
                  onClick={() => handleViewReport(r.report_date)}
                  className={`block w-full rounded-lg border p-3 text-left hover:shadow-md ${
                    selectedDate === r.report_date
                      ? "border-blue-400 bg-blue-50"
                      : "border-gray-200"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-gray-900">{r.report_date}</span>
                    <span
                      className={`rounded px-1.5 py-0.5 text-xs ${
                        r.status === "published"
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {r.status === "published" ? "已发布" : r.status}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-gray-500">
                    {r.topic_count} 个热点 · {r.generated_by === "manual" ? "手动" : "自动"}
                  </p>
                </button>
              ))}
            </div>
          )}

          {/* 4.5b 列表分页（复用 /bots 列表分页交互模式） */}
          {total > PAGE_SIZE && (
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
                <span className="px-2 py-1 text-sm">
                  第 {page} / {Math.max(1, Math.ceil(total / PAGE_SIZE))} 页
                </span>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page * PAGE_SIZE >= total}
                  className="rounded border px-3 py-1 text-sm disabled:opacity-50"
                >
                  下一页
                </button>
              </div>
            </div>
          )}
        </div>

        {/* 日报详情 */}
        <div className="md:col-span-2">
          {selectedDate ? (
            detailLoading ? (
              <div className="py-12 text-center text-gray-500">加载日报详情...</div>
            ) : detail ? (
              <div className="rounded-lg border border-gray-200 p-6">
                <h2 className="mb-4 text-xl font-bold">{detail.title}</h2>
                <div className="mb-4 flex items-center gap-3 text-sm text-gray-500">
                  <span>{detail.report_date}</span>
                  <span>· {detail.topic_count} 个热点</span>
                  <span>· {detail.generated_by === "manual" ? "手动生成" : "自动生成"}</span>
                </div>
                <div className="prose prose-sm max-w-none text-gray-700">
                  {/* 4.5a：真实 Markdown 渲染（react-markdown），取代直出源文本 */}
                  <ReactMarkdown>{detail.content_markdown}</ReactMarkdown>
                </div>
              </div>
            ) : (
              <div className="py-12 text-center text-gray-500">加载失败</div>
            )
          ) : (
            <div className="py-12 text-center text-gray-500">
              ← 选择左侧的日报查看详情
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
