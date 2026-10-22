/**
 * lib/api/ingest —— 链接解析入库域（C-T7 / C-T7R，契约 v0.3d/e/f/h）
 *
 * 全链：本地预校验 `validateArticleUrl`（10006，零网络）→ `resolveUrl` 解析预览
 *      → `extractUrl` 正文抽取与质量分（20003 低质拦截）→ `submitDoc` 提交入库
 *      → `pollDocStatus` 轮询至 READY。
 * 纯函数（批量粘贴/预览断点/轮询提示）见同目录 batch.ts。
 */

import { delay, request } from "./http";
import { ApiError, type ExtractedArticle, type ResolvedArticle } from "./types";

// ---------- 链接本地预校验（C-T7R 返工：对齐后端 normalize_article_url） ----------

/** URL 长度上限（与 backend source_resolver.MAX_URL_LENGTH=512 对齐） */
export const ARTICLE_URL_MAX_LENGTH = 512;
/** 白名单域名（与 backend source_resolver.ALLOWED_HOSTS 对齐，web 域随 M4 扩展） */
export const ARTICLE_ALLOWED_HOSTS = ["mp.weixin.qq.com"] as const;

export type ArticleUrlValidation =
  | { ok: true; url: string }
  | { ok: false; code: 10006; message: string };

/**
 * 前端本地 URL 预校验（纯函数，可单测）。
 * 语义对齐后端 normalize_article_url（契约 v0.3d）：5 类非法输入 → 10006
 *  ① 空串/纯空白 → 10006
 *  ② 长度 >512 → 10006
 *  ③ 含控制字符 → 10006
 *  ④ 非 http(s) scheme → 10006
 *  ⑤ 非白名单域名 → 10006
 * 合法输入返回 trim 化后的 url（供后续 resolve/extract 使用）。
 * 目的：非法输入在本地即拦截并给出 10006 气泡，不发网络请求；
 * 与后端 10006 是同一码位语义，双端校验不冲突（后端仍是权威）。
 */
export function validateArticleUrl(
  raw: string | null | undefined
): ArticleUrlValidation {
  const url = (raw ?? "").trim();
  if (!url) {
    return { ok: false, code: 10006, message: "链接不能为空" };
  }
  if (url.length > ARTICLE_URL_MAX_LENGTH) {
    return {
      ok: false,
      code: 10006,
      message: `链接超长（>${ARTICLE_URL_MAX_LENGTH}字符），请检查后重试`,
    };
  }
  // 控制字符（C0 区 + DEL）：与后端 any(ord(ch) < 32 or ch == 0x7f) 一致
  if (Array.from(url).some((ch) => ch.charCodeAt(0) < 32 || ch.charCodeAt(0) === 127)) {
    return { ok: false, code: 10006, message: "链接含非法控制字符，请检查后重试" };
  }
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return { ok: false, code: 10006, message: "链接格式不正确" };
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return { ok: false, code: 10006, message: "仅支持 http(s) 链接" };
  }
  const host = parsed.hostname.toLowerCase();
  if (!(ARTICLE_ALLOWED_HOSTS as readonly string[]).includes(host)) {
    return {
      ok: false,
      code: 10006,
      message: `不支持的域名：${host || "（缺失）"}`,
    };
  }
  return { ok: true, url };
}

// ---------- 解析 / 抽取 ----------

/**
 * POST /api/v1/resolve —— 链接解析（登录保护）。
 * 错误：10006 链接格式不正确 / 20001 非公众号文章 / 20002 网络失败。
 */
