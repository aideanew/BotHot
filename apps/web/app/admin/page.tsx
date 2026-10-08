"use client";

import Link from "next/link";
import { useAdminData } from "@/components/useAdminData";
import AdminDocSection from "@/components/AdminDocSection";
import AdminSpaceCard from "@/components/AdminSpaceCard";
import AdminOpsSection from "@/components/AdminOpsSection";
import {
  deleteAdminSpaceDocsBatch,
  recategorizeAdminSpaceDocsBatch,
} from "@/lib/api";
import { usePageTitle } from "@/components/usePageTitle";

export default function AdminPage() {
  const {
    status, isAdmin,
    spaces, activeSpaceId, setActiveSpaceId,
    docs, total, categoryFilter, setCategoryFilter,
    selected, setSelected,
    loadingMore, errorMsg, setReloadTick,
    editDescSpaceId, setEditDescSpaceId, editDescValue, setEditDescValue,
    savingDesc, setSavingDesc,
    confirmingDocDelete, setConfirmingDocDelete, deletingDoc,
    confirmingSpaceDelete, setConfirmingSpaceDelete, deletingSpace,
    openSpace, refreshDocs, loadMore,
    handleSaveDescription, handleDeleteDoc, handleDeleteSpace,
  } = useAdminData();
  usePageTitle("管理后台");

  if (status !== "authed") {
    return (
      <main className="mx-auto max-w-5xl px-4 py-10">
        <div className="card p-10 text-center text-neutral-500">正在加载…</div>
      </main>
    );
  }

  if (!isAdmin) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-16">
        <div className="card mx-auto max-w-md p-10 text-center">
          <p className="text-title-lg font-semibold text-neutral-900">权限不足</p>
          <p className="mt-3 text-neutral-500">
            后台管理台需要管理员权限。当前账号不具备该权限，
            或尚未在后端登记为 admin。
          </p>
          <Link
            href="/spaces"
            className="mt-8 inline-block rounded-input bg-brand-500 px-6 py-2 text-white hover:bg-brand-600"
          >
            返回空间列表
          </Link>
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

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="eyebrow">ADMIN CONSOLE</p>
          <h1 className="mt-1 text-title-lg font-semibold tracking-tight text-neutral-900">
            后台管理台
          </h1>
        </div>
        <Link
          href="/spaces"
          className="inline-flex items-center gap-1 text-caption text-neutral-400 hover:text-neutral-600"
        >
          ← 返回空间列表
        </Link>
      </div>

      <section className="mt-6">
        <h2 className="text-title-sm font-semibold text-neutral-900">全部空间</h2>
        {spaces === null ? (
          <div className="card mt-3 p-4">
            <div className="h-4 w-1/2 animate-pulse rounded bg-neutral-100" />
            <div className="mt-2 h-3 w-1/3 animate-pulse rounded bg-neutral-100" />
          </div>
        ) : spaces.length === 0 ? (
          <div className="card mt-3 p-10 text-center text-neutral-500">
            系统中还没有任何知识空间。
          </div>
        ) : (
          <ul className="mt-3 grid gap-3 sm:grid-cols-2">
            {spaces.map((s) => (
              <AdminSpaceCard
                key={s.id}
                space={s}
                isEditingDesc={editDescSpaceId === s.id}
                editDescValue={editDescValue}
                savingDesc={savingDesc}
                confirmingDelete={confirmingSpaceDelete === s.id}
                deleting={deletingSpace === s.id}
                onEditDescStart={(id, desc) => {
                  setEditDescSpaceId(id);
                  setEditDescValue(desc);
                }}
                onEditDescCancel={() => setEditDescSpaceId("")}
                onDescValueChange={setEditDescValue}
                onSaveDesc={handleSaveDescription}
                onOpen={openSpace}
                onDeleteConfirm={handleDeleteSpace}
                onDeleteCancel={() => setConfirmingSpaceDelete("")}
                onDeleteRequest={(id) => setConfirmingSpaceDelete(id)}
              />
            ))}
          </ul>
        )}
      </section>

      {activeSpaceId && (
        <AdminDocSection
          spaceId={activeSpaceId}
          docs={docs}
          total={total}
          categoryFilter={categoryFilter}
          selected={selected}
          loadingMore={loadingMore}
          confirmingDocDelete={confirmingDocDelete}
          deletingDoc={deletingDoc}
          deleteBatch={deleteAdminSpaceDocsBatch}
          recategorizeBatch={recategorizeAdminSpaceDocsBatch}
          onCategoryChange={(v) => { setCategoryFilter(v); refreshDocs(v); }}
          onToggleSelect={(docId) =>
            setSelected((prev) => {
              const next = new Set(prev);
              if (next.has(docId)) next.delete(docId);
              else next.add(docId);
              return next;
            })
          }
          onSelectChange={setSelected}
          onConfirmingDocDeleteChange={setConfirmingDocDelete}
          onDeleteDoc={handleDeleteDoc}
          onDocsChanged={() => refreshDocs(categoryFilter)}
          onLoadMore={loadMore}
        />
      )}

      <AdminOpsSection />
    </main>
  );
}
