/**
 * lib/api/hot —— 热点聚簇与日报 API 模块。
 *
 * 对应后端 /api/v1/hot/* 路由：
 * - 热点列表/详情/聚簇触发
 * - 日报列表/详情/生成
 * - Feed 流
 */

import type { PageResult } from "@bothot/contracts";
import { request } from "./http";

// ---------- 类型 ----------

export interface HotTopic {
  id: string;
  title: string;
  summary: string;
  hot_score: number;
  source_count: number;
  article_count: number;
  status: string;
  topic_date: string;
  category: string;
  created_at: string | null;
}

export interface HotTopicDetail extends HotTopic {
  articles: { asset_id: string; relevance_score: number }[];
}

export interface DailyReport {
  id: string;
  report_date: string;
  title: string;
  topic_count: number;
  status: string;
  generated_by: string;
  created_at: string | null;
}

export interface DailyReportDetail extends DailyReport {
  content_markdown: string;
}

export interface FeedItem {
  id: string;
  item_type: string;
  ref_id: string;
  title: string;
  summary: string;
  source_name: string;
  score: number;
  category: string;
  url: string;
  is_pinned: boolean;
  created_at: string | null;
}

// ---------- 热点 ----------

export async function listHotTopics(params?: {
  category?: string;
  status?: string;
  topic_date?: string;
  page?: number;
  page_size?: number;
}): Promise<PageResult<HotTopic>> {
  const sp = new URLSearchParams();
  if (params?.category) sp.set("category", params.category);
  if (params?.status) sp.set("status", params.status);
  if (params?.topic_date) sp.set("topic_date", params.topic_date);
  if (params?.page) sp.set("page", String(params.page));
  if (params?.page_size) sp.set("page_size", String(params.page_size));
  const query = sp.toString();
  return request(`/api/v1/hot/topics${query ? `?${query}` : ""}`);
}

export async function getHotTopic(id: string): Promise<HotTopicDetail> {
  return request(`/api/v1/hot/topics/${id}`);
}

/**
 * POST /api/v1/hot/topics/cluster —— 触发聚簇（W2 交付后为**异步入队**语义）。
 * 响应 {queued: true, ...}：页面展示「已入队」而非「已完成」；
 * 旧后端同步实现返 triggered，两字段都声明为可选，调用方按 queued 优先判定。
 */
export async function triggerCluster(days?: number): Promise<{
  queued?: boolean;
  triggered?: boolean;
  topic_date?: string;
  days: number;
  message?: string;
}> {
  const sp = new URLSearchParams();
  if (days) sp.set("days", String(days));
  const query = sp.toString();
  return request(`/api/v1/hot/topics/cluster${query ? `?${query}` : ""}`, {
    method: "POST",
  });
}

// ---------- 日报 ----------

export async function listDailyReports(params?: {
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<PageResult<DailyReport>> {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.page) sp.set("page", String(params.page));
  if (params?.page_size) sp.set("page_size", String(params.page_size));
  const query = sp.toString();
  return request(`/api/v1/hot/daily/reports${query ? `?${query}` : ""}`);
}

export async function getDailyReport(reportDate: string): Promise<DailyReportDetail> {
  return request(`/api/v1/hot/daily/reports/${reportDate}`);
}

export async function generateDailyReport(reportDate?: string): Promise<DailyReport> {
  const sp = new URLSearchParams();
  if (reportDate) sp.set("report_date", reportDate);
  const query = sp.toString();
  return request(`/api/v1/hot/daily/generate${query ? `?${query}` : ""}`, {
    method: "POST",
  });
}

// ---------- Feed 流 ----------

export async function getFeed(params?: {
  item_type?: string;
  category?: string;
  page?: number;
  page_size?: number;
}): Promise<PageResult<FeedItem>> {
  const sp = new URLSearchParams();
  if (params?.item_type) sp.set("item_type", params.item_type);
  if (params?.category) sp.set("category", params.category);
  if (params?.page) sp.set("page", String(params.page));
  if (params?.page_size) sp.set("page_size", String(params.page_size));
  const query = sp.toString();
  return request(`/api/v1/hot/feed${query ? `?${query}` : ""}`);
}
