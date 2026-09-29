"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { ApiError, authLogin, authLogout, authMe, isAuthError, type MeData } from "@/lib/api";

/**
 * 会话态上下文（C-T2）
 * 三态：loading（判定中）/ guest（未登录）/ authed（已登录）。
 * 单次 /auth/me 请求全站共享；登录/登出后通过 refresh() + 本地状态同步保证一致。
 * 任何失败（未登录码/网络异常）都回落 guest 态，禁止白屏。
 */

type AuthStatus = "loading" | "guest" | "authed";

interface AuthContextValue {
  status: AuthStatus;
  me: MeData | null;
  /** 登录入口（mock 写标记 / 真实跳 SSO），由 TopBar 与首页引导卡共用 */
  login: () => void;
  /** 退出：POST /auth/logout 后回落 guest 态 */
  logout: () => Promise<void>;
  /** 手动重试（用于网络失败后的重载） */
  reload: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** tier 中文映射（数据值非文案，未知值原样回显） */
export function tierLabel(tier: string): string {
  const map: Record<string, string> = {
    free: "免费版",
    pro: "专业版",
    team: "团队版",
  };
  return map[tier] ?? tier;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [me, setMe] = useState<MeData | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    authMe()
      .then((data) => {
        if (cancelled) return;
        setMe(data);
        setStatus("authed");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setMe(null);
        setStatus("guest");
        // 非未登录类错误（网络/服务异常）仅控制台留痕，不阻断渲染
        if (err instanceof ApiError && !isAuthError(err.code)) {
          console.warn(`会话判定失败（code=${err.code}）：${err.message}`);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  const login = useCallback(() => {
    authLogin(); // mock 态内部 reload；真实态整页跳 SSO
  }, []);

  const logout = useCallback(async () => {
    try {
      await authLogout();
    } finally {
      setMe(null);
      setStatus("guest");
      router.refresh(); // 全站路由状态同步
    }
  }, [router]);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  return (
    <AuthContext.Provider value={{ status, me, login, logout, reload }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth 必须在 AuthProvider 内使用");
  }
  return ctx;
}
