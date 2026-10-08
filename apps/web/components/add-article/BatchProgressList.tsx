"use client";

/**
 * BatchProgressList —— T1.2.4 批量进度子组件；**T2.6.2 改 Job 化**（原逐篇串行清单段）。
 *
 * 变更理由：后端 T2.6.1 起批量入库是 Job 化的——进度真相在 `GET /jobs/{id}` 的
 * `counts{total,succeeded,failed,pending}`，前端不再逐篇记账，故本组件由「逐篇列表」
 * 改为「聚合进度条 + 计数 + 终态汇总/重试」。纯展示，状态与副作用留在面板。
 *
 * R0.4.3：CANCELLED 加入终态后须单独成句——取消的批量作业 `counts.failed === 0`，
 * 若走「成功数」分支会显示「已完成：0 篇全部成功」，把用户主动取消读成系统完成。
 */
import type { JobView } from "@/lib/api";
import { batchProgressPercent, isBatchJobTerminal, jobStatusLabel } from "@/lib/api";
import type { BatchJobState } from "@/components/add-article/types";

interface Props {
  state: BatchJobState;
  /** 提交中（尚未拿到 jobId） */
  submitting: boolean;
  /** 轮询中 */
  polling: boolean;
  /** 失败重试中 */
  retrying: boolean;
  /** 提交/轮询错误文案（空串=无错） */
  errorMsg: string;
  /** 终态失败篇单篇重试（POST /jobs/{id}/retry） */
  onRetry: () => void;
  /** 网络中断后继续轮询（不重试篇目，仅恢复进度查看） */
  onResume: () => void;
  onDismiss: () => void;
}

export default function BatchProgressList({
  state,
  submitting,
  polling,
  retrying,
  errorMsg,
  onRetry,
  onResume,
  onDismiss,
}: Props) {
  const job: JobView | null = state.job;
  const status = job?.status ?? "";
  const counts = job?.counts ?? {
    total: state.urlCount,
    succeeded: 0,
    failed: 0,
    pending: state.urlCount,
  };
  const percent = batchProgressPercent(counts);
  const terminal = job !== null && isBatchJobTerminal(status);
  const cancelled = terminal && status === "CANCELLED";
  const hasFailure = counts.failed > 0;
  const busy = submitting || polling || retrying;

  return (
    <div className="mt-4 rounded-card border border-neutral-200 p-5" aria-label="批量入库进度">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-title-sm font-medium text-neutral-900">
          批量入库进度 {counts.succeeded + counts.failed}/{counts.total || state.urlCount}
        </h3>
        <div className="flex items-center gap-2">
          {state.skipped > 0 && (
            <span className="rounded-full bg-neutral-100 px-2.5 py-0.5 text-caption text-neutral-500">
              已跳过 {state.skipped} 条重复
            </span>
          )}
          <span className="rounded-full bg-neutral-100 px-2.5 py-0.5 text-caption text-neutral-500">
            {submitting
              ? "正在提交…"
              : retrying
                ? "正在重试…"
                : terminal
                  ? jobStatusLabel(status)
                  : "同步中…"}
          </span>
        </div>
      </div>

      {/* 进度条：已完成（成功+失败）/ 总数 */}
      <div
        className="mt-3 h-2 w-full overflow-hidden rounded-full bg-neutral-100"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <div
          className={`h-full transition-all ${hasFailure ? "bg-amber-500" : "bg-brand-500"}`}
          style={{ width: `${percent}%` }}
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-caption text-neutral-500">
        <span className="text-green-600">成功 {counts.succeeded}</span>
        <span className={hasFailure ? "text-red-600" : ""}>失败 {counts.failed}</span>
        <span>待处理 {counts.pending}</span>
        <span>共 {counts.total || state.urlCount} 篇</span>
      </div>

      {/* 终态汇总 */}
      {terminal && (
        <p className="mt-3 text-caption text-neutral-600">
          {cancelled
            ? `批量入库已取消：已完成 ${counts.succeeded} 篇，剩余篇目不再入库。`
            : counts.failed === 0
              ? `批量入库完成：${counts.succeeded} 篇全部成功。`
              : `批量入库结束：成功 ${counts.succeeded} 篇，失败 ${counts.failed} 篇（PARTIAL_SUCCESS）。`}
        </p>
      )}

      {/* 失败汇总 + 单篇重试（后端 POST /jobs/{id}/retry 只重试 FAILED item） */}
      {terminal && hasFailure && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            onClick={onRetry}
            disabled={busy}
            className="rounded-input border border-brand-500 px-3 py-1 text-base text-brand-500 hover:bg-brand-50 disabled:opacity-50"
          >
            {retrying ? "重试中…" : `重试失败的 ${counts.failed} 篇`}
          </button>
          <span className="text-caption text-neutral-400">
            重试仅针对失败篇目，已成功的不会重复入库。
          </span>
        </div>
      )}

      {/* 提交/轮询错误（网络异常等；不阻断已提交 Job 的进度恢复） */}
      {errorMsg && (
        <div className="mt-3 rounded-card border border-red-200 bg-red-50 p-3">
          <p className="text-caption text-danger">{errorMsg}</p>
          <div className="mt-2 flex gap-2">
            <button
              onClick={onResume}
              disabled={busy}
              className="rounded-input border border-brand-500 px-3 py-1 text-caption text-brand-500 hover:bg-brand-50 disabled:opacity-50"
            >
              继续同步
            </button>
            <button
              onClick={onDismiss}
              className="rounded-input border border-neutral-300 px-3 py-1 text-caption text-neutral-500 hover:border-neutral-400 hover:text-neutral-700"
            >
              关闭
            </button>
          </div>
        </div>
      )}

      {/* 终态且无失败：允许关闭面板（清除 jobId 断点） */}
      {terminal && !hasFailure && (
        <button
          onClick={onDismiss}
          className="mt-3 rounded-input border border-neutral-300 px-3 py-1 text-caption text-neutral-500 hover:border-neutral-400 hover:text-neutral-700"
        >
          {cancelled ? "关闭" : "完成"}
        </button>
      )}
    </div>
  );
}
