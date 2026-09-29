// @vitest-environment happy-dom
/**
 * R0.6.3 —— useBatchIngest 粘贴解析与提交编排
 *
 * 该编排原内联在 AddArticlePanel（588 行），**零测试覆盖**：全部消费方测试都把面板
 * `vi.mock("@/components/AddArticlePanel", () => ({ default: () => null }))` 置空
 *（见 hit-cache-toast.spec.ts、r026-doc-batch.spec.tsx），状态机因此从未被单测触达。
 * R0.6.3 下沉为 hook 后第一次可测，故本文件锁死的状态转移即原实现的契约
 *（行为不变，仅搬家）。
 *
 * 覆盖的不变式：
 * 1. `busyRef` 单飞守卫——进行中不重入，不重复发请求；
 * 2. 解析产物以 extract 为主、publishTime 由 resolve 兜底；断点写入时机在**成功之后**；
 * 3. 低质 20003 走 qualityReasons 而非 errorMsg，两者严格分流；
 * 4. 重试目标是 `lastUrl`（上次解析用的 URL），与用户当前输入框内容解耦；
 * 5. 单篇入库成功才通知 `onSubmitted` 并清预览断点；失败回预览态且不丢 preview；
 * 6. 批量提交即返后**先落断点再轮询**，首轮轮询返回前展示占位进度，终态才通知刷新；
 *    提交失败无断点可续、清面板态；
 * 7. `batchAbortRef` **原地**置位——卸载后挂起的轮询收敛时不得再调用 `onSubmitted`。
 */
import { createElement, StrictMode } from "react";
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ExtractedArticle, JobView } from "@/lib/api";
import { useBatchIngest } from "@/components/add-article/useBatchIngest";

const URL = "https://mp.weixin.qq.com/s/abc";
const URL2 = "https://mp.weixin.qq.com/s/def";

