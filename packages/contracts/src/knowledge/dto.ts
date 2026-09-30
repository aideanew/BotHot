/**
 * knowledge 域 — 契约 DTO
 *
 * 由 scripts/gen_contracts.py 自动生成，请勿手动修改（--check 幂等门禁）
 * 源：backend/app/models/entities.py（SQLAlchemy 模型内省）
 */

export interface KnowledgeSpace {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  langbot_kb_uuid: string;
  status: string;
  doc_count: number;
  is_public: boolean;
  owner_type: string;
  engine: string;
  engine_kb_id: string;
  created_at: string;
  updated_at: string;
}
