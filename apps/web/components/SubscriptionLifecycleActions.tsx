"use client";

import { useState } from "react";
import ConfirmModal, { type ConfirmOption } from "@/components/ConfirmModal";
import {
  cancelSubscription,
  updateSubscription,
  type SubscriptionItem,
  type SubscriptionView,
} from "@/lib/api";

/**
 * SubscriptionLifecycleActions —— R0.2.4 订阅卡生命周期入口（改频率 / 定时 / 退订），复用 ConfirmModal。
 *
 * F-2 背景：此前订阅只有建与列，整号采集管道建成后「订了就订着」——改不了频率、退不掉。
 * 后端已具备 `PATCH`/`DELETE /spaces/{id}/subscriptions/{subId}`（R0.2.3），本件只补入口。
 *
 * 三个已知语义（前端须知，已写进弹窗描述）：
 * - 调密频率只可能把下次同步**往前**拉；若已有一次同步逾期，本次调整不会把它往后推；
 * - 定时同步 = 每天固定整点触发（后端 `sync_anchor_hour`，0~23，北京时间）；
 *   取消定时回到按间隔滑动，是显式动作（PATCH 显式传 null，省略字段≠清除）；
 * - 退订是**软取消**——只停未来同步，已入库的文档/资产/清单一概不删（要清内容走文档行删除）。
 */
interface Props {
  spaceId: string;
  subscription: SubscriptionItem;
  onChanged: (view: SubscriptionView) => void;
  onCancelled: (view: SubscriptionView) => void;
}

/** 同步间隔预设（分钟）。后端上下界 5~4320，均落在界内。 */
const INTERVAL_OPTIONS: ConfirmOption[] = [
  { value: "5", label: "每 5 分钟" },
  { value: "30", label: "每 30 分钟" },
  { value: "60", label: "每小时" },
  { value: "120", label: "每 2 小时" },
  { value: "360", label: "每 6 小时" },
  { value: "720", label: "每 12 小时" },
  { value: "1440", label: "每天" },
  { value: "4320", label: "每 30 天" },
];

/** 固定时点锚预设：0~23 全量——「每天 7 点」这类非整点半点的需求也能精确选中。 */
const ANCHOR_OPTIONS: ConfirmOption[] = Array.from({ length: 24 }, (_, h) => ({
  value: String(h),
  label: anchorLabel(h),
}));

export function intervalLabel(minutes: number): string {
  // 整除口径，不做四舍五入：后端允许 5~4320 任意分钟数，非整小时值
  // （如 90）若按 Math.round 折算会被误报成「2 小时」
  if (minutes % 1440 === 0) return `${minutes / 1440} 天`;
  if (minutes % 60 === 0) return `${minutes / 60} 小时`;
  return `${minutes} 分钟`;
}

export function anchorLabel(hour: number): string {
  return `每天 ${String(hour).padStart(2, "0")}:00`;
}

/** 当前同步节奏（卡片/弹窗共用口径）：锚定优先，其次按间隔。 */
export function cadenceLabel(sub: SubscriptionItem): string {
  const hour = sub.syncAnchorHour ?? null;
  if (hour != null) return `${anchorLabel(hour)} 定时`;
  return `每 ${intervalLabel(sub.syncIntervalMinutes ?? 360)}`;
}

