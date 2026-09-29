import {
  JOB_STATUS_LABELS,
  JOB_TYPE_LABELS,
} from "@/lib/api";

const TYPE_OPTIONS = [["", "全部"], ...Object.entries(JOB_TYPE_LABELS)] as [
  string,
  string,
][];
const STATUS_OPTIONS = [["", "全部"], ...Object.entries(JOB_STATUS_LABELS)] as [
  string,
  string,
][];

interface JobFilterBarProps {
  typeFilter: string;
  statusFilter: string;
  total: number;
  onTypeChange: (value: string) => void;
  onStatusChange: (value: string) => void;
}

export default function JobFilterBar({
  typeFilter,
  statusFilter,
  total,
  onTypeChange,
  onStatusChange,
}: JobFilterBarProps) {
  return (
    <section className="mb-4 flex flex-wrap items-end gap-3 rounded-card border border-neutral-200 p-4">
      <label className="block">
        <span className="mb-1 block text-caption text-neutral-500">类型</span>
        <select
          aria-label="类型筛选"
          value={typeFilter}
          onChange={(e) => onTypeChange(e.target.value)}
          className="block rounded-input border border-neutral-300 px-3 py-1.5 text-base outline-none focus:border-brand-500"
        >
          {TYPE_OPTIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="mb-1 block text-caption text-neutral-500">状态</span>
        <select
          aria-label="状态筛选"
          value={statusFilter}
          onChange={(e) => onStatusChange(e.target.value)}
          className="block rounded-input border border-neutral-300 px-3 py-1.5 text-base outline-none focus:border-brand-500"
        >
          {STATUS_OPTIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <span className="pb-1.5 text-caption text-neutral-500">
        共 {total} 个任务
      </span>
    </section>
  );
}