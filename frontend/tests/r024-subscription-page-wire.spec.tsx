// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * R0.2.4 —— 订阅页与生命周期入口的接线（页面层）
 *
 * 组件自测只覆盖「点了按钮调了函数」，但 F-2 真正的接线风险在页面层：
 * `spaceId` 取自页面选中态（listSpaces()[0].id）。若这里传成空串或别的行的 id，
 * 退订/改频率会打到错误空间或 404，而卡片仍显示成功。本测钉住这条缝：
 * ①入口按钮与「重试失败 N 篇」共存（R0.2.4 重排过右列结构）；
 * ②退订/改频率回写后，卡片进入对应态且回调的是选中空间。
 */
const h = vi.hoisted(() => ({
  listSpaces: vi.fn(),
  listSubscriptions: vi.fn(),
  getJob: vi.fn(),
  retryJob: vi.fn(),
  registerSource: vi.fn(),
  subscribeToSource: vi.fn(),
  updateSubscription: vi.fn(),
  cancelSubscription: vi.fn(),
}));

vi.mock("@/components/AuthContext", () => ({
  useAuth: () => ({
    status: "authed",
    me: null,
    login: () => {},
    logout: async () => {},
    reload: () => {},
  }),
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
  // 真实标签表在 lib/api/jobs.ts（JOB_STATUS_LABELS）；此处镜像以保持渲染出真实中文
  const STATUS_LABELS: Record<string, string> = {
    QUEUED: "排队中",
    RUNNING: "执行中",
    SUCCEEDED: "已完成",
    PARTIAL_SUCCESS: "部分成功",
    FAILED: "失败",
    CANCELLED: "已取消",
  };
  return {
    ApiError,
    POLL_NET_FAIL_THRESHOLD: 3,
    networkPauseMessage: (n: number) => `网络异常，进度暂停（连续 ${n} 次）`,
    jobStatusLabel: (s: string) => STATUS_LABELS[s] ?? s,
    listSpaces: h.listSpaces,
    listSubscriptions: h.listSubscriptions,
    getJob: h.getJob,
    retryJob: h.retryJob,
    registerSource: h.registerSource,
    subscribeToSource: h.subscribeToSource,
    updateSubscription: h.updateSubscription,
    cancelSubscription: h.cancelSubscription,
  };
});

import SubscriptionPage from "@/app/subscriptions/page";

const realSetInterval = globalThis.setInterval;
const realClearInterval = globalThis.clearInterval;
const polls: Array<() => void | Promise<void>> = [];

const SPACE = {
  id: "sp-1",
  name: "我的空间",
  engine: "builtin",
  docCount: 0,
  createdAt: "2026-09-01T00:00:00+00:00",
} as never;

function sub(overrides: Record<string, unknown> = {}) {
  return {
    subscriptionId: "sub-1",
    sourceId: "src-1",
    biz: "MzABC",
    sourceName: "四川自考指南",
    syncPolicy: "auto",
    syncIntervalMinutes: 360,
    nextRunAt: "2026-09-22T10:00:00+00:00",
    status: "ACTIVE",
    ...overrides,
  } as never;
}

function job(overrides: Record<string, unknown> = {}) {
  return {
    jobId: "job-1",
    type: "SUBSCRIBE",
    status: "PARTIAL_SUCCESS",
    progress: 90,
    error: "",
    counts: { total: 10, succeeded: 8, failed: 2, pending: 0 },
    createdAt: "2026-09-22T09:00:00+00:00",
    ...overrides,
  } as never;
}

async function renderWith(subscriptions: unknown[]) {
  h.listSpaces.mockResolvedValue([SPACE]);
  h.listSubscriptions.mockResolvedValue(subscriptions);
  h.getJob.mockResolvedValue(job());
  render(createElement(SubscriptionPage));
  return await screen.findByText("四川自考指南");
}

/** 手动触发一次页面轮询（跳过 5 秒等待），填充进度与「重试失败 N 篇」按钮。 */
async function firePoll() {
  expect(polls.length).toBeGreaterThan(0);
  await polls[polls.length - 1]();
}

beforeEach(() => {
  polls.length = 0;
  for (const fn of [
    h.listSpaces,
    h.listSubscriptions,
    h.getJob,
    h.retryJob,
    h.registerSource,
    h.subscribeToSource,
    h.updateSubscription,
    h.cancelSubscription,
  ]) {
    fn.mockReset();
  }
  vi.stubGlobal(
    "setInterval",
    ((fn: () => void, ms?: number) => {
      if (typeof ms === "number" && ms >= 1000) {
        polls.push(fn);
        return polls.length;
      }
      return realSetInterval(fn, ms);
    }) as typeof setInterval
  );
  vi.stubGlobal(
    "clearInterval",
    ((id: unknown) => {
      if (typeof id === "number" && id <= polls.length) return;
      realClearInterval(id as ReturnType<typeof setInterval>);
    }) as typeof clearInterval
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("R0.2.4 订阅页生命周期入口接线", () => {
  it("入口与「重试失败 N 篇」共存（右列重排后仍齐全）", async () => {
    await renderWith([sub({ latestJobId: "job-1" })]);
    await firePoll();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /重试失败 2 篇/ })).toBeTruthy()
    );
    expect(screen.getByRole("button", { name: "调整频率" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "退订" })).toBeTruthy();
  });

  it("退订：回调选中空间，卡片进入已退订态（两入口禁用）", async () => {
    await renderWith([sub({ latestJobId: "job-1" })]);
    h.cancelSubscription.mockResolvedValue({
      subscriptionId: "sub-1",
      syncPolicy: "auto",
      syncIntervalMinutes: 360,
      nextRunAt: "",
      status: "CANCELLED",
      cancelled: true,
    });

    fireEvent.click(screen.getByRole("button", { name: "退订" }));
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "确认退订" }));

    expect(h.cancelSubscription).toHaveBeenCalledWith("sp-1", "sub-1");
    expect(await screen.findByText(/已退订（仅停未来同步/)).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "调整频率" }).hasAttribute("disabled")).toBe(true);
      expect(screen.getByRole("button", { name: "退订" }).hasAttribute("disabled")).toBe(true);
    });
  });

  it("改频率：回调选中空间与所选分钟数，弹窗关闭", async () => {
    await renderWith([sub({ latestJobId: "job-1" })]);
    h.updateSubscription.mockResolvedValue({
      subscriptionId: "sub-1",
      syncPolicy: "auto",
      syncIntervalMinutes: 1440,
      nextRunAt: "2026-09-23T10:00:00+00:00",
      status: "ACTIVE",
    });

    fireEvent.click(screen.getByRole("button", { name: "调整频率" }));
    // 弹窗内下拉落在 dialog 内（页面顶部另有目标空间下拉，勿取到那个）
    const select = screen.getByRole("dialog").querySelector("select");
    if (!select) throw new Error("弹窗未渲染下拉");
    fireEvent.change(select, { target: { value: "1440" } });
    fireEvent.click(screen.getByRole("button", { name: "保存频率" }));

    expect(h.updateSubscription).toHaveBeenCalledWith("sp-1", "sub-1", {
      sync_interval_minutes: 1440,
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("退订失败 → 页面错误横幅不干扰，卡片仍在订态（弹窗不关）", async () => {
    await renderWith([sub({ latestJobId: "job-1" })]);
    h.cancelSubscription.mockRejectedValue(new Error("知识空间不存在或已删除"));

    fireEvent.click(screen.getByRole("button", { name: "退订" }));
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "确认退订" }));

    await screen.findByText("知识空间不存在或已删除");
    expect(screen.queryByRole("dialog")).not.toBeNull();
    expect(screen.queryByText(/已退订（仅停未来同步/)).toBeNull();
  });
});
