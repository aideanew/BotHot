export default function AuthLoading() {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-5xl flex-col items-center justify-center px-4 py-16 text-center">
      <div className="h-10 w-10 animate-spin rounded-full border-2 border-neutral-200 border-t-brand-600" />
      <p className="mt-4 text-base text-neutral-500">正在完成统一登录…</p>
    </main>
  );
}
