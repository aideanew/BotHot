// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

/**
 * 入库状态拉模式接线（实测缺陷）
 *
 * 提交入库只把文档写到 pending（引擎侧 INDEXED），推进 READY 要靠
 * GET /docs/{id}/status 按篇回写——后端刻意不做请求内长轮询。
 * 此前前端**没有任何调用方**：LangBot 早已 completed，文章仍在列表里
 * 永久显示「采集中」。
 *
 * 钉住三条：
 * 1. 有 pending 就驱动状态回写并刷新列表，转 ready 后呈现「已就绪」；
 * 2. 全部就绪时不发起状态查询（不空转打接口）；
 * 3. 仍 pending 时按周期续查，不会只查一次就放弃。
 */
const h = vi.hoisted(() => ({
  router: {
    replace: vi.fn(),
    push: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
  },
  getSpace: vi.fn(),
  listSpaceDocs: vi.fn(),
  listSpaceDocCategories: vi.fn(),
  getDocIngestStatus: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => h.router,
}));

vi.mock("@/components/AuthContext", () => ({
  useAuth: () => ({
    status: "authed",
    me: null,
    login: () => {},
    logout: async () => {},
    reload: () => {},
  }),
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
    CATEGORIES: ["AI·技术", "产品·商业", "行业·动态", "观点·评论", "教程·实践", "其他"],
    UNCATEGORIZED: "__uncategorized__",
    BATCH_DOCS_MAX_IDS: 50,
    isAuthError: () => false,
    getSpace: h.getSpace,
    listSpaceDocs: h.listSpaceDocs,
    listSpaceDocCategories: h.listSpaceDocCategories,
    getDocIngestStatus: h.getDocIngestStatus,
  };
});

// 详情页其余区块与本测无关，置空以免各自打接口
vi.mock("@/components/AddArticlePanel", () => ({ default: () => null }));
vi.mock("@/components/PublicLibraryPicker", () => ({ default: () => null }));
vi.mock("@/components/EngineSwitcher", () => ({ default: () => null }));
vi.mock("@/components/SubscribeShortcut", () => ({ default: () => null }));

import SpaceDetailPage from "@/app/spaces/[id]/page";

const POLL_MS = 4000;

const SPACE = {
  id: "sp-1",
  name: "我的空间",
  description: "",
  docCount: 1,
  engine: "builtin",
  engineKbId: "lb-1",
  createdAt: "2026-09-01T00:00:00+00:00",
  updatedAt: "2026-09-22T00:00:00+00:00",
  stats: { docs: 1, chunks: 1 },
};

function article(id: string, status: "pending" | "ready" = "ready") {
  return {
    id,
    title: `文章 ${id}`,
    source: "公众号A",
    status,
    updatedAt: "2026-09-22T00:00:00+00:00",
  };
}

function pg(items: unknown[]) {
  return { items, total: items.length, limit: 50, offset: 0 };
}

function ready() {
  return { docId: "", status: "READY", langbotFileId: "f-1" };
}

beforeEach(() => {
  h.getSpace.mockReset();
  h.listSpaceDocs.mockReset();
  h.listSpaceDocCategories.mockReset();
  h.getDocIngestStatus.mockReset();
  h.getSpace.mockResolvedValue(SPACE);
  h.listSpaceDocCategories.mockResolvedValue([]);
  h.getDocIngestStatus.mockResolvedValue(ready());
});

afterEach(() => {
  cleanup();
});

describe("入库状态回写", () => {
  it("pending 驱动状态查询并刷新列表，转 ready 后显示「已就绪」", async () => {
    h.listSpaceDocs
      .mockResolvedValueOnce(pg([article("d-1", "pending")]))
      .mockResolvedValue(pg([article("d-1", "ready")]));

    render(createElement(SpaceDetailPage, { params: { id: "sp-1" } }));

    expect(await screen.findByText("采集中")).toBeTruthy();

    // 竞态说明（2026-09-28）：此处**不可**直接断言 getDocIngestStatus。
    // 「采集中」只证明第二轮 render 完成，而 tick() 的前半段
    // （await Promise.allSettled(...getDocIngestStatus...)）与其后的
    // loadFirstPage 走的是独立微任务链；在慢 runner 上 getDocIngestStatus
    // 可能尚未被调用 → 断言 calls=0。这正是 CI 偶发红的机理。
    // 改为 waitFor 等待该副作用真正发生，断言契约不变、去掉时序假设。
    await waitFor(() =>
      expect(h.getDocIngestStatus).toHaveBeenCalledWith("sp-1", "d-1")
    );
    expect(await screen.findByText("已就绪")).toBeTruthy();
    // 回写后确实重新拉了列表（状态不是前端猜的）
    await waitFor(() => expect(h.listSpaceDocs).toHaveBeenCalledTimes(2));
  });

  it("全部就绪时不发起状态查询（不空转）", async () => {
    h.listSpaceDocs.mockResolvedValue(pg([article("d-1"), article("d-2")]));

    render(createElement(SpaceDetailPage, { params: { id: "sp-1" } }));

    expect(await screen.findByText("文章 d-1")).toBeTruthy();
    await waitFor(() => expect(h.listSpaceDocs).toHaveBeenCalledTimes(1));

    expect(h.getDocIngestStatus).not.toHaveBeenCalled();
  });

  it("仍 pending 则按周期续查，不查一次就放弃", async () => {
    vi.useFakeTimers();
    try {
      h.listSpaceDocs.mockResolvedValue(pg([article("d-9", "pending")]));
      render(createElement(SpaceDetailPage, { params: { id: "sp-1" } }));

      // happy-dom + fake timer：首载 effect 链（getSpace→loadFirstPage→
      // pendingKey 变化→起轮询）需要多轮微任务刷新，固定轮数不可靠
      for (let i = 0; i < 20 && h.getDocIngestStatus.mock.calls.length === 0; i++) {
        await vi.advanceTimersByTimeAsync(0);
      }
      expect(h.getDocIngestStatus).toHaveBeenCalledTimes(1);

      for (let i = 0; i < 3; i++) {
        await vi.advanceTimersByTimeAsync(POLL_MS);
      }
      expect(h.getDocIngestStatus).toHaveBeenCalledTimes(4);
    } finally {
      vi.useRealTimers();
    }
  });
});
