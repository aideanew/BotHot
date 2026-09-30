/**
 * lib/api/bots —— 机器人渠道管理 API 模块。
 *
 * 对应后端 /api/v1/bots/* 路由：
 * - 渠道 CRUD（创建/列表/详情/更新/删除）
 * - 测试推送
 * - 推送日志查询
 * - 推送任务管理
 * - 可用渠道类型查询
 */

import { request } from "./http";

// ---------- 类型 ----------

export interface ChannelType {
  channel: string;
  implemented: boolean;
  description: string;
}

export interface BotChannel {
  id: string;
  name: string;
  channel_type: string;
  webhook_url: string;
  has_secret: boolean;
  extra_config: string;
  status: string;
  user_id: string | null;
  total_push_count: number;
  success_push_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface PushLog {
  id: string;
  bot_channel_id: string;
  push_task_id: string | null;
  status: string;
  content_preview: string;
  error_message: string;
  response_summary: string;
  created_at: string | null;
}

export interface PushTask {
  id: string;
  name: string;
  bot_channel_id: string;
  trigger_type: string;
  cron_expr: string;
  trigger_event: string;
  content_template: string;
  space_id: string | null;
  next_run_at: string | null;
  last_run_at: string | null;
  status: string;
  created_by: string;
  created_at: string | null;
}

interface PaginatedResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface PushResult {
  delivered: boolean;
  reason: string;
  channel: string;
}

// ---------- API 函数 ----------

export async function listChannelTypes(): Promise<ChannelType[]> {
  return request("/api/v1/bots/channels");
}

export async function listChannels(params?: {
  channel_type?: string;
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<PaginatedResult<BotChannel>> {
  const searchParams = new URLSearchParams();
  if (params?.channel_type) searchParams.set("channel_type", params.channel_type);
  if (params?.status) searchParams.set("status", params.status);
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.page_size) searchParams.set("page_size", String(params.page_size));
  const query = searchParams.toString();
  return request(`/api/v1/bots${query ? `?${query}` : ""}`);
}

export async function getChannel(id: string): Promise<BotChannel> {
  return request(`/api/v1/bots/${id}`);
}

export async function createChannel(data: {
  name: string;
  channel_type: string;
  webhook_url?: string;
  secret?: string;
  extra_config?: string;
}): Promise<BotChannel> {
  return request("/api/v1/bots", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateChannel(
  id: string,
  data: {
    name?: string;
    webhook_url?: string;
    secret?: string;
    extra_config?: string;
    status?: string;
  },
): Promise<BotChannel> {
  return request(`/api/v1/bots/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteChannel(id: string): Promise<{ id: string; status: string }> {
  return request(`/api/v1/bots/${id}`, { method: "DELETE" });
}

export async function testPush(
  id: string,
  message?: string,
  title?: string,
): Promise<PushResult> {
  const searchParams = new URLSearchParams();
  if (message) searchParams.set("message", message);
  if (title) searchParams.set("title", title);
  const query = searchParams.toString();
  return request(`/api/v1/bots/${id}/test${query ? `?${query}` : ""}`, {
    method: "POST",
  });
}

export async function listPushLogs(
  channelId: string,
  params?: { page?: number; page_size?: number },
): Promise<PaginatedResult<PushLog>> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.page_size) searchParams.set("page_size", String(params.page_size));
  const query = searchParams.toString();
  return request(`/api/v1/bots/${channelId}/logs${query ? `?${query}` : ""}`);
}

// ---------- 推送任务 ----------

export async function createPushTask(data: {
  name: string;
  bot_channel_id: string;
  trigger_type: string;
  cron_expr?: string;
  trigger_event?: string;
  content_template?: string;
  space_id?: string;
  created_by?: string;
}): Promise<PushTask> {
  return request("/api/v1/bots/tasks", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function listPushTasks(params?: {
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<PaginatedResult<PushTask>> {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set("status", params.status);
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.page_size) searchParams.set("page_size", String(params.page_size));
  const query = searchParams.toString();
  return request(`/api/v1/bots/tasks${query ? `?${query}` : ""}`);
}

/** W1 并行交付的 PUT 端点：局部更新（省略字段=不改；status 取 active|paused）。 */
export async function updatePushTask(
  id: string,
  data: {
    name?: string;
    cron_expr?: string;
    trigger_event?: string;
    content_template?: string;
    status?: string;
  },
): Promise<PushTask> {
  return request(`/api/v1/bots/tasks/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deletePushTask(id: string): Promise<{ id: string; deleted: boolean }> {
  return request(`/api/v1/bots/tasks/${id}`, { method: "DELETE" });
}

export async function runPushTaskNow(id: string): Promise<PushResult> {
  return request(`/api/v1/bots/tasks/${id}/run`, { method: "POST" });
}
