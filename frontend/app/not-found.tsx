import Link from "next/link";

/** T1.1.3：全局 404 兜底页（大纲 v1.1 前端收口；此前三路由均缺失）。 */
export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-3xl flex-col items-center justify-center px-4 py-16 text-center">
      <p className="eyebrow">404</p>
      <h1 className="mt-2 text-title-lg font-semibold text-neutral-900">
        页面不存在或已被移动
      </h1>
      <p className="mt-3 text-base text-neutral-500">
        您访问的地址没有对应内容。可以回到工作台，或从顶部导航进入空间 / 订阅 / 公共库。
      </p>
      <div className="mt-6 flex gap-3">
        <Link
          href="/"
          className="rounded bg-brand-600 px-4 py-2 text-base font-medium text-white hover:bg-brand-700"
        >
          返回工作台
        </Link>
        <Link
          href="/spaces"
          className="rounded border border-neutral-300 px-4 py-2 text-base text-neutral-700 hover:bg-neutral-50"
        >
          我的空间
        </Link>
      </div>
    </main>
  );
}
