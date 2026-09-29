import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/AuthContext";
import {
  ApiError,
  listSpaces,
  listSubscriptions,
  getJob,
  retryJob,
  registerSource,
  subscribeToSource,
  type Space,
  type SubscriptionItem,
  type SubscriptionView,
  type JobView,
} from "@/lib/api";

export function useSubscriptions() {
  const { status } = useAuth();
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [selectedSpaceId, setSelectedSpaceId] = useState("");
  const [bizInput, setBizInput] = useState("");
  const [registering, setRegistering] = useState(false);
  const [actionError, setActionError] = useState("");
  const [subscriptions, setSubscriptions] = useState<SubscriptionItem[]>([]);
  const [jobs, setJobs] = useState<Record<string, JobView>>({});
  const [loading, setLoading] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [netFailCount, setNetFailCount] = useState(0);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setActionError("");
    try {
      const list = await listSpaces();
      setSpaces(list);
      if (list.length > 0) {
        setSelectedSpaceId((prev) => prev || list[0].id);
      }
    } catch {
      setActionError("加载空间列表失败，请重试");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (status !== "authed") return;
    loadAll();
  }, [status, loadAll]);

  useEffect(() => {
    if (!selectedSpaceId || status !== "authed") return;
    let cancelled = false;
    listSubscriptions(selectedSpaceId)
      .then((items) => {
        if (cancelled) return;
        setSubscriptions(items);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [selectedSpaceId, status]);

  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      const next: Record<string, JobView> = {};
      let failCount = 0;
      for (const sub of subscriptions) {
        if (sub.latestJobId) {
          try {
            next[sub.latestJobId] = await getJob(sub.latestJobId);
          } catch {
            failCount += 1;
          }
        }
      }
      if (Object.keys(next).length > 0) setJobs(next);
      setNetFailCount((prev) =>
        failCount > 0 ? prev + 1 : Math.max(0, prev - 1)
      );
    }, 5000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [subscriptions]);

  const applySubscriptionView = useCallback((view: SubscriptionView) => {
    setSubscriptions((prev) =>
      prev.map((s) =>
        s.subscriptionId === view.subscriptionId
          ? {
              ...s,
              syncPolicy: view.syncPolicy,
              syncIntervalMinutes: view.syncIntervalMinutes,
              syncAnchorHour: view.syncAnchorHour ?? null,
              nextRunAt: view.nextRunAt,
              status: view.status,
            }
          : s
      )
    );
  }, []);

  const handleRegisterAndSubscribe = async () => {
    setRegistering(true);
    setActionError("");
    try {
      const biz = bizInput.trim();
      if (!biz) {
        setActionError("请输入公众号 biz 或 profile URL");
        return;
      }
      if (!selectedSpaceId) {
        setActionError("请先选择目标空间");
        return;
      }
      const src = await registerSource({ biz });
      const r = await subscribeToSource(selectedSpaceId, src.sourceId);
      if (r.created) {
        setSubscriptions((prev) => [
          ...prev,
          {
            subscriptionId: r.subscriptionId,
            sourceId: src.sourceId,
            biz: src.biz,
            sourceName: src.name,
            syncPolicy: "auto",
            nextRunAt: "",
            status: "ACTIVE",
            latestJobId: r.jobIds[0] ?? "",
          },
        ]);
      }
      setBizInput("");
    } catch (e) {
      if (e instanceof ApiError && (e.code === 30004 || e.code === 30101)) {
        setActionError("空间或信息源不存在，请检查后重试");
      } else {
        setActionError("订阅失败，请稍后重试");
      }
    } finally {
      setRegistering(false);
    }
  };

  const handleRetry = async (jobId: string) => {
    try {
      await retryJob(jobId);
      setActionError("");
      try {
        const jv = await getJob(jobId);
        setJobs((prev) => ({ ...prev, [jobId]: jv }));
      } catch {
        // keep old value
      }
    } catch {
      setActionError("重试失败，请稍后再试");
    }
  };

  return {
    status,
    spaces, selectedSpaceId, setSelectedSpaceId,
    bizInput, setBizInput,
    registering, actionError,
    subscriptions, jobs, loading, netFailCount,
    loadAll, handleRegisterAndSubscribe, handleRetry, applySubscriptionView,
  };
}
