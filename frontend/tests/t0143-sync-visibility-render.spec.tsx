// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * T1.4.3 / T1.4.4（N11）—— 订阅卡「预计篇数 + 同步可见性」渲染（页面层）
 *
 * 覆盖 `app/subscriptions/page.tsx` 四条呈现契约：
 * ①预计篇数（discoveredCount，U6）②上次成功同步（lastSuccessAt，空则「尚无成功同步」）
 * ③连续空轮询退避提示（consecutiveEmptySyncs > 0 才显示）④任务进度 done/total + 百分比
 *   + PARTIAL_SUCCESS 的「重试失败 N 篇」按钮。
 *
 * 策略同 t0131：jsdom + RTL 直渲染真实页面；mock `@/lib/api` 与 `@/components/AuthContext`。
 * 进度条由 5s 轮询填充（page.tsx:85-110），无法同步注入 → 用「按间隔分流」的 setInterval
 * 桩：≥1000ms 的定时（页面轮询）被捕获、手动触发；<1000ms 的（RTL waitFor 的 50ms 轮询）
 * 交给真实定时器。既确定又可断言，无需真等 5 秒。
 */

const h = vi.hoisted(() => ({
  listSpaces: vi.fn(),
  listSubscriptions: vi.fn(),
  getJob: vi.fn(),
  retryJob: vi.fn(),
  registerSource: vi.fn(),
  subscribeToSource: vi.fn(),
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
    registerSource: h.registerSource,
    subscribeToSource: h.subscribeToSource,
    listSpaces: h.listSpaces,
    listSubscriptions: h.listSubscriptions,
    getJob: h.getJob,
    retryJob: h.retryJob,
  };
});

import SubscriptionPage from "@/app/subscriptions/page";

const realSetInterval = globalThis.setInterval;
const realClearInterval = globalThis.clearInterval;
const polls: Array<() => void | Promise<void>> = [];

function job(overrides: Record<string, unknown> = {}) {
  return {
    jobId: "job-1",
    type: "SUBSCRIBE",
    status: "RUNNING",
    progress: 75,
    error: "",
    counts: { total: 12, succeeded: 9, failed: 0, pending: 3 },
    createdAt: "2026-09-22T09:00:00+00:00",
    ...overrides,
  } as never;
}

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
    nextRunAt: "2026-09-22T10:00:00+00:00",
    status: "ACTIVE",
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

/** 手动触发一次页面轮询（跳过 5 秒等待）。 */
async function firePoll() {
  expect(polls.length).toBeGreaterThan(0);
  await polls[polls.length - 1]();
}

beforeEach(() => {
  polls.length = 0;
  h.listSpaces.mockReset();
  h.listSubscriptions.mockReset();
  h.getJob.mockReset();
  h.retryJob.mockReset();
  h.registerSource.mockReset();
  h.subscribeToSource.mockReset();
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

describe("T1.4.3 预计篇数（discoveredCount）", () => {
  it("有 DISCOVERED 清单 → 渲染「预计篇数：N 篇」", async () => {
    await renderWith([sub({ discoveredCount: 37 })]);
    expect(screen.getByText(/预计篇数：37 篇/)).toBeTruthy();
  });

  it("字段缺省（老数据）→ 诚实显示 0 篇，不崩溃不隐藏", async () => {
    await renderWith([sub({})]);
    expect(screen.getByText(/预计篇数：0 篇/)).toBeTruthy();
  });
});

describe("T1.4.4 同步可见性（lastSuccessAt / consecutiveEmptySyncs）", () => {
  it("有上次成功时间 → 渲染本地化时间串，不显示「尚无成功同步」", async () => {
    await renderWith([sub({ lastSuccessAt: "2026-09-21T08:30:00+00:00" })]);
    expect(screen.getByText(/· 上次成功：/)).toBeTruthy();
    expect(screen.queryByText("· 尚无成功同步")).toBeNull();
  });

  it("无上次成功时间 → 诚实显示「尚无成功同步」", async () => {
    await renderWith([sub({ lastSuccessAt: "" })]);
    expect(screen.getByText(/· 尚无成功同步/)).toBeTruthy();
    expect(screen.queryByText(/· 上次成功：/)).toBeNull();
  });

  it("连续空轮询 > 0 → 显示退避提示", async () => {
    await renderWith([sub({ consecutiveEmptySyncs: 3 })]);
    expect(screen.getByText(/· 连续 3 次无新文章/)).toBeTruthy();
  });

  it("连续空轮询为 0 或缺省 → 不显示退避提示（避免噪音）", async () => {
    await renderWith([sub({ consecutiveEmptySyncs: 0 })]);
    expect(screen.queryByText(/连续 .*次无新文章/)).toBeNull();
  });
});

describe("T1.4.3/T1.4.4 任务进度与重试", () => {
  it("无 latestJobId → 显示「等待首次同步」，且轮询不取进度", async () => {
    await renderWith([sub({ latestJobId: "" })]);
    expect(screen.getByText("等待首次同步")).toBeTruthy();

    await firePoll();
    expect(h.getJob).not.toHaveBeenCalled();
  });

  it("轮询返回进度 → 渲染 done/total 篇数与百分比，「等待首次同步」消失", async () => {
    await renderWith([sub({ latestJobId: "job-1" })]);
    expect(screen.getByText("等待首次同步")).toBeTruthy();

    h.getJob.mockResolvedValue(job({ counts: { total: 12, succeeded: 9, failed: 0, pending: 3 } }));
    await firePoll();

    expect(h.getJob).toHaveBeenCalledWith("job-1");
    await waitFor(() => expect(screen.getByText("9/12 篇")).toBeTruthy());
    expect(screen.getByText("75%")).toBeTruthy();
    expect(screen.queryByText("等待首次同步")).toBeNull();
  });

  it("PARTIAL_SUCCESS → 显示「重试失败 N 篇」按钮并回调 retryJob", async () => {
    await renderWith([sub({ latestJobId: "job-1" })]);

    h.getJob.mockResolvedValue(
      job({
        status: "PARTIAL_SUCCESS",
        progress: 90,
        counts: { total: 10, succeeded: 8, failed: 2, pending: 0 },
      })
    );
    h.retryJob.mockResolvedValue({ jobId: "job-1", retried: 2, status: "RUNNING" });
    await firePoll();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /重试失败 2 篇/ })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole("button", { name: /重试失败 2 篇/ }));
    expect(h.retryJob).toHaveBeenCalledWith("job-1");
  });
});
