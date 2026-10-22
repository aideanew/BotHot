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
  getReadyProbe: vi.fn(),
  putDiscoveryConfig: vi.fn(),
}));

/**
 * 引擎密钥面板要按角色收写面（P-47），所以这里必须给一个可切换的 `useAuth`。
 * 默认 admin——既有那批渲染契约锁的是 admin 态，不该被这条改动牵连。
 */
const AUTH = vi.hoisted(() => ({ isAdmin: true }));
vi.mock("@/components/AuthContext", () => ({
  useAuth: () => ({ status: "authed", me: { is_admin: AUTH.isAdmin } }),
}));

import LivenessPanel from "@/components/admin/LivenessPanel";
import DiscoveryChannelsPanel from "@/components/admin/DiscoveryChannelsPanel";
import PushConsolePanel from "@/components/admin/PushConsolePanel";
import EngineKeysPanel from "@/components/admin/EngineKeysPanel";
import AlertBanner from "@/components/admin/AlertBanner";
import {
  getOpsLiveness,
  listDiscoveryChannels,
  getReadyProbe,
  listEngineKeys,
  listPushChannels,
  putDiscoveryConfig,
} from "@/lib/api/admin-ops";
import { ApiError } from "@/lib/api/types";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  AUTH.isAdmin = true;
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

describe("发现渠道启停（S14b.3.3 的写侧）", () => {
  const row = (name: string, enabled: boolean) => ({
    name,
    description: name,
    implemented: true,
    enabled,
    available: true,
    reason: "",
    contractVerifiedAt: null,
    verifiedScope: "search",
  });

  /** 服务端此刻：a、b 都启用，默认 a */
  const view = () => ({
    channels: [row("a", true), row("b", true)],
    defaultChannel: "a",
    selectionReason: "",
    configuredChannels: ["a", "b"],
  });

  it("取消当前默认渠道后保存，发出的 default 必须跟着换——悬空默认一定被后端 10005 拒", async () => {
    vi.mocked(listDiscoveryChannels).mockResolvedValue(view());
    vi.mocked(listPushChannels).mockResolvedValue([]);
    vi.mocked(putDiscoveryConfig).mockResolvedValue({ enabled: ["b"], default: "b", source: "db" });
    render(<DiscoveryChannelsPanel />);
    await waitFor(() => expect(screen.getByRole("button", { name: "保存启停配置" })).toBeTruthy());

    fireEvent.click(screen.getByLabelText("启用 a")); // 取消的正是当前默认渠道
    fireEvent.click(screen.getByRole("button", { name: "保存启停配置" }));
    // 判的是**发出去的载荷**：select 的 DOM value 会被 options 自动纠正，
    // 只看它就看不见组件 state 里那个悬空默认——上一版这条判据就是这么假绿的。
    await waitFor(() => expect(putDiscoveryConfig).toHaveBeenCalledWith(["b"], "b"));
  });

  it("保存只发 enabled 与 default，成功后重读注册表（勾选是草稿，丸是事实）", async () => {
    vi.mocked(listDiscoveryChannels).mockResolvedValue(view());
    vi.mocked(listPushChannels).mockResolvedValue([]);
    vi.mocked(putDiscoveryConfig).mockResolvedValue({
      enabled: ["a", "b"],
      default: "a",
      source: "db",
    });
    render(<DiscoveryChannelsPanel />);
    await waitFor(() => expect(screen.getByRole("button", { name: "保存启停配置" })).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "保存启停配置" }));
    await waitFor(() => expect(putDiscoveryConfig).toHaveBeenCalledWith(["a", "b"], "a"));
    await waitFor(() => expect(screen.getByText(/下一轮调度生效/)).toBeTruthy());
    expect(listDiscoveryChannels).toHaveBeenCalledTimes(2);
  });

  it("10005 时草稿不丢：一次失败不能吞掉运营刚勾的选择", async () => {
    vi.mocked(listDiscoveryChannels).mockResolvedValue(view());
    vi.mocked(listPushChannels).mockResolvedValue([]);
    vi.mocked(putDiscoveryConfig).mockRejectedValue(
      new ApiError(10005, "渠道未注册：x（可用：a, b）")
    );
    render(<DiscoveryChannelsPanel />);
    await waitFor(() => expect(screen.getByRole("button", { name: "保存启停配置" })).toBeTruthy());

    fireEvent.click(screen.getByLabelText("启用 b"));
    fireEvent.click(screen.getByRole("button", { name: "保存启停配置" }));
    await waitFor(() => expect(screen.getByText(/启停未生效/)).toBeTruthy());
    expect((screen.getByLabelText("启用 b") as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText("启用 a") as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText(/渠道未注册：x/)).toBeTruthy();
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
          keyId: "k-demo-0001",
          registeredBy: "u-9",
          updatedAt: "2026-10-15T06:00:00Z",
        },
      ],
    });
    render(<EngineKeysPanel />);
    await waitFor(() => expect(screen.getByText("k-de…0001")).toBeTruthy());
    expect(screen.queryByText("k-demo-0001")).toBeNull();
    expect(screen.getByText("有登记行")).toBeTruthy();
  });
});

