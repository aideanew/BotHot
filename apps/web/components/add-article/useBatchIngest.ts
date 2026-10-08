"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  clearBatchJobCheckpoint,
  clearPreviewCheckpoint,
  extractUrl,
  getJob,
  isBatchJobTerminal,
  parseBatchUrls,
  pollDocStatus,
  readBatchJobCheckpoint,
  readPreviewCheckpoint,
  resolveUrl,
  retryJob,
  saveBatchJobCheckpoint,
  savePreviewCheckpoint,
  submitDoc,
  submitDocsBatch,
  validateArticleUrl,
  type JobView,
  type PreviewCheckpoint,
} from "@/lib/api";
import type { BatchJobState, PanelPhase, PreviewState } from "./types";

/**
 * 粘贴解析与提交编排（R0.6.3 由 AddArticlePanel 下沉）
 *
 * AddArticlePanel 既有 4 个子件已达成「数量」拆分目标，本 hook 补的是**体量**：
 * 原组件 588 行里绝大部分是状态机与副作用（阶段流转、防抖、断点读写、Job 轮询、
 * 卸载中止），只留 JSX 不足以让面板成为纯展示。下沉后渲染面与编排面分离，
 * 编排逻辑第一次可单测（此前该面板**零测试覆盖**，全部消费方测试都把它
 * `vi.mock` 成空组件——见 tests/hit-cache-toast.spec.ts、tests/r026-doc-batch.spec.tsx）。
 *
 * 行为零变更：阶段流转顺序、`busyRef` 单飞守卫、`batchAbortRef` **原地**置位
 * （轮询闭包持有同一引用，整体替换会令中止信号失效）、断点写清时机、
 * `finally` 里 `!batchAbortRef.current.aborted` 才复位轮询态——全部原样保留。
 */

/** 批量 Job 轮询间隔（与后端 GET /jobs/{id} 契约注记的 5s 对齐）。 */
const BATCH_POLL_INTERVAL_MS = 5000;
/** 轮询上限次数：5s × 360 = 30 分钟（50 篇批量的宽松上界；超时后进度仍在后端，可续轮询）。 */
const BATCH_POLL_MAX_ATTEMPTS = 360;
const BATCH_TIMEOUT_MSG =
  "进度轮询已超过 30 分钟。进度已持久化在后端，可点「继续同步」恢复查看。";
const BATCH_NET_MSG = "网络异常，批量进度同步中断，可点「继续同步」恢复。";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * 模块级 Job 轮询（提到模块作用域是为了让 `useEffect` 里的「刷新后恢复」拿到稳定引用，
 * 避免 exhaustive-deps 反复重入）。进度真相在后端；`signal.aborted` 时立即停。
 */
async function pollJobUntilTerminal(
  jobId: string,
  signal: { aborted: boolean },
  onJob: (job: JobView) => void
): Promise<"terminal" | "timeout" | "aborted"> {
  for (let i = 0; i < BATCH_POLL_MAX_ATTEMPTS; i++) {
    if (signal.aborted) return "aborted";
    const job = await getJob(jobId);
    if (signal.aborted) return "aborted";
    onJob(job);
    if (isBatchJobTerminal(job.status)) return "terminal";
    await sleep(BATCH_POLL_INTERVAL_MS);
  }
  return "timeout";
}

export interface UseBatchIngestOptions {
  spaceId: string;
  /** 面板是否展开——两个断点恢复 effect 都在收起时短路 */
  open: boolean;
  onSubmitted?: () => void;
}

