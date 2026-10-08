import { UNCATEGORIZED, type SpaceDoc } from "@/lib/api";
import DocBatchActions from "@/components/DocBatchActions";
import DocList from "@/components/DocList";
import DocLifecycleActions from "@/components/DocLifecycleActions";

interface SpaceArticleSectionProps {
  spaceId: string;
  docs: SpaceDoc[] | null;
  total: number;
  categories: string[];
  categoryFilter: string;
  selected: Set<string>;
  loadingMore: boolean;
  onCategoryChange: (category: string) => void;
  onToggleSelect: (docId: string) => void;
  onDocsChanged: () => void;
  onSelectChange: (selected: Set<string>) => void;
  onLoadMore: () => void;
}

export default function SpaceArticleSection({
  spaceId,
  docs,
  total,
  categories,
  categoryFilter,
  selected,
  loadingMore,
  onCategoryChange,
  onToggleSelect,
  onDocsChanged,
  onSelectChange,
  onLoadMore,
}: SpaceArticleSectionProps) {
  return (
    <section className="mt-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-title-sm font-semibold text-neutral-900">
          文章列表
        </h2>
        <div className="flex items-center gap-2">
          {categories.length > 0 && (
            <select
              value={categoryFilter}
              onChange={(e) => onCategoryChange(e.target.value)}
              aria-label="按分类筛选"
              className="rounded-input border border-neutral-300 px-2 py-1 text-caption outline-none focus:border-brand-500"
            >
              <option value="">全部分类</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c === UNCATEGORIZED ? "未分类" : c}
                </option>
              ))}
            </select>
          )}
          <span className="text-caption text-neutral-400">
            {categoryFilter === "" ? "已入库内容" : `共 ${total} 篇`}
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
            ? "该空间还没有文章，使用上方「添加文章」粘贴公众号链接即可入库。"
            : categoryFilter === UNCATEGORIZED
              ? "该空间没有未分类的文章。"
              : `「${categoryFilter}」分类下暂无文章。`}
        </div>
      ) : (
        <DocList
          docs={docs}
          selected={selected}
          onToggleSelect={onToggleSelect}
          ariaSelectLabel="选择文章"
          renderTrailing={(doc) => (
            <DocLifecycleActions
              spaceId={spaceId}
              doc={doc}
              onDeleted={onDocsChanged}
              onRecategorized={onDocsChanged}
            />
          )}
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
              {loadingMore ? "加载中…" : `加载更多（已显示 ${docs.length}/${total}）`}
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