const h = vi.hoisted(() => ({
  onSubmitted: vi.fn(),
  extractUrl: vi.fn(),
  resolveUrl: vi.fn(),
  getJob: vi.fn(),
  pollDocStatus: vi.fn(),
  readPreviewCheckpoint: vi.fn(),
  readBatchJobCheckpoint: vi.fn(),
  savePreviewCheckpoint: vi.fn(),
  saveBatchJobCheckpoint: vi.fn(),
  clearPreviewCheckpoint: vi.fn(),
  clearBatchJobCheckpoint: vi.fn(),
  submitDoc: vi.fn(),
  submitDocsBatch: vi.fn(),
  retryJob: vi.fn(),
  validateArticleUrl: vi.fn(),
  parseBatchUrls: vi.fn(),
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
  return {
    ApiError,
    clearBatchJobCheckpoint: h.clearBatchJobCheckpoint,
    clearPreviewCheckpoint: h.clearPreviewCheckpoint,
    extractUrl: h.extractUrl,
    getJob: h.getJob,
    isBatchJobTerminal: (status: string) =>
      status === "succeeded" || status === "failed",
    parseBatchUrls: h.parseBatchUrls,
    pollDocStatus: h.pollDocStatus,
    readBatchJobCheckpoint: h.readBatchJobCheckpoint,
    readPreviewCheckpoint: h.readPreviewCheckpoint,
    resolveUrl: h.resolveUrl,
    retryJob: h.retryJob,
    saveBatchJobCheckpoint: h.saveBatchJobCheckpoint,
    savePreviewCheckpoint: h.savePreviewCheckpoint,
    submitDoc: h.submitDoc,
    submitDocsBatch: h.submitDocsBatch,
    validateArticleUrl: h.validateArticleUrl,
  };
});

import { ApiError } from "@/lib/api";

const EXTRACTED: ExtractedArticle = {
  title: "测试文章",
  author: "作者",
  publishTime: "",
  paragraphs: ["正文段落"],
  images: [],
  wordCount: 1200,
  langbotFormat: "markdown",
  qualityScore: 88,
  qualityPassed: true,
  qualityReasons: [],
};

const JOB: JobView = {
  jobId: "job-1",
  type: "batch_ingest",
  status: "succeeded",
  progress: 100,
  error: "",
  counts: { total: 2, succeeded: 2, failed: 0, pending: 0 },
  createdAt: "2026-09-23T00:00:00+00:00",
};

const RESOLVED = {
  title: "元信息标题",
  author: "",
  publishTime: "2026-09-20T00:00:00+08:00",
  content: "",
  url: URL,
  biz: "",
};

function setup(props: { open?: boolean; spaceId?: string; onSubmitted?: () => void } = {}) {
  return renderHook(
    ({
      open,
      spaceId,
      onSubmitted,
    }: {
      open: boolean;
      spaceId: string;
      onSubmitted?: () => void;
    }) => useBatchIngest({ open, spaceId, onSubmitted }),
    {
      initialProps: {
        open: props.open ?? true,
        spaceId: props.spaceId ?? "sp-1",
        onSubmitted: props.onSubmitted ?? h.onSubmitted,
      },
    }
  );
}

/** 跑通一次成功解析，让后续 submit 有 preview 可用 */
async function seedPreview() {
  h.validateArticleUrl.mockReturnValue({ ok: true, url: URL });
  h.resolveUrl.mockResolvedValue(RESOLVED);
  h.extractUrl.mockResolvedValue(EXTRACTED);
  const hook = setup();
  await act(async () => {
    await hook.result.current.parse(URL);
  });
  return hook;
}

beforeEach(() => {
  vi.clearAllMocks();
  h.validateArticleUrl.mockReturnValue({ ok: true, url: URL });
  h.readPreviewCheckpoint.mockReturnValue(null);
  h.readBatchJobCheckpoint.mockReturnValue(null);
  h.getJob.mockResolvedValue(JOB);
  h.parseBatchUrls.mockImplementation((text: string) => {
    const lines = text
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    const urls = Array.from(new Set(lines));
    return { urls, rawCount: lines.length, duplicatedCount: lines.length - urls.length };
  });
  h.pollDocStatus.mockImplementation((_sp: string, _doc: string, opts) => {
    opts?.onTick?.(0);
    return Promise.resolve({ docId: _doc, status: "READY" as const, langbotFileId: "" });
  });
  h.retryJob.mockResolvedValue({ jobId: "job-1", retried: 1, status: "running" });
  h.submitDoc.mockResolvedValue({
    docId: "doc-1",
    title: EXTRACTED.title,
    status: "INDEXED" as const,
    langbotFileId: "",
    taskId: "",
    hitCache: false,
    hitCount: 0,
  });
  h.submitDocsBatch.mockResolvedValue({
    jobId: "job-1",
    status: "running",
    counts: { total: 2, succeeded: 0, failed: 0, pending: 2 },
    reused: false,
    urlCount: 2,
  });
});

describe("R0.6.3 parse：解析预览", () => {
  it("非法 URL 本地拦截：不发请求，错误就地呈现", async () => {
    h.validateArticleUrl.mockReturnValue({
      ok: false,
      code: 10006,
      message: "链接形态不合法",
    });
    const { result } = setup();
    await act(async () => {
      await result.current.parse("http://bad");
    });
    expect(h.resolveUrl).not.toHaveBeenCalled();
    expect(h.extractUrl).not.toHaveBeenCalled();
    expect(result.current.errorMsg).toBe("链接形态不合法");
    expect(result.current.phase).toBe("idle");
    expect(result.current.preview).toBeNull();
    expect(result.current.qualityReasons).toEqual([]);
  });

  it("成功解析：extract 为主、publishTime 由 resolve 兜底，写断点后进预览态", async () => {
    h.resolveUrl.mockResolvedValue(RESOLVED);
    h.extractUrl.mockResolvedValue(EXTRACTED);
    const { result } = setup();
    await act(async () => {
      await result.current.parse(URL);
    });

    expect(h.resolveUrl).toHaveBeenCalledWith(URL);
    expect(h.extractUrl).toHaveBeenCalledWith(URL);
    expect(result.current.phase).toBe("preview");
    expect(result.current.preview?.data.title).toBe("测试文章");
    expect(result.current.preview?.data.publishTime).toBe("2026-09-20T00:00:00+08:00");
    expect(h.savePreviewCheckpoint).toHaveBeenCalledWith("sp-1", URL, {
      title: "测试文章",
      wordCount: 1200,
      qualityScore: 88,
      images: 0,
    });
    expect(result.current.lastUrl).toBe(URL);
    expect(result.current.busy).toBe(false);
  });

  it("extract 自带 publishTime 时不被 resolve 覆盖", async () => {
    h.resolveUrl.mockResolvedValue({ ...RESOLVED, publishTime: "2026-01-01T00:00:00+08:00" });
    h.extractUrl.mockResolvedValue({
      ...EXTRACTED,
      publishTime: "2026-09-01T00:00:00+08:00",
    });
    const { result } = setup();
    await act(async () => {
      await result.current.parse(URL);
    });
    expect(result.current.preview?.data.publishTime).toBe("2026-09-01T00:00:00+08:00");
  });

  it("低质 20003 走 qualityReasons 而非 errorMsg（与 30003 严格分流）", async () => {
    h.extractUrl.mockRejectedValue(new ApiError(20003, "正文过短，质量分不足"));
    h.resolveUrl.mockResolvedValue(RESOLVED);
    const { result } = setup();
    await act(async () => {
      await result.current.parse(URL);
    });
    expect(result.current.qualityReasons).toEqual(["正文过短，质量分不足"]);
    expect(result.current.errorMsg).toBe("");
    expect(result.current.phase).toBe("idle");
    expect(result.current.preview).toBeNull();
  });

  it("非低质错误走 errorMsg，lastUrl 保留供重试", async () => {
    h.extractUrl.mockRejectedValue(new ApiError(20001, "抓取失败"));
    h.resolveUrl.mockResolvedValue(RESOLVED);
    const { result } = setup();
    await act(async () => {
      await result.current.parse(URL);
    });
    expect(result.current.errorMsg).toBe("抓取失败");
    expect(result.current.qualityReasons).toEqual([]);
    expect(result.current.lastUrl).toBe(URL);
  });

  it("busy 单飞守卫：解析进行中不重入", async () => {
    let release!: (v: unknown) => void;
    h.extractUrl.mockReturnValue(
      new Promise((res) => {
        release = res;
      })
    );
    h.resolveUrl.mockResolvedValue(RESOLVED);
    const { result } = setup();
    await act(async () => {
      void result.current.parse(URL);
    });
    await act(async () => {
      await result.current.parse(URL2);
    });
    await act(async () => {
      release(EXTRACTED);
    });
    expect(h.extractUrl).toHaveBeenCalledTimes(1);
    expect(result.current.phase).toBe("preview");
  });
});

describe("R0.6.3 submit：单篇入库", () => {
  it("无 preview 时不提交", async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.submit();
    });
    expect(h.submitDoc).not.toHaveBeenCalled();
    expect(result.current.phase).toBe("idle");
  });

  it("成功入库：轮询至 READY → submitted，清预览断点并通知刷新（仅一次）", async () => {
    const { result } = await seedPreview();
    await act(async () => {
      await result.current.submit();
    });

    expect(h.submitDoc).toHaveBeenCalledWith("sp-1", URL);
    expect(h.pollDocStatus).toHaveBeenCalledWith(
      "sp-1",
      "doc-1",
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    expect(result.current.phase).toBe("submitted");
    expect(h.clearPreviewCheckpoint).toHaveBeenCalledTimes(1);
    expect(result.current.checkpoint).toBeNull();
    expect(h.onSubmitted).toHaveBeenCalledTimes(1);
    expect(result.current.hitCache).toBe(false);
    expect(result.current.hitCount).toBe(0);
    expect(result.current.busy).toBe(false);
  });

  it("提交命中缓存时回传 hitCache/hitCount", async () => {
    const { result } = await seedPreview();
    h.submitDoc.mockResolvedValue({
      docId: "doc-2",
      title: EXTRACTED.title,
      status: "READY" as const,
      langbotFileId: "",
      taskId: "",
      hitCache: true,
      hitCount: 3,
    });
    await act(async () => {
      await result.current.submit();
    });
    expect(result.current.hitCache).toBe(true);
    expect(result.current.hitCount).toBe(3);
  });

  it("轮询秒数经 onTick 回显", async () => {
    const { result } = await seedPreview();
    h.pollDocStatus.mockImplementation((_sp: string, _doc: string, opts) => {
      opts?.onTick?.(5500);
      return Promise.resolve({ docId: _doc, status: "READY" as const, langbotFileId: "" });
    });
    await act(async () => {
      await result.current.submit();
    });
    expect(result.current.pollSeconds).toBe(6);
  });

  it("提交失败 → 回预览态，错误文案落在 submitError，preview 保留可重试", async () => {
    const { result } = await seedPreview();
    h.submitDoc.mockRejectedValue(new ApiError(20002, "入库提交被拒"));
    await act(async () => {
      await result.current.submit();
    });
    expect(result.current.phase).toBe("preview");
    expect(result.current.submitError).toBe("入库提交被拒");
    expect(result.current.preview?.data.title).toBe("测试文章");
    expect(h.onSubmitted).not.toHaveBeenCalled();
    expect(h.clearPreviewCheckpoint).not.toHaveBeenCalled();
    expect(result.current.busy).toBe(false);
  });

  it("轮询期 30003 入库失败 → 同样回预览态且不通知刷新", async () => {
    const { result } = await seedPreview();
    h.pollDocStatus.mockRejectedValue(new Error("30003 入库失败"));
    await act(async () => {
      await result.current.submit();
    });
    expect(result.current.phase).toBe("preview");
    expect(result.current.submitError).toBe("30003 入库失败");
    expect(h.onSubmitted).not.toHaveBeenCalled();
  });
});

