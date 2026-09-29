/**
 * lib/api/batch —— 批量入库辅助纯函数（T-022 L-02/L-03/L-05）
 *
 * 本模块**全部为纯函数 + 存储辅助**（无网络请求），可独立单测：
 *  - L-02 `parseBatchUrls`：批量粘贴拆分与去重计划；
 *  - L-03 `read/save/clearPreviewCheckpoint`：解析预览断点（sessionStorage）；
 *  - L-05 `networkPauseMessage` + `POLL_NET_FAIL_THRESHOLD`：轮询失败提示文案；
 *  - T2.6.2 `read/save/clearBatchJobCheckpoint`：批量 **Job 断点**（刷新不丢）；
 *    `isBatchJobTerminal` / `batchProgressPercent`：Job 进度纯函数。
 */

import { validateArticleUrl } from "./ingest";

// ---------- T-022 L-02 批量粘贴（纯函数，可单测） ----------

export interface BatchUrlPlan {
  /** 去重后的目标 URL（保持首次出现顺序） */
  urls: string[];
  /** 原始有效行数（去重前） */
  rawCount: number;
  /** 被去重剔除的行数 */
  duplicatedCount: number;
}

/** 判定一行是否为批量粘贴中的有效 URL 行（复用 validateArticleUrl，零重复语义）。 */
function isBatchUrlLine(raw: string): boolean {
  return validateArticleUrl(raw).ok;
}

/**
 * T-022 L-02：批量粘贴拆分（纯函数，可单测）。
 * 规则：换行分隔 → 逐行 trim → 过滤空行与非 URL 行（validateArticleUrl 语义）
 *      → 行内去重（保持首次出现顺序）。
 * 返回去重计划：urls 供逐篇串行提交，duplicatedCount 供 UI 去重提示。
 * 注意：此处不做网络请求，提交编排归 AddArticlePanel（单篇路径保持不变）。
 */
export function parseBatchUrls(text: string): BatchUrlPlan {
  const lines = (text ?? "")
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && isBatchUrlLine(l));
  const seen = new Set<string>();
  const urls: string[] = [];
  for (const line of lines) {
    if (!seen.has(line)) {
      seen.add(line);
      urls.push(line);
    }
  }
  return { urls, rawCount: lines.length, duplicatedCount: lines.length - urls.length };
}

// ---------- T-022 L-03 预览断点（纯函数，可单测） ----------

export interface PreviewCheckpoint {
  /** 断点所在空间 id（跨空间不串味） */
  spaceId: string;
  /** 断点时刻的解析目标 URL */
  url: string;
  /** 断点写入时间戳（ms） */
  savedAt: number;
  /** 解析产物摘要：恢复时只做提示，不伪造完整正文 */
  title: string;
  wordCount: number;
  qualityScore: number;
  images: number;
}

const PREVIEW_CHECKPOINT_KEY = "bothot_preview_checkpoint_v1";

/** 读取预览断点：非法 JSON / 缺字段一律回 null，禁止让断点存储问题打断面板。 */
export function readPreviewCheckpoint(): PreviewCheckpoint | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(PREVIEW_CHECKPOINT_KEY);
    if (!raw) return null;
    const o = JSON.parse(raw) as Record<string, unknown> | null;
    if (!o || typeof o.spaceId !== "string" || typeof o.url !== "string") return null;
    return {
      spaceId: o.spaceId,
      url: o.url,
      savedAt: typeof o.savedAt === "number" ? o.savedAt : 0,
      title: typeof o.title === "string" ? o.title : "",
      wordCount: typeof o.wordCount === "number" ? o.wordCount : 0,
      qualityScore: typeof o.qualityScore === "number" ? o.qualityScore : 0,
      images: typeof o.images === "number" ? o.images : 0,
    };
  } catch {
    return null;
  }
}

/** 写入预览断点（解析成功后调用）；存储异常静默降级，不影响主流程。 */
export function savePreviewCheckpoint(
  spaceId: string,
  url: string,
  data: { title: string; wordCount: number; qualityScore: number; images: number }
): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      PREVIEW_CHECKPOINT_KEY,
      JSON.stringify({ spaceId, url, savedAt: Date.now(), ...data })
    );
  } catch {
    // sessionStorage 满/隐私模式禁用：断点能力降级为无，不阻断入库
  }
}