describe("告警状态条（S14b.2.3）", () => {
  /** 一份"依赖全就绪"的 /ready 读数，只有 alerting 由用例决定 */
  const ready = (alerting: "enabled" | "disabled") => ({
    status: "ready" as const,
    checks: {
      postgres: { ok: true, state: "ok" },
      redis: { ok: true, state: "ok" },
      schema: { ok: true, state: "ok" },
    },
    alerting,
  });

  it("依赖就绪但 ALERTING_ENABLED=false ⇒ 画降级并点名环境变量", async () => {
    vi.mocked(getReadyProbe).mockResolvedValue(ready("disabled"));
    render(<AlertBanner />);
    const bar = await screen.findByRole("status");
    expect(bar.querySelector('[data-tone="degraded"]')).toBeTruthy();
    expect(bar.textContent).toContain("ALERTING_ENABLED=false");
    // 告警关着时绝不出现"健康"丸——这一条就是这屏存在的理由（否则关着与开着同形）
    expect(bar.querySelector('[data-tone="ok"]')).toBeNull();
  });

  it("依赖未就绪优先于告警关闭：点名是哪一项、处于什么 state", async () => {
    vi.mocked(getReadyProbe).mockResolvedValue({
      status: "not_ready",
      checks: {
        postgres: { ok: true, state: "ok" },
        redis: { ok: false, state: "unreachable" },
        schema: { ok: true, state: "ok" },
      },
      alerting: "disabled",
    });
    render(<AlertBanner />);
    const bar = await screen.findByRole("status");
    expect(bar.querySelector('[data-tone="bad"]')).toBeTruthy();
    expect(bar.textContent).toContain("依赖未就绪");
    expect(bar.textContent).toContain("Redis（unreachable）");
  });

  it("探针读不到 ⇒ 画「未知」而不是绿：读取失败的处置是 fail-closed", async () => {
    vi.mocked(getReadyProbe).mockRejectedValue(new ApiError(50101, "网络异常，请检查连接后重试"));
    render(<AlertBanner />);
    const bar = await screen.findByRole("status");
    expect(bar.querySelector('[data-tone="unknown"]')).toBeTruthy();
    expect(bar.textContent).toContain("不当作健康");
  });

  it("全就绪且告警已启用 ⇒ 健康；挂载只取一次，新读数靠「重读」", async () => {
    vi.mocked(getReadyProbe).mockResolvedValue(ready("enabled"));
    render(<AlertBanner />);
    const bar = await screen.findByRole("status");
    expect(bar.querySelector('[data-tone="ok"]')).toBeTruthy();
    // /ready 整段只有 4s 预算（PG ping + Redis ping + schema 比对），常驻页面定时轮询等于把探针做成负载源
    expect(getReadyProbe).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "重读" }));
    await waitFor(() => expect(getReadyProbe).toHaveBeenCalledTimes(2));
  });
});

describe("引擎密钥面板的角色门（P-47）", () => {
  /** 一行已登记（轮换 + 停用）、一行未登记（登记），两个角色看到的读面完全相同 */
  const rows = () => ({
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
        keyId: "k-role-0001",
        registeredBy: "u-1",
        updatedAt: "2026-10-22T06:00:00Z",
      },
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

  it("admin：登记 / 轮换 / 停用三个写入口都在", async () => {
    vi.mocked(listEngineKeys).mockResolvedValue(rows());
    render(<EngineKeysPanel />);
    await waitFor(() => expect(screen.getByRole("button", { name: "轮换" })).toBeTruthy());
    expect(screen.getByRole("button", { name: "停用" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "登记" })).toBeTruthy();
    expect(screen.queryByText(/只读/)).toBeNull();
  });

  it("operator：写面全部收起并说明「该找谁」，而不是等点了才拿 10004", async () => {
    AUTH.isAdmin = false;
    vi.mocked(listEngineKeys).mockResolvedValue(rows());
    render(<EngineKeysPanel />);
    await waitFor(() => expect(screen.getByText(/本屏对 operator/)).toBeTruthy());
    expect(screen.queryByRole("button", { name: "登记" })).toBeNull();
    expect(screen.queryByRole("button", { name: "轮换" })).toBeNull();
    expect(screen.queryByRole("button", { name: "停用" })).toBeNull();
    // 读面照常：状态丸与掩码句柄都要在（只读不等于看不见）
    expect(screen.getByText("有登记行")).toBeTruthy();
    expect(screen.getByText("k-ro…0001")).toBeTruthy();
  });
});
