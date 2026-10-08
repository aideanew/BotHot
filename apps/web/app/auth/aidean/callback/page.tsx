"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, request } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import { usePageTitle } from "@/components/usePageTitle";

/**
 * SSO 回调承接页（C-T7R，推翻 C-T2"不建 callback 页"裁决）
 * 职责：主平台 authorize 经 redirect_uri 回跳后（浏览器不可达域名属预期），
 * 用户携带 code+state 手动/自动落到本页 → 转发 GET /api/v1/auth/callback
 * （经 rewrites 代理，服务端 code 兑换 + 种 HttpOnly 会话 cookie）→ 成功跳首页。
 * 演练路径：地址栏复制 code+state → 手动访问本页（M2 双 issuer 债）。
 * 错误语义（契约）：state 无效 → 10002；code 兑换被拒 → 10003。
 */

function CallbackInner() {
  usePageTitle("登录中");
  const router = useRouter();
  const searchParams = useSearchParams();
  const { reload: reloadAuth } = useAuth();
  const [errorText, setErrorText] = useState("");

  useEffect(() => {
    const code = searchParams.get("code") ?? "";
    const state = searchParams.get("state") ?? "";
    if (!code || !state) {
      setErrorText("回调参数缺失（code/state），请从主平台登录后重试。");
      return;
    }

    // 卸载保护：取消进行中的 callback 请求，且不更新已卸载组件。
    // StrictMode（dev）双执行：首次 effect 被同步 cleanup abort（code 尚未消费），
    // 第二次 effect 重新发起，因此不用模块级 firedRef 拦截（会导致 dev 登录卡死）。
    const ctrl = new AbortController();
    let cancelled = false;

    void (async () => {
      try {
        // 导出 request（信封解包）供本页复用：成功即已种会话 cookie
        await request<unknown>(
          `/api/v1/auth/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`,
          { signal: ctrl.signal }
        );
        if (cancelled) return;
        // 会话已建立：客户端路由跳转不会重挂 AuthProvider，必须显式重取 /auth/me，
        // 否则真实态登录后 UI 停在「未登录」直到手动刷新页面（B33）。
        reloadAuth();
        router.replace("/");
      } catch (err) {
        if (cancelled) return; // 卸载/StrictMode 首次取消：不更新状态
        if (err instanceof ApiError) {
          if (err.code === 10002) {
            setErrorText("登录状态校验失败（state 无效或已使用），请重新登录。");
          } else if (err.code === 10003) {
            setErrorText("授权码兑换失败（过期或被拒绝），请重新登录。");
          } else {
            setErrorText(err.message || "登录回调失败，请重新登录。");
          }
        } else {
          setErrorText("登录回调失败，请重新登录。");
        }
      }
    })();

    return () => {
      cancelled = true;
      ctrl.abort();
    };
  }, [searchParams, router, reloadAuth]);

  return (
    <main className="mx-auto max-w-3xl px-4 py-16">
      <div className="card mx-auto max-w-md p-10 text-center">
        {errorText ? (
          <>
            <h1 className="text-title-lg font-semibold text-neutral-900">
              登录回调失败
            </h1>
            <p className="mt-3 text-danger">{errorText}</p>
            <button
              onClick={() => router.replace("/")}
              className="mt-8 rounded-input bg-brand-500 px-6 py-2 text-white hover:bg-brand-600"
            >
              返回首页重新登录
            </button>
          </>
        ) : (
          <p className="text-neutral-500">正在完成登录，请稍候…</p>
        )}
      </div>
    </main>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-3xl px-4 py-16 text-center text-neutral-500">
          正在加载…
        </main>
      }
    >
      <CallbackInner />
    </Suspense>
  );
}
