"use client";

/**
 * T1.1.3：路由段错误兜底页（App Router error.tsx，client 组件带 reset 重试）。
 * 全局异常处理器之外的渲染期错误由此承接；错误详情仅在开发态展示。
 */
export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-3xl flex-col items-center justify-center px-4 py-16 text-center">
      <p className="eyebrow">出错了</p>
      <h1 className="mt-2 text-title-lg font-semibold text-neutral-900">
        页面渲染出现异常
      </h1>
      <p className="mt-3 text-base text-neutral-500">
        请重试；若持续出现，请稍后再访问或联系管理员。
        {process.env.NODE_ENV === "development" && (
          <span className="mt-2 block text-caption text-neutral-400">
            {error.message}
            {error.digest ? `（digest: ${error.digest}）` : ""}
          </span>
        )}
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 rounded bg-brand-600 px-4 py-2 text-base font-medium text-white hover:bg-brand-700"
      >
        重试
      </button>
    </main>
  );
}
