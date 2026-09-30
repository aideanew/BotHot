// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

/**
 * W9 D.5 —— NotificationBell 增强验收
 *
 * 1. 未读数 localStorage 持久化（刷新恢复）；
 * 2. SSE 增量去重（5s 内相同 title+message 不重复计）；
 * 3. 429 RATE_LIMITED 码位预留（下拉文案区分）。
 */

const h = vi.hoisted(() => ({
  auth: {
    status: "authed" as "loading" | "guest" | "authed",
    me: null as null | {
      sub: string;
      email: string;
      nickname: string;
      tier: string;
      wallet: string;
      is_admin: boolean;
    },
  },
}));

vi.mock("@/components/AuthContext", () => ({
  useAuth: () => ({
    status: h.auth.status,
    me: h.auth.me,
    login: () => {},
    logout: async () => {},
    reload: () => {},
  }),
}));

class FakeEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  static instances: FakeEventSource[] = [];

  url: string;
  withCredentials: boolean;
  readyState = FakeEventSource.OPEN;
  closed = false;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string, opts?: { withCredentials?: boolean }) {
    this.url = url;
    this.withCredentials = opts?.withCredentials ?? false;
    FakeEventSource.instances.push(this);
  }
  close(): void {
    this.closed = true;
    this.readyState = FakeEventSource.CLOSED;
  }
  emit(data: string): void {
    this.onmessage?.({ data });
  }
}

const latest = (): FakeEventSource => FakeEventSource.instances[FakeEventSource.instances.length - 1];

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  h.auth.status = "authed";
  h.auth.me = {
    sub: "u-w9",
    email: "w9@test",
    nickname: "W9测试",
    tier: "pro",
    wallet: "¥0",
    is_admin: false,
  };
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("NotificationBell D.5 增强", () => {
  it("未读数 localStorage 持久化：通知后 storage 有值", async () => {
    const Bell = (await import("@/components/NotificationBell")).default;
    render(createElement(Bell));
    act(() => latest().emit(JSON.stringify({ title: "持久测试", message: "m1" })));
    expect(screen.getByRole("button", { name: "通知，1 条未读" })).toBeTruthy();
    const stored = localStorage.getItem("bothot:unread:u-w9");
    expect(stored).toBe("1");
  });

  it("5s 内相同 title+message 去重不重复计数", async () => {
    const Bell = (await import("@/components/NotificationBell")).default;
    render(createElement(Bell));
    const data = JSON.stringify({ title: "重复通知", message: "相同内容" });
    act(() => latest().emit(data));
    act(() => latest().emit(data));
    expect(screen.getByRole("button", { name: "通知，1 条未读" })).toBeTruthy();
  });

  it("不同内容不去重", async () => {
    const Bell = (await import("@/components/NotificationBell")).default;
    render(createElement(Bell));
    act(() => latest().emit(JSON.stringify({ title: "通知A", message: "m1" })));
    act(() => latest().emit(JSON.stringify({ title: "通知B", message: "m2" })));
    expect(screen.getByRole("button", { name: "通知，2 条未读" })).toBeTruthy();
  });

  it("429 码位：CLOSED 状态触发 rateLimited 文案", async () => {
    const Bell = (await import("@/components/NotificationBell")).default;
    render(createElement(Bell));
    const es = latest();
    es.readyState = FakeEventSource.CLOSED;
    act(() => es.onerror?.());
    fireEvent.click(screen.getByRole("button", { name: "通知" }));
    expect(screen.getByText("请求过于频繁，请稍后再试")).toBeTruthy();
  });
});
