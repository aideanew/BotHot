/**
 * subscription 域 — 契约 DTO
 *
 * 由 scripts/gen_contracts.py 自动生成，请勿手动修改（--check 幂等门禁）
 * 源：apps/api/app/models/entities.py（SQLAlchemy 模型内省）
 */

export interface Source {
  id: string;
  type: string;
  external_id: string;
  name: string;
  url: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface SourceSubscription {
  id: string;
  user_id: string;
  source_id: string;
  space_id: string;
  sync_policy: string;
  sync_interval_minutes: number;
  sync_anchor_hour: number | null;
  next_run_at: string | null;
  last_success_at: string | null;
  consecutive_empty_syncs: number;
  status: string;
  created_at: string;
  updated_at: string;
}
