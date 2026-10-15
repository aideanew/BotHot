"use client";

/**
 * PushConsolePanel —— STEP-14b S14b.3.1：触发一次推送并**如实显示终态回执**。
 *
 * R7.5.4 之后通道未就绪时后端回 **200 + delivered=false + reason**（不再是 503/异常），
 * 这一屏的全部意义就在于把那个 reason 呈现出来：如果前端按"没抛异常 = 成功"渲染，
 * 用户会看到"已推送"而实际一条都没投出去——这正是 T6.2 立读侧接口要防的事。
 *
 * 未实接的通道仍可提交（后端会回 delivered=false + 原因），所以这里不用 implemented
 * 去禁用按钮，只用它改变徽标——把"没做"和"没配"都塞进 disabled 会让人以为功能存在。
 */

import { useCallback, useEffect, useState } from "react";
import LoadingErrorShell from "@/components/LoadingErrorShell";
import StatusPill from "./StatusPill";
import { adminPush, listPushChannels, type AdminPushReceipt, type PushChannelRow } from "@/lib/api/admin-ops";
import { ApiError } from "@/lib/api/types";

export default function PushConsolePanel() {
  const [channels, setChannels] = useState<PushChannelRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [channel, setChannel] = useState("");
  const [externalUserId, setExternalUserId] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [receipt, setReceipt] = useState<AdminPushReceipt | null>(null);
  const [failure, setFailure] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const list = await listPushChannels();
      setChannels(list);
      if (list.length > 0) setChannel((prev) => prev || list[0].channel);
    } catch (e) {
      setError(
        e instanceof ApiError && e.code === 10004
          ? "权限不足：推送需要 operator 以上角色"
          : "推送通道读取失败，请稍后重试"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function submit() {
    setSending(true);
    setReceipt(null);
    setFailure("");
    try {
      setReceipt(await adminPush({ channel, externalUserId: externalUserId.trim(), message: message.trim() }));
    } catch (e) {
      // 校验类失败（10005 空内容/未知通道、30004 空间或文档不存在）走这里
      setFailure(e instanceof ApiError ? `${e.code} · ${e.message}` : "推送请求失败，请稍后重试");
    } finally {
      setSending(false);
    }
  }

  return (
    <LoadingErrorShell loading={loading} error={error} onRetry={load} loadingText="读取推送通道…">
      <div className="card p-4">
        <p className="text-title-md font-semibold text-neutral-900">触发一次推送</p>
        <p className="mt-1 text-caption text-neutral-600">
          operator 以上可代用户投递。回执以 <code className="font-mono">delivered</code> 为准，不是「有没有报错」。
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="block text-caption text-neutral-600">
            通道
            <select
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
              className="mt-1 w-full rounded-input border border-neutral-300 px-3 py-2 text-sm"
            >
              {channels.length === 0 ? <option value="">（注册表为空）</option> : null}
              {channels.map((c) => (
                <option key={c.channel} value={c.channel}>
                  {c.channel}
                  {c.implemented ? "" : "（未实接）"}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-caption text-neutral-600">
            外部用户 ID
            <input
              value={externalUserId}
              onChange={(e) => setExternalUserId(e.target.value)}
              placeholder="渠道侧的接收者标识"
              className="mt-1 w-full rounded-input border border-neutral-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="block text-caption text-neutral-600 sm:col-span-2">
            正文（不填则需从空间/文档触发，本屏暂不提供选择器）
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
              className="mt-1 w-full rounded-input border border-neutral-300 px-3 py-2 text-sm"
            />
          </label>
        </div>
        <button
          type="button"
          disabled={sending || !channel || !externalUserId.trim()}
          onClick={() => void submit()}
          className="mt-3 rounded-input bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {sending ? "投递中…" : "投递"}
        </button>
      </div>

      {failure ? (
        <div className="card mt-4 border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <StatusPill tone="bad" label="被拒绝" />
          <p className="mt-2">{failure}</p>
        </div>
      ) : null}

      {receipt ? (
        <div
          className={`card mt-4 p-4 text-sm ${
            receipt.delivered ? "border border-emerald-200 bg-emerald-50 text-emerald-900" : "border border-amber-300 bg-amber-50 text-amber-900"
          }`}
        >
          <StatusPill
            tone={receipt.delivered ? "ok" : "degraded"}
            label={receipt.delivered ? "已投递" : "未投递"}
          />
          <p className="mt-2 font-mono text-caption">
            channel={receipt.channel} delivered={String(receipt.delivered)}
          </p>
          {!receipt.delivered && receipt.reason ? (
            <p className="mt-1">
              原因：<strong>{receipt.reason}</strong>
            </p>
          ) : null}
          {!receipt.delivered ? (
            <p className="mt-1 text-caption">
              这是 200 回执而非异常：请求被接受但没有真正投递。别把它当成功。
            </p>
          ) : null}
        </div>
      ) : null}
    </LoadingErrorShell>
  );
}
