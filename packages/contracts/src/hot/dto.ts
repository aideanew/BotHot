/**
 * hot 域 — 契约 DTO
 *
 * 由 scripts/gen_contracts.py 自动生成，请勿手动修改（--check 幂等门禁）
 * 源：backend/app/models/bothot_entities.py（SQLAlchemy 模型内省）
 */

export interface HotTopic {
  id: string;
  title: string;
  summary: string;
  center_asset_id: string | null;
  hot_score: number;
  source_count: number;
  article_count: number;
  status: string;
  topic_date: string;
  category: string;
  created_at: string;
  updated_at: string;
}

export interface HotTopicArticle {
  id: string;
  hot_topic_id: string;
  asset_id: string;
  relevance_score: number;
  created_at: string;
  updated_at: string;
}

export interface DailyReport {
  id: string;
  report_date: string;
  title: string;
  content_markdown: string;
  topic_count: number;
  status: string;
  generated_by: string;
  created_at: string;
  updated_at: string;
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
  created_at: string;
  updated_at: string;
}
