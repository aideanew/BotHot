"use client";

import { useCallback, useEffect, useState } from "react";
import {
  listAdminJobs,
  listAdminSubscriptions,
  cancelAdminJob,
  retryAdminJob,
  cancelAdminSubscription,
  listAdminSources,
  deleteAdminSource,
  ADMIN_RETRYABLE_STATUSES,
  type AdminSourceItem,
  type JobListItem,
  type SubscriptionItem,
  jobStatusLabel,
  jobTypeLabel,
  jobErrorText,
} from "@/lib/api";
import { cadenceLabel } from "./SubscriptionLifecycleActions";

function formatTime(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function AdminOpsSection() {
  const [jobs, setJobs] = useState<JobListItem[] | null>(null);
  const [subs, setSubs] = useState<SubscriptionItem[] | null>(null);
  const [sources, setSources] = useState<AdminSourceItem[] | null>(null);
  const [jobFilter, setJobFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [actingJob, setActingJob] = useState("");
  const [actingSub, setActingSub] = useState("");
  const [actingSource, setActingSource] = useState("");
  const [confirmingSourceDelete, setConfirmingSourceDelete] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [jRes, sRes, srcRes] = await Promise.all([
        listAdminJobs({ status: jobFilter || undefined, limit: 100 }),
        listAdminSubscriptions(),
        listAdminSources(),
      ]);
      setJobs(jRes.items);
      setSubs(sRes);
      setSources(srcRes.items);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [jobFilter]);

  useEffect(() => { load(); }, [load]);

  const handleCancelJob = useCallback(async (jobId: string) => {
    setActingJob(jobId);
    try { await cancelAdminJob(jobId); await load(); }
    catch (err: unknown) { setError(err instanceof Error ? err.message : "操作失败"); }
    finally { setActingJob(""); }
  }, [load]);

  const handleRetryJob = useCallback(async (jobId: string) => {
    setActingJob(jobId);
    try { await retryAdminJob(jobId); await load(); }
    catch (err: unknown) { setError(err instanceof Error ? err.message : "操作失败"); }
    finally { setActingJob(""); }
  }, [load]);

  const handleCancelSub = useCallback(async (subId: string) => {
    setActingSub(subId);
    try { await cancelAdminSubscription(subId); await load(); }
    catch (err: unknown) { setError(err instanceof Error ? err.message : "操作失败"); }
    finally { setActingSub(""); }
  }, [load]);

  const handleDeleteSource = useCallback(async (sourceId: string) => {
    setActingSource(sourceId);
    setConfirmingSourceDelete("");
    try { await deleteAdminSource(sourceId); await load(); }
    catch (err: unknown) { setError(err instanceof Error ? err.message : "操作失败"); }
    finally { setActingSource(""); }
  }, [load]);

  return (
    <div className="space-y-8">
      {error && (
        <div className="card p-3 text-caption text-red-600">{error}</div>
      )}

      <section>
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="text-title-sm font-semibold text-neutral-900">任务</h2>
          <select
            value={jobFilter}
            onChange={(e) => setJobFilter(e.target.value)}
            className="rounded-input border border-neutral-300 px-2 py-1 text-caption"
          >
            <option value="">全部状态</option>
            <option value="QUEUED">排队中</option>
            <option value="RUNNING">执行中</option>
            <option value="FAILED">失败</option>
            <option value="PARTIAL_SUCCESS">部分成功</option>
            <option value="SUCCEEDED">已完成</option>
            <option value="CANCELLED">已取消</option>
          </select>
        </div>
        {loading && jobs === null ? (
          <div className="card mt-3 p-4"><div className="h-4 w-1/2 animate-pulse rounded bg-neutral-100" /></div>
        ) : jobs && jobs.length === 0 ? (
          <div className="card mt-3 p-6 text-center text-caption text-neutral-500">暂无任务</div>
        ) : (
          <ul className="mt-3 space-y-2">
            {jobs?.map((j) => {
              const err = jobErrorText(j.error);
              return (
                <li key={j.jobId} className="card p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-caption font-medium text-neutral-900">
                        {jobTypeLabel(j.type)}
                        <span className="ml-2 font-normal text-neutral-500">{jobStatusLabel(j.status)}</span>
                      </p>
                      <p className="text-caption text-neutral-400">{formatTime(j.createdAt)}</p>
                      {err && <p className="truncate text-caption text-red-600" title={err}>{err}</p>}
                    </div>
                    <div className="flex shrink-0 gap-1">
                      {j.status === "QUEUED" && (
                        <button
                          type="button"
                          disabled={actingJob === j.jobId}
                          onClick={() => handleCancelJob(j.jobId)}
                          className="rounded border border-neutral-300 px-2 py-0.5 text-caption text-neutral-500 hover:border-red-400 hover:text-red-600 disabled:opacity-50"
                        >取消</button>
                      )}
                      {ADMIN_RETRYABLE_STATUSES.has(j.status) && (
                        <button
                          type="button"
                          disabled={actingJob === j.jobId}
                          onClick={() => handleRetryJob(j.jobId)}
                          className="rounded border border-neutral-300 px-2 py-0.5 text-caption text-neutral-500 hover:border-brand-400 hover:text-brand-600 disabled:opacity-50"
                        >重试</button>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section>
        <h2 className="text-title-sm font-semibold text-neutral-900">订阅</h2>
        {loading && subs === null ? (
          <div className="card mt-3 p-4"><div className="h-4 w-1/2 animate-pulse rounded bg-neutral-100" /></div>
        ) : subs && subs.length === 0 ? (
          <div className="card mt-3 p-6 text-center text-caption text-neutral-500">暂无订阅</div>
        ) : (
          <ul className="mt-3 space-y-2">
            {subs?.map((s) => (
              <li key={s.subscriptionId} className="card p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-caption font-medium text-neutral-900">{s.sourceName || s.biz}</p>
                    <p className="text-caption text-neutral-400">
                      {s.status} · {cadenceLabel(s)}
                      {s.nextRunAt ? ` · 下次同步 ${formatTime(s.nextRunAt)}` : ""}
                    </p>
                  </div>
                  {s.status !== "CANCELLED" && (
                    <button
                      type="button"
                      disabled={actingSub === s.subscriptionId}
                      onClick={() => handleCancelSub(s.subscriptionId)}
                      className="rounded border border-neutral-300 px-2 py-0.5 text-caption text-neutral-500 hover:border-red-400 hover:text-red-600 disabled:opacity-50"
                    >退订</button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="text-title-sm font-semibold text-neutral-900">来源</h2>
        {loading && sources === null ? (
          <div className="card mt-3 p-4"><div className="h-4 w-1/2 animate-pulse rounded bg-neutral-100" /></div>
        ) : sources && sources.length === 0 ? (
          <div className="card mt-3 p-6 text-center text-caption text-neutral-500">暂无来源</div>
        ) : (
          <ul className="mt-3 space-y-2">
            {sources?.map((s) => (
              <li key={s.id} className="card p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-caption font-medium text-neutral-900">{s.name || s.biz}</p>
                    <p className="text-caption text-neutral-400">
                      {s.subscriptionCount} 订阅 · {s.assetCount} 资产 · {s.manifestCount} 清单
                    </p>
                  </div>
                  {confirmingSourceDelete === s.id ? (
                    <div className="flex shrink-0 gap-1">
                      <button
                        type="button"
                        disabled={actingSource === s.id}
                        onClick={() => handleDeleteSource(s.id)}
                        className="rounded bg-red-600 px-2 py-0.5 text-caption text-white disabled:opacity-50"
                      >确认</button>
                      <button
                        type="button"
                        onClick={() => setConfirmingSourceDelete("")}
                        className="rounded border border-neutral-300 px-2 py-0.5 text-caption text-neutral-500"
                      >取消</button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      disabled={actingSource === s.id}
                      onClick={() => setConfirmingSourceDelete(s.id)}
                      className="rounded border border-neutral-300 px-2 py-0.5 text-caption text-neutral-500 hover:border-red-400 hover:text-red-600 disabled:opacity-50"
                    >删除</button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
