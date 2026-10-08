"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useJobsList } from "@/components/useJobsList";
import ConfirmModal from "@/components/ConfirmModal";
import JobCard from "@/components/JobCard";
import JobFilterBar from "@/components/JobFilterBar";
import LoadingErrorShell from "@/components/LoadingErrorShell";
import {
  POLL_NET_FAIL_THRESHOLD,
  jobTypeLabel,
  networkPauseMessage,
} from "@/lib/api";
import { usePageTitle } from "@/components/usePageTitle";

export default function JobsPage() {
  const {
    authStatus,
    typeFilter, statusFilter, setTypeFilter, setStatusFilter,
    items, total, loading, error, loadingMore,
    netFailCount, pendingCancel, cancelling, retryingJobId, actionError,
    hasMore, hasFilter,
    setPendingCancel, setActionError,
    loadFirst, loadMore, handleCancel, handleRetry,
  } = useJobsList();
  usePageTitle("任务中心");

  if (authStatus !== "authed") return null;

  const target = items.find((j) => j.jobId === pendingCancel);

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">JOBS</p>
          <h1 className="text-title-lg font-semibold text-neutral-900">任务中心</h1>
          <p className="mt-2 text-base text-neutral-500">
            全部入库与同步任务的进度、篇目明细与失败原因，含排队取消和失败篇目重试入口（跨空间）。
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadFirst()}
          disabled={loading || loadingMore}
          className="shrink-0 rounded-input border border-neutral-300 px-3 py-1 text-caption text-neutral-500 hover:border-neutral-400 hover:text-neutral-700 disabled:opacity-50"
        >
          刷新
        </button>
      </div>

      <JobFilterBar
        typeFilter={typeFilter}
        statusFilter={statusFilter}
        total={total}
        onTypeChange={(v) => { setTypeFilter(v); setActionError(""); }}
        onStatusChange={(v) => { setStatusFilter(v); setActionError(""); }}
      />

      {netFailCount >= POLL_NET_FAIL_THRESHOLD && (
        <div className="mb-4 rounded-card border border-amber-200 bg-amber-50 p-4">
          <p className="text-base text-amber-700">{networkPauseMessage(netFailCount)}</p>
        </div>
      )}

      {actionError && (
        <div className="mb-4 rounded-card border border-red-200 bg-red-50 p-4">
          <p className="text-base text-red-700">{actionError}</p>
        </div>
      )}

      <LoadingErrorShell
        loading={loading}
        error={error}
        onRetry={() => void loadFirst()}
        loadingText="加载任务列表…"
        skeletonRows={4}
      >
        {items.length === 0 ? (
          <div className="card p-8 text-center text-neutral-500">
            {hasFilter
              ? "没有符合条件的任务——换个筛选条件试试。"
              : "还没有任务记录。"}
          </div>
        ) : (
          <ul aria-label="任务列表" className="space-y-3">
            {items.map((j) => (
              <JobCard
                key={j.jobId}
                job={j}
                onCancel={(jobId) => setPendingCancel(jobId)}
                onRetry={(jobId) => void handleRetry(jobId)}
                retrying={retryingJobId === j.jobId}
              />
            ))}
          </ul>
        )}

        {hasMore && (
          <div className="mt-4 text-center">
            <button
              type="button"
              onClick={() => void loadMore()}
              disabled={loadingMore}
              className="rounded-input border border-neutral-300 px-4 py-1.5 text-base text-neutral-600 hover:border-neutral-400 hover:text-neutral-800 disabled:opacity-50"
            >
              {loadingMore ? "加载中…" : `加载更多（已显示 ${items.length}/${total}）`}
            </button>
          </div>
        )}
      </LoadingErrorShell>

      <ConfirmModal
        open={pendingCancel !== ""}
        title="取消这个任务？"
        description={
          target
            ? `「${jobTypeLabel(target.type)}」将标记为已取消，剩余篇目不再入库。已执行完成的篇目不受影响。`
            : "该任务将标记为已取消。"
        }
        confirmText="确认取消"
        cancelText="保留任务"
        busy={cancelling}
        onConfirm={() => void handleCancel()}
        onCancel={() => {
          setPendingCancel("");
          setActionError("");
        }}
      />
    </main>
  );
}