export async function resolveUrl(url: string): Promise<ResolvedArticle> {
  return request<ResolvedArticle>("/api/v1/resolve", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

/**
 * POST /api/v1/extract —— 正文抽取与质量评分（登录保护）。
 * 低质（qualityPassed=false）后端返回 20003，但 reasons 随信封可观测：
 * 前端抛 ApiError(20003) 时携带 reasons，供低质拦截 UI 展示。
 */
export async function extractUrl(
  url: string
): Promise<ExtractedArticle & { qualityReasons: string[] }> {
  return request<ExtractedArticle>("/api/v1/extract", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

// ---------- 入库提交与状态轮询（C-T7R，契约 v0.3h） ----------

/** POST /api/v1/spaces/{id}/docs → 202 data（taskId 恒空串，勿依赖；AB-P004 P0 追加 hitCache/hitCount） */
export interface SubmitDocResult {
  docId: string;
  title: string;
  status: string;
  langbotFileId: string;
  taskId: string;
  /** AB-P004 P0：素材缓存命中（true=0 微信请求，直接复用 content_markdown） */
  hitCache?: boolean;
  /** AB-P004 P0：命中次数（0=首抓，≥1=命中） */
  hitCount?: number;
}

/** GET /api/v1/spaces/{id}/docs/{docId}/status → data */
export interface DocStatusResult {
  docId: string;
  status: "FETCHED" | "INDEXED" | "READY";
  langbotFileId: string;
}

/**
 * 提交入库：POST /api/v1/spaces/{id}/docs，body {url}（登录保护，无效空间 30004）。
 * 护栏（10006/20001/20002/20003）同步返回对应错误码；低质 20003 同步拦截。
 * 幂等：同 url 同空间重复提交 → 覆盖重走 ingest，202 不报错。
 */
export async function submitDoc(
  spaceId: string,
  url: string
): Promise<SubmitDocResult> {
  return request<SubmitDocResult>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/docs`,
    { method: "POST", body: JSON.stringify({ url }) }
  );
}

/**
 * 轮询入库状态至 READY（契约 v0.3h：FETCHED|INDEXED|READY；
 * 失败为 30003 INGEST_FAILED 抛错而非 200 返回）。
 * 间隔 1.5s（SPEC §3.2 建议），上限 120s / 80 次（对齐后端 langbot_ingest_timeout_seconds）；
 * onTick 每次轮询回调（供 UI 显示已等待时长/次数）。
 * 超时抛 50101 中文超时文案（UI 给重试路径；重试走幂等覆盖）。
 */
export async function pollDocStatus(
  spaceId: string,
  docId: string,
  opts?: {
    intervalMs?: number;
    timeoutMs?: number;
    maxAttempts?: number;
    onTick?: (elapsedMs: number) => void;
    signal?: { aborted: boolean };
  }
): Promise<DocStatusResult> {
  const intervalMs = opts?.intervalMs ?? 1500;
  const timeoutMs = opts?.timeoutMs ?? 120_000;
  // 次数上限：默认 = 时间上限 / 间隔（1.5s×80 = 120s），与 timeout 双保险防轮询风暴
  const maxAttempts = opts?.maxAttempts ?? Math.ceil(timeoutMs / intervalMs);
  const started = Date.now();
  let attempts = 0;

  for (;;) {
    attempts += 1;
    if (opts?.signal?.aborted) {
      throw new ApiError(50101, "操作已取消");
    }
    // 单次查询：真实态与演示态都走 request()（演示态由表给"第一跳即 READY"的演练路径，
    // 轮询循环本身照跑——这才叫同一条管道）
    const fetchOne = (): Promise<DocStatusResult> =>
      request<DocStatusResult>(
        `/api/v1/spaces/${encodeURIComponent(spaceId)}/docs/${encodeURIComponent(docId)}/status`
      );

    const result = await fetchOne();
    if (result.status === "READY") return result;

    const elapsed = Date.now() - started;
    if (elapsed >= timeoutMs || attempts >= maxAttempts) {
      throw new ApiError(
        50101,
        `入库超时（已轮询 ${attempts} 次 / ${Math.round(elapsed / 1000)} 秒），请稍后在文档列表中确认状态，或重试入库`
      );
    }
    opts?.onTick?.(elapsed);
    await delay(Math.min(intervalMs, timeoutMs - elapsed));
  }
}

// ---------- T2.6.2 批量粘贴 Job 化（提交即返 + Job 轮询） ----------

/**
 * POST /api/v1/spaces/{id}/docs:batch → data（202，T2.6.1 后端契约）。
 *
 * 语义：**提交即返**——同步段零网络抓取，仅建 Job + 逐篇 JobItem(PENDING) 落库；
 * 逐篇抓取由后端 JobWorker 异步消费，进度经 `getJob(jobId)` 轮询获得。
 * `reused=true` 表示同批在途 Job 被复用（防双击双份排队），此时不重复计数。
 */
export interface BatchSubmitResult {
  jobId: string;
  status: string;
  counts: { total: number; succeeded: number; failed: number; pending: number };
  reused: boolean;
  urlCount: number;
}

/**
 * 批量提交入库（换行粘贴的多篇）。
 *
 * 不做客户端条数上限：业务上限（`batch_ingest_max_urls`，默认 50）由后端统一裁决并回
 * 10005 错误信封——避免前端并行的第二套规则与后端漂移（与域名白名单同一取舍口径）。
 * URL 形态仍先经 `parseBatchUrls` 本地过滤，故此处传出的都是形态合法的链接。
 */
export async function submitDocsBatch(
  spaceId: string,
  urls: string[]
): Promise<BatchSubmitResult> {
  return request<BatchSubmitResult>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/docs:batch`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls }),
    }
  );
}
