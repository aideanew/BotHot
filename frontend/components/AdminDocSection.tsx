import {
  CATEGORIES,
  UNCATEGORIZED,
  type DeleteDocsBatchResult,
  type RecategorizeDocsBatchResult,
} from "@/lib/api";
import type { SpaceDoc } from "@/lib/api";
import DocBatchActions from "./DocBatchActions";
import DocList from "./DocList";

type DeleteBatchFn = (
  spaceId: string,
  ids: string[]
) => Promise<DeleteDocsBatchResult>;
type RecategorizeBatchFn = (
  spaceId: string,
  ids: string[],
  category: string
) => Promise<RecategorizeDocsBatchResult>;

interface AdminDocSectionProps {
  spaceId: string;
  docs: SpaceDoc[] | null;
  total: number;
  categoryFilter: string;
  selected: Set<string>;
  loadingMore: boolean;
  confirmingDocDelete: string;
  deletingDoc: string;
  deleteBatch: DeleteBatchFn;
  recategorizeBatch: RecategorizeBatchFn;
  onCategoryChange: (v: string) => void;
  onToggleSelect: (docId: string) => void;
  onSelectChange: (s: Set<string>) => void;
  onConfirmingDocDeleteChange: (docId: string) => void;
  onDeleteDoc: (docId: string) => void;
  onDocsChanged: () => void;
  onLoadMore: () => void;
}

export default function AdminDocSection({
  spaceId,
  docs,
  total,
  categoryFilter,
  selected,
  loadingMore,
  confirmingDocDelete,
  deletingDoc,
  deleteBatch,
  recategorizeBatch,
  onCategoryChange,
  onToggleSelect,
  onSelectChange,
  onConfirmingDocDeleteChange,
  onDeleteDoc,
  onDocsChanged,
  onLoadMore,
}: AdminDocSectionProps) {
  return (
    <section className="mt-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-title-sm font-semibold text-neutral-900">
          文档清单
        </h2>
        <div className="flex items-center gap-2">
          <select
            value={categoryFilter}
            onChange={(e) => onCategoryChange(e.target.value)}
            aria-label="按分类筛选"
            className="rounded-input border border-neutral-300 px-2 py-1 text-caption outline-none focus:border-brand-500"
          >
            <option value="">全部分类</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
            <option value={UNCATEGORIZED}>未分类</option>
          </select>
          <span className="text-caption text-neutral-400">
            共 {total} 篇
          </span>
        </div>
      </div>

      {docs !== null && (
        <DocBatchActions
          spaceId={spaceId}
          docs={docs}
          total={total}
          selected={selected}
          onSelectChange={onSelectChange}
          onDocsChanged={onDocsChanged}
          deleteBatch={deleteBatch}
          recategorizeBatch={recategorizeBatch}
        />
      )}

      {docs === null ? (
        <div className="mt-3 space-y-3">
          {[0, 1].map((i) => (
            <div key={i} className="card p-4">
              <div className="h-4 w-1/2 animate-pulse rounded bg-neutral-100" />
              <div className="mt-2 h-3 w-1/3 animate-pulse rounded bg-neutral-100" />
            </div>
          ))}
        </div>
      ) : docs.length === 0 ? (
        <div className="card mt-3 p-10 text-center text-neutral-500">
          {categoryFilter === ""
            ? "该空间还没有文档。"
            : categoryFilter === UNCATEGORIZED
              ? "该空间没有未分类的文档。"
              : `「${categoryFilter}」分类下暂无文档。`}
        </div>
      ) : (
        <DocList
          docs={docs}
          selected={selected}
          onToggleSelect={onToggleSelect}
          ariaSelectLabel="选择文档"
          renderTrailing={(doc) =>
            confirmingDocDelete === doc.id ? (
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  disabled={deletingDoc === doc.id}
                  onClick={() => onDeleteDoc(doc.id)}
                  className="rounded px-2 py-0.5 text-caption text-red-600 hover:bg-red-50"
                >
                  {deletingDoc ? "删除中…" : "确认"}
                </button>
                <button
                  type="button"
                  onClick={() => onConfirmingDocDeleteChange("")}
                  className="rounded px-2 py-0.5 text-caption text-neutral-500 hover:bg-neutral-100"
                >
                  取消
                </button>
              </div>
            ) : (
              <button
                type="button"
                title="删除该文档"
                onClick={() => onConfirmingDocDeleteChange(doc.id)}
                className="rounded p-1 text-caption text-neutral-400 hover:bg-red-50 hover:text-red-600"
              >
                删除
              </button>
            )
          }
        />
      )}

      {docs !== null && docs.length > 0 && (
        <div className="mt-4 flex items-center justify-center">
          {docs.length < total ? (
            <button
              type="button"
              onClick={onLoadMore}
              disabled={loadingMore}
              className="rounded-input border border-neutral-300 px-5 py-1.5 text-caption text-neutral-600 hover:bg-neutral-50 disabled:opacity-60"
            >
              {loadingMore
                ? "加载中…"
                : `加载更多（已显示 ${docs.length}/${total}）`}
            </button>
          ) : (
            <p className="text-caption text-neutral-400">
              已显示全部 {total} 篇
            </p>
          )}
        </div>
      )}
    </section>
  );
}
