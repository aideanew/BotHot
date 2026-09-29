/**
 * PublicLibraryPicker —— AB-P004 P1「一键引入 AI 库」组件。
 *
 * 在空间详情页/问答页公共库分组中使用：
 * - 拉取 GET /spaces/public 列表；
 * - 「一键引入」按钮调 POST /spaces/{targetSpaceId}/links 批量 copy；
 * - 引入进度条（copied/skipped/total）；
 * - 已引入（skipped > 0 或 copied = 0 且 total > 0）显示「已引入 ✓」防重复。
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  linkPublicSpace,
  listPublicSpaces,
  type LinkResult,
  type PublicSpace,
} from "@/lib/api";

interface Props {
  /** 目标用户空间 id（引入到哪里） */
  targetSpaceId: string;
  /** 引入完成回调（刷新 doc 列表等） */
  onLinked?: (result: LinkResult) => void;
}

export default function PublicLibraryPicker({ targetSpaceId, onLinked }: Props) {
  const [publicSpaces, setPublicSpaces] = useState<PublicSpace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [linking, setLinking] = useState(false);
  const [result, setResult] = useState<LinkResult | null>(null);
  const [actionError, setActionError] = useState("");

  const loadPublicSpaces = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const list = await listPublicSpaces();
      setPublicSpaces(list);
    } catch (e) {
      if (e instanceof ApiError && e.code === 10001) {
        setError("未登录，请重新登录");
      } else {
        setError("公共库列表加载失败，请重试");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPublicSpaces();
  }, [loadPublicSpaces]);

  const handleLink = async (publicSpaceId: string) => {
    setLinking(true);
    setActionError("");
    setResult(null);
    try {
      const r = await linkPublicSpace(targetSpaceId, publicSpaceId);
      setResult(r);
      onLinked?.(r);
    } catch (e) {
      if (e instanceof ApiError && (e.code === 30004 || e.code === 30101)) {
        setActionError("目标空间或公共库不存在，请刷新重试");
      } else if (e instanceof ApiError && e.code === 10001) {
        setActionError("登录已过期，请重新登录");
      } else {
        setActionError("引入失败，请稍后重试");
      }
    } finally {
      setLinking(false);
    }
  };

  const isLinked =
    result !== null && result.copied === 0 && result.total > 0;

  return (
    <div className="card border border-neutral-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="eyebrow">公共库</p>
        <button
          type="button"
          onClick={loadPublicSpaces}
          disabled={loading}
          className="text-caption text-brand-600 hover:underline disabled:opacity-40"
        >
          {loading ? "加载中…" : "刷新"}
        </button>
      </div>

      {error && <p className="mb-2 text-caption text-red-600">{error}</p>}
      {actionError && <p className="mb-2 text-caption text-red-600">{actionError}</p>}

      {publicSpaces.length === 0 && !loading && (
        <p className="text-caption text-neutral-400">暂无公共库</p>
      )}

      <ul className="space-y-2">
        {publicSpaces.map((ps) => (
          <li
            key={ps.id}
            className="flex items-center justify-between rounded border border-neutral-100 p-2"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-neutral-800">
                {ps.name}
                <span className="ml-2 text-caption text-neutral-400">
                  {ps.docCount} 篇 · {ps.engine === "builtin" ? "内置" : ps.engine}
                </span>
              </p>
            </div>
            {isLinked ? (
              <span className="shrink-0 text-caption text-green-600">已引入 ✓</span>
            ) : (
              <button
                type="button"
                onClick={() => handleLink(ps.id)}
                disabled={linking}
                className="shrink-0 rounded bg-brand-600 px-3 py-1 text-caption font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              >
                {linking ? "引入中…" : "一键引入 AI 库"}
              </button>
            )}
          </li>
        ))}
      </ul>

      {result && (
        <div className="mt-3">
          <p className="mb-1 text-caption text-neutral-500">
            引入进度：{result.copied} 篇已引入，{result.skipped} 篇已存在（共 {result.total} 篇）
          </p>
          <div className="h-1.5 w-full overflow-hidden rounded bg-neutral-100">
            <div
              className="h-full bg-brand-500 transition-all"
              style={{
                width: result.total > 0 ? `${(result.copied / result.total) * 100}%` : "100%",
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
