// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";

/**
 * R0.4.3 —— 任务中心页（/jobs）接线与呈现不变式
 *
 * 锁五条：
 * 1. **CANCELLED 必须渲成「已取消」而非「进行中 0%」**——取消的批量/同步作业
 *    `progress === 0` 且 `counts.failed === 0`，走「进行中」分支会被读成任务卡死；
 * 2. **只有 QUEUED 有取消入口**——RUNNING 与终态后端一律 30005 拒绝；
 * 3. **取消被拒不谎报成功**——30005 的进度只在 message 里（错误信封无 error-data 通道），
 *    且该行必须仍显示原状态；
 * 4. **筛选空结果 ≠ 列表空**（R0.1.4 口径）——两种空态文案必须可分辨；
 * 5. **有非终态才轮询**——全终态自动停，不空转打接口。
 *
 * 请求 mock 用**服务端仿真**（按 limit/offset 切片 + 按 type/status 过滤），与
 * R0.1.3/R0.1.4/R0.2.6 同口径：翻页响应取决于页面发出的 offset，手工排响应序列
 * 无法表达该因果。
 *
 * 行内文案断言一律限定在 `任务列表` 作用域内：筛选下拉的 option 与行内标签同文案，
 * 不限定作用域会命中 option 而非真实呈现。
 */
import type { JobListItem } from "@/lib/api";

const h = vi.hoisted(() => ({
  listJobs: vi.fn(),
  cancelJob: vi.fn(),
  retryJob: vi.fn(),
  getJob: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  // 保留真实标签表 / 终态判定 / ApiError，只把网络函数换掉
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    listJobs: h.listJobs,
    cancelJob: h.cancelJob,
    retryJob: h.retryJob,
    getJob: h.getJob,
  };
});

vi.mock("@/components/AuthContext", () => ({
  useAuth: () => ({
    status: "authed",
    me: null,
    login: () => {},
    logout: async () => {},
  }),
}));

import JobsPage from "@/app/jobs/page";
import { ApiError } from "@/lib/api";

const POLL_MS = 5000;

/** 服务端仿真数据源 */
let rows: JobListItem[] = [];

function job(over: Partial<JobListItem> & { jobId: string }): JobListItem {
  return {
    type: "batch_ingest",
    status: "QUEUED",
    progress: 0,
    error: "",
    workerHeartbeatAt: "",
    createdAt: "2026-09-23T08:00:00Z",
    updatedAt: "2026-09-23T08:00:00Z",
    ...over,
  };
}

/** 列表内查询作用域类型 */
type QM = NonNullable<ReturnType<typeof within>>;

/** 等列表出现，返回其查询作用域（行内文案断言的公共入口） */
async function listScope(): Promise<QM> {
  return within(await screen.findByRole("list", { name: "任务列表" }))!;
}

/** 立即取作用域（找不到即抛）——供 waitFor 内每次重试重新获取：
 *  reload 会让 LoadingErrorShell 换掉整个 <ul> 节点，先前捕获的作用域会变成游离节点。 */
function scope(): QM {
  return within(screen.getByRole("list", { name: "任务列表" }))!;
}

beforeEach(() => {
  rows = [];
  h.listJobs.mockReset();
  h.cancelJob.mockReset();
  h.retryJob.mockReset();
  h.getJob.mockReset();
  h.listJobs.mockImplementation(
    async (opts: {
      limit?: number;
      offset?: number;
      type?: string;
      status?: string;
    } = {}) => {
      const limit = opts.limit ?? 50;
      const offset = opts.offset ?? 0;
      let filtered = rows;
      if (opts.type) filtered = filtered.filter((j) => j.type === opts.type);
      if (opts.status) filtered = filtered.filter((j) => j.status === opts.status);
      return {
        items: filtered.slice(offset, offset + limit),
        total: filtered.length,
        limit,
        offset,
      };
    }
  );
});

afterEach(() => {
  cleanup();
});

