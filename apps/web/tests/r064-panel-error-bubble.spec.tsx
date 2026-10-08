// @vitest-environment happy-dom
/**
 * 添加文章面板：错误气泡的「重试」按钮前置条件
 *
 * 气泡里的重试语义是「重新解析 lastUrl」。批量断点类错误（断点指向的 Job 已 30004
 * 不在后端）此时 lastUrl 为空——按钮若照常渲染，一点就把可操作文案换成一条无关的
 * 「链接形态不合法」，用户反而看不到原因。故仅在有过解析目标时才给按钮。
 *
 * hook 层测不到这个交互（面板此前在全部消费方测试里都被置空），故单独立文件。
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  parse: vi.fn(),
  submit: vi.fn(),
  runBatch: vi.fn(),
  retryBatch: vi.fn(),
  resumeExistingBatch: vi.fn(),
  dismissBatch: vi.fn(),
  dismissCheckpoint: vi.fn(),
  reset: vi.fn(),
  state: {
    phase: "idle",
    preview: null,
    errorMsg: "",
    qualityReasons: [],
    pollSeconds: 0,
    submitError: "",
    lastUrl: "",
    hitCache: false,
    hitCount: 0,
    checkpoint: null,
    batchJob: null,
    batchSubmitting: false,
    batchPolling: false,
    batchRetrying: false,
    batchError: "",
    busy: false,
  },
}));

vi.mock("@/components/add-article/useBatchIngest", () => ({
  useBatchIngest: () => ({
    ...h.state,
    parse: h.parse,
    submit: h.submit,
    runBatch: h.runBatch,
    retryBatch: h.retryBatch,
    resumeExistingBatch: h.resumeExistingBatch,
    dismissBatch: h.dismissBatch,
    dismissCheckpoint: h.dismissCheckpoint,
    reset: h.reset,
  }),
}));

vi.mock("@/lib/api", () => ({
  parseBatchUrls: () => ({ urls: [], rawCount: 0, duplicatedCount: 0 }),
}));

// 三个子件与本测无关，置空以免引入各自的契约依赖
vi.mock("@/components/add-article/BatchProgressList", () => ({ default: () => null }));
vi.mock("@/components/add-article/ParsePreviewCard", () => ({ default: () => null }));
vi.mock("@/components/add-article/SubmitSuccessCard", () => ({ default: () => null }));

import AddArticlePanel from "@/components/AddArticlePanel";

const STALE_JOB_MSG = "上次的批量任务已不存在（可能已过期清理），请重新提交。";

beforeEach(() => {
  vi.clearAllMocks();
  Object.assign(h.state, {
    phase: "idle",
    preview: null,
    errorMsg: "",
    qualityReasons: [],
    pollSeconds: 0,
    submitError: "",
    lastUrl: "",
    hitCache: false,
    hitCount: 0,
    checkpoint: null,
    batchJob: null,
    batchSubmitting: false,
    batchPolling: false,
    batchRetrying: false,
    batchError: "",
    busy: false,
  });
});

function openPanel() {
  render(
    <AddArticlePanel spaceId="sp-1" />
  );
  fireEvent.click(screen.getByRole("button", { name: "添加文章" }));
}

describe("错误气泡的重试前置条件", () => {
  it("批量断点类错误无可解析目标：只提示、不给重试按钮，输入框仍可用", () => {
    h.state.errorMsg = STALE_JOB_MSG;
    h.state.lastUrl = "";

    openPanel();

    expect(screen.getByText(STALE_JOB_MSG)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "重试" })).toBeNull();
    const ta = screen.getByLabelText("文章链接") as HTMLTextAreaElement;
    expect(ta.disabled).toBe(false);
  });

  it("解析错误有目标：给重试按钮，点击打的是上次解析的 URL", () => {
    h.state.errorMsg = "解析失败，请稍后重试";
    h.state.lastUrl = "https://mp.weixin.qq.com/s/abc";

    openPanel();

    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(h.parse).toHaveBeenCalledWith("https://mp.weixin.qq.com/s/abc");
  });
});
