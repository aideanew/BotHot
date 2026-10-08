"use client";

import { useState } from "react";
import BatchProgressList from "@/components/add-article/BatchProgressList";
import ParsePreviewCard from "@/components/add-article/ParsePreviewCard";
import SubmitSuccessCard from "@/components/add-article/SubmitSuccessCard";
import { parseBatchUrls } from "@/lib/api";
import { useBatchIngest } from "@/components/add-article/useBatchIngest";

/**
 * 添加文章面板（C-T7 建面板，C-T7R 接真入库；T1.2.4 拆三子组件——
 * 解析预览 ParsePreviewCard / 批量进度 BatchProgressList / 入库确认 SubmitSuccessCard；
 * R0.6.3 再把粘贴解析与提交编排下沉为 useBatchIngest hook——
 * 子组件纯展示、hook 持状态机与副作用、本组件只留展开/输入与渲染，行为零变更）。
 * 流程：粘贴链接 → resolve+extract 解析预览（质量徽标 ≥30 绿 <30 红）
 *      → 「确认入库」→ POST spaces/{id}/docs（202）→ 轮询 docs/{docId}/status
 *        至 READY（1.5s 间隔/120s·80 次上限，SPEC §3.2 建议 + 阶段II 裁定）→ 成功提示并刷新文档列表。
 * 低质拦截：qualityPassed=false 或 20003 错误时展示 qualityReasons，禁用入库。
 * 30003 INGEST_FAILED（注意与低质 20003 严格区分）→ 错误气泡 + 重试。
 *
 * T2.6.2 批量路径改 **Job 化**（原 T-022 L-02 前端逐篇串行 await 已废弃）：
 *   多行粘贴 → `POST /spaces/{id}/docs:batch`（202 **提交即返**，同步段零抓取）
 *   → 前端仅轮询 `GET /jobs/{id}` 展示聚合进度；jobId 落 sessionStorage 断点，
 *   **刷新不丢**（进度真相在后端 Job/JobItem）；终态失败可 `POST /jobs/{id}/retry`
 *   单篇重试。前端不再逐篇 resolve/extract/submit——那既慢（50 篇串行）又不可续。
 */