describe("R0.4.3 呈现", () => {
  it("列表按中文类型/状态渲染，含总数；终态行无取消入口", async () => {
    rows = [
      job({ jobId: "j-1", status: "SUCCEEDED", progress: 100 }),
      job({
        jobId: "j-2",
        type: "sync_account",
        status: "FAILED",
        error: "all_failed: 3/4 篇失败",
      }),
    ];
    render(<JobsPage />);

    const s = await listScope();
    expect(screen.getByText("共 2 个任务")).toBeTruthy();
    expect(s.getByText("批量入库")).toBeTruthy();
    expect(s.getByText("整号同步")).toBeTruthy();
    expect(s.getByText("已完成")).toBeTruthy();
    expect(s.getByText("失败")).toBeTruthy();
    // error 机器前缀已剥离（给日志检索的 reason: 不进用户视野）
    expect(s.getByText("3/4 篇失败")).toBeTruthy();
    expect(s.queryByText(/all_failed/)).toBeNull();
  });

  it("QUEUED 有取消入口；RUNNING 显示进度且不设取消入口", async () => {
    rows = [
      job({ jobId: "j-queued", status: "QUEUED" }),
      job({
        jobId: "j-run",
        status: "RUNNING",
        progress: 37,
        workerHeartbeatAt: "2026-09-23T08:05:00Z",
      }),
    ];
    render(<JobsPage />);

    expect(await screen.findByRole("button", { name: "取消" })).toBeTruthy();
    const s = await listScope();
    expect(s.getByText("37%")).toBeTruthy();
    expect(s.getByText("执行中")).toBeTruthy();
    // RUNNING 不可取消——后端状态机亦不设 RUNNING→CANCELLED 出边
    expect(screen.getAllByRole("button", { name: "取消" })).toHaveLength(1);
  });

  it("CANCELLED 渲成「已取消」而非「进行中 0%」——回归锁", async () => {
    rows = [
      job({
        jobId: "j-x",
        status: "CANCELLED",
        progress: 0,
        error: "cancelled: 用户取消",
      }),
    ];
    render(<JobsPage />);

    const s = await listScope();
    expect(s.getByText("已取消")).toBeTruthy();
    expect(s.getByText("用户取消")).toBeTruthy();
    // 不得被读成任务卡死
    expect(s.queryByText("执行中")).toBeNull();
    expect(s.queryByText("排队中")).toBeNull();
    expect(screen.queryByRole("button", { name: "取消" })).toBeNull();
    // 取消作业不渲染 RUNNING 进度条
    expect(document.querySelector('[role="progressbar"]')).toBeNull();
  });
});

describe("R0.4.3 取消流程", () => {
  it("确认 → cancelJob(jobId) → 列表刷新为「已取消」", async () => {
    rows = [job({ jobId: "j-q", status: "QUEUED" })];
    render(<JobsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "取消" }));
    expect(screen.getByText("取消这个任务？")).toBeTruthy();

    const cancelled = job({
      jobId: "j-q",
      status: "CANCELLED",
      error: "cancelled: 用户取消",
    });
    h.cancelJob.mockResolvedValueOnce(cancelled);
    rows = [cancelled];

    fireEvent.click(screen.getByRole("button", { name: "确认取消" }));

    expect(h.cancelJob).toHaveBeenCalledWith("j-q");
    await waitFor(() => expect(scope().queryByText("已取消")).not.toBeNull());
    await waitFor(() => {
      expect(screen.queryByText("取消这个任务？")).toBeNull();
      expect(screen.queryByRole("button", { name: "取消" })).toBeNull();
    });
  });

  it("取消被拒（30005，任务已执行中）→ 展示带进度的原因，该行仍显示原状态", async () => {
    rows = [job({ jobId: "j-q", status: "QUEUED" })];
    render(<JobsPage />);

    h.cancelJob.mockRejectedValueOnce(
      new ApiError(30005, "任务执行中，无法取消（当前进度 42%）")
    );
    fireEvent.click(await screen.findByRole("button", { name: "取消" }));
    fireEvent.click(screen.getByRole("button", { name: "确认取消" }));

    const msg = await screen.findByText(/无法取消/);
    expect(msg.textContent).toContain("42%");
    // 不谎报成功：行仍是原状态，取消入口仍在
    await waitFor(() => expect(scope().queryByText("排队中")).not.toBeNull());
    expect(scope().queryByText("已取消")).toBeNull();
  });

  it("点「保留任务」→ 不调用 cancelJob，状态不变", async () => {
    rows = [job({ jobId: "j-q", status: "QUEUED" })];
    render(<JobsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "取消" }));
    fireEvent.click(screen.getByRole("button", { name: "保留任务" }));

    expect(h.cancelJob).not.toHaveBeenCalled();
    await waitFor(() => expect(scope().queryByText("排队中")).not.toBeNull());
    await waitFor(() => {
      expect(screen.queryByText("取消这个任务？")).toBeNull();
    });
  });
});

