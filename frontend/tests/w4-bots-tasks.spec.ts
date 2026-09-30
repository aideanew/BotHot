// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";

/**
 * W4 4.6a —— /bots「推送任务」Tab 交互不变式
 *
 * 锁四条：
 * 1. **Tab 渲染**：切到「推送任务」后拉取并渲出任务行（死导入已移除，UI 真实消费 API）；
 * 2. **表单联动**：仅 trigger_type=event 时展示事件类型下拉，cron 时展示 CronEditor；
 * 3. **行操作**：立即执行/暂停恢复/删除分别命中 run/toggle(PUT)/delete，且带确认；
 * 4. **服务端 400 透出**：cron 非法时以 createPushTask 抛出的 message 展示，不自造文案。
 */
const h = vi.hoisted(() => ({
  listChannels: vi.fn(),
  listChannelTypes: vi.fn(),
  createChannel: vi.fn(),
  deleteChannel: vi.fn(),
  updateChannel: vi.fn(),
  testPush: vi.fn(),
  listPushLogs: vi.fn(),
  listPushTasks: vi.fn(),
  createPushTask: vi.fn(),
  updatePushTask: vi.fn(),
  deletePushTask: vi.fn(),
  runPushTaskNow: vi.fn(),
}));

vi.mock("@/components/AuthContext", () => ({
  useAuth: () => ({
    status: "authed",
    me: { sub: "u-1", email: "a@a", nickname: "运营", tier: "pro", wallet: "¥0", is_admin: true },
    login: () => {},
    logout: async () => {},
    reload: () => {},
  }),
}));

vi.mock("@/lib/api/bots", () => ({
  listChannels: h.listChannels,
  listChannelTypes: h.listChannelTypes,
  createChannel: h.createChannel,
  deleteChannel: h.deleteChannel,
  updateChannel: h.updateChannel,
  testPush: h.testPush,
  listPushLogs: h.listPushLogs,
  listPushTasks: h.listPushTasks,
  createPushTask: h.createPushTask,
  updatePushTask: h.updatePushTask,
  deletePushTask: h.deletePushTask,
  runPushTaskNow: h.runPushTaskNow,
}));

import BotsPage from "@/app/bots/page";

function channel() {
  return {
    id: "ch-1",
    name: "飞书技术群",
    channel_type: "feishu",
    webhook_url: "https://x",
    has_secret: false,
    extra_config: "{}",
    status: "active",
    user_id: null,
    total_push_count: 0,
    success_push_count: 0,
    created_at: null,
    updated_at: null,
  };
}

function task(over: Record<string, unknown> = {}) {
  return {
    id: "t-1",
    name: "每日速报",
    bot_channel_id: "ch-1",
    trigger_type: "cron",
    cron_expr: "10:00",
    trigger_event: "",
    content_template: "",
    space_id: null,
    next_run_at: null,
    last_run_at: null,
    status: "active",
    created_by: "u-1",
    created_at: null,
    ...over,
  };
}

const paged = <T,>(items: T[]) => ({ items, total: items.length, page: 1, page_size: 20 });

async function openTasksTab() {
  fireEvent.click(screen.getByRole("tab", { name: "推送任务" }));
}

