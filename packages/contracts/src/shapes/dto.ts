/**
 * shapes 域 — 契约 DTO
 *
 * 由 scripts/gen_contracts.py 自动生成，请勿手动修改（--check 幂等门禁）
 * 源：packages/contracts/schemas/shapes.schema.json（← apps/api/app/contracts/shapes.py，ADR-0008）
 */

export interface BatchDocFailure {
  code: number;
  docId: string;
  error: string;
}

export interface DocCategoryList {
  items: Array<string>;
}

export interface DocCategoryPatch {
  category: string;
  docId: string;
}

export interface DocDeleteResult {
  assets: number;
  docId: string;
  docs: number;
  ok: boolean;
}

export interface DocIngestState {
  docId: string;
  langbotFileId: string;
  status: DocIngestStatus;
}

export type DocIngestStatus = "FETCHED" | "INDEXED" | "READY";

export interface DocsBatchDeleteResult {
  assets: number;
  docs: number;
  failed: Array<BatchDocFailure>;
  ok: boolean;
  requested: number;
}

export interface DocsRecategorizeResult {
  category: string;
  docs: number;
  ok: boolean;
  requested: number;
}

export interface ExtractedArticleView {
  author: string;
  images: Array<ExtractedImageView>;
  langbotFormat: string;
  paragraphs: Array<string>;
  publishTime: string;
  qualityPassed: boolean;
  qualityReasons: Array<string>;
  qualityScore: number;
  title: string;
  wordCount: number;
}

export interface ExtractedImageView {
  caption: string;
  src: string;
}

export interface IngestAccepted {
  docId: string;
  hitCache: boolean;
  hitCount: number;
  langbotFileId: string;
  status: DocIngestStatus;
  taskId: string;
  title: string;
}

export interface LinkResult {
  copied: number;
  skipped: number;
  total: number;
}

export interface LogoutResult {
  logged_out: boolean;
}

export interface MeUser {
  email: string;
  is_admin: boolean;
  nickname: string;
  role: string;
  sub: string;
  tier: string;
}

export interface MeView {
  providerUnreachable?: boolean;
  qaFixture?: boolean;
  user: MeUser;
  wallet: MeWallet;
}

export interface MeWallet {
  available?: boolean;
  availableYuan?: string | number;
  balanceYuan: string | number;
  currency: string;
  heldYuan?: string | number;
}

export interface NotificationHistoryPage {
  items: Array<NotificationItem>;
  limit: number;
  offset: number;
  total: number;
  unread_total: number;
}

export interface NotificationItem {
  created_at: string | null;
  doc_id: string | null;
  id: string;
  is_broadcast: boolean;
  message: string;
  read_at: string | null;
  space_id: string | null;
  title: string;
  url: string | null;
}

export interface NotificationReadResult {
  updated: number;
}

export interface PublicSpacePage {
  items: Array<PublicSpaceView>;
  limit: number;
  offset: number;
  total: number;
}

export interface PublicSpaceView {
  description: string;
  docCount: number;
  engine: string;
  id: string;
  isPublic: boolean;
  name: string;
  updatedAt: string;
}

export interface ResolvedArticleView {
  author: string;
  biz: string;
  content: string;
  publishTime: string;
  title: string;
  url: string;
}

export interface SpaceDeleteResult {
  engineResidue: boolean;
  ok: boolean;
}

export interface SpaceDetail {
  createdAt: string;
  description: string;
  docCount: number;
  engine: string;
  engineKbId: string;
  id: string;
  isPublic: boolean;
  name: string;
  stats: SpaceStats;
  updatedAt: string;
}

export interface SpaceDocItem {
  category: string;
  id: string;
  source: string;
  status: SpaceDocStatus;
  title: string;
  updatedAt: string;
}

export interface SpaceDocPage {
  items: Array<SpaceDocItem>;
  limit: number;
  offset: number;
  total: number;
}

export type SpaceDocStatus = "pending" | "ready" | "failed";

export interface SpacePage {
  items: Array<SpaceView>;
  limit: number;
  offset: number;
  total: number;
}

export interface SpaceStats {
  chunks: number | null;
  docs: number;
}

export interface SpaceView {
  description: string;
  docCount: number;
  engine: string;
  engineKbId: string;
  id: string;
  isPublic: boolean;
  name: string;
  updatedAt: string;
}
