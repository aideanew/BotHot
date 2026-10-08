// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * R0.1.3 —— 服务端分页与分类枚举接线（F-1 + F-9 前端销账）
 *
 * 三个必须钉住的不变式：
 * 1. **分页是服务端语义**：首屏只取一页，`加载更多` 以「已加载条数」为 offset 追加；
 *    全部载完不再出现加载更多按钮。
 * 2. **分类下拉来自 `:categories` 服务端枚举**，而非当前页数据推导——这是 F-9 的核心：
 *    分页后单页推导会漏掉不在本页的分类（>100 篇时下拉只剩第一页那几个分类）。
 * 3. **页面不做客户端二次过滤**：`category` 只出现在请求参数里，服务端返回什么就渲染什么。
 *
 * 注意：`useRouter` 必须返回**同一个对象**——页面把 `router` 放进 useEffect 依赖，
 * 若每次渲染新造一个对象会触发无限重渲染。
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
  };
});

// 详情页其余区块与本测无关，置空以免各自打接口
vi.mock("@/components/AddArticlePanel", () => ({ default: () => null }));
vi.mock("@/components/PublicLibraryPicker", () => ({ default: () => null }));
vi.mock("@/components/EngineSwitcher", () => ({ default: () => null }));
vi.mock("@/components/SubscribeShortcut", () => ({ default: () => null }));

import SpaceDetailPage from "@/app/spaces/[id]/page";

const SPACE = {
  id: "sp-1",
  name: "我的空间",
  description: "",
  docCount: 2,
  engine: "builtin",
  engineKbId: "lb-1",
  createdAt: "2026-09-01T00:00:00+00:00",
  updatedAt: "2026-09-22T00:00:00+00:00",
  stats: { docs: 2, chunks: 5 },
};

function article(id: string, title: string, category?: string) {
  return {
    id,
    title,
    source: "公众号A",
    status: "ready",
    updatedAt: "2026-09-22T00:00:00+00:00",
    category,
  };
}

/** 分页响应（`total` 与 `items` 同谓词；可显式覆盖 total 以模拟过滤场景）。 */
function pg(items: unknown[], total = items.length) {
  return { items, total, limit: 50, offset: 0 };
}

async function renderPage(docs = [article("d-1", "文章甲", "AI·技术")], total = docs.length) {
  h.getSpace.mockResolvedValue(SPACE);
  h.listSpaceDocs.mockResolvedValue(pg(docs, total));
  h.listSpaceDocCategories.mockResolvedValue(["AI·技术", "__uncategorized__"]);
  await act(async () => { render(createElement(SpaceDetailPage, { params: Promise.resolve({ id: "sp-1" }) })); });
  return await screen.findByText("文章甲");
}

/** 页头分类筛选下拉。 */
function filterSelect(): HTMLSelectElement {
  return screen.getByLabelText("按分类筛选") as HTMLSelectElement;
}

