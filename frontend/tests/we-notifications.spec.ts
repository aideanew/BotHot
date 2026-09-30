// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

/**
 * WE 5.3 前端订阅侧验收（mock EventSource，零真实网络）：
 * 1. parseNotificationFrame：通知帧 / 控制帧 / 脏帧三类分流；
 * 2. connectNotifications：连接建立（url + withCredentials）、消息入列、降级回调、close 幂等；
 * 3. NotificationBell：登录才连、消息 → 未读计数、展开下拉入列并清零、
 *    卸载断连、登出（status 翻转）即断连。
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

// ------------------------------------------------------------------ 假 EventSource

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

  /** 测试辅助：模拟服务端推来一条 data 帧 */
  emit(data: string): void {
    this.onmessage?.({ data });
  }
}

const latest = (): FakeEventSource => FakeEventSource.instances[FakeEventSource.instances.length - 1];

// ------------------------------------------------------------------ 纯函数：帧解析

describe("parseNotificationFrame", () => {
  it("通知帧 → kind=notification，字段透传", async () => {
    const { parseNotificationFrame } = await import("@/lib/api/notifications");
    const raw = JSON.stringify({ title: "空间更新", message: "新文档已入库", space_id: "s1" });
    expect(parseNotificationFrame(raw)).toEqual({
      kind: "notification",
      notification: {
        title: "空间更新",
        message: "新文档已入库",
        url: undefined,
        space_id: "s1",
        doc_id: undefined,
      },
    });
  });

  it("含 type 键 → 控制帧（service_unavailable 等）", async () => {
    const { parseNotificationFrame } = await import("@/lib/api/notifications");
    expect(parseNotificationFrame(JSON.stringify({ type: "service_unavailable", message: "暂不可用" }))).toEqual({
      kind: "control",
      type: "service_unavailable",
      message: "暂不可用",
    });
  });

  it("非 JSON / 非对象 → ignore（绝不抛穿渲染期）", async () => {
    const { parseNotificationFrame } = await import("@/lib/api/notifications");
    expect(parseNotificationFrame("not json")).toEqual({ kind: "ignore" });
    expect(parseNotificationFrame("42")).toEqual({ kind: "ignore" });
    expect(parseNotificationFrame(JSON.stringify({ foo: "bar" }))).toEqual({ kind: "ignore" });
  });
});

// ------------------------------------------------------------------ 连接封装

describe("connectNotifications", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
  });

  it("以同源端点 + withCredentials 建连（SSO cookie 随请求走）", async () => {
    const { connectNotifications, NOTIFICATIONS_ENDPOINT } = await import("@/lib/api/notifications");
    const disconnect = connectNotifications({ onNotification: () => {} });
    expect(NOTIFICATIONS_ENDPOINT).toBe("/api/v1/system/notifications");
    expect(latest().url).toBe("/api/v1/system/notifications");
    expect(latest().withCredentials).toBe(true);
    disconnect();
    expect(latest().closed).toBe(true);
  });

  it("通知帧入 onNotification；控制帧入 onUnavailable；脏帧静默", async () => {
    const { connectNotifications } = await import("@/lib/api/notifications");
    const onNotification = vi.fn();
    const onUnavailable = vi.fn();
    connectNotifications({ onNotification, onUnavailable });
    const es = latest();
    es.emit(JSON.stringify({ title: "t", message: "m" }));
    expect(onNotification).toHaveBeenCalledWith({ title: "t", message: "m" });
    es.emit(JSON.stringify({ type: "service_unavailable", message: "Redis 不可达" }));
    expect(onUnavailable).toHaveBeenCalledWith("Redis 不可达");
    es.emit("garbage");
    expect(onNotification).toHaveBeenCalledTimes(1);
  });

  it("close 幂等：重复调用不抛", async () => {
    const { connectNotifications } = await import("@/lib/api/notifications");
    const disconnect = connectNotifications({ onNotification: () => {} });
    disconnect();
    expect(() => disconnect()).not.toThrow();
  });
});

// ------------------------------------------------------------------ 铃铛组件

describe("NotificationBell", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    h.auth.status = "authed";
    h.auth.me = {
      sub: "u-1",
      email: "a@a.local",
      nickname: "测试用户",
      tier: "pro",
      wallet: "¥0",
      is_admin: false,
    };
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("登录态建连；未读计数随通知增长", async () => {
    const NotificationBell = (await import("@/components/NotificationBell")).default;
    render(createElement(NotificationBell));
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(latest().url).toBe("/api/v1/system/notifications");

    act(() => latest().emit(JSON.stringify({ title: "空间更新", message: "第一条" })));
    expect(screen.getByRole("button", { name: "通知，1 条未读" })).toBeTruthy();

    act(() => latest().emit(JSON.stringify({ title: "热点日报", message: "第二条" })));
    expect(screen.getByRole("button", { name: "通知，2 条未读" })).toBeTruthy();
  });

  it("展开下拉：列表最新在前 + 未读清零", async () => {
    const NotificationBell = (await import("@/components/NotificationBell")).default;
    render(createElement(NotificationBell));
    act(() => latest().emit(JSON.stringify({ title: "第一条", message: "先到的通知" })));
    act(() => latest().emit(JSON.stringify({ title: "第二条", message: "后到的通知" })));

    fireEvent.click(screen.getByRole("button", { name: "通知，2 条未读" }));
    // 展开即已读：徽标消失，按钮名回落「通知」
    expect(screen.getByRole("button", { name: "通知" })).toBeTruthy();
    expect(screen.getByText("第一条")).toBeTruthy();
    expect(screen.getByText("先到的通知")).toBeTruthy();
    const titles = screen.getAllByText(/第[一二]条/).map((el) => el.textContent);
    expect(titles.slice(0, 2)).toEqual(["第二条", "第一条"]); // 最新在前
  });

  it("后端控制帧 → 下拉展示「通知服务暂不可用」，不崩渲染", async () => {
    const NotificationBell = (await import("@/components/NotificationBell")).default;
    render(createElement(NotificationBell));
    act(() => latest().emit(JSON.stringify({ type: "service_unavailable", message: "暂不可用" })));
    fireEvent.click(screen.getByRole("button", { name: "通知" }));
    expect(screen.getByText("通知服务暂不可用，请稍后重试")).toBeTruthy();
    expect(screen.getByText("暂无通知")).toBeTruthy();
  });

  it("卸载即断连（cleanup → EventSource.close）", async () => {
    const NotificationBell = (await import("@/components/NotificationBell")).default;
    const { unmount } = render(createElement(NotificationBell));
    const es = latest();
    unmount();
    expect(es.closed).toBe(true);
  });

  it("登出（authed→guest 翻转）立即断连并清空视图", async () => {
    const NotificationBell = (await import("@/components/NotificationBell")).default;
    const { rerender } = render(createElement(NotificationBell));
    const es = latest();
    act(() => es.emit(JSON.stringify({ title: "在网通知", message: "m" })));
    expect(screen.getByRole("button", { name: "通知，1 条未读" })).toBeTruthy();

    h.auth.status = "guest";
    rerender(createElement(NotificationBell));
    expect(es.closed).toBe(true);
    expect(screen.queryByRole("button", { name: /通知/ })).toBeNull(); // guest 不渲染铃铛
  });

  it("未登录不建连（省资源，登录后再订阅）", async () => {
    h.auth.status = "guest";
    const NotificationBell = (await import("@/components/NotificationBell")).default;
    render(createElement(NotificationBell));
    expect(FakeEventSource.instances).toHaveLength(0);
  });
});
