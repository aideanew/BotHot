// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * STEP-14b S14b.3 —— 运维四屏的渲染契约单测。
 *
 * 锁的是"这一屏存在的理由"，不是样式：
 * - 进程从未启动（lastHeartbeatAt=null）必须画成**从未启动**，不能与"心跳卡死"共用一个徽标；
 * - 发现渠道 `defaultChannel=null` 必须显示成"本轮不做发现"，而不是空串；
 * - 推送 `delivered=false` 必须显示"未投递 + 原因"，绝不因为 HTTP 200 就画成成功；
 * - 主密钥未配置时登记/轮换按钮必须禁用并说明原因；Key 句柄只能掩码显示。
 * 三布尔（implemented/enabled/available）不合并，也在此锁住——合并是渲染层最容易"顺手简化"的地方。
 */

vi.mock("@/lib/api/admin-ops", () => ({
  getOpsLiveness: vi.fn(),
  listDiscoveryChannels: vi.fn(),
  listPushChannels: vi.fn(),
  listEngineKeys: vi.fn(),
  registerEngineKey: vi.fn(),
  revokeEngineKey: vi.fn(),
  adminPush: vi.fn(),
}));

import LivenessPanel from "@/components/admin/LivenessPanel";
import DiscoveryChannelsPanel from "@/components/admin/DiscoveryChannelsPanel";
import PushConsolePanel from "@/components/admin/PushConsolePanel";
import EngineKeysPanel from "@/components/admin/EngineKeysPanel";
import {
  getOpsLiveness,
  listDiscoveryChannels,
  listEngineKeys,
  listPushChannels,
} from "@/lib/api/admin-ops";
import { ApiError } from "@/lib/api/types";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("进程存活屏", () => {
  it("lastHeartbeatAt=null 画成「从未启动」，与 stale 卡死分列", async () => {
    vi.mocked(getOpsLiveness).mockResolvedValue({
      processes: [
        {
          processKey: "scheduler",
          purpose: "调度",
          lastHeartbeatAt: null,
          ageSeconds: null,
          stale: true,
          lastDetail: "",
        },
        {
          processKey: "worker",
          purpose: "投递",
          lastHeartbeatAt: "2026-10-15T07:00:00+00:00",
          ageSeconds: 900,
          stale: true,
          lastDetail: "",
        },
      ],
      maxAgeSeconds: 300,
      allHealthy: false,
    });
    render(<LivenessPanel />);
    await waitFor(() => expect(screen.getAllByRole("row").length).toBe(3));
    expect(screen.getByText("从未启动")).toBeTruthy();
    expect(screen.getByText("心跳卡死")).toBeTruthy();
    expect(screen.getByText("从未上报")).toBeTruthy();
    expect(screen.getByText("—")).toBeTruthy();
  });

  it("10004 → 权限不足文案而不是通用失败", async () => {
    vi.mocked(getOpsLiveness).mockRejectedValue(new ApiError(10004, "权限不足", "r1"));
    render(<LivenessPanel />);
    await waitFor(() => expect(screen.getByText(/运维存活需要 operator 以上角色/)).toBeTruthy());
  });
});

describe("发现渠道屏", () => {
  it("defaultChannel=null 显示为「不设默认」，且三布尔各自成徽标", async () => {
    vi.mocked(listDiscoveryChannels).mockResolvedValue({
      channels: [
        {
          name: "tikhub",
          description: "搜索",
          implemented: true,
          enabled: false,
          available: false,
          reason: "缺 TIKHUB_TOKEN",
          contractVerifiedAt: null,
          verifiedScope: "search",
        },
      ],
      defaultChannel: null,
      selectionReason: "无可用渠道",
      configuredChannels: [],
    });
    vi.mocked(listPushChannels).mockResolvedValue([]);
    render(<DiscoveryChannelsPanel />);
    await waitFor(() => expect(screen.getByText(/不设默认，仅做清单 diff/)).toBeTruthy());
    expect(screen.getByText("已实接")).toBeTruthy();
    expect(screen.getByText("未启用")).toBeTruthy();
    expect(screen.getByText("缺凭据")).toBeTruthy();
    expect(screen.getByText(/缺 TIKHUB_TOKEN/)).toBeTruthy();
  });
});

describe("推送终态屏", () => {
  it("200 + delivered=false 必须显示「未投递」和原因，不得显示成功", async () => {
    vi.mocked(listPushChannels).mockResolvedValue([
      { channel: "clawbot", implemented: false, description: "微信 ClawBot" },
    ]);
    vi.mocked(listDiscoveryChannels).mockResolvedValue({
      channels: [],
      defaultChannel: null,
      selectionReason: "",
      configuredChannels: [],
    });
    const { adminPush } = await import("@/lib/api/admin-ops");
    vi.mocked(adminPush).mockResolvedValue({
      ok: false,
      channel: "clawbot",
      delivered: false,
      reason: "通道未实接投递",
    });
    render(<PushConsolePanel />);
    await waitFor(() => expect(screen.getAllByText(/clawbot/).length).toBeGreaterThan(0));
    fireEvent.change(screen.getByPlaceholderText(/渠道侧的接收者标识/), {
      target: { value: "u-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "投递" }));
    await waitFor(() => expect(screen.getByText("未投递")).toBeTruthy());
    expect(screen.getByText(/通道未实接投递/)).toBeTruthy();
    expect(screen.queryByText("已投递")).toBeNull();
  });
});

describe("引擎密钥屏", () => {
  it("masterKeyConfigured=false 时禁用登记按钮并给出原因", async () => {
    vi.mocked(listEngineKeys).mockResolvedValue({
      masterKeyConfigured: false,
      items: [
        {
          engine: "tikhub",
          registered: false,
          configured: false,
          activeSource: "none",
          envConfigured: false,
          decryptFailed: false,
          keyEnv: "TIKHUB_TOKEN",
          keyId: "",
          registeredBy: "",
          updatedAt: "",
        },
      ],
    });
    render(<EngineKeysPanel />);
    await waitFor(() => expect(screen.getByText(/ENGINE_KEY_MASTER_KEY 未配置/)).toBeTruthy());
    const btn = screen.getByRole("button", { name: "登记" });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it("keyId 掩码显示，完整句柄不落到 DOM 文本里", async () => {
    vi.mocked(listEngineKeys).mockResolvedValue({
      masterKeyConfigured: true,
      items: [
        {
          engine: "dajiala",
          registered: true,
          configured: true,
          activeSource: "registered",
          envConfigured: false,
          decryptFailed: false,
          keyEnv: "DAJIALA_TOKEN",
          keyId: "abcd1234efgh5678",
          registeredBy: "u-9",
          updatedAt: "2026-10-15T06:00:00Z",
        },
      ],
    });
    render(<EngineKeysPanel />);
    await waitFor(() => expect(screen.getByText("abcd…5678")).toBeTruthy());
    expect(screen.queryByText("abcd1234efgh5678")).toBeNull();
    expect(screen.getByText("有登记行")).toBeTruthy();
  });
});
