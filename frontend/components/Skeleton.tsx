/**
 * Skeleton —— T1.2.3 基础骨架屏件（大纲 v1.1 组件化批次）。
 * 各页自写 loading 块的统一替代；可通过 count/height 组合出列表骨架。
 */
export default function Skeleton({
  count = 1,
  height = "h-16",
}: {
  count?: number;
  height?: string;
}) {
  return (
    <div className="space-y-3" aria-hidden>
      {Array.from({ length: Math.max(1, count) }).map((_, i) => (
        <div key={i} className={`animate-pulse rounded-card bg-neutral-100 ${height}`} />
      ))}
    </div>
  );
}
