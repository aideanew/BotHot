// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { SubscriptionItem, SubscriptionView } from "@/lib/api";

/**
 * R0.2.4 —— 订阅卡生命周期入口（调整频率 / 退订）
 *
 * F-2 背景：此前订阅只有建与列，整号采集管道建成后「订了就订着」——改不了频率、退不掉。
 * 后端 R0.2.3 已提供 PATCH/DELETE，本测锁定 `SubscriptionLifecycleActions` 的入口语义：
 * - 间隔预设全部落在后端上下界 5~4320 内（越界会被 10005/422 打回）；
 * - 当前间隔不在预设里时补一项「当前」，保证打开即选中现值；
 * - 非整小时的间隔按整除口径展示（90 分钟不得四舍五入成「2 小时」）；
 * - 退订为纯确认（软取消）；已退订订阅两个入口都禁用并提示语义。
 */
const MOCKED = vi.hoisted(() => ({
  updateSubscription: vi.fn(),
  cancelSubscription: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  updateSubscription: MOCKED.updateSubscription,
  cancelSubscription: MOCKED.cancelSubscription,
}));

import SubscriptionLifecycleActions from "@/components/SubscriptionLifecycleActions";

interface Callbacks {
  onChanged: (view: SubscriptionView) => void;
  onCancelled: (view: SubscriptionView) => void;
}

function subscription(overrides: Partial<SubscriptionItem> = {}): SubscriptionItem {
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
  };
}

function renderActions(s: SubscriptionItem, cbs: Callbacks): void {
  render(
    createElement(SubscriptionLifecycleActions, {
      spaceId: "sp-1",
      subscription: s,
      ...cbs,
    })
  );
}

function modalSelect(): HTMLSelectElement {
  const el = document.querySelector("select");
  if (!el) throw new Error("弹窗未渲染下拉");
  return el as HTMLSelectElement;
}

async function openInterval(s: SubscriptionItem, cbs: Callbacks): Promise<void> {
  renderActions(s, cbs);
  fireEvent.click(screen.getByRole("button", { name: "调整频率" }));
  await screen.findByRole("dialog");
}

async function openCancel(s: SubscriptionItem, cbs: Callbacks): Promise<HTMLElement> {
  renderActions(s, cbs);
  fireEvent.click(screen.getByRole("button", { name: "退订" }));
  return await screen.findByRole("dialog");
}