beforeEach(() => {
  h.listChannels.mockResolvedValue(paged([channel()]));
  h.listChannelTypes.mockResolvedValue([]);
  h.listPushTasks.mockResolvedValue(paged([task()]));
  h.listPushLogs.mockResolvedValue(
    paged([
      { id: "l-1", bot_channel_id: "ch-1", push_task_id: "t-1", status: "success", content_preview: "已推送", error_message: "", created_at: null },
      { id: "l-2", bot_channel_id: "ch-1", push_task_id: "other", status: "failed", content_preview: "别的任务", error_message: "boom", created_at: null },
    ]),
  );
  h.createPushTask.mockResolvedValue(task({ id: "t-new" }));
  h.updatePushTask.mockResolvedValue(task());
  h.deletePushTask.mockResolvedValue({ id: "t-1", deleted: true });
  h.runPushTaskNow.mockResolvedValue({ delivered: true, reason: "", channel: "feishu" });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("/bots 推送任务 Tab", () => {
  it("切到 Tab 后拉取并渲出任务行", async () => {
    render(createElement(BotsPage));
    await openTasksTab();
    await waitFor(() => expect(h.listPushTasks).toHaveBeenCalled());
    expect(await screen.findByText("每日速报")).toBeTruthy();
    // cron 人类可读预览出现在触发方式列
    expect(screen.getByText("定时")).toBeTruthy();
    expect(screen.getByText("每天 10:00")).toBeTruthy();
  });

  it("新建表单默认 cron：显示 CronEditor，隐藏事件下拉", async () => {
    render(createElement(BotsPage));
    await openTasksTab();
    fireEvent.click(await screen.findByText("+ 新建任务"));
    expect(await screen.findByLabelText("定时规则预设")).toBeTruthy();
    // 事件类型下拉不出现
    expect(screen.queryByText("事件类型")).toBeNull();
  });

  it("切到 event 触发类型才显示事件下拉（表单联动）", async () => {
    render(createElement(BotsPage));
    await openTasksTab();
    fireEvent.click(await screen.findByText("+ 新建任务"));
    const dialog = await screen.findByText("新建推送任务");
    const modal = dialog.parentElement as HTMLElement;
    // cron 时无事件下拉
    expect(within(modal).queryByText("事件类型")).toBeNull();
    // 选择「事件」radio
    fireEvent.click(within(modal).getByLabelText("事件"));
    await waitFor(() => expect(within(modal).getByText("事件类型")).toBeTruthy());
    expect(within(modal).getByRole("option", { name: "热点更新" })).toBeTruthy();
    // cron 编辑器隐藏
    expect(within(modal).queryByLabelText("定时规则预设")).toBeNull();
  });

  it("立即执行带确认后命中 runPushTaskNow", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true));
    render(createElement(BotsPage));
    await openTasksTab();
    fireEvent.click(await screen.findByText("立即执行"));
    await waitFor(() => expect(h.runPushTaskNow).toHaveBeenCalledWith("t-1"));
    expect(await screen.findByText(/已投递成功/)).toBeTruthy();
  });

  it("暂停走 PUT status=paused", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true));
    render(createElement(BotsPage));
    await openTasksTab();
    fireEvent.click(await screen.findByText("暂停"));
    await waitFor(() =>
      expect(h.updatePushTask).toHaveBeenCalledWith("t-1", { status: "paused" }),
    );
  });

  it("删除带确认后命中 deletePushTask", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true));
    render(createElement(BotsPage));
    await openTasksTab();
    fireEvent.click(await screen.findByText("删除"));
    await waitFor(() => expect(h.deletePushTask).toHaveBeenCalledWith("t-1"));
  });

  it("任务日志按 push_task_id 过滤（复用日志弹窗）", async () => {
    render(createElement(BotsPage));
    await openTasksTab();
    fireEvent.click(await screen.findByText("日志"));
    expect(await screen.findByText("已推送")).toBeTruthy();
    // 非本任务的日志被过滤掉
    expect(screen.queryByText("别的任务")).toBeNull();
  });

  it("cron 非法：展示服务端 400 的 message，不自造文案", async () => {
    h.createPushTask.mockRejectedValueOnce(
      new Error("cron 表达式不合法: 99:99（时/分越界）"),
    );
    render(createElement(BotsPage));
    await openTasksTab();
    fireEvent.click(await screen.findByText("+ 新建任务"));
    const dialog = await screen.findByText("新建推送任务");
    const modal = dialog.parentElement as HTMLElement;
    fireEvent.change(within(modal).getByPlaceholderText("如：每日热点速报"), {
      target: { value: "非法任务" },
    });
    fireEvent.click(within(modal).getByRole("button", { name: "保存" }));
    expect(
      await screen.findByText("cron 表达式不合法: 99:99（时/分越界）"),
    ).toBeTruthy();
  });
});
