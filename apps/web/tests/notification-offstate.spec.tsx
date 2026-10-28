// @vitest-environment happy-dom
/**
 * STEP-65 U1 + U2 —— `ux_states` 冻结稿对 NotificationBell 的两条要求：
 *
 * U1 `offstate`：「⚠ MOCK_ENABLED 时 notifications.ts 直接不连接 ⇒ 默认演示态看不到实时通知。
 *    契约要求：演示态必须显式显示「演示数据，未连接实时通道」，禁止静默装作正常。」
 * U2 `degraded`：「Redis 缺失 ⇒ service_unavailable 帧 ⇒ 显示「实时推送暂不可用，历史仍可查」，
 *    不得显示为「无通知」」；限流那一支保留「请求过于频繁，请稍后再试」原文（契约未给新字）。
 *
 * 两条都在**渲染分支**上，jsdom 级就够判（不进 e2e 的理由见 `08` §3.4）。
 * 断言口径刻意避开 `getByText` 只看直接文本子节点的坑：需要跨子节点时用 textContent。
 *
 * U2 的契约原句带两句：横幅用「实时推送暂不可用，历史仍可查」，且「不得显示为「无通知」」。
 * 两句都做了：横幅换原字在 `NotificationBell.tsx`，后半句是 `unavailable` 时不再渲那条空态标签；
 * 连带把既有用例 `tests/we-notifications.spec.ts:208` 的断言方向也翻过来了（它原先断言"仍然显示暂无通知"）。
 * 这两处既有用例都在卡面第 6 格允许面外 ⇒ 面外笔申报与理由见 `EVD-V23-65/s65_readings.md` §6 与台账 P-143 第四条。
 */
import { createElement } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  mockMode: false,
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
  conn: null as null | {
    onNotification?: (n: unknown) => void;
    onUnavailable?: (msg?: string) => void;
    onError?: (es: { readyState: number }) => void;
  },
  disconnects: 0,
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

// 演示态门在本模块（notifications.ts 的 connectNotifications 里 isMockMode() 短路），
// 本文件用最小假实现替掉它，让"连不连"由测试决定而不是让 SSE 真发出去。
vi.mock("@/lib/api/notifications", () => ({
  connectNotifications: (handlers: typeof h.conn) => {
    h.conn = handlers;
    return () => {
      h.disconnects += 1;
    };
  },
  fetchHistory: async () => ({ items: [], total: 0, page: 1, page_size: 20, unread_total: 0 }),
  markRead: async () => 0,
}));

// isMockMode 的 USE_MOCK 是模块级常量（`process.env.NEXT_PUBLIC_API_MOCK === "true"` 在导入时定格），
// stubEnv 改不动它 ⇒ 必须 spread importOriginal 再覆盖这一个函数，其余导出（ApiError 等）保持真实。
vi.mock("@/lib/api/http", async (importOriginal) => ({
  ...((await importOriginal()) as Record<string, unknown>),
  isMockMode: () => h.mockMode,
}));

import NotificationBell from "@/components/NotificationBell";

function openPanel(): void {
  fireEvent.click(screen.getByRole("button", { name: /通知/ }));
}

beforeEach(() => {
  h.mockMode = false;
  h.conn = null;
  h.disconnects = 0;
  h.auth.status = "authed";
  h.auth.me = {
    sub: "u-65",
    email: "a@b",
    nickname: "测试者",
    tier: "pro",
    wallet: "¥0",
    is_admin: true,
  };
  // 组件的 onError 分支读 EventSource.CLOSED（全局），这里只补那一个常量
  vi.stubGlobal("EventSource", { CLOSED: 2, OPEN: 1, CONNECTING: 0 });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("U1 演示态必须显式声明（禁止静默装作正常）", () => {
  it("mock 态打开面板：出现「演示数据，未连接实时通道」，且它在列表之上", () => {
    h.mockMode = true;
    const { container } = render(createElement(NotificationBell));
    openPanel();

    const demo = screen.getByText("演示数据，未连接实时通道");
    const empty = screen.getByText("暂无通知");
    expect(demo.textContent).toBe("演示数据，未连接实时通道");
    // 「面板顶部、列表之上」（08 §3.2 第 1 行的落点）：用文档顺序判，不靠 class
    expect(
      demo.compareDocumentPosition(empty) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(container.textContent).toContain("演示数据");
  });

  it("非 mock 态不得出现演示声明（极性：不是把整行常显就交差）", () => {
    h.mockMode = false;
    render(createElement(NotificationBell));
    openPanel();
    expect(screen.queryByText("演示数据，未连接实时通道")).toBeNull();
  });
});

describe("U2 降级横幅用契约原字，且不得显示为「无通知」", () => {
  it("service_unavailable 帧 ⇒「实时推送暂不可用，历史仍可查」，旧文案不得残留", () => {
    render(createElement(NotificationBell));
    openPanel();
    act(() => {
      h.conn?.onUnavailable?.("redis unavailable");
    });

    expect(screen.getByText("实时推送暂不可用，历史仍可查")).toBeTruthy();
    expect(screen.queryByText("通知服务暂不可用，请稍后重试")).toBeNull();
  });

  it("契约后半句：降级态下不得把状态显示成「暂无通知」（横幅承担说明，空标签闭嘴）", () => {
    render(createElement(NotificationBell));
    openPanel();
    // 先证明这条判据有牙齿：非降级 + 零条目时「暂无通知」是在的
    expect(screen.getByText("暂无通知")).toBeTruthy();

    act(() => {
      h.conn?.onUnavailable?.("redis unavailable");
    });
    expect(screen.queryByText("暂无通知")).toBeNull();
    expect(screen.getByText("实时推送暂不可用，历史仍可查")).toBeTruthy();
  });

  it("限流分支保留原文案「请求过于频繁，请稍后再试」（契约未给新字，不许换）", () => {
    render(createElement(NotificationBell));
    openPanel();
    act(() => {
      h.conn?.onError?.({ readyState: 2 }); // EventSource.CLOSED
    });

    expect(screen.getByText("请求过于频繁，请稍后再试")).toBeTruthy();
  });
});
