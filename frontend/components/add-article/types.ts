/** T1.2.4：AddArticlePanel 拆分共享类型（面板内部契约，不外溢）。 */
import type { ExtractedArticle, JobView } from "@/lib/api";

export type PanelPhase =
  | "idle"
  | "parsing"
  | "preview"
  | "submitting"
  | "polling"
  /** T2.6.2：批量 Job 轮询期（提交即返；进度由后端 Job 记账，前端仅展示） */
  | "batching"
  | "submitted";

export interface PreviewState {
  data: ExtractedArticle;
}

/**
 * T2.6.2：批量入库面板态。
 *
 * 与旧的「逐篇串行 BatchItem[]」的根本差别：**进度真相在后端 Job**。前端不再逐篇
 * 记账（既不 resolve/extract 也不逐篇 submit），只持有 jobId 与后端回传的聚合进度，
 * 因此刷新后凭 jobId 即可完整恢复（sessionStorage 断点只存 jobId）。
 */
export interface BatchJobState {
  /** 本批提交的链接数（用于 total 缺省时的占位） */
  urlCount: number;
  /** 被去重剔除的行数（UI 提示用） */
  skipped: number;
  /** 后端 Job 视图；提交成功、首轮轮询返回前为 null */
  job: JobView | null;
}
