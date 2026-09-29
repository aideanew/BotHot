"use client";

import { useAuth } from "@/components/AuthContext";
import { useSpaceDetail } from "@/components/useSpaceDetail";
import { usePageTitle } from "@/components/usePageTitle";
import SpaceHeaderPanel from "@/components/SpaceHeaderPanel";
import SpaceArticleSection from "@/components/SpaceArticleSection";

export default function SpaceDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const { status } = useAuth();
  const {
    space, docs, total, categories,
    loadingMore, notFound, errorMsg,
    setReloadTick, categoryFilter, selected, setSelected,
    refreshDocs, handleCategoryChanged, handleDocChanged,
    loadMore, toggleSelected,
  } = useSpaceDetail(params.id);
  usePageTitle(space ? `${space.name}` : "空间详情");

  if (status !== "authed") {
    return (
      <main className="mx-auto max-w-5xl px-4 py-10">
        <div className="card p-10 text-center text-neutral-500">正在加载…</div>
      </main>
    );
  }

  if (notFound) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-16">
        <div className="card mx-auto max-w-md p-10 text-center">
          <p className="text-title-lg font-semibold text-neutral-900">
            未找到该知识空间
          </p>
          <p className="mt-3 text-neutral-500">
            空间可能已被删除，或链接地址有误。
          </p>
          <a
            href="/spaces"
            className="mt-8 inline-block rounded-input bg-brand-500 px-6 py-2 text-white hover:bg-brand-600"
          >
            返回空间列表
          </a>
        </div>
      </main>
    );
  }

  if (errorMsg) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-16">
        <div className="card mx-auto max-w-md p-10 text-center">
          <p className="text-danger">{errorMsg}</p>
          <button
            onClick={() => setReloadTick((t) => t + 1)}
            className="mt-6 rounded-input bg-brand-500 px-5 py-1.5 text-white hover:bg-brand-600"
          >
            重新加载
          </button>
        </div>
      </main>
    );
  }

  if (!space) {
    return (
      <main className="page-shell">
        <div className="card p-8">
          <div className="h-6 w-40 animate-pulse rounded bg-neutral-200" />
          <div className="mt-3 h-4 w-2/3 animate-pulse rounded bg-neutral-100" />
          <div className="mt-5 h-4 w-48 animate-pulse rounded bg-neutral-100" />
        </div>
        <div className="mt-4 space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="card p-4">
              <div className="h-4 w-1/2 animate-pulse rounded bg-neutral-100" />
              <div className="mt-2 h-3 w-1/3 animate-pulse rounded bg-neutral-100" />
            </div>
          ))}
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <SpaceHeaderPanel
        space={space}
        onSubmitted={() => void refreshDocs()}
        onDocsChanged={() => void refreshDocs()}
      />
      <SpaceArticleSection
        spaceId={space.id}
        docs={docs}
        total={total}
        categories={categories}
        categoryFilter={categoryFilter}
        selected={selected}
        loadingMore={loadingMore}
        onCategoryChange={handleCategoryChanged}
        onToggleSelect={toggleSelected}
        onDocsChanged={handleDocChanged}
        onSelectChange={setSelected}
        onLoadMore={() => void loadMore()}
      />
    </main>
  );
}