describe("R0.4.3 过滤与分页", () => {
  it("状态过滤下推服务端；筛选空结果 ≠ 列表空（R0.1.4 口径）", async () => {
    rows = [job({ jobId: "j-1", status: "SUCCEEDED" })];
    render(<JobsPage />);

    await screen.findByText("共 1 个任务");
    fireEvent.change(screen.getByLabelText("状态筛选"), {
      target: { value: "QUEUED" },
    });

    await waitFor(() => {
      expect(h.listJobs).toHaveBeenCalledWith(
        expect.objectContaining({ status: "QUEUED", offset: 0 })
      );
    });
    expect(
      await screen.findByText("没有符合条件的任务——换个筛选条件试试。")
    ).toBeTruthy();
    expect(screen.getByText("共 0 个任务")).toBeTruthy();
    // 不得把「筛不到」误报成「还没有任务」
    expect(screen.queryByText("还没有任务记录。")).toBeNull();
  });

  it("空列表才有「还没有任务记录」", async () => {
    render(<JobsPage />);
    expect(await screen.findByText("还没有任务记录。")).toBeTruthy();
  });

  it("加载更多：offset 由已加载条数推导，追加而非替换", async () => {
    rows = Array.from(
      { length: 120 },
      (_, i) => job({ jobId: `j-${i}`, status: "SUCCEEDED" })
    );
    render(<JobsPage />);

    expect(await screen.findByText("加载更多（已显示 50/120）")).toBeTruthy();
    expect(h.listJobs).toHaveBeenLastCalledWith(
      expect.objectContaining({ offset: 0, limit: 50 })
    );

    fireEvent.click(screen.getByText("加载更多（已显示 50/120）"));
    await waitFor(() => {
      expect(h.listJobs).toHaveBeenLastCalledWith(
        expect.objectContaining({ offset: 50 })
      );
    });
    expect(await screen.findByText("加载更多（已显示 100/120）")).toBeTruthy();

    fireEvent.click(screen.getByText("加载更多（已显示 100/120）"));
    await waitFor(() => {
      expect(h.listJobs).toHaveBeenLastCalledWith(
        expect.objectContaining({ offset: 100 })
      );
    });
    expect(await screen.findByText("共 120 个任务")).toBeTruthy();
    await waitFor(() => {
      expect(screen.queryByText(/加载更多/)).toBeNull();
    });
    const s = await listScope();
    expect(s.getAllByText("已完成")).toHaveLength(120);
  });
});

