// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * R0.2.4 —— 空间详情页与文档生命周期入口的接线（页面层）
 *
 * 组件自测只覆盖「点了按钮调了函数」；页面层的风险在于回写是否真的反映到列表与统计：
 * 删除后该行若未摘除、`stats.docs` 若未递减，用户会看到「已删除却还在」的假闭环，
 * 与 F-1（单页 100 条上限）叠加又回到删不动的死锁。本测钉住这两条回写。
 *
 * R0.1.3 起回写方式是**重新拉取第一页**，不是本地改写：服务端分页下本地增删会让
 * 「本页条数 ≠ total」、本地回写 PATCH 值会让清空标签的行显示「其他」直到刷新。
 * 故本测同时钉住「各端点恰好各拉两次（初始 + 操作后）」——既证明回写生效，
 * 也证明没有多余的重复刷新循环。
 *
 * 注意：`useRouter` 必须返回**同一个对象**——页面把 `router` 放进 useEffect 依赖，
 * 若每次渲染新造一个对象会触发无限重渲染。
 */
const h = vi.hoisted(() => ({
  categories: ["AI·技术", "产品·商业", "行业·动态", "观点·评论", "教程·实践", "其他"] as const,
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
  deleteSpaceDoc: vi.fn(),
  patchSpaceDocCategory: vi.fn(),
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
    CATEGORIES: h.categories,
    UNCATEGORIZED: "__uncategorized__",
    BATCH_DOCS_MAX_IDS: 50,
    isAuthError: () => false,
    getSpace: h.getSpace,
    listSpaceDocs: h.listSpaceDocs,
    listSpaceDocCategories: h.listSpaceDocCategories,
    deleteSpaceDoc: h.deleteSpaceDoc,
    patchSpaceDocCategory: h.patchSpaceDocCategory,
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

function article(id: string, title: string, category: string | undefined) {
  return {
    id,
    title,
    source: "公众号A",
    status: "ready",
    updatedAt: "2026-09-22T00:00:00+00:00",
    category,
  } as never;
}

const DOCS = [
  article("doc-1", "文章甲", "AI·技术"),
  article("doc-2", "文章乙", undefined),
];

/** 服务端分页响应包装（total 与 items 同谓词）。 */
function page(items: unknown[]) {
  return { items, total: items.length, limit: 50, offset: 0 };
}

/** 初始各端点各拉一次；返回的 `page` 供操作后重拉时替换。 */
function armInitial(items = DOCS, cats: string[] = ["AI·技术"]) {
  h.getSpace.mockResolvedValue(SPACE);
  h.listSpaceDocs.mockResolvedValue(page(items));
  h.listSpaceDocCategories.mockResolvedValue(cats);
}

async function renderPage() {
  await act(async () => { render(createElement(SpaceDetailPage, { params: Promise.resolve({ id: "sp-1" }) })); });
  return await screen.findByText("文章甲");
}

/** 定位某篇文档所在行（入口按钮与弹窗都渲染在该行内）。 */
function rowOf(title: string): HTMLElement {
  const li = screen.getByText(title).closest("li");
  if (!li) throw new Error(`未找到行：${title}`);
  return li as HTMLElement;
}

/** 该行内的入口按钮（顺序：改分类、删除）。 */
function entryButtons(title: string): HTMLButtonElement[] {
  return Array.from(rowOf(title).querySelectorAll("button")) as HTMLButtonElement[];
}

beforeEach(() => {
  h.getSpace.mockReset();
  h.listSpaceDocs.mockReset();
  h.listSpaceDocCategories.mockReset();
  h.deleteSpaceDoc.mockReset();
  h.patchSpaceDocCategory.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("R0.2.4 空间详情页文档生命周期接线", () => {
  it("每行都有改分类/删除入口（两篇文档 = 两组入口）", async () => {
    armInitial();
    await renderPage();
    expect(screen.getAllByRole("button", { name: "改分类" }).length).toBe(2);
    expect(screen.getAllByRole("button", { name: "删除" }).length).toBe(2);
    expect(entryButtons("文章甲").map((b) => b.textContent)).toEqual(["改分类", "删除"]);
    expect(screen.queryByRole("dialog")).toBeNull();
    // 初始各端点各拉一次
    expect(h.getSpace).toHaveBeenCalledTimes(1);
    expect(h.listSpaceDocs).toHaveBeenCalledTimes(1);
    expect(h.listSpaceDocCategories).toHaveBeenCalledTimes(1);
  });

  it("删除 → 重拉第一页（摘行 + 统计递减），且不整页重载、无重复刷新循环", async () => {
    armInitial();
    h.listSpaceDocs.mockResolvedValueOnce(page(DOCS)).mockResolvedValueOnce(page([DOCS[1]]));
    h.getSpace.mockResolvedValueOnce(SPACE).mockResolvedValueOnce({
      ...SPACE,
      docCount: 1,
      stats: { docs: 1, chunks: 5 },
    });
    await renderPage();
    expect(screen.getByText("2 篇文档")).toBeTruthy();

    h.deleteSpaceDoc.mockResolvedValue({ ok: true, docId: "doc-1", docs: 1, assets: 2 });
    fireEvent.click(entryButtons("文章甲")[1]);
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    expect(h.deleteSpaceDoc).toHaveBeenCalledWith("sp-1", "doc-1");
    // 回写走重拉而非本地摘行（服务端分页下本地摘行会让本页条数 ≠ total）
    await waitFor(() => expect(h.listSpaceDocs).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText("文章甲")).toBeNull());
    expect(screen.queryByRole("dialog")).toBeNull();
    // 统计随服务端返回的删除计数递减
    await waitFor(() => expect(screen.getByText("1 篇文档")).toBeTruthy());
    expect(screen.getByText("文章乙")).toBeTruthy();
    // 恰好各两次：初始 + 删除后，没有重复刷新循环
    expect(h.getSpace).toHaveBeenCalledTimes(2);
    expect(h.listSpaceDocs).toHaveBeenCalledTimes(2);
    expect(h.listSpaceDocCategories).toHaveBeenCalledTimes(2);
  });

  it("改分类 → 重拉后行内分类文案更新、分类集合同步刷新，统计不变", async () => {
    const updated = [DOCS[0], article("doc-2", "文章乙", "观点·评论")];
    armInitial();
    h.listSpaceDocs
      .mockResolvedValueOnce(page(DOCS))
      .mockResolvedValueOnce(page(updated));
    h.listSpaceDocCategories
      .mockResolvedValueOnce(["AI·技术"])
      .mockResolvedValueOnce(["AI·技术", "观点·评论"]);
    await renderPage();
    expect(rowOf("文章乙").textContent).not.toContain("· 观点·评论");

    h.patchSpaceDocCategory.mockResolvedValue({ docId: "doc-2", category: "观点·评论" });
    fireEvent.click(entryButtons("文章乙")[0]);
    await screen.findByRole("dialog");
    // 弹窗内下拉落在该行内（页头另有分类筛选下拉，需按行定位）
    const select = rowOf("文章乙").querySelector("select");
    if (!select) throw new Error("弹窗未渲染下拉");
    fireEvent.change(select, { target: { value: "观点·评论" } });
    fireEvent.click(screen.getByRole("button", { name: "保存分类" }));

    expect(h.patchSpaceDocCategory).toHaveBeenCalledWith("sp-1", "doc-2", "观点·评论");
    // 重拉而非本地回写（本地写回 PATCH 值会让清空标签的行显示「其他」直到刷新）
    await waitFor(() => expect(h.listSpaceDocs).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(rowOf("文章乙").textContent).toContain("· 观点·评论 ·")
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("2 篇文档")).toBeTruthy();
    // 分类集合随操作同步刷新（category 是资产级属性，改写后集合可能变化）
    expect(h.listSpaceDocCategories).toHaveBeenCalledTimes(2);
    expect(h.listSpaceDocs.mock.calls[1][1]).toMatchObject({ offset: 0 });
  });

  it("删除失败 → 该行保留、弹窗不关、错误文案就地可见，且不触发重拉", async () => {
    armInitial();
    await renderPage();
    h.deleteSpaceDoc.mockRejectedValue(new Error("知识空间不存在或已删除"));

    fireEvent.click(entryButtons("文章甲")[1]);
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    await screen.findByText("知识空间不存在或已删除");
    expect(screen.queryByRole("dialog")).not.toBeNull();
    expect(screen.getByText("文章甲")).toBeTruthy();
    expect(screen.getByText("2 篇文档")).toBeTruthy();
    // 失败不重拉（不产生假刷新，也不掩盖失败）
    expect(h.listSpaceDocs).toHaveBeenCalledTimes(1);
    expect(h.getSpace).toHaveBeenCalledTimes(1);
  });
});
