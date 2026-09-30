"use client";

import { useCallback } from "react";

/**
 * Pagination —— 通用分页导航组件（W9 D.4）
 *
 * 兼容双形状（page/page_size 与 limit/offset），由 usePagedList 统一归一
 * 后的 page/totalPages 驱动；不在组件内感知原始形状。
 *
 * 交互：上一页/下一页 + 页码点击（窗口展示当前页 ±2），首页/末页省略号。
 */

interface Props {
  page: number;
  totalPages: number;
  total: number;
  onPageChange: (page: number) => void;
}

export default function Pagination({ page, totalPages, total, onPageChange }: Props) {
  const canPrev = page > 1;
  const canNext = page < totalPages;

  const go = useCallback(
    (p: number) => {
      if (p !== page && p >= 1 && p <= totalPages) onPageChange(p);
    },
    [page, totalPages, onPageChange]
  );

  if (totalPages <= 1) return null;

  const pages: (number | "ellipsis")[] = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
  } else {
    pages.push(1);
    if (page > 3) pages.push("ellipsis");
    const start = Math.max(2, page - 1);
    const end = Math.min(totalPages - 1, page + 1);
    for (let i = start; i <= end; i++) pages.push(i);
    if (page < totalPages - 2) pages.push("ellipsis");
    pages.push(totalPages);
  }

  return (
    <nav
      className="mt-4 flex items-center justify-between"
      aria-label="分页导航"
    >
      <span className="text-sm text-neutral-500">共 {total} 条</span>
      <div className="flex items-center gap-1">
        <button
          onClick={() => go(page - 1)}
          disabled={!canPrev}
          className="rounded border border-neutral-200 px-2.5 py-1 text-sm text-neutral-600 transition hover:bg-neutral-50 disabled:opacity-40 disabled:cursor-not-allowed"
          aria-label="上一页"
        >
          ‹
        </button>
        {pages.map((p, i) =>
          p === "ellipsis" ? (
            <span key={`e${i}`} className="px-1 text-neutral-400">
              …
            </span>
          ) : (
            <button
              key={p}
              onClick={() => go(p)}
              aria-current={p === page ? "page" : undefined}
              className={`min-w-[2rem] rounded px-2 py-1 text-sm transition ${
                p === page
                  ? "bg-brand-500 text-white font-medium"
                  : "text-neutral-600 hover:bg-neutral-50"
              }`}
            >
              {p}
            </button>
          )
        )}
        <button
          onClick={() => go(page + 1)}
          disabled={!canNext}
          className="rounded border border-neutral-200 px-2.5 py-1 text-sm text-neutral-600 transition hover:bg-neutral-50 disabled:opacity-40 disabled:cursor-not-allowed"
          aria-label="下一页"
        >
          ›
        </button>
      </div>
    </nav>
  );
}
