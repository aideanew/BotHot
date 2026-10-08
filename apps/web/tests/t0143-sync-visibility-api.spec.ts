import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * T1.4.3 / T1.4.4（N11）—— 订阅卡「预计篇数 + 同步可见性」字段保真（API 层）
 *
 * 后端 `services/subscription.py:list_subscriptions` 透出四项 N11 字段：
 *   discoveredCount（U6 预计篇数 = ArticleManifest DISCOVERED 计数）
 *   / nextRunAt / lastSuccessAt / consecutiveEmptySyncs（退避可见性）
 * 订阅页 `app/subscriptions/page.tsx:260-267` 据此渲染，进度条另取 `getJob().counts`
 * （total/succeeded/failed/pending，page.tsx:241-242、:290）。
 *
 * 本测锁定 **API 层不丢字段**（解析层若改名/删键，渲染层会静默显示 0 或空态）：
 * stub fetch 直测生产实现，策略同 resolve.spec / t0114，不改生产代码。
 */

async function importRealApi() {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_MOCK", "false");
  return import("@/lib/api");
}

function jsonEnvelope(data: unknown): Response {
  return new Response(
    JSON.stringify({ code: 0, message: "ok", data, requestId: "req-t0143" }),
    { status: 200, headers: { "content-type": "application/json" } }
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("T1.4.3/T1.4.4 订阅列表 N11 字段保真", () => {
  it("四项字段逐字透出（预计篇数 / 下次同步 / 上次成功 / 连续空轮询）", async () => {
    const { listSubscriptions } = await importRealApi();
    vi.mocked(fetch).mockResolvedValue(
      jsonEnvelope({
        items: [
          {
            subscriptionId: "sub-1",
            sourceId: "src-1",
            biz: "MzABC",
            sourceName: "四川自考指南",
            syncPolicy: "auto",
            nextRunAt: "2026-09-22T10:00:00+00:00",
            status: "ACTIVE",
            latestJobId: "job-1",
            lastSuccessAt: "2026-09-21T08:30:00+00:00",
            consecutiveEmptySyncs: 2,
            discoveredCount: 37,
          },
        ],
      })
    );

    const items = await listSubscriptions("sp-1");

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/spaces/sp-1/subscriptions",
      expect.any(Object)
    );
    expect(items).toHaveLength(1);
    expect(items[0].discoveredCount).toBe(37);
    expect(items[0].nextRunAt).toBe("2026-09-22T10:00:00+00:00");
    expect(items[0].lastSuccessAt).toBe("2026-09-21T08:30:00+00:00");
    expect(items[0].consecutiveEmptySyncs).toBe(2);
  });

  it("字段缺省（老数据/老后端）→ 保持 undefined，不臆造 0 或空串", async () => {
    const { listSubscriptions } = await importRealApi();
    vi.mocked(fetch).mockResolvedValue(
      jsonEnvelope({
        items: [
          {
            subscriptionId: "sub-2",
            sourceId: "src-2",
            biz: "MzDEF",
            sourceName: "某号",
            syncPolicy: "auto",
            nextRunAt: "",
            status: "ACTIVE",
          },
        ],
      })
    );

    const [item] = await listSubscriptions("sp-2");

    expect(item).toBeDefined();
    expect(item.nextRunAt).toBe("");
    expect(item.discoveredCount).toBeUndefined();
    expect(item.lastSuccessAt).toBeUndefined();
    expect(item.consecutiveEmptySyncs).toBeUndefined();
  });

  it("spaceId 含特殊字符 → encodeURIComponent 转义（不拼坏路径）", async () => {
    const { listSubscriptions } = await importRealApi();
    vi.mocked(fetch).mockResolvedValue(jsonEnvelope({ items: [] }));

    await listSubscriptions("sp/1 2");

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/spaces/sp%2F1%202/subscriptions",
      expect.any(Object)
    );
  });
});

describe("T1.4.3 进度条数据源 getJob().counts 保真", () => {
  it("counts 四键逐字透出（驱动 done/total 与百分比）", async () => {
    const { getJob } = await importRealApi();
    vi.mocked(fetch).mockResolvedValue(
      jsonEnvelope({
        jobId: "job-1",
        type: "SUBSCRIBE",
        status: "PARTIAL_SUCCESS",
        progress: 80,
        error: "",
        counts: { total: 10, succeeded: 8, failed: 1, pending: 1 },
        createdAt: "2026-09-22T09:00:00+00:00",
      })
    );

    const job = await getJob("job-1");

    expect(job.counts).toEqual({ total: 10, succeeded: 8, failed: 1, pending: 1 });
    expect(job.status).toBe("PARTIAL_SUCCESS");
    expect(vi.mocked(fetch)).toHaveBeenCalledWith("/api/v1/jobs/job-1", expect.any(Object));
  });

  it("信封非零 code → 抛 ApiError（渲染层走错误态而非显示 0/0）", async () => {
    const { getJob, ApiError } = await importRealApi();
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 30004,
          message: "知识空间不存在或已删除",
          data: null,
          requestId: "req-404",
        }),
        { status: 404, headers: { "content-type": "application/json" } }
      )
    );

    await expect(getJob("job-missing")).rejects.toBeInstanceOf(ApiError);
  });
});
