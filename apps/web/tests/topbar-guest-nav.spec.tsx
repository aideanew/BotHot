// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { cleanup, render, screen } from "@testing-library/react";

/**
 * G3.4 —— TopBar 私有导航项会话态三形态单测（2026-10-09，二期登记项落地）。
 * 锁定契约：guest → 四私有项渲染为锁形徽标按钮（点击触发 login，同 G3.1 入口），
 * admin 项对游客仍隐藏（权限门 ≠ 登录门）；authed → 恢复正常 Link，无锁按钮；
 * loading → 私有项不渲染（避免判定中闪徽标）。
 */

const h = vi.hoisted(() => ({
  status: "guest" as "loading" | "guest" | "authed",
  me: null as null | { email: string; nickname: string; is_admin: boolean },
  login: vi.fn(),
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: h.push, replace: vi.fn(), back: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  MOCK_LABEL: "MOCK",
  MOCK_ENABLED: true,
}));

vi.mock("@/components/NotificationBell", () => ({
  default: () => null,
}));

vi.mock("@/components/AuthContext", () => ({
  useAuth: () => ({ status: h.status, me: h.me, login: h.login, logout: vi.fn(), reload: vi.fn() }),
}));

import TopBar from "@/components/TopBar";

afterEach(() => {
  cleanup();
  h.status = "guest";
  h.me = null;
  h.login.mockClear();
  h.push.mockClear();
});

const PRIVATE_LABELS = ["订阅", "任务", "引擎", "机器人"] as const;

describe("TopBar 私有导航项三形态（G3.4）", () => {
  it("guest → 四私有项渲染为锁形徽标按钮，点击触发 login；admin 项隐藏", async () => {
    const { fireEvent } = await import("@testing-library/react");
    h.status = "guest";
    render(createElement(TopBar));
    for (const label of PRIVATE_LABELS) {
      const btn = screen.getByRole("button", { name: `登录后可见：${label}` });
      expect(btn.getAttribute("title")).toBe(`登录后可见：${label}`);
    }
    // 公共项不受影响，仍是链接
    expect(screen.getByRole("link", { name: "公共库" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "热点" })).toBeTruthy();
    // admin 是权限门（is_admin），对游客不展示锁形徽标
    expect(screen.queryByRole("button", { name: "登录后可见：管理" })).toBeNull();
    // 点击徽标 → 直连 login()，不发生路由跳转
    fireEvent.click(screen.getByRole("button", { name: "登录后可见：订阅" }));
    expect(h.login).toHaveBeenCalledTimes(1);
    expect(h.push).not.toHaveBeenCalled();
  });

  it("authed → 四私有项恢复为正常链接，锁形按钮消失", () => {
    h.status = "authed";
    h.me = { email: "a@b.c", nickname: "QA管理员", is_admin: true };
    render(createElement(TopBar));
    for (const label of PRIVATE_LABELS) {
      expect(screen.getByRole("link", { name: label })).toBeTruthy();
      expect(screen.queryByRole("button", { name: `登录后可见：${label}` })).toBeNull();
    }
    // admin（is_admin=true）可见
    expect(screen.getByRole("link", { name: "管理" })).toBeTruthy();
  });

  it("loading → 私有项不渲染（判定中不闪徽标），公共项保持", () => {
    h.status = "loading";
    render(createElement(TopBar));
    for (const label of PRIVATE_LABELS) {
      expect(screen.queryByRole("button", { name: `登录后可见：${label}` })).toBeNull();
      expect(screen.queryByRole("link", { name: label })).toBeNull();
    }
    expect(screen.getByRole("link", { name: "公共库" })).toBeTruthy();
  });
});