export interface UseBatchIngestResult {
  phase: PanelPhase;
  preview: PreviewState | null;
  errorMsg: string;
  qualityReasons: string[];
  pollSeconds: number;
  submitError: string;
  /** 最近一次解析用的 URL——错误气泡与低质拦截的重试都打它（用户改动输入框不影响重试目标） */
  lastUrl: string;
  hitCache: boolean;
  hitCount: number;
  checkpoint: PreviewCheckpoint | null;
  batchJob: BatchJobState | null;
  batchSubmitting: boolean;
  batchPolling: boolean;
  batchRetrying: boolean;
  batchError: string;
  /** 渲染期读取 `busyRef.current`：置位处总是伴随 phase 更新，UI 不会滞留 */
  busy: boolean;
  parse: (input: string) => Promise<void>;
  submit: () => Promise<void>;
  runBatch: (input: string) => Promise<void>;
  retryBatch: () => Promise<void>;
  resumeExistingBatch: () => void;
  dismissBatch: () => void;
  dismissCheckpoint: () => void;
  /** 复位编排态（**不含**面板展开与输入框，那两项归调用方）；不清 jobId 断点 */
  reset: () => void;
}

export function useBatchIngest({
  spaceId,
  open,
  onSubmitted,
}: UseBatchIngestOptions): UseBatchIngestResult {
  const [phase, setPhase] = useState<PanelPhase>("idle");
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [qualityReasons, setQualityReasons] = useState<string[]>([]);
  const [lastUrl, setLastUrl] = useState(""); // 重试用
  const [pollSeconds, setPollSeconds] = useState(0); // 轮询已等待秒数
  const [submitError, setSubmitError] = useState(""); // 入库阶段错误（与解析错误分开）
  // AB-P004 P0：素材缓存命中提示（"命中缓存，秒入库"）
  const [hitCache, setHitCache] = useState(false);
  const [hitCount, setHitCount] = useState(0);
  // C-T7R：双击防抖（提交/解析进行中不再重入）与卸载中止（轮询不遗留后台 timer）
  const busyRef = useRef(false);
  const pollAbortRef = useRef<AbortController | null>(null);
  // T-022 L-03：预览断点横幅（刷新/回入后提示「上次预览，点击重新解析」）
  const [checkpoint, setCheckpoint] = useState<PreviewCheckpoint | null>(null);
  // T2.6.2：批量入库面板态（进度真相在后端 Job；前端只持 jobId + 聚合进度）
  const [batchJob, setBatchJob] = useState<BatchJobState | null>(null);
  const [batchSubmitting, setBatchSubmitting] = useState(false);
  const [batchPolling, setBatchPolling] = useState(false);
  const [batchRetrying, setBatchRetrying] = useState(false);
  const [batchError, setBatchError] = useState("");
  const batchAbortRef = useRef<{ aborted: boolean }>({ aborted: false });

  // 同一 Job 只允许一条轮询链：StrictMode 双执行会让恢复 effect 跑两次，
  // 无守卫时会并发轮询同一 Job、终态重复回调 onSubmitted（列表刷新两次）
  const batchResumeInFlightRef = useRef(false);

  // onSubmitted 由调用方以**内联箭头**传入（每次渲染都是新引用）：若直接进 useCallback 依赖，
  // resumeBatch 会随父级每次渲染换引用 → 下方断点恢复 effect 反复重入 → 已终态的 Job
  // 被无限轮询（终态首轮即返回、无 5s 间隔，退化成紧密死循环；实测单页 1000+ 条请求）。
  // 用 ref 始终取最新回调，使 resumeBatch 稳定；ref 同步 effect 必须声明在恢复 effect 之前。
  const onSubmittedRef = useRef(onSubmitted);
  useEffect(() => {
    onSubmittedRef.current = onSubmitted;
  }, [onSubmitted]);

  // 组件卸载：中止进行中的轮询，清理 timer，不更新已卸载组件
  useEffect(() => {
    const abortRef = batchAbortRef.current;
    return () => {
      pollAbortRef.current?.abort();
      pollAbortRef.current = null;
      // 原地置位（不可整体替换对象）：轮询闭包持有的是同一引用，替换会令中止信号失效
      abortRef.aborted = true;
    };
  }, []);

  // T-022 L-03：仅同一空间恢复预览断点（跨空间不串味）；无断点时静默
  useEffect(() => {
    if (!open) return;
    const cp = readPreviewCheckpoint();
    if (cp && cp.spaceId === spaceId) setCheckpoint(cp);
  }, [open, spaceId]);

  /**
   * T2.6.2：续轮询已提交的 Job（提交后 / 刷新恢复 / 失败重试三处共用）。
   * 只读后端进度，不重复提交——幂等由后端 Job 键保证，前端无需记账。
   */
  const resumeBatch = useCallback(
    async (jobId: string) => {
      if (batchResumeInFlightRef.current) return;
      batchResumeInFlightRef.current = true;
      setPhase("batching");
      setBatchPolling(true);
      setBatchError("");
      try {
        const outcome = await pollJobUntilTerminal(jobId, batchAbortRef.current, (job) =>
          setBatchJob((st) => (st ? { ...st, job } : st))
        );
        if (batchAbortRef.current.aborted) return;
        if (outcome === "timeout") setBatchError(BATCH_TIMEOUT_MSG);
        if (outcome === "terminal") onSubmittedRef.current?.(); // 终态刷新文档列表（成功篇已落库）
      } catch (err) {
        if (batchAbortRef.current.aborted) return;
        if (err instanceof ApiError && err.code === 30004) {
          // 断点指向的 Job 已不在后端（过期清理 / 归属已变）：清断点并交回输入态。
          // 断点不清，每次展开面板都会重放这条死链，卡在「同步中…」且看不到原因。
          clearBatchJobCheckpoint();
          setBatchJob(null);
          setBatchPolling(false);
          setPhase("idle");
          setBatchError("");
          setErrorMsg("上次的批量任务已不存在（可能已过期清理），请重新提交。");
          return;
        }
        setBatchError(err instanceof Error ? err.message : BATCH_NET_MSG);
      } finally {
        batchResumeInFlightRef.current = false;
        if (!batchAbortRef.current.aborted) {
          setBatchPolling(false);
          setPhase("idle");
        }
      }
    },
    // 依赖留空是刻意的：全部状态设置器与模块级 pollJobUntilTerminal 均稳定，
    // onSubmitted 走 ref（见上方）。若把 onSubmitted 放进依赖，断点恢复 effect
    // 会随父级每次渲染重入，已终态的 Job 被无限轮询。
    []
  );

  // T2.6.2：批量 Job 断点恢复——刷新/回入后凭 jobId 续轮询，进度不丢（仅同空间）
  useEffect(() => {
    if (!open) return;
    const cp = readBatchJobCheckpoint();
    if (!cp || cp.spaceId !== spaceId) return;
    // 原地复位中止标记：组件卸载/StrictMode 双执行会置位，复位后它永远是 true，
    // pollJobUntilTerminal 会在发请求前短路返回 "aborted"，面板永久停在「同步中…」
    // 且无关闭入口、输入框禁用（无任何请求发出）。
    batchAbortRef.current.aborted = false;
    setBatchJob((st) => st ?? { urlCount: cp.urlCount, skipped: 0, job: null });
    void resumeBatch(cp.jobId);
  }, [open, spaceId, resumeBatch]);

  /** 解析：resolve 取元信息 + extract 取正文与质量分（合并为预览态） */
  async function parse(targetUrl: string) {
    if (busyRef.current) return; // 防抖：解析进行中不重入
    // C-T7R 返工：入口本地预校验（对齐后端 10006 五类语义），非法 URL 不发请求
    const validation = validateArticleUrl(targetUrl);
    if (!validation.ok) {
      setPhase("idle");
      setErrorMsg(validation.message);
      setPreview(null);
      setQualityReasons([]);
      return;
    }
    busyRef.current = true;
    try {
      setPhase("parsing");
      setErrorMsg("");
      setQualityReasons([]);
      setPreview(null);
      setLastUrl(validation.url);
      try {
        const [resolved, extracted] = await Promise.all([
          resolveUrl(validation.url),
          extractUrl(validation.url),
        ]);
        // 预览卡以 extract 为主（含质量分），publishTime 缺失时用 resolve 的兜底
        const data = {
          ...extracted,
          publishTime: extracted.publishTime || resolved.publishTime,
        };
        setPreview({ data });
        // T-022 L-03：解析成功后写断点（刷新/回入可提示重新解析）
        savePreviewCheckpoint(spaceId, validation.url, {
          title: data.title,
          wordCount: data.wordCount,
          qualityScore: data.qualityScore,
          images: data.images.length,
        });
        setCheckpoint(null);
        setPhase("preview");
      } catch (err) {
        if (err instanceof ApiError && err.code === 20003) {
          // 低质拦截：reasons 可观测（v0.3f），展示后禁用入库
          setQualityReasons(err.message ? [err.message] : ["内容质量不足"]);
        } else {
          setErrorMsg(err instanceof Error ? err.message : "解析失败，请稍后重试");
        }
        setPhase("idle"); // 失败后允许重试（原输入保留）
      }
    } finally {
      busyRef.current = false;
    }
  }

  /** 确认入库（接真：202 提交 → 轮询 status 至 READY；契约 v0.3h） */
  async function submit() {
    if (!preview || busyRef.current) return; // 防抖：多次快速点击只发一个 submit 请求
    busyRef.current = true;
    setPhase("submitting");
    setSubmitError("");
    // 独立 AbortController：卸载时中止轮询（清理内部 timer）
    const ctrl = new AbortController();
    pollAbortRef.current = ctrl;
    try {
      // ① 提交（202 接受；护栏 10006/20001/20002/20003 同步返回）
      const result = await submitDoc(spaceId, lastUrl);
      const docId = result.docId;
      setHitCache(result.hitCache ?? false);
      setHitCount(result.hitCount ?? 0);
      // ② 轮询状态至 READY（1.5s/120s·80次；30003 抛错；signal 中止抛"操作已取消"）
      setPhase("polling");
      setPollSeconds(0);
      await pollDocStatus(spaceId, docId, {
        onTick: (ms) => {
          if (!ctrl.signal.aborted) setPollSeconds(Math.round(ms / 1000));
        },
        signal: ctrl.signal,
      });
      if (ctrl.signal.aborted) return; // 卸载后不更新已卸载组件
      setPhase("submitted");
      // T-022 L-03：入库成功后断点不再有效
      clearPreviewCheckpoint();
      setCheckpoint(null);
      onSubmitted?.(); // 通知详情页刷新文档列表（仅成功后一次）
    } catch (err) {
      if (ctrl.signal.aborted) return; // 卸载中止：静默，不更新状态
      // 30003 INGEST_FAILED（与低质 20003 严格区分）→ 错误 + 重试回预览态
      // retry 使用原始 URL（lastUrl 保留）；预览数据不清空
      setSubmitError(err instanceof Error ? err.message : "入库提交失败，请稍后重试");
      setPhase("preview");
    } finally {
      if (pollAbortRef.current === ctrl) {
        pollAbortRef.current = null;
      }
      busyRef.current = false;
    }
  }

  /**
   * T2.6.2：批量粘贴提交（换行分隔多 URL）——**提交即返 + Job 轮询**。
   *
   * 与旧 T-022 L-02「前端逐篇串行 await（resolve+extract+submit+轮询）」的区别：
   * ① 提交阶段只发**一个**请求（`POST /spaces/{id}/docs:batch`），后端建 Job 后即 202；
   * ② 抓取/解析/入库全部由后端 JobWorker 逐篇消费，前端只轮询聚合进度；
   * ③ jobId 落 sessionStorage 断点 → **刷新不丢**（旧实现刷新即全丢）；
   * ④ 失败不再需要前端逐篇重跑：终态失败由后端 `POST /jobs/{id}/retry` 单篇重试。
   * 去重仍由 `parseBatchUrls` 在前端先做（省一次请求、且 UI 可提示跳过条数）。
   */
  async function runBatch(input: string) {
    if (busyRef.current) return;
    const plan = parseBatchUrls(input);
    if (plan.urls.length === 0) {
      // 空/全非法：与单篇一致给 10006 气泡，不发请求
      setPhase("idle");
      const single = validateArticleUrl(input.trim());
      setErrorMsg(single.ok ? "链接不能为空" : single.message);
      setPreview(null);
      setQualityReasons([]);
      return;
    }
    busyRef.current = true;
    batchAbortRef.current.aborted = false; // 原地复位（轮询闭包共享同一引用）
    setBatchJob({ urlCount: plan.urls.length, skipped: plan.duplicatedCount, job: null });
    setBatchSubmitting(true);
    setBatchError("");
    setSubmitError("");
    setErrorMsg("");
    setPhase("batching");

    try {
      // ① 提交即返（202 + jobId）；护栏 10005（空批/超上限）/10006（形态）同步返回
      const res = await submitDocsBatch(spaceId, plan.urls);
      if (batchAbortRef.current.aborted) return;
      // ② 先落断点再轮询：即便随后刷新/断网，凭 jobId 也能恢复进度
      saveBatchJobCheckpoint({ spaceId, jobId: res.jobId, urlCount: res.urlCount });
      setBatchJob((st) => ({
        urlCount: res.urlCount,
        skipped: st?.skipped ?? 0,
        job: {
          jobId: res.jobId,
          type: "batch_ingest",
          status: res.status,
          progress: 0,
          error: "",
          counts: res.counts,
          createdAt: new Date().toISOString(),
        },
      }));
      setBatchSubmitting(false);
      // ③ 轮询至终态（进度真相在后端）
      await resumeBatch(res.jobId);
    } catch (err) {
      if (batchAbortRef.current.aborted) return;
      // 提交失败：无 jobId 可续，清面板态并走既有错误气泡（用户可再次点「批量入库」）
      setBatchSubmitting(false);
      setBatchJob(null);
      setPhase("idle");
      setErrorMsg(err instanceof Error ? err.message : "批量提交失败，请稍后重试");
    } finally {
      busyRef.current = false;
    }
  }

  /** T2.6.2：终态失败篇单篇重试（后端只重试 FAILED item，已成功的不重复入库）。 */
  async function retryBatch() {
    const jobId = batchJob?.job?.jobId;
    if (!jobId || batchRetrying || batchPolling) return;
    setBatchRetrying(true);
    setBatchError("");
    try {
      await retryJob(jobId);
      if (batchAbortRef.current.aborted) return;
      setBatchRetrying(false);
      await resumeBatch(jobId); // 重试后 Job 回到推进态，继续轮询
    } catch (err) {
      if (batchAbortRef.current.aborted) return;
      setBatchRetrying(false);
      setBatchError(err instanceof Error ? err.message : "重试失败，请稍后再试");
    }
  }

  /** T2.6.2：网络中断后继续轮询（只恢复进度查看，不触发篇目重试）。 */
  function resumeExistingBatch() {
    const jobId = batchJob?.job?.jobId;
    if (!jobId) return;
    void resumeBatch(jobId);
  }

  /** T2.6.2：收起批量面板并清除 jobId 断点（用户已处理完终态）。 */
  function dismissBatch() {
    clearBatchJobCheckpoint();
    setBatchJob(null);
    setBatchError("");
    setBatchSubmitting(false);
    setBatchPolling(false);
    setBatchRetrying(false);
    setPhase("idle");
  }

  function dismissCheckpoint() {
    clearPreviewCheckpoint();
    setCheckpoint(null);
  }

  function reset() {
    // 批量面板态复位；**不清 jobId 断点**——收起后重新展开仍应恢复未终结的 Job 进度
    setBatchJob(null);
    setBatchSubmitting(false);
    setBatchPolling(false);
    setBatchRetrying(false);
    setBatchError("");
    setPhase("idle");
    setPreview(null);
    setErrorMsg("");
    setQualityReasons([]);
    setSubmitError("");
    setHitCache(false);
    setHitCount(0);
  }

  return {
    phase,
    preview,
    errorMsg,
    qualityReasons,
    pollSeconds,
    submitError,
    lastUrl,
    hitCache,
    hitCount,
    checkpoint,
    batchJob,
    batchSubmitting,
    batchPolling,
    batchRetrying,
    batchError,
    busy: busyRef.current,
    parse,
    submit,
    runBatch,
    retryBatch,
    resumeExistingBatch,
    dismissBatch,
    dismissCheckpoint,
    reset,
  };
}