describe("R0.6.3 runBatch：批量提交即返 + Job 轮询", () => {
  it("全非法输入不发请求，走既有错误气泡", async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.runBatch("");
    });
    expect(h.submitDocsBatch).not.toHaveBeenCalled();
    expect(result.current.errorMsg).toBe("链接不能为空");
    expect(result.current.batchJob).toBeNull();
    expect(result.current.phase).toBe("idle");
  });

  it("提交成功 → 先落断点再轮询，Job 视图按契约装配", async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.runBatch(`${URL}\n${URL2}`);
    });

    expect(h.submitDocsBatch).toHaveBeenCalledWith("sp-1", [URL, URL2]);
    expect(h.saveBatchJobCheckpoint).toHaveBeenCalledWith({
      spaceId: "sp-1",
      jobId: "job-1",
      urlCount: 2,
    });
    // 断点必须在轮询之前落地（刷新不丢进度）
    const calls = [h.saveBatchJobCheckpoint, h.getJob].map((fn) => fn.mock.invocationCallOrder[0]);
    expect(calls[0]).toBeLessThan(calls[1]);
    expect(h.getJob).toHaveBeenCalledWith("job-1");
    // 占位 Job 视图被后端回传的真实视图覆盖（进度真相在后端，前端不记账）
    expect(result.current.batchJob).toMatchObject({
      urlCount: 2,
      skipped: 0,
      job: {
        jobId: "job-1",
        type: "batch_ingest",
        status: "succeeded",
        progress: 100,
        counts: { total: 2, succeeded: 2, failed: 0, pending: 0 },
      },
    });
    expect(result.current.batchSubmitting).toBe(false);
    expect(result.current.batchPolling).toBe(false);
    expect(h.onSubmitted).toHaveBeenCalledTimes(1);
    expect(result.current.busy).toBe(false);
  });

  it("首轮轮询返回前展示占位进度（提交回传的状态 + progress 0）", async () => {
    let release!: () => void;
    h.getJob.mockReturnValue(
      new Promise((res) => {
        release = () => res(JOB);
      })
    );
    h.submitDocsBatch.mockResolvedValue({
      jobId: "job-1",
      status: "queued",
      counts: { total: 2, succeeded: 0, failed: 0, pending: 2 },
      reused: false,
      urlCount: 2,
    });
    const { result } = setup();
    await act(async () => {
      void result.current.runBatch(`${URL}\n${URL2}`);
    });
    expect(result.current.batchJob?.job).toMatchObject({
      jobId: "job-1",
      type: "batch_ingest",
      status: "queued",
      progress: 0,
    });
    expect(result.current.batchPolling).toBe(true);
    expect(result.current.batchSubmitting).toBe(false);
    expect(h.onSubmitted).not.toHaveBeenCalled();

    await act(async () => {
      release();
    });
    expect(result.current.batchJob?.job?.status).toBe("succeeded");
    expect(result.current.batchPolling).toBe(false);
    expect(h.onSubmitted).toHaveBeenCalledTimes(1);
  });

  it("去重剔除的行数计入 skipped", async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.runBatch(`${URL}\n${URL}\n${URL2}`);
    });
    expect(h.submitDocsBatch).toHaveBeenCalledWith("sp-1", [URL, URL2]);
    expect(result.current.batchJob?.skipped).toBe(1);
  });

  it("提交失败 → 无断点可续：清面板态并进错误气泡，不通知刷新", async () => {
    h.submitDocsBatch.mockRejectedValue(new ApiError(10005, "批量条数超出上限"));
    const { result } = setup();
    await act(async () => {
      await result.current.runBatch(`${URL}\n${URL2}`);
    });
    expect(result.current.batchJob).toBeNull();
    expect(result.current.phase).toBe("idle");
    expect(result.current.errorMsg).toBe("批量条数超出上限");
    expect(h.saveBatchJobCheckpoint).not.toHaveBeenCalled();
    expect(h.onSubmitted).not.toHaveBeenCalled();
    expect(result.current.busy).toBe(false);
  });
});

