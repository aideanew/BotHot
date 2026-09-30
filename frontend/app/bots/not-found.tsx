import Link from "next/link";

export default function BotsNotFound() {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-5xl flex-col items-center justify-center px-4 py-16 text-center">
      <p className="eyebrow">404</p>
      <h1 className="mt-2 text-title-lg font-semibold text-neutral-900">
        机器人渠道不存在
      </h1>
      <p className="mt-3 text-base text-neutral-500">
        该渠道可能已被删除或地址有误。
      </p>
      <Link
        href="/bots"
        className="mt-6 rounded bg-brand-600 px-4 py-2 text-base font-medium text-white hover:bg-brand-700"
      >
        返回机器人管理
      </Link>
    </main>
  );
}
