"use client";

/**
 * LivenessPanel —— STEP-14b S14b.3.2：常驻进程存活（scheduler / worker / backend）。
 *
 * 这一屏存在的理由写在后端注释里：2026-09-28 实测，backend 健康检查全绿而 scheduler/worker
 * **从未启动**（compose 里有服务但 `docker restart` 不创建容器），静默失效 5 天无人察觉。
 * 所以这里必须按 EXPECTED_PROCESSES **全景**渲染，缺进程也要占一行——
 * 只渲染"有回报的进程"就等于把这次要防的盲区再造一遍。
 */

import { useCallback, useEffect, useState } from "react";
import LoadingErrorShell from "@/components/LoadingErrorShell";
import StatusPill, { livenessTone } from "./StatusPill";
import { getOpsLiveness, type OpsLiveness } from "@/lib/api/admin-ops";
import { ApiError } from "@/lib/api/types";

const THRESHOLDS = [300, 600, 1800];

export default function LivenessPanel() {
  const [data, setData] = useState<OpsLiveness | null>(null);
  const [maxAge, setMaxAge] = useState(300);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getOpsLiveness(maxAge));
    } catch (e) {
      setData(null);
      setError(
        e instanceof ApiError && e.code === 10004
          ? "权限不足：运维存活需要 operator 以上角色"
          : "运维存活读取失败，请稍后重试"
      );
    } finally {
      setLoading(false);
    }
  }, [maxAge]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <LoadingErrorShell loading={loading} error={error} onRetry={load} loadingText="读取进程心跳…">
      {data && data.processes.length === 0 ? (
        <div className="card p-6 text-center text-neutral-500">
          后端没有回报任何期望进程——这本身就是故障信号，不是「一切正常」。
        </div>
      ) : null}
      {data && data.processes.length > 0 ? (
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-neutral-100 px-4 py-3">
            <p className="text-title-md font-semibold text-neutral-900">常驻进程心跳</p>
            <label className="flex items-center gap-2 text-caption text-neutral-600">
              判定阈值
              <select
                value={maxAge}
                onChange={(e) => setMaxAge(Number(e.target.value))}
                className="rounded-input border border-neutral-300 px-2 py-1 text-caption"
                aria-label="心跳过期阈值（秒）"
              >
                {THRESHOLDS.map((s) => (
                  <option key={s} value={s}>
                    {s}s
                  </option>
                ))}
              </select>
            </label>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 text-left text-caption text-neutral-500">
              <tr>
                <th className="px-4 py-2 font-medium">进程</th>
                <th className="px-4 py-2 font-medium">用途</th>
                <th className="px-4 py-2 font-medium">最近心跳</th>
                <th className="px-4 py-2 font-medium">距今</th>
                <th className="px-4 py-2 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              {data.processes.map((p) => {
                const t = livenessTone(p);
                return (
                  <tr key={p.processKey} className="border-t border-neutral-100">
                    <td className="px-4 py-2 font-mono text-caption">{p.processKey}</td>
                    <td className="px-4 py-2 text-neutral-700">{p.purpose}</td>
                    <td className="px-4 py-2 text-neutral-600">
                      {/* null 与 0 秒前是两种故障：这里必须原样区分，不渲染成"1970-01-01" */}
                      {p.lastHeartbeatAt ?? "从未上报"}
                    </td>
                    <td className="px-4 py-2 text-neutral-600">
                      {p.ageSeconds === null ? "—" : `${p.ageSeconds}s`}
                    </td>
                    <td className="px-4 py-2">
                      <StatusPill tone={t.tone} label={t.label} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="px-4 py-3 text-caption text-neutral-500">
            {data.allHealthy
              ? `全部进程在 ${data.maxAgeSeconds}s 内有心跳。`
              : `有进程超过 ${data.maxAgeSeconds}s 未心跳。「从未启动」要补 docker compose up -d，「心跳卡死」要查进程日志——两者动作不同。`}
          </p>
        </div>
      ) : null}
    </LoadingErrorShell>
  );
}
