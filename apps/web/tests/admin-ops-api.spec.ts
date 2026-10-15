import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * STEP-15 S15.2.3 / STEP-14b 消费面 —— 管理端运维 API 层契约
 *
 * 与 r043-jobs-api 同口径：stub fetch 直测生产实现，锁定 method + path + query + 信封解包。
 * 该域无 MOCK 分支（伪造跨用户运维数据等于伪造授权面），故强制 `NEXT_PUBLIC_API_MOCK=false`。
 *
 * 五条刻意锁住的语义（都是后端注释里写明的纪律，一旦被前端"顺手简化"就失效）：
 * - `defaultChannel === null` 必须原样保留：null 表示"本轮不做发现"，把 null 当空串渲染
 *   会让用户以为配了渠道却不工作；
 * - `lastHeartbeatAt === null` ≠ 0 秒前：前者是进程从未启动，后者是启动后卡死，处置动作不同；
 * - `implemented/enabled/available` 三个布尔不合并：合并就把"功能没做"和"功能没配"混成一谈；
 * - 推送未就绪时后端回 **200 + delivered=false + reason**，所以 `delivered` 必须被读出来，
 *   "没抛异常"不等于投递成功；
 * - 引擎 Key 明文只允许出现在请求体，不允许进 URL（URL 会进访问日志）。
 */

async function importApi() {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_MOCK", "false");
  return import("@/lib/api");
}

function envelope(data: unknown, code = 0, message = "ok", requestId = "req-ops"): Response {
  return new Response(JSON.stringify({ code, message, data, requestId }), {
    status: code === 0 ? 200 : 403,
    headers: { "content-type": "application/json" },
  });
}

