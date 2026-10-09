import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * 全局认证守卫（路由层）—— 与 AuthGate（渲染层）形成双层保护
 *
 * 公开路由白名单：
 * - /：首页（含引导卡）
 * - /auth/*：SSO 回调
 * - /api/*：API 路由（自行处理 401）
 *
 * 受保护路由：未登录访问时重定向到首页（AuthGate 会显示统一提示）
 */
const PUBLIC_PATHS = ["/", "/auth"];
const PUBLIC_PREFIXES = ["/auth/", "/api/"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // 公开路由直接放行
  if (PUBLIC_PATHS.includes(pathname) || PUBLIC_PREFIXES.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // 检查会话 cookie（存在即视为已登录，AuthGate 会做最终判定）
  const sessionCookie = request.cookies.get("bothot_session");

  if (!sessionCookie) {
    // 未登录 → 重定向到首页（AuthGate 会显示统一提示）
    const url = request.nextUrl.clone();
    url.pathname = "/";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
