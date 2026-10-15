"use client";

/**
 * DiscoveryChannelsPanel —— STEP-14b S14b.3.3：发现渠道就绪度（只读 + 启停说明）。
 *
 * 三布尔**不合并**成一个 available 是后端 registry 的纪律（R7.6）：
 * implemented=代码实接、enabled=在启用白名单、available=凭据就位。
 * 合成一列就把"功能没做"和"功能没配"混成一谈，运维会去查一个根本没实现的渠道。
 * `defaultChannel=null` 也必须显示成"本轮不做发现"，不是显示成空字符串。
 */

import { useCallback, useEffect, useState } from "react";
import LoadingErrorShell from "@/components/LoadingErrorShell";
import StatusPill, { type PillTone } from "./StatusPill";
import {
  listDiscoveryChannels,
  listPushChannels,
  type DiscoveryChannelView,
  type PushChannelRow,
} from "@/lib/api/admin-ops";
import { ApiError } from "@/lib/api/types";

function flagTone(on: boolean): PillTone {
  return on ? "ok" : "bad";
}

export default function DiscoveryChannelsPanel() {
  const [discovery, setDiscovery] = useState<DiscoveryChannelView | null>(null);
  const [push, setPush] = useState<PushChannelRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [d, p] = await Promise.all([listDiscoveryChannels(), listPushChannels()]);
      setDiscovery(d);
      setPush(p);
    } catch (e) {
      setDiscovery(null);
      setPush(null);
      setError(
        e instanceof ApiError && e.code === 10004
          ? "权限不足：渠道就绪度需要 operator 以上角色"
          : "渠道清单读取失败，请稍后重试"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <LoadingErrorShell loading={loading} error={error} onRetry={load} loadingText="读取渠道注册表…">
      {discovery ? (
        <div className="card overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-100 px-4 py-3">
            <p className="text-title-md font-semibold text-neutral-900">发现渠道</p>
            <p className="text-caption text-neutral-600">
              当前默认：
              {/* null 是"本轮调度不做发现、仅按既有清单 diff"，不是"渠道名为空" */}
              <strong>{discovery.defaultChannel ?? "（不设默认，仅做清单 diff）"}</strong>
              {discovery.selectionReason ? ` · ${discovery.selectionReason}` : ""}
            </p>
          </div>
          {discovery.channels.length === 0 ? (
            <p className="px-4 py-6 text-center text-neutral-500">注册表为空——发现能力当前不可用。</p>
          ) : (
            <ul className="divide-y divide-neutral-100">
              {discovery.channels.map((c) => (
                <li key={c.name} className="px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-neutral-900">{c.name}</span>
                    <span className="text-caption text-neutral-500">{c.description}</span>
                    <StatusPill tone={flagTone(c.implemented)} label={c.implemented ? "已实接" : "未实接"} />
                    <StatusPill tone={flagTone(c.enabled)} label={c.enabled ? "已启用" : "未启用"} />
                    <StatusPill tone={flagTone(c.available)} label={c.available ? "凭据就位" : "缺凭据"} />
                  </div>
                  {c.reason ? (
                    <p className="mt-1 text-caption text-amber-900">原因：{c.reason}</p>
                  ) : null}
                  {/* 启停是配置项（discovery_channels 白名单），不是本屏的写操作：
                      在这里放一个开关会假装后端有 PATCH 端点，而它没有。 */}
                  <p className="mt-1 text-caption text-neutral-500">
                    启用状态由配置项 <code className="font-mono">discovery_channels</code> /{" "}
                    <code className="font-mono">discovery_default_channel</code> 决定，改配置需重启 backend。
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
      {push ? (
        <div className="card mt-4 p-4">
          <p className="text-title-md font-semibold text-neutral-900">推送通道</p>
          {push.length === 0 ? (
            <p className="mt-2 text-caption text-neutral-500">注册表为空——没有可投递的通道。</p>
          ) : (
            <ul className="mt-2 flex flex-wrap gap-2">
              {push.map((c) => (
                <li key={c.channel} className="flex items-center gap-2 rounded-input border border-neutral-200 px-3 py-1.5">
                  <span className="text-sm text-neutral-800">{c.channel}</span>
                  <StatusPill tone={flagTone(c.implemented)} label={c.implemented ? "可投递" : "未实接"} />
                  <span className="text-caption text-neutral-500">{c.description}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </LoadingErrorShell>
  );
}
