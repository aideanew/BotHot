/**
 * ingest 域 — 契约 DTO
 *
 * 由 scripts/gen_contracts.py 自动生成，请勿手动修改（--check 幂等门禁）
 * 源：backend/app/models/entities.py（SQLAlchemy 模型内省）
 */

export interface Job {
  id: string;
  type: string;
  user_id: string;
  payload: string;
  status: string;
  progress: number;
  error: string;
  result: string;
  idempotency_key: string;
  worker_heartbeat_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobItem {
  id: string;
  job_id: string;
  external_id: string;
  url: string;
  status: string;
  error: string;
  retry_count: number;
  completed: boolean;
  created_at: string;
  updated_at: string;
}