beforeEach(() => {
  MOCKED.updateSubscription.mockReset();
  MOCKED.cancelSubscription.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("R0.2.4 订阅卡生命周期入口", () => {
  it("在订订阅渲染三个入口，无模态无下拉", () => {
    renderActions(subscription(), { onChanged: vi.fn(), onCancelled: vi.fn() });
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "调整频率",
      "定时同步",
      "退订",
    ]);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("下拉初始选中当前间隔（360 分钟 → 每 6 小时）", async () => {
    await openInterval(subscription({ syncIntervalMinutes: 360 }), {
      onChanged: vi.fn(),
      onCancelled: vi.fn(),
    });
    const select = modalSelect();
    expect(select.value).toBe("360");
    expect(select.selectedOptions[0].textContent).toBe("每 6 小时");
  });

  it("预设全部落在后端上下界 5~4320 内，且两端点都在", async () => {
    await openInterval(subscription({ syncIntervalMinutes: 360 }), {
      onChanged: vi.fn(),
      onCancelled: vi.fn(),
    });
    const values = Array.from(modalSelect().options).map((o) => Number(o.value));
    for (const v of values) {
      expect(v).toBeGreaterThanOrEqual(5);
      expect(v).toBeLessThanOrEqual(4320);
    }
    expect(values).toContain(5);
    expect(values).toContain(4320);
  });

  it("当前间隔不在预设里 → 补「当前」项并默认选中，非整小时按整除口径展示", async () => {
    await openInterval(subscription({ syncIntervalMinutes: 90 }), {
      onChanged: vi.fn(),
      onCancelled: vi.fn(),
    });
    const select = modalSelect();
    expect(select.value).toBe("90");
    expect(select.selectedOptions[0].textContent).toBe("当前：每 90 分钟");
    // 90 分钟不得被四舍五入折算成「2 小时」
    expect(screen.getByText(/当前每 90 分钟/)).toBeTruthy();
    expect(screen.queryByText(/当前每 2 小时/)).toBeNull();
  });

  it("改间隔 → PATCH 提交所选分钟数，回调用新视图回写", async () => {
    const onChanged = vi.fn();
    MOCKED.updateSubscription.mockResolvedValue({
      subscriptionId: "sub-1",
      syncPolicy: "auto",
      syncIntervalMinutes: 720,
      nextRunAt: "2026-09-22T12:00:00+00:00",
      status: "ACTIVE",
    });
    await openInterval(subscription({ syncIntervalMinutes: 360 }), {
      onChanged,
      onCancelled: vi.fn(),
    });

    fireEvent.change(modalSelect(), { target: { value: "720" } });
    fireEvent.click(screen.getByRole("button", { name: "保存频率" }));

    await waitFor(() =>
      expect(MOCKED.updateSubscription).toHaveBeenCalledWith("sp-1", "sub-1", {
        sync_interval_minutes: 720,
      })
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(onChanged).toHaveBeenCalledWith(
      expect.objectContaining({ syncIntervalMinutes: 720, status: "ACTIVE" })
    );
  });

  it("改间隔失败 → 错误文案就地展示、弹窗不关、不回写", async () => {
    const onChanged = vi.fn();
    MOCKED.updateSubscription.mockRejectedValue(new Error("请求参数不合法"));
    await openInterval(subscription(), { onChanged, onCancelled: vi.fn() });

    fireEvent.change(modalSelect(), { target: { value: "60" } });
    fireEvent.click(screen.getByRole("button", { name: "保存频率" }));

    await screen.findByText("请求参数不合法");
    expect(screen.queryByRole("dialog")).not.toBeNull();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("调整频率弹窗明示调密方向性（只提前、不推迟逾期同步）", async () => {
    await openInterval(subscription(), { onChanged: vi.fn(), onCancelled: vi.fn() });
    expect(screen.getByText(/调密只会把下次同步提前/)).toBeTruthy();
    expect(screen.getByText(/不会把已逾期的一次同步往后推/)).toBeTruthy();
  });

  it("定时同步下拉 0~23 全量，默认选中 12 点（与后端 default_sync_anchor_hour 一致）", async () => {
    renderActions(subscription(), { onChanged: vi.fn(), onCancelled: vi.fn() });
    fireEvent.click(screen.getByRole("button", { name: "定时同步" }));
    await screen.findByRole("dialog");
    const select = modalSelect();
    expect(select.value).toBe("12");
    expect(select.selectedOptions[0].textContent).toBe("每天 12:00");
    // 全量 24 小时：「每天 7 点」这类非预设需求也能精确选中
    expect(Array.from(select.options).map((o) => Number(o.value))).toEqual(
      Array.from({ length: 24 }, (_, i) => i)
    );
  });

  it("定时同步弹窗明示时区口径与空轮询退避方向", async () => {
    renderActions(subscription(), { onChanged: vi.fn(), onCancelled: vi.fn() });
    fireEvent.click(screen.getByRole("button", { name: "定时同步" }));
    await screen.findByRole("dialog");
    expect(screen.getByText(/北京时间/)).toBeTruthy();
    expect(screen.getByText(/按天往后延/)).toBeTruthy();
  });

  it("设定时 → PATCH 提交所选小时，回调用新视图回写", async () => {
    const onChanged = vi.fn();
    MOCKED.updateSubscription.mockResolvedValue({
      subscriptionId: "sub-1",
      syncPolicy: "auto",
      syncIntervalMinutes: 360,
      syncAnchorHour: 22,
      nextRunAt: "2026-09-26T14:00:00+00:00",
      status: "ACTIVE",
    });
    renderActions(subscription(), { onChanged, onCancelled: vi.fn() });
    fireEvent.click(screen.getByRole("button", { name: "定时同步" }));
    await screen.findByRole("dialog");

    fireEvent.change(modalSelect(), { target: { value: "22" } });
    fireEvent.click(screen.getByRole("button", { name: "保存定时" }));

    await waitFor(() =>
      expect(MOCKED.updateSubscription).toHaveBeenCalledWith("sp-1", "sub-1", {
        sync_anchor_hour: 22,
      })
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(onChanged).toHaveBeenCalledWith(
      expect.objectContaining({ syncAnchorHour: 22, status: "ACTIVE" })
    );
  });

  it("已锚定订阅 → 入口切换为「每天 HH:00 / 恢复间隔 / 退订」，不再提供按间隔调频", async () => {
    renderActions(subscription({ syncAnchorHour: 10 }), {
      onChanged: vi.fn(),
      onCancelled: vi.fn(),
    });
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "每天 10:00",
      "恢复间隔",
      "退订",
    ]);
    expect(screen.queryByRole("button", { name: "调整频率" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "每天 10:00" }));
    await screen.findByRole("dialog");
    expect(modalSelect().value).toBe("10");
  });

  it("恢复间隔 → 显式传 null 清除锚定（省略字段后端视为「不改」，不会清除）", async () => {
    const onChanged = vi.fn();
    MOCKED.updateSubscription.mockResolvedValue({
      subscriptionId: "sub-1",
      syncPolicy: "auto",
      syncIntervalMinutes: 360,
      syncAnchorHour: null,
      nextRunAt: "2026-09-22T14:00:00+00:00",
      status: "ACTIVE",
    });
    renderActions(subscription({ syncAnchorHour: 10 }), { onChanged, onCancelled: vi.fn() });
    fireEvent.click(screen.getByRole("button", { name: "恢复间隔" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog.querySelector("select")).toBeNull();
    expect(screen.getByText(/回到按间隔滑动/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "确认恢复" }));
    await waitFor(() =>
      expect(MOCKED.updateSubscription).toHaveBeenCalledWith("sp-1", "sub-1", {
        sync_anchor_hour: null,
      })
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ syncAnchorHour: null }));
  });

  it("已锚定的已退订订阅 → 三个入口都禁用", () => {
    renderActions(subscription({ status: "CANCELLED", syncAnchorHour: 10 }), {
      onChanged: vi.fn(),
      onCancelled: vi.fn(),
    });
    for (const name of ["每天 10:00", "恢复间隔", "退订"]) {
      expect(screen.getByRole("button", { name }).hasAttribute("disabled")).toBe(true);
    }
  });

  it("退订为纯确认弹窗，确认后回调软取消视图", async () => {
    const onCancelled = vi.fn();
    MOCKED.cancelSubscription.mockResolvedValue({
      subscriptionId: "sub-1",
      syncPolicy: "auto",
      syncIntervalMinutes: 360,
      nextRunAt: "",
      status: "CANCELLED",
      cancelled: true,
    });
    const dialog = await openCancel(subscription(), { onChanged: vi.fn(), onCancelled });
    expect(dialog.querySelector("select")).toBeNull();
    expect(screen.getByText(/退订是软取消/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "确认退订" }));
    await waitFor(() => expect(MOCKED.cancelSubscription).toHaveBeenCalledWith("sp-1", "sub-1"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(onCancelled).toHaveBeenCalledWith(
      expect.objectContaining({ status: "CANCELLED", cancelled: true })
    );
    expect(MOCKED.updateSubscription).not.toHaveBeenCalled();
  });

  it("取消 → 不发请求，弹窗关闭", async () => {
    renderActions(subscription(), { onChanged: vi.fn(), onCancelled: vi.fn() });
    fireEvent.click(screen.getByRole("button", { name: "退订" }));
    await screen.findByRole("dialog");

    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(MOCKED.cancelSubscription).not.toHaveBeenCalled();
  });

  it("已退订订阅 → 三个入口禁用并提示「仅停未来同步」语义", () => {
    renderActions(subscription({ status: "CANCELLED" }), {
      onChanged: vi.fn(),
      onCancelled: vi.fn(),
    });
    expect(screen.getByRole("button", { name: "调整频率" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "定时同步" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "退订" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/已退订（仅停未来同步，已入库内容保留）/)).toBeTruthy();
  });

  it("已退订订阅点击不重开弹窗（按钮禁用态即最终态）", () => {
    renderActions(subscription({ status: "CANCELLED" }), {
      onChanged: vi.fn(),
      onCancelled: vi.fn(),
    });
    fireEvent.click(screen.getByRole("button", { name: "调整频率" }));
    fireEvent.click(screen.getByRole("button", { name: "退订" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
