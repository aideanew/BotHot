import type { ReactNode } from "react";
import { DocStatusBadge, formatTime } from "./DocStatusBadge";
import type { SpaceDoc } from "@/lib/api";

interface DocListProps {
  docs: SpaceDoc[];
  selected: Set<string>;
  onToggleSelect: (docId: string) => void;
  ariaSelectLabel?: string;
  renderTrailing?: (doc: SpaceDoc) => ReactNode;
}

/**
 * 文档清单行列表（admin 和 space 详情共用）。
 *
 * 两处原本近似复制约 60 行，差异仅在 aria-label 文案和行尾组件；
 * 抽出后通过 ariaSelectLabel 和 renderTrailing 表达差异。
 */
export default function DocList({
  docs,
  selected,
  onToggleSelect,
  ariaSelectLabel = "选择文章",
  renderTrailing,
}: DocListProps) {
  if (docs.length === 0) return null;
  return (
    <ul className="mt-3 space-y-3">
      {docs.map((doc) => (
        <li key={doc.id} className="card flex items-center gap-4 p-4">
          <input
            type="checkbox"
            checked={selected.has(doc.id)}
            onChange={() => onToggleSelect(doc.id)}
            aria-label={`${ariaSelectLabel}：${doc.title}`}
            className="h-4 w-4 shrink-0 accent-brand-500"
          />
          <div className="min-w-0 flex-1">
            <p className="truncate text-base font-medium text-neutral-900">
              {doc.title}
            </p>
            <p className="mt-1 text-caption text-neutral-400">
              {doc.source}
              {doc.category ? ` · ${doc.category}` : ""} · 更新于{" "}
              {formatTime(doc.updatedAt)}
            </p>
          </div>
          <DocStatusBadge status={doc.status} />
          {renderTrailing?.(doc)}
        </li>
      ))}
    </ul>
  );
}