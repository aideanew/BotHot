"use client";

export default function ErrorJobs({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-5xl flex-col items-center justify-center px-4 py-16 text-center">
      <p className="eyebrow">出错了</p>
      <h1 className="mt-2 text-title-lg font-semibold text-neutral-900">
        任务页渲染异常
      </h1>
      <p className="mt-3 text-base text-neutral-500">
        请重试；若持续出现，请稍后再访问。
        {process.env.NODE_ENV === "development" && (
          <span className="mt-2 block text-caption text-neutral-400">
            {error.message}
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
