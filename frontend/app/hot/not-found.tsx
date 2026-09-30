import Link from "next/link";

export default function HotNotFound() {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-4xl flex-col items-center justify-center px-4 py-16 text-center">
      <p className="eyebrow">404</p>
      <h1 className="mt-2 text-title-lg font-semibold text-neutral-900">
        热点页面不存在
      </h1>
      <p className="mt-3 text-base text-neutral-500">
        请从顶部导航进入热点中心。
      </p>
      <Link
        href="/hot"
        className="mt-6 rounded bg-brand-600 px-4 py-2 text-base font-medium text-white hover:bg-brand-700"
      >
        返回热点中心
      </Link>
    </main>
  );
}
