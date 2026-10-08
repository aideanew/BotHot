/**
 * push_event 域 — 契约 DTO
 *
 * 由 scripts/gen_contracts.py 自动生成，请勿手动修改（--check 幂等门禁）
 * 源：apps/api/app/models/bothot_entities.py（SQLAlchemy 模型内省）
 */

export interface PushEvent {
  id: string;
  event_type: string;
  payload: string;
  consumed_at: string | null;
  created_at: string;
  updated_at: string;
}
