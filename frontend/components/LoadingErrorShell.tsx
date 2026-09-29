"use client";

/**
 * LoadingErrorShell —— T1.2.1 统一加载/错误/重试外壳（大纲 v1.1 组件化批次）。
 *
 * 合并 5+ 页各写一份的 loading/error/重试三态（spaces/[id]、AddArticlePanel、
 * /public、/engines 等）：loading → Skeleton；error → 错误卡 + 重试按钮；
 * 就绪 → children。未登录（ApiError 10001）调用方应传入差异化文案。
 */
import type { ReactNode } from "react";
import Skeleton from "@/components/Skeleton";

interface Props {
  loading: boolean;
  error: string;
  onRetry?: () => void;
  loadingText?: string;
  skeletonRows?: number;
  children: ReactNode;
}

export default function LoadingErrorShell({
  loading,
  error,
  onRetry,
  loadingText = "加载中…",
  skeletonRows = 3,
  children,
}: Props) {
  if (loading) {
    return (
      <div className="card p-6">
        <p className="mb-3 text-center text-caption text-neutral-400">{loadingText}</p>
        <Skeleton count={skeletonRows} />
      </div>
    );
  }
  if (error) {
    return (
      <div className="card border border-red-200 bg-red-50 p-6">
        <p className="text-base text-red-700">{error}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 rounded-input border border-red-400 px-3 py-1 text-base text-red-700 hover:bg-red-100"
          >
            重新加载
          </button>
        )}
      </div>
    );
  }
  return <>{children}</>;
}
