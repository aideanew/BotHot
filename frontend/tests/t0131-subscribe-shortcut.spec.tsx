// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * T1.3.1 —— 详情页「订阅此号」快捷入口（components/SubscribeShortcut.tsx）
 *
 * 复用订阅页能力但本空间已预选：registerSource({biz}) → subscribeToSource(spaceId, sourceId)。
 * 策略：jsdom + RTL 直渲染真实组件；mock @/lib/api（ApiError + 两个域函数）。
 * 覆盖：空输入拦截、成功（created:true）、幂等已订阅（created:false）、
 *       错误码映射（30004/30101、10001、兜底）、成功后清空输入。
 */

const h = vi.hoisted(() => ({
  registerSource: vi.fn(),
  subscribeToSource: vi.fn(),
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
  return {
    ApiError,
    registerSource: h.registerSource,
    subscribeToSource: h.subscribeToSource,
  };
});

import SubscribeShortcut from "@/components/SubscribeShortcut";

beforeEach(() => {
  h.registerSource.mockReset();
  h.subscribeToSource.mockReset();
});

afterEach(() => {
  cleanup();
});

const SRC = { sourceId: "src-1", biz: "MzABC", name: "四川自考指南", url: "" };

describe("T1.3.1 订阅此号快捷入口", () => {
  it("空输入 → 本地拦截，不调用任何后端接口", async () => {
    render(createElement(SubscribeShortcut, { spaceId: "sp-1" }));
    fireEvent.click(screen.getByRole("button", { name: "订阅此号" }));

    expect(await screen.findByText("请输入公众号 biz 或 profile URL")).toBeTruthy();
    expect(h.registerSource).not.toHaveBeenCalled();
    expect(h.subscribeToSource).not.toHaveBeenCalled();
  });

  it("成功订阅（created:true）→ 两步调用 + 成功文案 + 回调 + 清空输入", async () => {
    h.registerSource.mockResolvedValue(SRC);
    h.subscribeToSource.mockResolvedValue({
      subscriptionId: "sub-1",
      jobIds: ["job-1"],
      created: true,
    });
    const onSubscribed = vi.fn();
    render(createElement(SubscribeShortcut, { spaceId: "sp-1", onSubscribed }));

    const input = screen.getByLabelText("公众号 biz 或 profile URL") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "MzABC" } });
    fireEvent.click(screen.getByRole("button", { name: "订阅此号" }));

    await waitFor(() => expect(h.registerSource).toHaveBeenCalledWith({ biz: "MzABC" }));
    expect(h.subscribeToSource).toHaveBeenCalledWith("sp-1", "src-1");
    expect(await screen.findByText(/已订阅「四川自考指南」/)).toBeTruthy();
    expect(onSubscribed).toHaveBeenCalledWith({
      subscriptionId: "sub-1",
      jobIds: ["job-1"],
      created: true,
    });
    expect(input.value).toBe("");
  });

  it("幂等已订阅（created:false）→ 明示未重复创建", async () => {
    h.registerSource.mockResolvedValue(SRC);
    h.subscribeToSource.mockResolvedValue({
      subscriptionId: "sub-1",
      jobIds: [],
      created: false,
    });
    render(createElement(SubscribeShortcut, { spaceId: "sp-1" }));

    fireEvent.change(screen.getByLabelText("公众号 biz 或 profile URL"), {
      target: { value: "MzABC" },
    });
    fireEvent.click(screen.getByRole("button", { name: "订阅此号" }));

    // 契约：幂等提示必须同时说明「未重复创建」与「重复点击不重新触发采集」——
    // 后者是 _create_sync_job 幂等键的真实语义，漏说会让用户以为点一次就多采一轮。
    expect(await screen.findByText(/已在订阅列表中（幂等，未重复创建/)).toBeTruthy();
    expect(screen.getByText(/重复点击不会重新触发采集/)).toBeTruthy();
  });

  it("错误码 30004/30101 → 空间或信息源不存在文案", async () => {
    const { ApiError } = await import("@/lib/api");
    h.registerSource.mockRejectedValue(new ApiError(30004, "不存在"));
    render(createElement(SubscribeShortcut, { spaceId: "sp-1" }));

    fireEvent.change(screen.getByLabelText("公众号 biz 或 profile URL"), {
      target: { value: "MzABC" },
    });
    fireEvent.click(screen.getByRole("button", { name: "订阅此号" }));

    expect(await screen.findByText("空间或信息源不存在，请检查后重试")).toBeTruthy();
  });

  it("错误码 10001 → 登录已过期文案", async () => {
    const { ApiError } = await import("@/lib/api");
    h.registerSource.mockRejectedValue(new ApiError(10001, "未登录"));
    render(createElement(SubscribeShortcut, { spaceId: "sp-1" }));

    fireEvent.change(screen.getByLabelText("公众号 biz 或 profile URL"), {
      target: { value: "MzABC" },
    });
    fireEvent.click(screen.getByRole("button", { name: "订阅此号" }));

    expect(await screen.findByText("登录已过期，请重新登录")).toBeTruthy();
  });

  it("非 ApiError 异常 → 兜底订阅失败文案", async () => {
    h.registerSource.mockRejectedValue(new Error("ECONNREFUSED"));
    render(createElement(SubscribeShortcut, { spaceId: "sp-1" }));

    fireEvent.change(screen.getByLabelText("公众号 biz 或 profile URL"), {
      target: { value: "MzABC" },
    });
    fireEvent.click(screen.getByRole("button", { name: "订阅此号" }));

    expect(await screen.findByText("订阅失败，请稍后重试")).toBeTruthy();
  });
});
