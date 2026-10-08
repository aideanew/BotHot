"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  createSpace,
  deleteSpace,
  listSpaces,
  isAuthError,
  type Space,
} from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import { formatTime } from "@/components/DocStatusBadge";
import { usePageTitle } from "@/components/usePageTitle";

/**
 * 知识空间列表页（C-T3）
 * 卡片网格：名称/简介/文章数/更新时间；空态/加载骨架/错误态齐全；
 * 未登录访问跳回首页引导卡（与 C-T2 行为一致）。
 */
export default function SpacesPage() {
  const router = useRouter();
  const { status } = useAuth();
  usePageTitle("知识空间");
  const [spaces, setSpaces] = useState<Space[] | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [reloadTick, setReloadTick] = useState(0);
  const [deletingSpaceId, setDeletingSpaceId] = useState("");
  const [confirmingDelete, setConfirmingDelete] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [creatingBusy, setCreatingBusy] = useState(false);
  const [createError, setCreateError] = useState("");

  // 未登录（含判定完成后的 guest）→ 跳回首页引导卡
  useEffect(() => {
    if (status === "guest") {
      router.replace("/");
    }
  }, [status, router]);

  // 登录态加载列表
  useEffect(() => {
    if (status !== "authed") return;
    let cancelled = false;
    setSpaces(null);
    setErrorMsg("");
    listSpaces()
      .then((list) => {
        if (!cancelled) setSpaces(list);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && isAuthError(err.code)) {
          router.replace("/");
          return;
        }
        setErrorMsg(err instanceof Error ? err.message : "加载失败");
        setSpaces([]);
      });
    return () => {
      cancelled = true;
    };
  }, [status, reloadTick, router]);

  // 未登录跳转进行中
  if (status !== "authed") {
    return (
      <main className="mx-auto max-w-5xl px-4 py-10">
        <div className="card p-10 text-center text-neutral-500">正在加载…</div>
      </main>
    );
  }

  /** 新建空间（R0.5：/spaces 补 create 入口，与 delete 入口对称） */
  const handleCreateSpace = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const name = newName.trim();
    if (!name || creatingBusy) return;
    setCreatingBusy(true);
    setCreateError("");
    try {
      const detail = await createSpace({
        name,
        description: newDescription.trim() || undefined,
      });
      setSpaces((prev) =>
        prev
          ? [
              {
                id: detail.id,
                name: detail.name,
                description: detail.description,
                docCount: detail.docCount,
                updatedAt: detail.updatedAt,
                engine: detail.engine,
                engineKbId: detail.engineKbId,
                isPublic: detail.isPublic,
              },
              ...prev,
            ]
          : prev
      );
      setNewName("");
      setNewDescription("");
      setCreating(false);
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : "创建失败");
    } finally {
      setCreatingBusy(false);
    }
  };

  /** R5.4.3：删除空间（确认两步；删除后列表刷新） */
  const handleDeleteSpace = async (id: string) => {
    setConfirmingDelete("");
    setDeletingSpaceId(id);
    try {
      await deleteSpace(id);
      setSpaces((prev) => (prev ? prev.filter((s) => s.id !== id) : prev));
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDeletingSpaceId("");
    }
  };

  return (
    <main className="page-shell">
      <section className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <p className="eyebrow">ORGANIZE YOUR SOURCES</p>
          <h1 className="mt-2 section-title">知识空间</h1>
          <p className="mt-2 muted-copy">按主题管理文章入库与机器人问答，点击卡片查看空间详情。</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setCreating((v) => !v)}
            className="rounded-input bg-brand-500 px-4 py-1.5 text-caption font-medium text-white shadow-card transition hover:bg-brand-600"
          >
            新建空间
          </button>
          <span className="w-fit rounded-full bg-white px-3 py-1.5 text-caption text-neutral-500 shadow-card">
            全部空间{spaces !== null ? ` · ${spaces.length}` : ""}
          </span>
        </div>
      </section>

      {creating && (
        <form onSubmit={(e) => void handleCreateSpace(e)} className="card mt-6 p-6">
          <p className="text-title-sm font-medium text-neutral-900">新建知识空间</p>
          <div className="mt-4 flex flex-col gap-3">
            <label className="flex flex-col gap-1.5">
              <span className="text-caption text-neutral-500">空间名称</span>
              <input
                autoFocus
                required
                maxLength={64}
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="例如：人民日报 AI 观察"
                aria-label="空间名称"
                className="rounded-input border border-neutral-200 bg-neutral-50 px-3 py-2 text-base outline-none transition focus:border-brand-400 focus:bg-white"
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-caption text-neutral-500">简介（可选）</span>
              <input
                maxLength={200}
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                placeholder="一句话说明这个空间收录什么"
                aria-label="空间简介"
                className="rounded-input border border-neutral-200 bg-neutral-50 px-3 py-2 text-base outline-none transition focus:border-brand-400 focus:bg-white"
              />
            </label>
          </div>
          {createError && <p className="mt-3 text-caption text-danger">{createError}</p>}
          <div className="mt-5 flex gap-2">
            <button
              type="submit"
              disabled={creatingBusy || !newName.trim()}
              className="rounded-input bg-brand-500 px-5 py-2 text-base font-medium text-white transition hover:bg-brand-600 disabled:opacity-50"
            >
              {creatingBusy ? "创建中…" : "创建"}
            </button>
            <button
              type="button"
              onClick={() => {
                setCreating(false);
                setCreateError("");
              }}
              className="rounded-input border border-neutral-300 px-5 py-2 text-base text-neutral-600 transition hover:bg-neutral-50"
            >
              取消
            </button>
          </div>
        </form>
      )}

      {/* 加载骨架屏 */}
      {spaces === null && (
        <section className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="card p-5">
              <div className="h-5 w-28 animate-pulse rounded bg-neutral-200" />
              <div className="mt-3 h-4 w-full animate-pulse rounded bg-neutral-100" />
              <div className="mt-2 h-4 w-3/4 animate-pulse rounded bg-neutral-100" />
              <div className="mt-4 h-3 w-20 animate-pulse rounded bg-neutral-100" />
            </div>
          ))}
        </section>
      )}

      {/* 错误态 */}
      {errorMsg && (
        <div className="card mt-6 p-8 text-center">
          <p className="text-danger">{errorMsg}</p>
          <button
            onClick={() => setReloadTick((t) => t + 1)}
            className="mt-4 rounded-input bg-brand-500 px-5 py-1.5 text-white hover:bg-brand-600"
          >
            重新加载
          </button>
        </div>
      )}

      {/* 空态 */}
      {spaces !== null && !errorMsg && spaces.length === 0 && (
        <div className="card mt-6 p-12 text-center">
          <p className="text-neutral-500">还没有知识空间</p>
          <p className="mt-2 text-caption text-neutral-400">
            先建一个空间，再往里面采集公众号文章。
          </p>
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="mt-5 rounded-input bg-brand-500 px-5 py-2 text-base font-medium text-white shadow-card transition hover:bg-brand-600"
          >
            新建第一个空间
          </button>
        </div>
      )}

      {/* 卡片网格 */}
      {spaces !== null && !errorMsg && spaces.length > 0 && (
        <section className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {spaces.map((s) => (
            <div key={s.id} className="relative">
              <a
                href={`/spaces/${s.id}`}
                className="card block p-5 transition hover:border-brand-300 hover:shadow-popover"
              >
                <h2 className="text-title-sm font-medium text-neutral-900">
                  {s.name}
                </h2>
                <p className="mt-2 line-clamp-2 min-h-10 text-base text-neutral-500">
                  {s.description || "暂无简介"}
                </p>
                <p className="mt-3 flex items-center justify-between text-caption text-neutral-400">
                  <span>{s.docCount} 篇文章</span>
                  <span>更新于 {formatTime(s.updatedAt)}</span>
                </p>
              </a>
              {confirmingDelete === s.id ? (
                <div className="absolute inset-x-0 top-full mt-2 flex gap-2">
                  <button
                    type="button"
                    disabled={deletingSpaceId === s.id}
                    onClick={() => void handleDeleteSpace(s.id)}
                    className="rounded bg-red-600 px-3 py-1 text-caption text-white disabled:opacity-60"
                  >
                    {deletingSpaceId === s.id ? "删除中…" : "确认删除"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmingDelete("")}
                    className="rounded border border-neutral-300 px-3 py-1 text-caption text-neutral-600 hover:bg-neutral-50"
                  >
                    取消
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  title="删除该空间"
                  onClick={(e) => {
                    e.stopPropagation();
                    setConfirmingDelete(s.id);
                  }}
                  className="absolute right-2 top-2 rounded p-1 text-caption text-neutral-400 hover:bg-red-50 hover:text-red-600"
                >
                  删除
                </button>
              )}
            </div>
          ))}
        </section>
      )}
    </main>
  );
}
