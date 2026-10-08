import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/AuthContext";
import {
  ApiError,
  cancelJob,
  isBatchJobTerminal,
  listJobs,
  retryJob,
  type JobListItem,
} from "@/lib/api";

const PAGE_SIZE = 50;
const POLL_INTERVAL_MS = 5000;

export function useJobsList() {
  const { status: authStatus } = useAuth();
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [items, setItems] = useState<JobListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [loadingMore, setLoadingMore] = useState(false);
  const [netFailCount, setNetFailCount] = useState(0);
  const [pendingCancel, setPendingCancel] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [retryingJobId, setRetryingJobId] = useState("");
  const [actionError, setActionError] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const hasActive = items.some((j) => !isBatchJobTerminal(j.status));
  const hasMore = items.length < total;
  const hasFilter = typeFilter !== "" || statusFilter !== "";

  const loadFirst = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const page = await listJobs({
        type: typeFilter,
        status: statusFilter,
        limit: PAGE_SIZE,
        offset: 0,
      });
      setItems(page.items);
      setTotal(page.total);
      setNetFailCount(0);
    } catch (e) {
      setError(
        e instanceof ApiError && e.code === 10001
          ? "未登录，请重新登录后查看任务"
          : "任务列表加载失败，请重试"
      );
    } finally {
      setLoading(false);
    }
  }, [typeFilter, statusFilter]);

  const poll = useCallback(async () => {
    try {
      const page = await listJobs({
        type: typeFilter,
        status: statusFilter,
        limit: PAGE_SIZE,
        offset: 0,
      });
      setItems((prev) => {
        const seen = new Set(page.items.map((j) => j.jobId));
        return [...page.items, ...prev.filter((j) => !seen.has(j.jobId))];
      });
      setTotal(page.total);
      setNetFailCount((p) => Math.max(0, p - 1));
    } catch {
      setNetFailCount((p) => p + 1);
    }
  }, [typeFilter, statusFilter]);

  useEffect(() => {
    if (authStatus === "authed") void loadFirst();
  }, [authStatus, loadFirst]);

  useEffect(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (loading || error || !hasActive) return;
    pollRef.current = setInterval(() => {
      void poll();
    }, POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [hasActive, loading, error, poll]);

  const loadMore = useCallback(async () => {
    if (loading || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await listJobs({
        type: typeFilter,
        status: statusFilter,
        limit: PAGE_SIZE,
        offset: items.length,
      });
      setItems((prev) => [...prev, ...page.items]);
      setTotal(page.total);
    } catch (e) {
      setError(
        e instanceof ApiError && e.code === 10001
          ? "未登录，请重新登录后查看任务"
          : "加载更多失败，请重试"
      );
    } finally {
      setLoadingMore(false);
    }
  }, [loading, loadingMore, typeFilter, statusFilter, items.length]);

  const handleCancel = async () => {
    const jobId = pendingCancel;
    if (!jobId) return;
    setCancelling(true);
    setActionError("");
    try {
      await cancelJob(jobId);
      setPendingCancel("");
      await loadFirst();
    } catch (e) {
      setPendingCancel("");
      if (e instanceof ApiError && e.code === 30005) {
        setActionError(e.message);
      } else if (e instanceof ApiError && e.code === 30004) {
        setActionError("该任务不存在或已不在你的名下，请刷新列表");
      } else {
        setActionError("取消失败，请稍后再试");
      }
    } finally {
      setCancelling(false);
    }
  };

  const handleRetry = async (jobId: string) => {
    setRetryingJobId(jobId);
    setActionError("");
    try {
      const r = await retryJob(jobId);
      if (r.retried === 0) {
        setActionError("没有可重试的失败篇目——失败篇目可能已被处理，或该任务不存在篇目。");
      }
      await loadFirst();
    } catch (e) {
      if (e instanceof ApiError && e.code === 30005) {
        setActionError(e.message);
      } else if (e instanceof ApiError && e.code === 30004) {
        setActionError("该任务不存在或已不在你的名下，请刷新列表");
      } else {
        setActionError("重试失败，请稍后再试");
      }
    } finally {
      setRetryingJobId("");
    }
  };

  return {
    authStatus,
    typeFilter, statusFilter, setTypeFilter, setStatusFilter,
    items, total, loading, error, loadingMore,
    netFailCount, pendingCancel, cancelling, retryingJobId, actionError,
    hasMore, hasFilter,
    setPendingCancel, setActionError,
    loadFirst, loadMore, handleCancel, handleRetry,
  };
}
