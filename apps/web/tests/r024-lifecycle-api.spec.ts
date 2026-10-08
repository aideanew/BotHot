import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * R0.2.1~R0.2.3 —— 文档/订阅生命周期写接口的 API 层契约
 *
 * 四个新写函数（`deleteSpaceDoc` / `patchSpaceDocCategory` / `updateSubscription` /
 * `cancelSubscription`）是 F-2 的前端入口，路径与方法错了后端只会回 10005「Not Found」
 * （main.py 把非 5xx 的 HTTPException 一律映射成 10005），渲染层无从分辨。
 * 本测用 stub fetch 直测生产实现，锁定 method + path + body + 信封解包。
 *
 * 口径说明：`lib/api/spaces.ts` 的写函数带 MOCK 分支（演示模式闭环），
 * `lib/api/subscriptions.ts` 整域无 MOCK 分支（整号采集依赖真实 Job 链路），
 * 后者两条约定都用测试钉住，不做约定俗成。
 */

async function importApi(mockEnv?: string) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_MOCK", mockEnv ?? "false");
  return import("@/lib/api");
}

function jsonEnvelope(data: unknown, code = 0): Response {
  return new Response(
    JSON.stringify({ code, message: code === 0 ? "ok" : "请求参数不合法", data, requestId: "req-r024" }),
    { status: code === 0 ? 200 : 422, headers: { "content-type": "application/json" } }
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("R0.2.1 DELETE /spaces/{id}/docs/{docId}", () => {
  it("走 DELETE、路径逐段编码、无请求体", async () => {
    const { deleteSpaceDoc } = await importApi();
    vi.mocked(fetch).mockResolvedValue(
      jsonEnvelope({ ok: true, docId: "doc-1", docs: 1, assets: 2 })
    );

    const r = await deleteSpaceDoc("sp-1", "doc-1");

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/spaces/sp-1/docs/doc-1",
      expect.objectContaining({ method: "DELETE" })
    );
    expect(r).toEqual({ ok: true, docId: "doc-1", docs: 1, assets: 2 });
  });

  it("id 含特殊字符 → encodeURIComponent（不拼坏路径）", async () => {
    const { deleteSpaceDoc } = await importApi();
    vi.mocked(fetch).mockResolvedValue(jsonEnvelope({ ok: true, docId: "d", docs: 1, assets: 0 }));

    await deleteSpaceDoc("sp/1 2", "doc 3");

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/spaces/sp%2F1%202/docs/doc%203",
      expect.any(Object)
    );
  });
});

describe("R0.2.2 PATCH /spaces/{id}/docs/{docId}", () => {
  it("走 PATCH + JSON 体 {category}", async () => {
    const { patchSpaceDocCategory } = await importApi();
    vi.mocked(fetch).mockResolvedValue(jsonEnvelope({ docId: "doc-1", category: "观点·评论" }));

    const r = await patchSpaceDocCategory("sp-1", "doc-1", "观点·评论");

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/spaces/sp-1/docs/doc-1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ category: "观点·评论" }),
      })
    );
    expect(r).toEqual({ docId: "doc-1", category: "观点·评论" });
  });

  it("空串原样提交（= 清空人工标签），不被省略成缺字段", async () => {
    const { patchSpaceDocCategory } = await importApi();
    vi.mocked(fetch).mockResolvedValue(jsonEnvelope({ docId: "doc-1", category: "其他" }));

    await patchSpaceDocCategory("sp-1", "doc-1", "");

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/spaces/sp-1/docs/doc-1",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ category: "" }) })
    );
  });

  it("信封非零 code（如越界分类 10005/422）→ 抛 ApiError 带上原始 code", async () => {
    const { patchSpaceDocCategory, ApiError } = await importApi();
    // mockImplementation 而非 mockResolvedValue：同一 Response 体只能读一次
    vi.mocked(fetch).mockImplementation(() => Promise.resolve(jsonEnvelope(null, 10005)));

    await expect(patchSpaceDocCategory("sp-1", "doc-1", "乱写的分类")).rejects.toBeInstanceOf(
      ApiError
    );
    await expect(patchSpaceDocCategory("sp-1", "doc-1", "x")).rejects.toMatchObject({
      code: 10005,
    });
  });
});

describe("R0.2.3 PATCH /spaces/{id}/subscriptions/{subId}", () => {
  it("走 PATCH + 部分更新体（省略字段 = 不改）", async () => {
    const { updateSubscription } = await importApi();
    vi.mocked(fetch).mockResolvedValue(
      jsonEnvelope({
        subscriptionId: "sub-1",
        syncPolicy: "auto",
        syncIntervalMinutes: 720,
        nextRunAt: "2026-09-22T12:00:00+00:00",
        status: "ACTIVE",
      })
    );

    const r = await updateSubscription("sp-1", "sub-1", { sync_interval_minutes: 720 });

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/spaces/sp-1/subscriptions/sub-1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ sync_interval_minutes: 720 }),
      })
    );
    expect(r.syncIntervalMinutes).toBe(720);
    expect(r.status).toBe("ACTIVE");
  });
});

describe("R0.2.3 DELETE /spaces/{id}/subscriptions/{subId}", () => {
  it("走 DELETE、无请求体，回传软取消视图", async () => {
    const { cancelSubscription } = await importApi();
    vi.mocked(fetch).mockResolvedValue(
      jsonEnvelope({
        subscriptionId: "sub-1",
        syncPolicy: "auto",
        syncIntervalMinutes: 360,
        nextRunAt: "",
        status: "CANCELLED",
        cancelled: true,
      })
    );

    const r = await cancelSubscription("sp-1", "sub-1");

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/spaces/sp-1/subscriptions/sub-1",
      expect.objectContaining({ method: "DELETE" })
    );
    expect(r.status).toBe("CANCELLED");
    expect(r.cancelled).toBe(true);
  });
});

describe("订阅域无 MOCK 分支（整号采集依赖真实 Job 链路）", () => {
  it("MOCK 开关默认开启时，订阅写函数仍走真实 fetch", async () => {
    const { updateSubscription, cancelSubscription, MOCK_ENABLED } = await importApi("true");
    expect(MOCK_ENABLED).toBe(true);
    vi.mocked(fetch).mockImplementation(() =>
      Promise.resolve(
        jsonEnvelope({
          subscriptionId: "sub-1",
          syncPolicy: "auto",
          syncIntervalMinutes: 60,
          nextRunAt: "",
          status: "ACTIVE",
        })
      )
    );

    await updateSubscription("sp-1", "sub-1", { sync_interval_minutes: 60 });
    await cancelSubscription("sp-1", "sub-1");

    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2);
  });
});
