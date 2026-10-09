// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { createElement, type ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";

/**
 * G1.3 —— AuthGate 统一未登录守卫三态单测（2026-10-10）。
 * 锁定契约：loading → 骨架（无按钮）；guest → 锚点文案"尚未登录或会话已过期"
 * + 登录按钮（onClick=login）+ 返回首页 Link；authed → 原样渲染 children。
 * 会话过期（authed→guest 掉落自动切卡）由 rerender 用例锁定（G3.2）。
 */

const h = vi.hoisted(() => ({
  status: "authed" as "loading" | "guest" | "authed",
  login: vi.fn(),
}));

vi.mock("@/components/AuthContext", () => ({
  useAuth: () => ({ status: h.status, me: null, login: h.login, logout: vi.fn(), reload: vi.fn() }),
}));

import AuthGate from "@/components/AuthGate";

function renderGate() {
  return render(
    createElement(
      AuthGate,
      null,
      createElement("p", null, "PROTECTED_CONTENT") as unknown as ReactNode
    )
  );
}

afterEach(() => {
  cleanup();
  h.status = "authed";
  h.login.mockClear();
});

describe("AuthGate 三态渲染", () => {
  it("authed → 原样渲染 children，不出现守卫文案", () => {
    h.status = "authed";
    renderGate();
    expect(screen.getByText("PROTECTED_CONTENT")).toBeTruthy();
    expect(screen.queryByText("尚未登录或会话已过期")).toBeNull();
  });

  it("guest → 统一提示卡：锚点文案 + 登录按钮（触发 login）+ 返回首页，children 不渲染", async () => {
    const { fireEvent } = await import("@testing-library/react");
    h.status = "guest";
    renderGate();
    expect(screen.getByText("尚未登录或会话已过期")).toBeTruthy();
    expect(screen.queryByText("PROTECTED_CONTENT")).toBeNull();
    const btn = screen.getByRole("button", { name: "使用主平台账号登录" });
    fireEvent.click(btn);
    expect(h.login).toHaveBeenCalledTimes(1);
    expect(screen.getByText("返回首页")).toBeTruthy();
  });

  it("loading → 骨架占位（无按钮、无守卫文案、无 children），禁止白屏", () => {
    h.status = "loading";
    renderGate();
    expect(screen.queryByText("尚未登录或会话已过期")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByText("PROTECTED_CONTENT")).toBeNull();
    // 骨架卡存在（animate-pulse 占位）
    expect(document.querySelector(".animate-pulse")).toBeTruthy();
  });

  it("会话过期：authed 渲染中掉落 guest → rerender 后自动切卡（G3.2）", () => {
    h.status = "authed";
    const { rerender } = renderGate();
    expect(screen.getByText("PROTECTED_CONTENT")).toBeTruthy();
    h.status = "guest";
    rerender(
      createElement(
        AuthGate,
        null,
        createElement("p", null, "PROTECTED_CONTENT") as unknown as ReactNode
      )
    );
    expect(screen.getByText("尚未登录或会话已过期")).toBeTruthy();
    expect(screen.queryByText("PROTECTED_CONTENT")).toBeNull();
  });
});
