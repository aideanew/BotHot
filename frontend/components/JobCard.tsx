import { useState } from "react";
import { formatTime } from "./DocStatusBadge";
import {
  getJob,
  isBatchJobTerminal,
  jobErrorText,
  jobStatusLabel,
  jobTypeLabel,
  RETRYABLE_STATUSES,
} from "@/lib/api";
import type { JobListItem, JobView } from "@/lib/api";

function statusDot(status: string): { cls: string; label: string } {
  const label = jobStatusLabel(status);
  switch (status) {
    case "QUEUED":
      return { cls: "bg-neutral-400", label };
    case "RUNNING":
      return { cls: "bg-brand-500", label };
    case "SUCCEEDED":
      return { cls: "bg-green-500", label };
    case "PARTIAL_SUCCESS":
      return { cls: "bg-amber-500", label };
    case "FAILED":
      return { cls: "bg-red-500", label };
    default:
      return { cls: "bg-neutral-300", label };
  }
}

interface JobCardProps {
  job: JobListItem;
  onCancel?: (jobId: string) => void;
  onRetry?: (jobId: string) => void;
  /** 重试请求进行中（禁用按钮，避免连点重复入队） */
  retrying?: boolean;
}

export default function JobCard({ job: j, onCancel, onRetry, retrying }: JobCardProps) {
  const dot = statusDot(j.status);
  const err = jobErrorText(j.error);
  const retryable = RETRYABLE_STATUSES.has(j.status) && !!onRetry;

  // 篇级失败明细按需钻取：列表页不逐条拉详情（列表每 5s 轮询一次，
  // 失败任务多时会放大成 N 条请求），只有用户展开时才取。
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<JobView | null>(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const [detailError, setDetailError] = useState("");

  const toggle = async () => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (detail || detailBusy) return;
    setDetailBusy(true);
    setDetailError("");
    try {
      setDetail(await getJob(j.jobId));
    } catch {
      setDetailError("失败明细加载失败，请稍后再试");
    } finally {
      setDetailBusy(false);
    }
  };

  return (
    <li className="card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 text-base font-medium text-neutral-900">
            {jobTypeLabel(j.type)}
            <span className="flex items-center gap-1.5 text-caption font-normal text-neutral-500">
              <span
                className={`inline-block h-2 w-2 rounded-full ${dot.cls}`}
                aria-hidden
              />
              {dot.label}
            </span>
          </p>
          <p className="mt-1 text-caption text-neutral-400">
            创建于 {formatTime(j.createdAt)}
            {j.workerHeartbeatAt
              ? ` · 最近心跳 ${formatTime(j.workerHeartbeatAt)}`
              : " · 尚未被 worker 认领"}
          </p>
          {err && (
            <p className="mt-1 truncate text-caption text-red-600" title={err}>
              {err}
            </p>
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          {retryable && (
            <button
              type="button"
              onClick={() => onRetry?.(j.jobId)}
              disabled={retrying}
              className="rounded border border-brand-400 px-3 py-1 text-caption text-brand-600 hover:bg-brand-50 disabled:opacity-50"
            >
              {retrying ? "重试中…" : "重试失败篇目"}
            </button>
          )}
          {j.status === "QUEUED" && onCancel && (
            <button
              type="button"
              onClick={() => onCancel(j.jobId)}
              className="rounded border border-neutral-300 px-3 py-1 text-caption text-neutral-500 hover:border-red-400 hover:text-red-600"
            >
              取消
            </button>
          )}
        </div>
      </div>

      <div className="mt-2 flex gap-3">
        <button
          type="button"
          onClick={() => void toggle()}
          aria-expanded={open}
          className="text-caption text-neutral-400 hover:text-neutral-700"
        >
          {open ? "收起明细" : "查看篇目明细"}
        </button>
        {!isBatchJobTerminal(j.status) && (
          <span className="text-caption text-neutral-300">任务仍在进行中</span>
        )}
      </div>

      {open && (
        <div className="mt-2 border-t border-neutral-100 pt-2">
          {detailBusy && (
            <p className="text-caption text-neutral-400">加载明细中…</p>
          )}
          {detailError && (
            <p className="text-caption text-red-600">{detailError}</p>
          )}
          {detail && (
            <JobDetail detail={detail} />
          )}
        </div>
      )}

      {j.status === "RUNNING" && (
        <div className="mt-3">
          <div className="mb-1 flex justify-between text-caption text-neutral-500">
            <span>进度</span>
            <span>{j.progress}%</span>
          </div>
          <div
            className="h-1.5 w-full overflow-hidden rounded bg-neutral-100"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={j.progress}
          >
            <div
              className="h-full bg-brand-500 transition-all"
              style={{ width: `${j.progress}%` }}
            />
          </div>
        </div>
      )}
    </li>
  );
}

function JobDetail({ detail }: { detail: JobView }) {
  const c = detail.counts;
  const failed = detail.failedItems ?? [];

  return (
    <div className="space-y-2">
      <p className="text-caption text-neutral-500">
        共 {c.total} 篇 · 成功 {c.succeeded} · 失败 {c.failed} · 待处理 {c.pending}
      </p>
      {c.total === 0 && (
        <p className="text-caption text-neutral-400">该任务没有篇目明细。</p>
      )}
      {failed.length > 0 && (
        <ul className="space-y-1.5" aria-label="失败篇目">
          {failed.map((it) => (
            <li key={it.itemId} className="text-caption text-neutral-600">
              {it.url ? (
                <a
                  href={it.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block truncate text-brand-600 hover:underline"
                  title={it.url}
                >
                  {it.url}
                </a>
              ) : (
                <span className="text-neutral-400">（无原文链接）</span>
              )}
              <span className="block truncate text-red-600" title={jobErrorText(it.error)}>
                {jobErrorText(it.error) || "（未记录失败原因）"}
                {it.retryCount > 0 && ` · 已重试 ${it.retryCount} 次`}
              </span>
            </li>
          ))}
        </ul>
      )}
      {failed.length === 0 && c.failed > 0 && (
        <p className="text-caption text-neutral-400">有失败篇目但未记录原因。</p>
      )}
    </div>
  );
}