describe("R0.6.3 retryBatch / dismissBatch", () => {
  async function seedJob() {
    const hook = setup();
    await act(async () => {
      await hook.result.current.runBatch(`${URL}\n${URL2}`);
    });
    return hook;
  }

  it("无 jobId 时重试为空操作", async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.retryBatch();
    });
    expect(h.retryJob).not.toHaveBeenCalled();
  });

  it("重试调用后端 retry 后继续轮询，终态收敛", async () => {
    const { result } = await seedJob();
    h.retryJob.mockClear();
    h.getJob.mockResolvedValue({
      ...JOB,
      status: "failed",
      progress: 50,
      counts: { total: 2, succeeded: 1, failed: 1, pending: 0 },
    });

    await act(async () => {
      await result.current.retryBatch();
    });
    expect(h.retryJob).toHaveBeenCalledWith("job-1");
    expect(result.current.batchRetrying).toBe(false);
    expect(result.current.batchPolling).toBe(false);
    expect(result.current.batchJob?.job?.status).toBe("failed");
  });

  it("重试失败 → 错误文案就地呈现，retrying 回落", async () => {
    const { result } = await seedJob();
    h.retryJob.mockRejectedValue(new ApiError(30002, "任务已终态不可重试"));
    await act(async () => {
      await result.current.retryBatch();
    });
    expect(result.current.batchError).toBe("任务已终态不可重试");
    expect(result.current.batchRetrying).toBe(false);
  });

  it("dismissBatch 清 jobId 断点并复位面板态（不触碰预览态）", async () => {
    const { result } = await seedJob();
    h.clearBatchJobCheckpoint.mockClear();
    await act(async () => {
      result.current.dismissBatch();
    });
    expect(h.clearBatchJobCheckpoint).toHaveBeenCalledTimes(1);
    expect(result.current.batchJob).toBeNull();
    expect(result.current.phase).toBe("idle");
  });
});