export default function SubscriptionLifecycleActions({
  spaceId,
  subscription,
  onChanged,
  onCancelled,
}: Props) {
  const [modal, setModal] = useState<"interval" | "anchor" | "unschedule" | "cancel" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const cancelled = subscription.status === "CANCELLED";
  const anchorHour = subscription.syncAnchorHour ?? null;
  const currentInterval = subscription.syncIntervalMinutes ?? 360;
  // 当前值不在预设里时补一项，保证打开即选中现值
  const options = INTERVAL_OPTIONS.some((o) => Number(o.value) === currentInterval)
    ? INTERVAL_OPTIONS
    : [
        { value: String(currentInterval), label: `当前：每 ${intervalLabel(currentInterval)}` },
        ...INTERVAL_OPTIONS,
      ];

  const handleConfirm = async (value?: string) => {
    setBusy(true);
    setError("");
    try {
      if (modal === "cancel") {
        onCancelled(await cancelSubscription(spaceId, subscription.subscriptionId));
        setModal(null);
      } else if (modal === "interval" && value !== undefined) {
        onChanged(
          await updateSubscription(spaceId, subscription.subscriptionId, {
            sync_interval_minutes: Number(value),
          })
        );
        setModal(null);
      } else if (modal === "anchor" && value !== undefined) {
        onChanged(
          await updateSubscription(spaceId, subscription.subscriptionId, {
            sync_anchor_hour: Number(value),
          })
        );
        setModal(null);
      } else if (modal === "unschedule") {
        // 显式 null：清除锚定回到滑动窗口（省略字段后端视为「不改」，不会清除）
        onChanged(
          await updateSubscription(spaceId, subscription.subscriptionId, {
            sync_anchor_hour: null,
          })
        );
        setModal(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex shrink-0 flex-col items-end gap-1">
      <div className="flex flex-wrap items-center justify-end gap-2">
        {anchorHour == null ? (
          <>
            <button
              type="button"
              disabled={cancelled}
              onClick={() => {
                setError("");
                setModal("interval");
              }}
              className="rounded border border-neutral-300 px-3 py-1 text-caption text-neutral-600 hover:bg-neutral-50 disabled:opacity-40"
            >
              调整频率
            </button>
            <button
              type="button"
              disabled={cancelled}
              onClick={() => {
                setError("");
                setModal("anchor");
              }}
              className="rounded border border-brand-500 px-3 py-1 text-caption text-brand-600 hover:bg-brand-50 disabled:opacity-40"
            >
              定时同步
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              disabled={cancelled}
              onClick={() => {
                setError("");
                setModal("anchor");
              }}
              className="rounded border border-brand-500 bg-brand-50 px-3 py-1 text-caption text-brand-700 hover:bg-brand-100 disabled:opacity-40"
            >
              {anchorLabel(anchorHour)}
            </button>
            <button
              type="button"
              disabled={cancelled}
              onClick={() => {
                setError("");
                setModal("unschedule");
              }}
              title="取消定时，回到按间隔滑动"
              className="rounded border border-neutral-300 px-3 py-1 text-caption text-neutral-600 hover:bg-neutral-50 disabled:opacity-40"
            >
              恢复间隔
            </button>
          </>
        )}
        <button
          type="button"
          disabled={cancelled}
          onClick={() => {
            setError("");
            setModal("cancel");
          }}
          className="rounded border border-red-300 px-3 py-1 text-caption text-red-600 hover:bg-red-50 disabled:opacity-40"
        >
          退订
        </button>
      </div>
      {cancelled && (
        <span className="text-caption text-neutral-400">已退订（仅停未来同步，已入库内容保留）</span>
      )}
      {error && <p className="text-caption text-red-600">{error}</p>}

      <ConfirmModal
        open={modal === "interval"}
        title={`调整同步频率：${subscription.sourceName || subscription.biz}`}
        description={`当前每 ${intervalLabel(currentInterval)}（策略 ${subscription.syncPolicy}，当前仅支持 auto）。调密只会把下次同步提前，不会把已逾期的一次同步往后推。`}
        confirmText="保存频率"
        options={options}
        initialValue={String(currentInterval)}
        busy={busy}
        onConfirm={(v) => void handleConfirm(v)}
        onCancel={() => setModal(null)}
      />
      <ConfirmModal
        open={modal === "anchor"}
        title={`${anchorHour == null ? "改为定时同步" : "调整定时同步"}：${subscription.sourceName || subscription.biz}`}
        description={
          anchorHour == null
            ? `每天选中的整点自动同步一次（北京时间），替代当前「每 ${intervalLabel(currentInterval)}」的滑动间隔；连续几天无新文章时，下次触发按天往后延一天。`
            : `当前 ${anchorLabel(anchorHour)}（北京时间）。改定时后下次同步对准最近的一个整点；连续无新文章时按天往后延。`
        }
        confirmText="保存定时"
        options={ANCHOR_OPTIONS}
        initialValue={String(anchorHour ?? 12)} // 须与后端 default_sync_anchor_hour 一致（见 backend/app/core/config.py）
        busy={busy}
        onConfirm={(v) => void handleConfirm(v)}
        onCancel={() => setModal(null)}
      />
      <ConfirmModal
        open={modal === "unschedule"}
        title="恢复按间隔同步"
        description={`取消「${anchorLabel(anchorHour ?? 0)}」定时后回到按间隔滑动（当前每 ${intervalLabel(currentInterval)}），下次同步按间隔从当前时刻重新排期。`}
        confirmText="确认恢复"
        busy={busy}
        onConfirm={() => void handleConfirm()}
        onCancel={() => setModal(null)}
      />
      <ConfirmModal
        open={modal === "cancel"}
        title={`退订：${subscription.sourceName || subscription.biz}`}
        description="退订是软取消：只停止未来自动同步，已入库的文档、资产与清单一概不删。要清理已入库内容，请到对应知识空间逐篇删除。"
        confirmText="确认退订"
        busy={busy}
        onConfirm={() => void handleConfirm()}
        onCancel={() => setModal(null)}
      />
    </div>
  );
}
