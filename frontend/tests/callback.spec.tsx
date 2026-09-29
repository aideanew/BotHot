// @vitest-environment happy-dom
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { StrictMode, createElement, type ComponentType } from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

/**
 * SSO callback 页功能逻辑单测（C-2/C-7，契约错误码 10002/10003）
 * 策略：jsdom + RTL 直渲染真实页面组件；
 * mock next/navigation（router/searchParams）与 @/lib/api（request/ApiError）。
 * 覆盖：缺 code、缺 state、成功跳转、10002/10003 映射、
 *       其他 ApiError / 非 ApiError、URL 编码、StrictMode 双执行、卸载静默。
 */

const h = vi.hoisted(() => ({
  search: "",
  replace: vi.fn(),
  reload: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: h.replace,
    push: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(h.search),
  usePathname: () => "/auth/aidean/callback",
}));

vi.mock("@/lib/api", () => {
  class ApiError extends Error {
    code: number;
    requestId: string;
    constructor(code: number, message: string, requestId = "") {
      super(message);
      this.name = "ApiError";
      this.code = code;
      this.requestId = requestId;
    }
  }
  return { ApiError, request: vi.fn() };
});

// 回调页成功后要显式重取 /auth/me（B33：router.replace 是客户端跳转，不会重挂
// AuthProvider）。本文件直接渲染页面组件、不套 AuthProvider，故 mock 掉该 hook。
vi.mock("@/components/AuthContext", () => ({
  useAuth: () => ({ reload: h.reload }),
}));

// 顶层 await 在当前 tsconfig target 下不可用，改用 beforeAll 动态导入（vi.mock 已 hoist，导入拿到 mock）
let AuthCallbackPage: ComponentType;
let ApiError: new (code: number, message: string, requestId?: string) => Error & {
  code: number;
  requestId: string;
};
let requestMock: Mock;

beforeAll(async () => {
  ({ default: AuthCallbackPage } = await import("@/app/auth/aidean/callback/page"));
  const api = await import("@/lib/api");
  ApiError = api.ApiError as typeof ApiError;
  requestMock = api.request as unknown as Mock;
});

beforeEach(() => {
  h.search = "";
  h.replace.mockClear();
  h.reload.mockClear();
  requestMock.mockReset();
  requestMock.mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
});

/** 渲染当前参数下的回调页并等待稳定 */
async function renderCallback() {
  render(createElement(AuthCallbackPage));
  await waitFor(() => {
    // 至少一个终态出现：错误文案或跳转
    const done =
      h.replace.mock.calls.length > 0 ||
      screen.queryByText(/回调参数缺失|请重新登录|state 无效|授权码兑换|网络异常/) !== null;
    if (!done) throw new Error("not settled");
  });
}

describe("SSO callback：参数校验", () => {
  it("缺 code：显示既定错误且不发 callback 请求、不跳转", async () => {
    h.search = "?state=xyz";
    await renderCallback();
    expect(screen.getByText(/回调参数缺失（code\/state）/)).toBeTruthy();
    expect(requestMock).not.toHaveBeenCalled();
    expect(h.replace).not.toHaveBeenCalled();
  });

  it("缺 state：显示既定错误且不发 callback 请求、不跳转", async () => {
    h.search = "?code=abc";
    await renderCallback();
    expect(screen.getByText(/回调参数缺失（code\/state）/)).toBeTruthy();
    expect(requestMock).not.toHaveBeenCalled();
    expect(h.replace).not.toHaveBeenCalled();
  });

  it("code/state 完整且成功：请求一次并仅跳转一次，不显示错误", async () => {
    h.search = "?code=abc&state=xyz";
    await renderCallback();
    expect(requestMock).toHaveBeenCalledTimes(1);
    expect(requestMock.mock.calls[0]?.[0]).toBe("/api/v1/auth/callback?code=abc&state=xyz");
    expect(h.replace).toHaveBeenCalledTimes(1);
    expect(h.replace).toHaveBeenCalledWith("/");
    expect(screen.queryByText(/登录回调失败/)).toBeNull();
    // B33：真实态登录后 UI 曾停在「未登录」直到手动刷新——成功路径必须显式重取
    // /auth/me，且必须在跳转前发出（跳转后本组件即被替换）。
    expect(h.reload).toHaveBeenCalledTimes(1);
    expect(h.reload.mock.invocationCallOrder[0]).toBeLessThan(
      h.replace.mock.invocationCallOrder[0]
    );
  });

  it("code/state 含特殊字符时按 encodeURIComponent 转发", async () => {
    h.search = "?code=a%20b%26c&state=s%2Fx";
    await renderCallback();
    const called = requestMock.mock.calls[0]?.[0] as string;
    expect(called).toBe(
      `/api/v1/auth/callback?code=${encodeURIComponent("a b&c")}&state=${encodeURIComponent("s/x")}`
    );
  });
});