describe("R0.6.3 断点恢复：仅同空间生效", () => {
  it("同空间预览断点恢复为横幅态；跨空间不串味", async () => {
    h.readPreviewCheckpoint.mockReturnValue({
      spaceId: "sp-1",
      url: URL,
      savedAt: 1,
      title: "上次的文章",
      wordCount: 800,
      qualityScore: 45,
      images: 2,
    });
    const same = setup();
    await act(async () => {});
    expect(same.result.current.checkpoint?.title).toBe("上次的文章");

    const other = setup({ spaceId: "sp-9" });
    await act(async () => {});
    expect(other.result.current.checkpoint).toBeNull();
  });

  it("批量 Job 断点恢复：装配占位进度并续轮询", async () => {
    h.readBatchJobCheckpoint.mockReturnValue({
      spaceId: "sp-1",
      jobId: "job-7",
      urlCount: 5,
      savedAt: 1,
    });
    h.getJob.mockResolvedValue({ ...JOB, jobId: "job-7" });
    const { result } = setup();
    await act(async () => {});
    expect(result.current.batchJob).toMatchObject({ urlCount: 5, skipped: 0 });
    expect(h.getJob).toHaveBeenCalledWith("job-7");
  });

  it("面板收起时不恢复任何断点", async () => {
    h.readBatchJobCheckpoint.mockReturnValue({
      spaceId: "sp-1",
      jobId: "job-7",
      urlCount: 5,
      savedAt: 1,
    });
    const { result } = setup({ open: false });
    await act(async () => {});
    expect(result.current.batchJob).toBeNull();
    expect(h.getJob).not.toHaveBeenCalled();
  });
});

