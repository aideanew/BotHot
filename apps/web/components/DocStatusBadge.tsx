import type { DocStatus } from "@/lib/api";

/**
 * 文章状态徽标（C-T3）
 * 配色契约：ready=绿 / pending=黄 / failed=红；全中文文案。
 */
const STATUS_META: Record<DocStatus, { label: string; cls: string }> = {
  ready: { label: "已就绪", cls: "bg-green-100 text-green-700" },
  pending: { label: "采集中", cls: "bg-amber-100 text-amber-700" },
  failed: { label: "失败", cls: "bg-red-100 text-red-700" },
};

export function DocStatusBadge({ status }: { status: DocStatus }) {
  const meta = STATUS_META[status] ?? {
    label: "未知",
    cls: "bg-neutral-100 text-neutral-500",
  };
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-caption ${meta.cls}`}
    >
      {meta.label}
    </span>
  );
}

/** 更新时间友好化：当天显示时刻，今年显示月日，其余显示完整日期 */
export function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const sameYear = d.getFullYear() === now.getFullYear();
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  if (sameDay) return `今天 ${hm}`;
  if (sameYear) return `${d.getMonth() + 1} 月 ${d.getDate()} 日`;
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月 ${d.getDate()} 日`;
}