describe("SSO callback：错误映射", () => {
  it("10002：显示 state 无效文案，不跳转", async () => {
    h.search = "?code=abc&state=bad";
    requestMock.mockRejectedValue(new ApiError(10002, "登录状态校验失败，请重新登录"));
    await renderCallback();
    expect(screen.getByText(/state 无效或已使用/)).toBeTruthy();
    expect(h.replace).not.toHaveBeenCalled();
    // 兑换失败 = 会话未建立，绝不能重取 /auth/me（否则会把 UI 误刷成已登录态）
    expect(h.reload).not.toHaveBeenCalled();
  });

  it("10003：显示授权码兑换失败文案，不跳转", async () => {
    h.search = "?code=expired&state=xyz";
    requestMock.mockRejectedValue(new ApiError(10003, "授权码兑换失败，请重新登录"));
    await renderCallback();
    expect(screen.getByText(/授权码兑换失败（过期或被拒绝）/)).toBeTruthy();
    expect(h.replace).not.toHaveBeenCalled();
  });

  it("其他 ApiError（50101 网络异常）：透出后端中文文案，不跳转", async () => {
    h.search = "?code=abc&state=xyz";
    requestMock.mockRejectedValue(new ApiError(50101, "网络异常，请检查连接后重试"));
    await renderCallback();
    expect(screen.getByText("网络异常，请检查连接后重试")).toBeTruthy();
    expect(h.replace).not.toHaveBeenCalled();
  });

  it("非 ApiError 异常：回落默认失败文案，不跳转", async () => {
    h.search = "?code=abc&state=xyz";
    requestMock.mockRejectedValue(new Error("boom"));
    await renderCallback();
    expect(screen.getByText("登录回调失败，请重新登录。")).toBeTruthy();
    expect(h.replace).not.toHaveBeenCalled();
  });
});

describe("SSO callback：渲染与卸载行为", () => {
  it("StrictMode 双执行：最终成功且仅跳转一次（首次 effect 取消静默）", async () => {
    h.search = "?code=abc&state=xyz";
    render(
      createElement(
        StrictMode,
        null,
        createElement(AuthCallbackPage)
      )
    );
    await waitFor(() => expect(h.replace).toHaveBeenCalled());
    // 双执行下允许两次请求（首次被同步 abort），但成功跳转必须恰好一次
    expect(h.replace).toHaveBeenCalledTimes(1);
    expect(h.replace).toHaveBeenCalledWith("/");
    // 重取 /auth/me 与跳转严格配对（首次 effect 被 abort，不得漏刷或刷空）
    expect(h.reload.mock.calls.length).toBe(h.replace.mock.calls.length);
  });

  it("卸载：请求进行中卸载组件后不更新状态、不跳转", async () => {
    h.search = "?code=abc&state=xyz";
    let release!: (v: undefined) => void;
    requestMock.mockReturnValue(
      new Promise<undefined>((resolve) => {
        release = resolve;
      })
    );
    const { unmount } = render(createElement(AuthCallbackPage));
    await waitFor(() => expect(requestMock).toHaveBeenCalled());
    unmount(); // 触发 cleanup：cancelled + abort
    release(undefined); // 请求迟到的 resolve 也不应触发跳转
    await new Promise((r) => setTimeout(r, 20));
    expect(h.replace).not.toHaveBeenCalled();
    expect(screen.queryByText(/登录回调失败/)).toBeNull();
  });
});