describe("R0.6.3 断点恢复：中止标记复位与死链收敛", () => {
  it("StrictMode 双执行不复位 aborted 标记时，断点恢复永不发起请求", async () => {
    h.readBatchJobCheckpoint.mockReturnValue({
      spaceId: "sp-1",
      jobId: "job-7",
      urlCount: 5,
      savedAt: 1,
    });
    h.getJob.mockResolvedValue({ ...JOB, jobId: "job-7" });

    // dev 双执行顺序：卸载清理 effect 的 setup→cleanup 先跑（aborted=true），
    // 断点恢复 effect 的二次 setup 后跑。不复位则 pollJobUntilTerminal 在
    // 发请求前短路返回 "aborted"——面板永久「同步中…」、输入框禁用、无任何请求。
    const { result } = renderHook(
      (props: { open: boolean; spaceId: string }) =>
        useBatchIngest({
          open: props.open,
          spaceId: props.spaceId,
          onSubmitted: h.onSubmitted,
        }),
      {
        initialProps: { open: true, spaceId: "sp-1" },
        wrapper: ({ children }) => createElement(StrictMode, null, children),
      }
    );
    await act(async () => {});

    expect(h.getJob).toHaveBeenCalledWith("job-7");
    expect(result.current.batchJob).toMatchObject({ urlCount: 5, skipped: 0 });
    expect(result.current.phase).toBe("idle");
    expect(h.onSubmitted).toHaveBeenCalledTimes(1);
  });

  it("断点指向已不存在的 Job（30004）→ 清断点、回 idle、给可操作文案", async () => {
    h.readBatchJobCheckpoint.mockReturnValue({
      spaceId: "sp-1",
      jobId: "job-gone",
      urlCount: 2,
      savedAt: 1,
    });
    h.getJob.mockRejectedValue(new ApiError(30004, "资源不存在或无权限: job-gone"));

    const { result } = setup();
    await act(async () => {
      // 恢复 effect → resumeBatch → getJob 拒绝 → catch 落态，跨多轮微任务
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(h.getJob).toHaveBeenCalledWith("job-gone");
    expect(h.clearBatchJobCheckpoint).toHaveBeenCalledTimes(1);
    expect(result.current.phase).toBe("idle");
    expect(result.current.batchPolling).toBe(false);
    expect(result.current.batchJob).toBeNull();
    expect(result.current.errorMsg).toContain("请重新提交");
  });
});

describe("B36 父级重渲染不得重放已终态 Job 的轮询", () => {
  it("调用方每次渲染都传新的内联 onSubmitted 时，断点恢复只轮询一次", async () => {
    h.readBatchJobCheckpoint.mockReturnValue({
      spaceId: "sp-1",
      jobId: "job-7",
      urlCount: 5,
      savedAt: 1,
    });
    h.getJob.mockResolvedValue({ ...JOB, jobId: "job-7" });

    // 复刻真实调用方（SpaceDetailPage → SpaceHeaderPanel → AddArticlePanel）：
    // onSubmitted 传的是内联箭头，每次父级渲染都是新引用。
    // 修复前 resumeBatch 的依赖含 onSubmitted → 每次重渲染换引用 → 断点恢复 effect
    // 反复重入 → 终态 Job（首轮即返回、无 5s 间隔）被无限轮询。
    type Props = { onSubmitted?: () => void };
    const { rerender } = renderHook(
      (props: Props) =>
        useBatchIngest({ open: true, spaceId: "sp-1", onSubmitted: props.onSubmitted }),
      // 用 `{} as Props` 而非 `{ onSubmitted: undefined }`：后者会让 TS 把属性推断成
      // 字面量 undefined 类型，rerender 传入真实函数时报 TS2322。
      { initialProps: {} as Props }
    );
    await act(async () => {});
    expect(h.getJob).toHaveBeenCalledTimes(1);

    for (let i = 0; i < 5; i++) {
      rerender({ onSubmitted: () => {} });
      await act(async () => {});
    }
    expect(h.getJob).toHaveBeenCalledTimes(1);
  });
});

describe("R0.6.3 卸载收敛：batchAbortRef 原地置位", () => {
  it("卸载后挂起的轮询收敛不得再调用 onSubmitted（原地置位而非替换引用）", async () => {
    let release!: () => void;
    h.getJob.mockReturnValue(
      new Promise((res) => {
        release = () => res(JOB);
      })
    );
    const hook = setup();
    await act(async () => {
      void hook.result.current.runBatch(`${URL}\n${URL2}`);
    });
    expect(h.getJob).toHaveBeenCalledTimes(1);
    expect(h.onSubmitted).not.toHaveBeenCalled();

    hook.unmount();
    await act(async () => {
      release();
    });

    // 挂起的 getJob 收敛后循环必须终止：不再发第二次轮询，也不通知刷新
    expect(h.getJob).toHaveBeenCalledTimes(1);
    expect(h.onSubmitted).not.toHaveBeenCalled();
  });
});

describe("R0.6.3 reset / dismissCheckpoint", () => {
  it("dismissCheckpoint 清预览断点并从横幅移除", async () => {
    h.readPreviewCheckpoint.mockReturnValue({
      spaceId: "sp-1",
      url: URL,
      savedAt: 1,
      title: "上次的文章",
      wordCount: 800,
      qualityScore: 45,
      images: 2,
    });
    const { result } = setup();
    await act(async () => {});
    expect(result.current.checkpoint).toBeTruthy();
    h.clearPreviewCheckpoint.mockClear();

    await act(async () => {
      result.current.dismissCheckpoint();
    });
    expect(h.clearPreviewCheckpoint).toHaveBeenCalledTimes(1);
    expect(result.current.checkpoint).toBeNull();
  });

  it("reset 复位编排态（预览/错误/命中提示/批量态全清），但不清 jobId 断点", async () => {
    const hook = await seedPreview();
    await act(async () => {
      hook.result.current.reset();
    });
    const s = hook.result.current;
    expect(s.phase).toBe("idle");
    expect(s.preview).toBeNull();
    expect(s.errorMsg).toBe("");
    expect(s.qualityReasons).toEqual([]);
    expect(s.submitError).toBe("");
    expect(s.hitCache).toBe(false);
    expect(s.hitCount).toBe(0);
    expect(s.batchJob).toBeNull();
    expect(s.batchPolling).toBe(false);
    // 面板展开态与输入框归调用方；jobId 断点刻意不清（重新展开仍应续查）
    expect(h.clearBatchJobCheckpoint).not.toHaveBeenCalled();
  });
});
