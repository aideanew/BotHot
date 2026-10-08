"use client";

/**
 * PublicPage —— T1.1.1 公共库页真实现（替换 36 行壳页；大纲 v1.1）。
 *
 * - 概览卡片：GET /spaces/public 列表渲染（名称/简介/篇数/引擎/更新时间）；
 * - 引入流程：选择目标空间 → 复用 PublicLibraryPicker（列表+一键引入+进度条）；
 * - 空态/错误态/未建空间引导齐备。
 * 验收锚（大纲 T1.1.1）：公共库列表可点引入。
 */
import { useCallback, useEffect, useState } from "react";
import LoadingErrorShell from "@/components/LoadingErrorShell";
import PublicLibraryPicker from "@/components/PublicLibraryPicker";
import { usePageTitle } from "@/components/usePageTitle";
import {
  ApiError,
  listPublicSpaces,
  listSpaces,
  type PublicSpace,
  type Space,
} from "@/lib/api";

export default function PublicPage() {
  usePageTitle("公共 AI 库");
  const [publicSpaces, setPublicSpaces] = useState<PublicSpace[]>([]);
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [selectedSpaceId, setSelectedSpaceId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [pubs, mine] = await Promise.all([listPublicSpaces(), listSpaces()]);
      setPublicSpaces(pubs);
      setSpaces(mine);
      setSelectedSpaceId((prev) => prev || (mine[0]?.id ?? ""));
    } catch (e) {
      setError(
        e instanceof ApiError && e.code === 10001
          ? "未登录，请重新登录后查看公共库"
          : "公共库加载失败，请重试"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6">
        <p className="eyebrow">PUBLIC LIBRARY</p>
        <h1 className="text-title-lg font-semibold text-neutral-900">公共 AI 库</h1>
        <p className="mt-2 text-base text-neutral-500">
          系统空间发布的免费公共内容；选择你的空间后一键引入（copy 幂等，不重复抓取）。
        </p>
      </div>

      <LoadingErrorShell
        loading={loading}
        error={error}
        onRetry={() => void load()}
        skeletonRows={2}
      >
        <>
          {/* 概览卡片 */}
          {publicSpaces.length === 0 ? (
            <div className="card p-8 text-center text-neutral-500">
              暂无已发布的公共库（管理员可在系统空间上发布）。
            </div>
          ) : (
            <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {publicSpaces.map((ps) => (
                <li key={ps.id} className="card p-4">
                  <p className="text-base font-medium text-neutral-900">{ps.name}</p>
                  <p className="mt-1 text-caption text-neutral-500">{ps.description}</p>
                  <p className="mt-2 text-caption text-neutral-400">
                    {ps.docCount} 篇 · {ps.engine === "builtin" ? "内置引擎" : ps.engine} ·{" "}
                    {ps.updatedAt ? new Date(ps.updatedAt).toLocaleDateString("zh-CN") : "—"}
                  </p>
                </li>
              ))}
            </ul>
          )}

          {/* 引入流程：选目标空间 → PublicLibraryPicker */}
          <section className="mt-8">
            <h2 className="mb-3 text-title-sm font-semibold text-neutral-900">引入到我的空间</h2>
            {spaces.length === 0 ? (
              <div className="card p-6 text-center text-neutral-500">
                你还没有自己的空间——先到 <a className="text-brand-600 underline" href="/spaces">空间页</a> 或
                引导流程创建一个，再回来一键引入。
              </div>
            ) : (
              <>
                <label className="mb-1 block text-caption text-neutral-500" htmlFor="target-space">
                  目标空间
                </label>
                <select
                  id="target-space"
                  value={selectedSpaceId}
                  onChange={(e) => setSelectedSpaceId(e.target.value)}
                  className="mb-4 w-full rounded-input border border-neutral-300 px-3 py-2 text-base outline-none focus:border-brand-500"
                >
                  {spaces.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}（{s.docCount} 篇）
                    </option>
                  ))}
                </select>
                {selectedSpaceId && <PublicLibraryPicker targetSpaceId={selectedSpaceId} />}
              </>
            )}
          </section>
        </>
      </LoadingErrorShell>
    </main>
  );
}