beforeEach(() => {
  h.getSpace.mockReset();
  h.listSpaceDocs.mockReset();
  h.listSpaceDocCategories.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("R0.1.3 服务端分页", () => {
  it("首屏只取一页，加载更多以已加载条数为 offset 追加，载完不再出现按钮", async () => {
    const first = Array.from({ length: 50 }, (_, i) => article(`d-${i}`, `第 ${i + 1} 篇`));
    const second = Array.from(
      { length: 10 },
      (_, i) => article(`d-${50 + i}`, `第 ${51 + i} 篇`)
    );
    h.getSpace.mockResolvedValue(SPACE);
    h.listSpaceDocs
      .mockResolvedValueOnce({ items: first, total: 60, limit: 50, offset: 0 })
      .mockResolvedValueOnce({ items: second, total: 60, limit: 50, offset: 50 });
    h.listSpaceDocCategories.mockResolvedValue([]);
    await act(async () => { render(createElement(SpaceDetailPage, { params: Promise.resolve({ id: "sp-1" }) })); });
    await screen.findByText("第 1 篇");

    // 首屏一页 50 条，没有第 51 篇（服务端没返回就不渲染，不做本地补齐）
    expect(screen.getAllByRole("listitem").length).toBe(50);
    expect(screen.queryByText("第 51 篇")).toBeNull();
    expect(h.listSpaceDocs.mock.calls[0][1]).toMatchObject({ limit: 50, offset: 0 });

    fireEvent.click(screen.getByRole("button", { name: /加载更多/ }));
    await screen.findByText("第 60 篇");

    // offset 由已加载条数推导，不是固定步长
    expect(h.listSpaceDocs.mock.calls[1][1]).toMatchObject({ limit: 50, offset: 50 });
    expect(screen.getAllByRole("listitem").length).toBe(60);
    expect(screen.getByText("已显示全部 60 篇")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /加载更多/ })).toBeNull();
  });

  it("加载更多带当前分类过滤（过滤下的分页与全量同一套 offset 语义）", async () => {
    const first = Array.from({ length: 50 }, (_, i) => article(`d-${i}`, `篇 ${i + 1}`, "AI·技术"));
    const next = Array.from({ length: 50 }, (_, i) =>
      article(`e-${i}`, `篇 ${51 + i}`, "AI·技术")
    );
    h.getSpace.mockResolvedValue(SPACE);
    h.listSpaceDocs
      .mockResolvedValueOnce({ items: first, total: 120, limit: 50, offset: 0 })
      .mockResolvedValueOnce({ items: first, total: 120, limit: 50, offset: 0 })
      .mockResolvedValueOnce({ items: next, total: 120, limit: 50, offset: 50 });
    h.listSpaceDocCategories
      .mockResolvedValueOnce(["AI·技术"])
      .mockResolvedValueOnce(["AI·技术"]);
    await act(async () => { render(createElement(SpaceDetailPage, { params: Promise.resolve({ id: "sp-1" }) })); });
    await screen.findByText("篇 1");

    fireEvent.change(filterSelect(), { target: { value: "AI·技术" } });
    await waitFor(() => expect(h.listSpaceDocs.mock.calls.length).toBe(2));
    expect(h.listSpaceDocs.mock.calls[1][1]).toMatchObject({
      offset: 0,
      category: "AI·技术",
    });

    fireEvent.click(screen.getByRole("button", { name: /加载更多/ }));
    await waitFor(() => expect(h.listSpaceDocs.mock.calls.length).toBe(3));
    expect(h.listSpaceDocs.mock.calls[2][1]).toMatchObject({
      offset: 50,
      category: "AI·技术",
    });
    expect(screen.getAllByRole("listitem").length).toBe(100);
  });
});