function lastCall(): { url: string; init: RequestInit } {
  const fetchMock = vi.mocked(fetch);
  const call = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
  return { url: String(call[0]), init: (call[1] ?? {}) as RequestInit };
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("引擎 Key 登记", () => {
  it("listEngineKeys 打 GET /admin/engines/keys 并原样回报 masterKeyConfigured", async () => {
    vi.mocked(fetch).mockResolvedValue(
      envelope({ masterKeyConfigured: false, items: [{ engine: "tikhub", registered: false }] })
    );
    const api = await importApi();
    const res = await api.listEngineKeys();
    expect(lastCall().url).toBe("/api/v1/admin/engines/keys");
    // masterKeyConfigured=false 是"登记接口会 50002"的信号，不能被解包层吃掉
    expect(res.masterKeyConfigured).toBe(false);
    expect(res.items).toHaveLength(1);
  });

  it("registerEngineKey：明文只进请求体，不进 URL", async () => {
    vi.mocked(fetch).mockResolvedValue(envelope({ ok: true, keyId: "k-123" }));
    const api = await importApi();
    const res = await api.registerEngineKey("tik hub", "SECRET-PLAINTEXT-VALUE");
    const { url, init } = lastCall();
    expect(init.method).toBe("POST");
    expect(url).toBe("/api/v1/admin/engines/keys/tik%20hub");
    expect(url).not.toContain("SECRET-PLAINTEXT-VALUE");
    expect(JSON.parse(String(init.body))).toEqual({ key: "SECRET-PLAINTEXT-VALUE" });
    expect(res.keyId).toBe("k-123");
  });

  it("revokeEngineKey 用 DELETE（撤销不是 POST 幂等覆盖）", async () => {
    vi.mocked(fetch).mockResolvedValue(envelope({ ok: true }));
    const api = await importApi();
    await api.revokeEngineKey("dajiala");
    expect(lastCall().init.method).toBe("DELETE");
    expect(lastCall().url).toBe("/api/v1/admin/engines/keys/dajiala");
  });
});

describe("渠道就绪度", () => {
  it("listPushChannels 缺 channels 键时回空数组而不是抛错", async () => {
    vi.mocked(fetch).mockResolvedValue(envelope({}));
    const api = await importApi();
    expect(await api.listPushChannels()).toEqual([]);
  });

  it("listDiscoveryChannels 保留 defaultChannel=null 与三布尔不合并", async () => {
    vi.mocked(fetch).mockResolvedValue(
      envelope({
        channels: [
          {
            name: "tikhub",
            description: "搜索",
            implemented: true,
            enabled: false,
            available: true,
            reason: "不在启用白名单",
            contractVerifiedAt: null,
            verifiedScope: "search",
          },
        ],
        defaultChannel: null,
        selectionReason: "无启用渠道",
        configuredChannels: [],
      })
    );
    const api = await importApi();
    const res = await api.listDiscoveryChannels();
    // null 不能被规范化成 ""：UI 要按"本轮不做发现"渲染
    expect(res.defaultChannel).toBeNull();
    const row = res.channels[0];
    expect([row.implemented, row.enabled, row.available]).toEqual([true, false, true]);
    expect(row.reason).toBe("不在启用白名单");
  });
});

describe("常驻进程存活", () => {
  it("不传参时不带 query（让后端用默认阈值）", async () => {
    vi.mocked(fetch).mockResolvedValue(envelope({ processes: [], maxAgeSeconds: 300, allHealthy: false }));
    const api = await importApi();
    await api.getOpsLiveness();
    expect(lastCall().url).toBe("/api/v1/admin/ops/liveness");
  });

  it("传 300 时按 snake_case 查询参数发出", async () => {
    vi.mocked(fetch).mockResolvedValue(envelope({ processes: [], maxAgeSeconds: 300, allHealthy: true }));
    const api = await importApi();
    await api.getOpsLiveness(300);
    expect(lastCall().url).toBe("/api/v1/admin/ops/liveness?max_age_seconds=300");
  });

  it("lastHeartbeatAt=null 与 stale 并存时原样透出（从未启动 ≠ 卡死）", async () => {
    vi.mocked(fetch).mockResolvedValue(
      envelope({
        processes: [
          {
            processKey: "scheduler",
            purpose: "调度",
            lastHeartbeatAt: null,
            ageSeconds: null,
            stale: true,
            lastDetail: "",
          },
        ],
        maxAgeSeconds: 300,
        allHealthy: false,
      })
    );
    const api = await importApi();
    const res = await api.getOpsLiveness();
    expect(res.processes[0].lastHeartbeatAt).toBeNull();
    expect(res.processes[0].ageSeconds).toBeNull();
    expect(res.allHealthy).toBe(false);
  });
});

describe("推送触发回执", () => {
  it("camelCase 入参映射为后端 snake_case，空可选位发空串而不是 undefined", async () => {
    vi.mocked(fetch).mockResolvedValue(envelope({ ok: true, channel: "webhook", delivered: true }));
    const api = await importApi();
    const res = await api.adminPush({ channel: "webhook", externalUserId: "u-1", message: "hi" });
    const { url, init } = lastCall();
    expect(url).toBe("/api/v1/admin/push");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      channel: "webhook",
      external_user_id: "u-1",
      space_id: "",
      doc_id: "",
      message: "hi",
    });
    expect(res.delivered).toBe(true);
  });

  it("200 + delivered=false + reason 不抛异常——回执要能被读出来", async () => {
    vi.mocked(fetch).mockResolvedValue(
      envelope({ ok: false, channel: "clawbot", delivered: false, reason: "通道未实接投递" })
    );
    const api = await importApi();
    const res = await api.adminPush({ channel: "clawbot", externalUserId: "u-1" });
    expect(res.delivered).toBe(false);
    expect(res.reason).toBe("通道未实接投递");
  });

  it("权限不足 10004 归一为 ApiError 并带可展示中文", async () => {
    vi.mocked(fetch).mockResolvedValue(envelope(null, 10004, "Forbidden"));
    const api = await importApi();
    await expect(api.getOpsLiveness()).rejects.toMatchObject({
      code: 10004,
      message: "权限不足",
    });
  });
});