export default function AddArticlePanel({
  spaceId,
  onSubmitted,
}: {
  spaceId: string;
  onSubmitted?: () => void;
}) {
  const [open, setOpen] = useState(false); // 面板展开（避免干扰详情页默认视图）
  const [url, setUrl] = useState("");

  const ingest = useBatchIngest({ spaceId, open, onSubmitted });
  const {
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
    busy,
    parse,
    submit,
    runBatch,
    retryBatch,
    resumeExistingBatch,
    dismissBatch,
    dismissCheckpoint,
  } = ingest;

  /** 收起：面板展开态与输入框在本组件，编排态复位走 hook（不清 jobId 断点） */
  function reset() {
    setOpen(false);
    setUrl("");
    ingest.reset();
  }

  const urlText = url.trim();
  const multiLine = /\r?\n/.test(urlText) && urlText.length > 0;
  const batchPlan = multiLine ? parseBatchUrls(urlText) : null;

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="mt-4 rounded-input bg-brand-500 px-4 py-2 text-base text-white hover:bg-brand-600"
      >
        添加文章
      </button>
    );
  }

  return (
    <section className="card mt-5 p-5 sm:p-6" aria-label="添加文章面板">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="eyebrow">ADD A SOURCE</p>
          <h2 className="mt-1 text-title-sm font-semibold text-neutral-900">添加文章</h2>
          {/* 两种采集方式口径（M2+）：粘贴即时采集 vs 订阅后台增量采集。
              原 SPEC D5/(a)「仅支持单篇文章链接」是 M1 范围红线，订阅实装后已失效，勿再引用。 */}
          <p className="mt-1 text-caption text-neutral-400">
            支持单篇公众号文章链接与多行批量粘贴（mp.weixin.qq.com），提交后即时采集入库；
            整号持续采集用下方「订阅此号」，由后台按同步间隔增量拉取新文章。
          </p>
        </div>
        <button
          onClick={reset}
          className="text-caption text-neutral-400 hover:text-neutral-600"
        >
          收起
        </button>
      </div>

      {/* 输入区：T-022 L-02 多行 → 批量入口；单行 → 原有单篇解析入口 */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const u = urlText;
          if (!u || busy) return;
          if (multiLine) {
            void runBatch(u);
            return;
          }
          void parse(u);
        }}
        className="mt-4 flex flex-col gap-3"
      >
        <textarea
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="粘贴公众号文章链接，可换行粘贴多篇（每行一条），例如 https://mp.weixin.qq.com/s/..."
          aria-label="文章链接"
          rows={multiLine ? 4 : 2}
          disabled={busy || phase === "parsing" || phase === "submitting" || phase === "polling" || phase === "batching"}
          className="w-full resize-y rounded-input border border-neutral-300 bg-neutral-50 px-4 py-2 text-base outline-none focus:border-brand-500 focus:bg-white disabled:opacity-60"
        />
        {batchPlan && (
          <p className="text-caption text-neutral-500">
            识别到 {batchPlan.urls.length} 条有效链接
            {batchPlan.duplicatedCount > 0
              ? `（已跳过 ${batchPlan.duplicatedCount} 条重复）`
              : ""}
            {batchPlan.rawCount < batchPlan.urls.length + batchPlan.duplicatedCount
              ? "，其余行非法已忽略"
              : ""}
            ，将提交为批量任务（提交即返，可在下方查看进度）。
          </p>
        )}
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={
              !urlText ||
              busy ||
              phase === "parsing" ||
              phase === "submitting" ||
              phase === "polling" ||
              phase === "batching"
            }
            className="rounded-input bg-brand-500 px-5 py-2 text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {phase === "parsing" || phase === "polling" || phase === "batching"
              ? "处理中…"
              : multiLine
                ? `批量入库 ${batchPlan?.urls.length ?? 0} 篇`
                : "解析"}
          </button>
          {multiLine && !busy && (
            <p className="text-caption text-neutral-400">
              支持换行批量粘贴，每行一条链接。
            </p>
          )}
        </div>
      </form>

      {/* T-022 L-03：预览断点横幅（刷新/回入后提示重新解析） */}
      {checkpoint &&
        phase !== "preview" &&
        phase !== "submitting" &&
        phase !== "polling" &&
        !busy && (
          <div className="mt-4 rounded-card border border-blue-200 bg-blue-50 p-4">
            <p className="text-base text-blue-700">
              上次预览《{checkpoint.title}》（{checkpoint.wordCount} 字 · 质量分{" "}
              {checkpoint.qualityScore}）未入库，刷新后预览已丢失。
            </p>
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => void parse(checkpoint.url)}
                className="rounded-input border border-blue-500 px-3 py-1 text-base text-blue-600 hover:bg-blue-100"
              >
                点击重新解析
              </button>
              <button
                onClick={dismissCheckpoint}
                className="rounded-input border border-neutral-300 px-3 py-1 text-base text-neutral-500 hover:border-neutral-400 hover:text-neutral-700"
              >
                忽略
              </button>
            </div>
          </div>
        )}

      {/* 错误气泡 + 重试。重试 = 重新解析 lastUrl，故仅在有过解析目标时才给：
          批量断点类错误（如 30004 死链）在此时 lastUrl 为空，点了只会把可操作文案
          换成一条无关的「链接形态不合法」。 */}
      {errorMsg && (
        <div className="mt-4 rounded-card border border-red-200 bg-red-50 p-4">
          <p className="text-danger">{errorMsg}</p>
          {lastUrl && (
            <button
              onClick={() => void parse(lastUrl)}
              className="mt-3 rounded-input border border-brand-500 px-3 py-1 text-base text-brand-500 hover:bg-brand-50"
            >
              重试
            </button>
          )}
        </div>
      )}

      {/* 低质拦截提示（qualityReasons 可观测，禁用入库） */}
      {qualityReasons.length > 0 && (
        <div className="mt-4 rounded-card border border-amber-200 bg-amber-50 p-4">
          <p className="font-medium text-amber-700">
            内容质量不足，已拦截入库
          </p>
          <ul className="mt-2 list-inside list-disc text-base text-amber-600">
            {qualityReasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
          <button
            onClick={() => void parse(lastUrl)}
            className="mt-3 rounded-input border border-neutral-300 px-3 py-1 text-base text-neutral-500 hover:border-neutral-400 hover:text-neutral-700"
          >
            重新解析
          </button>
        </div>
      )}

      {/* 解析中骨架（T1.2.3 起复用 Skeleton 基础件） */}
      {phase === "parsing" && (
        <div className="mt-4" aria-label="解析中骨架">
          <div className="mb-3 h-5 w-2/3 animate-pulse rounded bg-neutral-200" />
          <div className="h-4 w-full animate-pulse rounded bg-neutral-100" />
          <div className="mt-3 h-4 w-5/6 animate-pulse rounded bg-neutral-100" />
        </div>
      )}

      {/* 解析预览卡（T1.2.4 子组件；提交中/轮询中保持可见，展示入库进度） */}
      {(phase === "preview" || phase === "submitting" || phase === "polling") && preview && (
        <ParsePreviewCard
          data={preview.data}
          submitting={phase === "submitting"}
          polling={phase === "polling"}
          pollSeconds={pollSeconds}
          submitError={submitError}
          onSubmit={() => void submit()}
        />
      )}

      {/* T2.6.2：批量 Job 进度面板（T1.2.4 子组件，已改 Job 化聚合展示） */}
      {batchJob && (
        <BatchProgressList
          state={batchJob}
          submitting={batchSubmitting}
          polling={batchPolling}
          retrying={batchRetrying}
          errorMsg={batchError}
          onRetry={() => void retryBatch()}
          onResume={resumeExistingBatch}
          onDismiss={dismissBatch}
        />
      )}

      {/* 入库成功提示（T1.2.4 子组件） */}
      {phase === "submitted" && (
        <SubmitSuccessCard
          hitCache={hitCache}
          hitCount={hitCount}
          title={preview?.data.title ?? ""}
          onDone={reset}
        />
      )}
    </section>
  );
}
