// 轻量健康探针（A-T024 配套 3.2，2026-10-09）——Dockerfile HEALTHCHECK 专用。
// 零依赖零 SSR：进程活着即 200。放 /api/health 而非 /api/v1/** 是为绕开
// next.config.mjs 里 backend rewrite（`/api/v1/*` → BACKEND_ORIGIN），保证探针
// 只测前端本身，不与后端健康度耦合。
export const dynamic = "force-dynamic";

export async function GET() {
  return new Response("ok", {
    status: 200,
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
}