describe("R0.4.3 轮询纪律", () => {
  // 纯调用次数断言：fake timer 下 `waitFor` 的 setTimeout 也被冻结，等待会永久挂起。
  it("有非终态才轮询（5s）；全部终态自动停，不空转打接口", async () => {
    vi.useFakeTimers();
    try {
      rows = [job({ jobId: "j-run", status: "RUNNING", progress: 12 })];
      render(<JobsPage />);
      await vi.advanceTimersByTimeAsync(0);
      // 首载 1 次（非轮询）
      expect(h.listJobs).toHaveBeenCalledTimes(1);

      // happy-dom: React useEffect（setInterval 注册）需要额外一轮微任务刷新
      await vi.advanceTimersByTimeAsync(0);

      await vi.advanceTimersByTimeAsync(POLL_MS);
      expect(h.listJobs).toHaveBeenCalledTimes(2);

      // 任务到达终态 → 这次轮询拉回终态后停表
      rows = [job({ jobId: "j-run", status: "SUCCEEDED", progress: 100 })];
      await vi.advanceTimersByTimeAsync(POLL_MS);
      expect(h.listJobs).toHaveBeenCalledTimes(3);

      // 停表后继续推进时间，不得再打接口
      await vi.advanceTimersByTimeAsync(POLL_MS * 4);
      expect(h.listJobs).toHaveBeenCalledTimes(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it("初始即全终态（或空列表）→ 只首载一次，不起轮询", async () => {
    vi.useFakeTimers();
    try {
      rows = [job({ jobId: "j-ok", status: "SUCCEEDED", progress: 100 })];
      render(<JobsPage />);
      await vi.advanceTimersByTimeAsync(0);
      expect(h.listJobs).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(POLL_MS * 6);
      expect(h.listJobs).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("R0.4.3 失败重试入口", () => {
  it("只有 FAILED / PARTIAL_SUCCESS 有重试入口；成功与排队任务不设", async () => {
    rows = [
      job({ jobId: "j-failed", status: "FAILED", error: "all_failed: 2/2 篇失败" }),
      job({ jobId: "j-partial", status: "PARTIAL_SUCCESS", progress: 50 }),
      job({ jobId: "j-ok", status: "SUCCEEDED", progress: 100 }),
      job({ jobId: "j-queued", status: "QUEUED" }),
      job({ jobId: "j-run", status: "RUNNING", progress: 12 }),
    ];
    render(<JobsPage />);

    const buttons = await screen.findAllByRole("button", {
      name: "重试失败篇目",
    });
    expect(buttons).toHaveLength(2);
    // 已成功/排队/执行中的任务不存在可重试的失败篇目
    expect(screen.queryByRole("button", { name: /重试中/ })).toBeNull();
  });

  it("点重试 → retryJob(jobId) → 列表刷新为新状态", async () => {
    rows = [job({ jobId: "j-failed", status: "FAILED" })];
    render(<JobsPage />);

    h.retryJob.mockResolvedValueOnce({
      jobId: "j-failed",
      retried: 2,
      status: "QUEUED",
    });
    rows = [job({ jobId: "j-failed", status: "QUEUED" })];

    fireEvent.click(await screen.findByRole("button", { name: "重试失败篇目" }));

    expect(h.retryJob).toHaveBeenCalledWith("j-failed");
    await waitFor(() => expect(scope().queryByText("排队中")).not.toBeNull());
    expect(scope().queryByText("失败")).toBeNull();
    // 已无失败篇目的任务不得再挂重试入口
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "重试失败篇目" })).toBeNull()
    );
  });

  it("没有可重试篇目（retried=0）→ 如实提示，不谎报成功", async () => {
    rows = [job({ jobId: "j-none", status: "FAILED" })];
    render(<JobsPage />);

    h.retryJob.mockResolvedValueOnce({
      jobId: "j-none",
      retried: 0,
      status: "FAILED",
    });
    fireEvent.click(await screen.findByRole("button", { name: "重试失败篇目" }));

    expect(await screen.findByText(/没有可重试的失败篇目/)).toBeTruthy();
    // 失败行仍在，入口仍在
    expect(scope().getByText("失败")).toBeTruthy();
  });

  it("重试被拒（30004，任务不在本人名下）→ 展示原因", async () => {
    rows = [job({ jobId: "j-x", status: "FAILED" })];
    render(<JobsPage />);

    h.retryJob.mockRejectedValueOnce(new ApiError(30004, "资源不存在"));
    fireEvent.click(await screen.findByRole("button", { name: "重试失败篇目" }));

    expect(await screen.findByText(/不在你的名下/)).toBeTruthy();
  });

  it("展开明细按需拉 getJob，展示篇目计数与失败原因（机器前缀不进视野）", async () => {
    rows = [job({ jobId: "j-detail", status: "PARTIAL_SUCCESS", progress: 50 })];
    render(<JobsPage />);

    h.getJob.mockResolvedValueOnce({
      jobId: "j-detail",
      type: "batch_ingest",
      status: "PARTIAL_SUCCESS",
      progress: 50,
      error: "",
      counts: { total: 2, succeeded: 1, failed: 1, pending: 0 },
      failedItems: [
        {
          itemId: "i-1",
          url: "https://mp.weixin.qq.com/s/abc",
          error: "20003 EXTRACT_QUALITY_LOW: 质量分 40 低于阈值",
          retryCount: 1,
        },
      ],
      createdAt: "2026-09-23T08:00:00Z",
    });

    expect(h.getJob).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: "查看篇目明细" }));

    expect(h.getJob).toHaveBeenCalledWith("j-detail");
    expect(await screen.findByText(/共 2 篇/)).toBeTruthy();
    expect(screen.getByText(/成功 1/)).toBeTruthy();
    const url = screen.getByRole("link", {
      name: "https://mp.weixin.qq.com/s/abc",
    });
    expect(url.getAttribute("href")).toBe("https://mp.weixin.qq.com/s/abc");
    expect(screen.getByText(/质量分 40 低于阈值/)).toBeTruthy();
    expect(screen.getByText(/已重试 1 次/)).toBeTruthy();
    // 给日志检索用的 reason 前缀不进用户视野
    expect(screen.queryByText(/EXTRACT_QUALITY_LOW/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "收起明细" }));
    await waitFor(() =>
      expect(screen.queryByText(/共 2 篇/)).toBeNull()
    );
  });

  it("明细缺失字段（旧后端镜像）→ 按空数组降级，不报错", async () => {
    rows = [job({ jobId: "j-legacy", status: "FAILED" })];
    render(<JobsPage />);

    h.getJob.mockResolvedValueOnce({
      jobId: "j-legacy",
      type: "batch_ingest",
      status: "FAILED",
      progress: 0,
      error: "",
      counts: { total: 3, succeeded: 0, failed: 3, pending: 0 },
      createdAt: "2026-09-23T08:00:00Z",
    });

    fireEvent.click(await screen.findByRole("button", { name: "查看篇目明细" }));

    expect(await screen.findByText(/共 3 篇/)).toBeTruthy();
    expect(screen.getByText(/有失败篇目但未记录原因/)).toBeTruthy();
  });
});
