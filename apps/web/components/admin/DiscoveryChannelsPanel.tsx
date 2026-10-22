"use client";

/**
 * DiscoveryChannelsPanel —— STEP-14b S14b.3.3：发现渠道就绪度 + 启停。
 *
 * 三布尔**不合并**成一个 available 是后端 registry 的纪律（R7.6）：
 * implemented=代码实接、enabled=在启用白名单、available=凭据就位。
 * 合成一列就把"功能没做"和"功能没配"混成一谈，运维会去查一个根本没实现的渠道。
 * `defaultChannel=null` 也必须显示成"本轮不做发现"，不是显示成空字符串。
 *
 * 启停在 STEP-28（D-V12-12）之后才是可写面：`PUT /admin/discovery/config` 落
 * `system_settings.discovery`，**下一轮调度生效、不需重启 backend**。这一屏早先只读，
 * 理由当时是"后端只有 GET"——那个前提已经不成立，留着只读就是把一个已存在的能力画没。
 */

import { useCallback, useEffect, useState } from "react";
import LoadingErrorShell from "@/components/LoadingErrorShell";
import StatusPill, { type PillTone } from "./StatusPill";
import {
  listDiscoveryChannels,
  listPushChannels,
  putDiscoveryConfig,
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
  // 草稿：勾选结果与默认渠道。保存前不动服务端，失败时也留着，否则一次 10005 就把运营的选择吞了
  const [enabledDraft, setEnabledDraft] = useState<string[]>([]);
  const [defaultDraft, setDefaultDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [writeError, setWriteError] = useState("");
  const [savedNote, setSavedNote] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [d, p] = await Promise.all([listDiscoveryChannels(), listPushChannels()]);
      setDiscovery(d);
      setPush(p);
      setEnabledDraft(d.channels.filter((c) => c.enabled).map((c) => c.name));
      setDefaultDraft(d.defaultChannel ?? "");
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

  const toggle = (name: string, on: boolean) => {
    setSavedNote("");
    setWriteError("");
    const next = on ? [...enabledDraft, name] : enabledDraft.filter((n) => n !== name);
    setEnabledDraft(next);
    // 后端要求 default ∈ enabled（enabled 空时只允许空串），所以取消"当前默认"必须当场补一个，
    // 否则发出去的一定是 10005。补的选择画在选择器里，不是静默改。
    if (next.length > 0 && !next.includes(defaultDraft)) setDefaultDraft(next[0]);
    if (next.length === 0) setDefaultDraft("");
  };

  const save = async () => {
    setSaving(true);
    setWriteError("");
    setSavedNote("");
    try {
      const got = await putDiscoveryConfig(enabledDraft, defaultDraft);
      setSavedNote(`已保存：启用 ${got.enabled.length} 个渠道，默认「${got.default || "（不设）"}」，下一轮调度生效。`);
      await load();
    } catch (e) {
      setWriteError(
        e instanceof ApiError
          ? `启停未生效：${e.message}`
          : "启停未生效：写入失败，请稍后重试"
      );
    } finally {
      setSaving(false);
    }
  };

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
                    <label className="flex items-center gap-2 text-sm text-neutral-900">
                      <input
                        type="checkbox"
                        checked={enabledDraft.includes(c.name)}
                        onChange={(e) => toggle(c.name, e.target.checked)}
                        aria-label={`启用 ${c.name}`}
                      />
                      {c.name}
                    </label>
                    <span className="text-caption text-neutral-500">{c.description}</span>
                    <StatusPill tone={flagTone(c.implemented)} label={c.implemented ? "已实接" : "未实接"} />
                    <StatusPill tone={flagTone(c.enabled)} label={c.enabled ? "已启用" : "未启用"} />
                    <StatusPill tone={flagTone(c.available)} label={c.available ? "凭据就位" : "缺凭据"} />
                  </div>
                  {c.reason ? (
                    <p className="mt-1 text-caption text-amber-900">原因：{c.reason}</p>
                  ) : null}
                  {/* 勾选是草稿，"已启用"丸是服务端此刻的事实——两者不同形是有意的：
                      保存后才会重读，未保存的改动不该伪装成已生效 */}
                </li>
              ))}
            </ul>
          )}

          <div className="flex flex-wrap items-center gap-3 border-t border-neutral-100 px-4 py-3">
            <label className="flex items-center gap-2 text-caption text-neutral-600">
              默认渠道
              <select
                value={defaultDraft}
                onChange={(e) => {
                  setDefaultDraft(e.target.value);
                  setSavedNote("");
                }}
                className="rounded-input border border-neutral-300 px-2 py-1 text-caption"
                aria-label="默认发现渠道"
              >
                {/* 空串只在"一个都不启用"时合法，所以有启用渠道时不提供"不设默认"这一项 */}
                {enabledDraft.length === 0 ? <option value="">（不设默认）</option> : null}
                {enabledDraft.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving}
              className="rounded-input bg-neutral-900 px-4 py-1.5 text-caption text-white hover:bg-neutral-800 disabled:opacity-50"
            >
              {saving ? "保存中…" : "保存启停配置"}
            </button>
            {writeError ? <p className="text-caption text-red-800">{writeError}</p> : null}
            {savedNote ? <p className="text-caption text-emerald-800">{savedNote}</p> : null}
          </div>
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