/** 清除预览断点（入库成功或用户忽略后调用）。 */
export function clearPreviewCheckpoint(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(PREVIEW_CHECKPOINT_KEY);
  } catch {
    // no-op
  }
}

// ---------- T-022 L-05 轮询失败提示（纯函数，可单测） ----------

/** 轮询连续失败阈值：达到即提示「网络异常，同步进度已暂停」。 */
export const POLL_NET_FAIL_THRESHOLD = 3;

/** 网络异常暂停文案（订阅页轮询失败横幅共享，避免文案漂移）。 */
export function networkPauseMessage(failCount: number): string {
  return `网络异常，同步进度已暂停（连续 ${failCount} 次轮询失败），请检查连接后重试。`;
}

// ---------- T2.6.2 批量 Job 断点（刷新不丢）与进度纯函数 ----------

/**
 * 批量入库 Job 断点：把 `jobId` 落到 sessionStorage。
 *
 * 为什么存 jobId 而不是逐篇状态：T2.6.1 起批量入库是 **Job 化** 的——真正的进度由后端
 * Job/JobItem 持久化，前端只需记住 jobId，刷新后调 `getJob(jobId)` 即可完整恢复进度
 * （进度真相在后端，前端不重复记账）。
 */
export interface BatchJobCheckpoint {
  /** 断点所属空间 id（跨空间不串味） */
  spaceId: string;
  /** 后端 Job id（进度恢复的唯一凭据） */
  jobId: string;
  /** 本批提交的链接数（用于首轮渲染前的占位进度） */
  urlCount: number;
  /** 写入时间戳（ms） */
  savedAt: number;
}

const BATCH_JOB_CHECKPOINT_KEY = "bothot_batch_job_checkpoint_v1";

/** 读取批量 Job 断点：非法 JSON / 缺字段一律回 null，禁止让断点存储问题打断面板。 */
export function readBatchJobCheckpoint(): BatchJobCheckpoint | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(BATCH_JOB_CHECKPOINT_KEY);
    if (!raw) return null;
    const o = JSON.parse(raw) as Record<string, unknown> | null;
    if (!o || typeof o.spaceId !== "string" || typeof o.jobId !== "string") return null;
    return {
      spaceId: o.spaceId,
      jobId: o.jobId,
      urlCount: typeof o.urlCount === "number" ? o.urlCount : 0,
      savedAt: typeof o.savedAt === "number" ? o.savedAt : 0,
    };
  } catch {
    return null;
  }
}

/** 写入批量 Job 断点（提交成功后立即调用）；存储异常静默降级，不影响主流程。 */
export function saveBatchJobCheckpoint(cp: {
  spaceId: string;
  jobId: string;
  urlCount: number;
}): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      BATCH_JOB_CHECKPOINT_KEY,
      JSON.stringify({ ...cp, savedAt: Date.now() })
    );
  } catch {
    // sessionStorage 满/隐私模式禁用：断点能力降级为无，不阻断入库
  }
}

/** 清除批量 Job 断点（Job 达终态且用户已处理后调用）。 */
export function clearBatchJobCheckpoint(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(BATCH_JOB_CHECKPOINT_KEY);
  } catch {
    // no-op
  }
}

/** Job 终态集合（对齐 `models/entities.py` Job 状态机；QUEUED/RUNNING 为非终态）。
 *
 * 状态中文名表见 lib/api/jobs.ts 的 `JOB_STATUS_LABELS`——本处只判终态，勿重复定义状态字典。
 * CANCELLED（R0.4.2 用户取消）必在此列：漏掉会让被取消的作业被判为「进行中」而无限轮询。
 */
export const BATCH_JOB_TERMINAL_STATUSES = [
  "SUCCEEDED",
  "PARTIAL_SUCCESS",
  "FAILED",
  "CANCELLED",
] as const;

/** 判定 Job 是否已停止推进（终态）——决定是否停止轮询、是否展示失败汇总。 */
export function isBatchJobTerminal(status: string): boolean {
  return (BATCH_JOB_TERMINAL_STATUSES as readonly string[]).includes(status);
}

/** 已完结篇数占本批的百分比（0~100 取整；total<=0 → 0）。 */
export function batchProgressPercent(counts: {
  total: number;
  succeeded: number;
  failed: number;
}): number {
  if (!counts || counts.total <= 0) return 0;
  const done = counts.succeeded + counts.failed;
  return Math.min(100, Math.max(0, Math.round((done / counts.total) * 100)));
}
