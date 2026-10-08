import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * R0.4.1/R0.4.2 —— 任务域 API 层契约与状态纯函数
 *
 * 与 r024-lifecycle-api 同口径：stub fetch 直测生产实现，锁定 method + path + query + 信封解包。
 * 该域无 MOCK 分支（Job 进度依赖真实后端链路），故 `NEXT_PUBLIC_API_MOCK=false` 强制走真实现。
 *
 * 特别锁住的三条：
 * - 空串 `type`/`status` **不发**——后端对 `?status=` 空串同样视为不过滤，发了会把用户选的
 *   筛选静默变成「全部」（读路径无校验闸门，服务端不会报错，只是数字对不上用户意图）；
 * - `30005` 的进度信息只在 message 里（错误信封无 error-data 通道）；
 * - `jobErrorText` 剥离机器前缀——前缀是给日志检索的，不是给人看的。
 */

async function importApi(mockEnv?: string) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_MOCK", mockEnv ?? "false");
  return import("@/lib/api");
}

function jsonEnvelope(data: unknown, code = 0, message?: string): Response {
  const httpStatus = code === 0 ? 200 : code === 10005 ? 422 : 409;
  return new Response(
    JSON.stringify({
      code,
      message: message ?? (code === 0 ? "ok" : "请求失败"),
      data,
      requestId: "req-r043",
    }),
    { status: httpStatus, headers: { "content-type": "application/json" } }
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("R0.4.1 GET /api/v1/jobs（清单分页）", () => {
  it("默认 limit=50 & offset=0；不发送空的 type/status", async () => {
    const { listJobs } = await importApi();
    vi.mocked(fetch).mockResolvedValue(
      jsonEnvelope({ items: [], total: 0, limit: 50, offset: 0 })
    );

    await listJobs();

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/jobs?limit=50&offset=0",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("带过滤时 type/status 逐段设置", async () => {
    const { listJobs } = await importApi();
    vi.mocked(fetch).mockResolvedValue(
      jsonEnvelope({ items: [], total: 0, limit: 20, offset: 40 })
    );

    await listJobs({ limit: 20, offset: 40, type: "sync_account", status: "RUNNING" });

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/jobs?limit=20&offset=40&type=sync_account&status=RUNNING",
      expect.any(Object)
    );
  });

  it("空串过滤**不发送**——发送 ?status= 会被后端当作「不过滤」，筛选被静默变成全部", async () => {
    const { listJobs } = await importApi();
    vi.mocked(fetch).mockResolvedValue(
      jsonEnvelope({ items: [], total: 0, limit: 50, offset: 0 })
    );

    await listJobs({ type: "", status: "" });

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/jobs?limit=50&offset=0",
      expect.any(Object)
    );
  });

  it("信封 data 原样解包（items/total/limit/offset 四字段）", async () => {
    const { listJobs } = await importApi();
    const page = {
      items: [
        {
          jobId: "j-1",
          type: "batch_ingest",
          status: "QUEUED",
          progress: 0,
          error: "",
          workerHeartbeatAt: "",
          createdAt: "2026-09-23T08:00:00Z",
          updatedAt: "2026-09-23T08:00:00Z",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    };
    vi.mocked(fetch).mockResolvedValue(jsonEnvelope(page));

    expect(await listJobs()).toEqual(page);
  });
});

describe("R0.4.2 POST /api/v1/jobs/{id}/cancel", () => {
  it("走 POST、jobId 逐段编码、无请求体", async () => {
    const { cancelJob } = await importApi();
    vi.mocked(fetch).mockResolvedValue(
      jsonEnvelope({
        jobId: "j a",
        type: "batch_ingest",
        status: "CANCELLED",
        progress: 0,
        error: "cancelled: 用户取消",
        workerHeartbeatAt: "",
        createdAt: "2026-09-23T08:00:00Z",
        updatedAt: "2026-09-23T08:01:00Z",
      })
    );

    await cancelJob("j a");

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/jobs/j%20a/cancel",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("30005 上抛 ApiError，进度只在 message 里（错误信封 data 恒 null）", async () => {
    const { ApiError, cancelJob } = await importApi();
    // 每次调用都新建 Response——同一实例的 body 只能读一次
    vi.mocked(fetch).mockImplementation(
      async () => jsonEnvelope(null, 30005, "任务执行中，无法取消（当前进度 42%）")
    );

    await expect(cancelJob("j-1")).rejects.toMatchObject({ code: 30005 });
    try {
      await cancelJob("j-1");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as InstanceType<typeof ApiError>).message).toContain("42%");
      // 客户端无法从 data 取进度——信封只有 code/message
      expect((e as InstanceType<typeof ApiError>).message).toContain("无法取消");
    }
  });
});

describe("状态 / 类型中文标签与 error 文本（R0.4.3 呈现）", () => {
  it("jobStatusLabel 六态全译；未知取值回落原值，不伪造状态", async () => {
    const { jobStatusLabel } = await importApi();
    expect(jobStatusLabel("QUEUED")).toBe("排队中");
    expect(jobStatusLabel("RUNNING")).toBe("执行中");
    expect(jobStatusLabel("SUCCEEDED")).toBe("已完成");
    expect(jobStatusLabel("PARTIAL_SUCCESS")).toBe("部分成功");
    expect(jobStatusLabel("FAILED")).toBe("失败");
    expect(jobStatusLabel("CANCELLED")).toBe("已取消");
    expect(jobStatusLabel("WEIRD")).toBe("WEIRD");
    expect(jobStatusLabel("")).toBe("");
  });

  it("jobTypeLabel 两型全译；未知回落原值", async () => {
    const { jobTypeLabel } = await importApi();
    expect(jobTypeLabel("batch_ingest")).toBe("批量入库");
    expect(jobTypeLabel("sync_account")).toBe("整号同步");
    expect(jobTypeLabel("future_type")).toBe("future_type");
  });

  it("jobErrorText 剥离 `reason:` 机器前缀，取中文说明段", async () => {
    const { jobErrorText } = await importApi();
    expect(jobErrorText("cancelled: 用户取消")).toBe("用户取消");
    expect(jobErrorText("worker_stale: 心跳超时，已回退 QUEUED 待重入")).toBe(
      "心跳超时，已回退 QUEUED 待重入"
    );
    expect(jobErrorText("all_failed: 3/4 篇失败")).toBe("3/4 篇失败");
  });

  it("无前缀原样返回；无空格冒号不截断；空串回空串（不渲染占位）", async () => {
    const { jobErrorText } = await importApi();
    expect(jobErrorText("清单为空")).toBe("清单为空");
    expect(jobErrorText("a:b:c")).toBe("a:b:c");
    expect(jobErrorText("")).toBe("");
  });
});
