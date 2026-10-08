/**
 * bot 域 — 契约 DTO
 *
 * 由 scripts/gen_contracts.py 自动生成，请勿手动修改（--check 幂等门禁）
 * 源：apps/api/app/models/bothot_entities.py（SQLAlchemy 模型内省）
 */

export interface BotChannel {
  id: string;
  name: string;
  channel_type: string;
  webhook_url: string;
  secret_enc: string;
  extra_config: string;
  status: string;
  user_id: string | null;
  total_push_count: number;
  success_push_count: number;
  created_at: string;
  updated_at: string;
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
  retry_count: number;
  next_retry_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PushLog {
  id: string;
  bot_channel_id: string;
  push_task_id: string | null;
  status: string;
  content_preview: string;
  error_message: string;
  response_summary: string;
  created_at: string;
  updated_at: string;
}

 */

export interface ChannelCreateRequest {
  name: string;
  channel_type: string;
  webhook_url: string | null;
  secret: string | null;
  extra_config: string | null;
}

export interface ChannelUpdateRequest {
  name: unknown | null;
  webhook_url: unknown | null;
  secret: unknown | null;
  extra_config: unknown | null;
  status: unknown | null;
}

export interface PushTaskCreateRequest {
  name: string;
  bot_channel_id: string;
  trigger_type: string | null;
  cron_expr: string | null;
  trigger_event: string | null;
  content_template: string | null;
  space_id: string | null;
  created_by: string | null;
}

export interface PushTaskUpdateRequest {
  name: unknown | null;
  cron_expr: unknown | null;
  trigger_event: unknown | null;
  content_template: unknown | null;
  status: unknown | null;
}