describe("R0.1.3 分类下拉来自服务端枚举（F-9）", () => {
  it("选项取自 :categories，含当前页没有的分类与未分类——单页推导做不到这一点", async () => {
    // 当前页只有一篇「AI·技术」，但服务端枚举另有「教程·实践」与未分类
    h.getSpace.mockResolvedValue(SPACE);
    h.listSpaceDocs.mockResolvedValue(
      pg([article("d-1", "文章甲", "AI·技术")], 3)
    );
    h.listSpaceDocCategories.mockResolvedValue([
      "AI·技术",
      "教程·实践",
      "__uncategorized__",
    ]);
    await act(async () => { render(createElement(SpaceDetailPage, { params: Promise.resolve({ id: "sp-1" }) })); });
    await screen.findByText("文章甲");

    expect(
      Array.from(filterSelect().querySelectorAll("option")).map((o) => o.textContent)
    ).toEqual(["全部分类", "AI·技术", "教程·实践", "未分类"]);
  });

  it("空空间 :categories 返空数组 → 不渲染下拉（无 doc 即无「未分类」，不回填哨兵）", async () => {
    h.getSpace.mockResolvedValue(SPACE);
    h.listSpaceDocs.mockResolvedValue(pg([], 0));
    h.listSpaceDocCategories.mockResolvedValue([]);
    await act(async () => { render(createElement(SpaceDetailPage, { params: Promise.resolve({ id: "sp-1" }) })); });
    await screen.findByText(/该空间还没有文章/);
    expect(screen.queryByLabelText("按分类筛选")).toBeNull();
  });

  it("选择分类 → 请求带 category 且 offset 归零；未分类选项发送哨兵值", async () => {
    await renderPage();

    fireEvent.change(filterSelect(), { target: { value: "AI·技术" } });
    await waitFor(() => expect(h.listSpaceDocs.mock.calls.length).toBe(2));
    expect(h.listSpaceDocs.mock.calls[1][1]).toMatchObject({
      offset: 0,
      category: "AI·技术",
    });

    fireEvent.change(filterSelect(), { target: { value: "__uncategorized__" } });
    await waitFor(() => expect(h.listSpaceDocs.mock.calls.length).toBe(3));
    expect(h.listSpaceDocs.mock.calls[2][1]).toMatchObject({
      offset: 0,
      category: "__uncategorized__",
    });
    // 分类集合随操作同步刷新（category 是资产级属性）：初始 1 次 + 两次切换各 1 次
    expect(h.listSpaceDocCategories.mock.calls.length).toBe(3);
  });

  it("不发送空串 category：「全部分类」= 不过滤（空串在服务端语义上等于未分类）", async () => {
    await renderPage();
    const opts = h.listSpaceDocs.mock.calls[0][1] as {
      offset: number;
      category?: string;
    };
    expect(opts.offset).toBe(0);
    expect(opts.category ?? "").toBe("");
  });
});

describe("R0.1.3 无客户端二次过滤", () => {
  it("服务端返回什么就渲染什么——category 只在请求参数里，页面不本地过滤", async () => {
    await renderPage();

    // 故意模拟上游失准：请求了「AI·技术」，返回的却是「教程·实践」
    h.listSpaceDocs.mockResolvedValue(
      pg([article("d-2", "教程篇", "教程·实践")], 1)
    );
    fireEvent.change(filterSelect(), { target: { value: "AI·技术" } });
    await screen.findByText("教程篇");

    // 若页面存在客户端二次过滤，这篇会被过滤掉、只剩空态
    expect(screen.getByText("教程篇")).toBeTruthy();
    expect(screen.queryByText(/分类下暂无文章/)).toBeNull();
    expect(h.listSpaceDocs.mock.calls[1][1]).toMatchObject({ category: "AI·技术" });
  });
});

describe("R0.1.3 空态按 total 判定（分页下本页为空 ≠ 空间为空）", () => {
  it("未过滤且 total=0 → 引导入库文案", async () => {
    h.getSpace.mockResolvedValue(SPACE);
    h.listSpaceDocs.mockResolvedValue(pg([], 0));
    h.listSpaceDocCategories.mockResolvedValue([]);
    await act(async () => { render(createElement(SpaceDetailPage, { params: Promise.resolve({ id: "sp-1" }) })); });
    await screen.findByText(
      "该空间还没有文章，使用上方「添加文章」粘贴公众号链接即可入库。"
    );
    expect(screen.queryByText(/分类下暂无文章/)).toBeNull();
  });

  it("过滤后 total=0 → 指明是哪个分类为空", async () => {
    await renderPage();
    h.listSpaceDocs.mockResolvedValue(pg([], 0));
    fireEvent.change(filterSelect(), { target: { value: "AI·技术" } });
    await screen.findByText("「AI·技术」分类下暂无文章。");
    expect(screen.queryByText(/该空间还没有文章/)).toBeNull();
  });

  it("未分类过滤后 total=0 → 指明是未分类为空", async () => {
    await renderPage();
    h.listSpaceDocs.mockResolvedValue(pg([], 0));
    fireEvent.change(filterSelect(), { target: { value: "__uncategorized__" } });
    await screen.findByText("该空间没有未分类的文章。");
  });
});
