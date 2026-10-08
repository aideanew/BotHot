// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * R0.1.4 —— 大空间回归锁定：>100 篇时分类仍可完整选择（F-1 + F-9 的原始缺陷形态）
 *
 * F-1 的原始形态是两件事叠加：
 * 1. 下拉选项由**当前页**数据推导 → 空间有 150 篇时，下拉只看得见首页那几个分类，
 *    后页才有的分类根本无从选择（「仍可完整选择」的字面要求）。
 * 2. 客户端二次过滤作用在**当前页**上 → 选了个首页没有的分类，过滤结果为空，
 *    空态于是显示「该空间还没有文章」，把一个 150 篇的空间报成空的。
 *
 * R0.1.3 之后的正确口径：下拉取自 `GET /docs:categories` 的服务端枚举，分页深度与
 * 已加载条数都不影响它；空态判据在分页下等价于 `total`。本测用真实量级数据钉住这两点。
 *
 * **未沿用大纲锚点建议的 t0143「按间隔分流 setInterval 桩」**：本页面渲染树内没有
 * setInterval（全仓仅 `app/subscriptions/page.tsx` 使用；`AddArticlePanel` 用的是
 * setTimeout 且本测将其置空），加该桩是死代码。理由已落档。
 *
 * 请求 mock 用**服务端仿真**（按请求的 offset/category 切片，`total` 与 `items` 同谓词），
 * 而非手工排响应序列：翻页场景下响应取决于页面发出的 offset，仿真让因果链与真实一致，
 * 请求形状仍由 `mock.calls` 断言锁住。
 */
const { UNCAT, h } = vi.hoisted(() => ({
  /** 与后端 `categorizer.UNCATEGORIZED` 同值；须 hoisted，mock 工厂在 import 解析期即执行 */
  UNCAT: "__uncategorized__" as const,
  h: {
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
  },
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
    UNCATEGORIZED: UNCAT,
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

/** 页面 PAGE_SIZE：首屏 50 条。 */
const PAGE_SIZE = 50;

/** 只出现在首页的分类。 */
const CATS_PAGE1 = ["AI·技术", "产品·商业"] as const;
/** 只出现在首页之后的分类（第 2 页起）。 */
const CATS_DEEP = ["行业·动态", "教程·实践", "其他"] as const;

/** 服务端枚举全量返回（按规则版声明序，未分类哨兵置末）。 */
const ALL_CATEGORIES = [
  "AI·技术",
  "产品·商业",
  "行业·动态",
  "教程·实践",
  "其他",
  UNCAT,
];

const SPACE = {
  id: "sp-1",
  name: "大空间",
  description: "",
  docCount: 150,
  engine: "builtin",
  engineKbId: "lb-1",
  createdAt: "2026-09-01T00:00:00+00:00",
  updatedAt: "2026-09-22T00:00:00+00:00",
  stats: { docs: 150, chunks: 900 },
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

/** 150 篇：首页 50 篇只含 2 类；后 100 篇才出现深部分类与未分类。 */
function docs150() {
  // 标题用全局序号，与 offset 直观对应：首屏 = 第 1~50 篇，第 2 页 = 第 51~100 篇
  const first = Array.from({ length: PAGE_SIZE }, (_, i) =>
    article(`d-${String(i).padStart(3, "0")}`, `第 ${i + 1} 篇`, CATS_PAGE1[i % 2])
  );
  const rest = Array.from({ length: 100 }, (_, i) => {
    const n = PAGE_SIZE + i;
    // 每 7 篇留 1 篇无分类，保证「未分类」在数据中真实存在
    const category = n % 7 === 0 ? undefined : CATS_DEEP[(i + 1) % 3];
    return article(`d-${String(n).padStart(3, "0")}`, `第 ${n + 1} 篇`, category);
  });
  return [...first, ...rest];
}

const ALL_DOCS = docs150();

/** 按分类过滤（哨兵 = 无分类）。 */
function ofCategory(category?: string) {
  if (!category) return ALL_DOCS;
  if (category === UNCAT) return ALL_DOCS.filter((d) => !d.category);
  return ALL_DOCS.filter((d) => (d.category ?? "") === category);
}

/** 服务端仿真：按请求切片，`total` 与 `items` 同谓词。 */
function armServer() {
  h.listSpaceDocs.mockImplementation(
    (_id: string, opts: { limit?: number; offset?: number; category?: string } = {}) => {
      const limit = opts.limit ?? 100;
      const offset = opts.offset ?? 0;
      const all = ofCategory(opts.category);
      return Promise.resolve({
        items: all.slice(offset, offset + limit),
        total: all.length,
        limit,
        offset,
      });
    }
  );
}

function lastOpts(): { offset: number; category?: string } {
  const calls = h.listSpaceDocs.mock.calls;
  const last = calls[calls.length - 1][1];
  if (!last) throw new Error("listSpaceDocs 未收到 opts");
  return last as { offset: number; category?: string };
}

async function renderLargeSpace() {
  h.getSpace.mockResolvedValue(SPACE);
  armServer();
  h.listSpaceDocCategories.mockResolvedValue(ALL_CATEGORIES);
  render(createElement(SpaceDetailPage, { params: { id: "sp-1" } }));
  return await screen.findByText("第 1 篇");
}

function filterSelect(): HTMLSelectElement {
  return screen.getByLabelText("按分类筛选") as HTMLSelectElement;
}

function optionTexts(): string[] {
  return Array.from(filterSelect().querySelectorAll("option")).map(
    (o) => o.textContent
  );
}

function selectCategory(value: string) {
  fireEvent.change(filterSelect(), { target: { value } });
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

describe("R0.1.4 大空间分类完整性（F-1 + F-9 原始缺陷形态）", () => {
  it("150 篇时空下拉仍完整：选项含首页根本没有的分类与未分类", async () => {
    await renderLargeSpace();

    // 首屏只有 50 条（后 100 条服务端没返回，不做本地补齐）
    expect(screen.getAllByRole("listitem").length).toBe(PAGE_SIZE);

    // 首页只含 AI·技术 / 产品·商业，但下拉必须有全量 6 类 + 全部分类
    expect(optionTexts()).toEqual([
      "全部分类",
      "AI·技术",
      "产品·商业",
      "行业·动态",
      "教程·实践",
      "其他",
      "未分类",
    ]);
  });

  it("加载更多不改变下拉集合，也不重取分类枚举", async () => {
    await renderLargeSpace();
    const before = optionTexts();

    fireEvent.click(screen.getByRole("button", { name: /加载更多/ }));
    await screen.findByText("第 51 篇");

    // 下拉集合与加载前逐字相同——不因已加载条数增长而重算
    expect(optionTexts()).toEqual(before);
    expect(screen.getAllByRole("listitem").length).toBe(PAGE_SIZE * 2);
    // 翻页 offset 由已加载条数推导；未过滤态在 API 层传空串
    //（由 listSpaceDocs 负责不把空串写进 URL，见 r013 同主题测试）
    expect(lastOpts()).toMatchObject({ offset: PAGE_SIZE, category: "" });
    // 分类枚举只取一次：翻页不重取，也不由已加载数据重算
    expect(h.listSpaceDocCategories).toHaveBeenCalledTimes(1);
  });

  it("能选中只存在于第 2 页的分类，offset 归零且返回该分类的行", async () => {
    await renderLargeSpace();
    const deep = ofCategory("行业·动态");
    expect(deep.length).toBeGreaterThan(0);

    selectCategory("行业·动态");
    await screen.findByText(deep[0].title);

    expect(lastOpts()).toMatchObject({ offset: 0, category: "行业·动态" });
    // 全部渲染行都属于该分类，且不包含首页才有的分类
    expect(screen.getAllByRole("listitem").length).toBe(deep.length);
    // 页头计数显示过滤后的 total，而非空间全量 150
    expect(screen.getByText(`共 ${deep.length} 篇`)).toBeTruthy();
    expect(screen.queryByText("已入库内容")).toBeNull();
  });
});

describe("R0.1.4 空态不得误报（客户端过滤时代的核心错报）", () => {
  it("150 篇的空间选了个空的分类 → 指明分类为空，不得报成「该空间还没有文章」", async () => {
    await renderLargeSpace();
    // 故意让该分类在服务端为空（其余分类不受影响）
    h.listSpaceDocs.mockImplementationOnce(() =>
      Promise.resolve({ items: [], total: 0, limit: PAGE_SIZE, offset: 0 })
    );

    selectCategory("其他");
    await screen.findByText("「其他」分类下暂无文章。");
    expect(screen.queryByText(/该空间还没有文章/)).toBeNull();
    expect(lastOpts()).toMatchObject({ offset: 0, category: "其他" });
  });

  it("过滤清空后回到首屏语义，不残留上一页的累积行", async () => {
    await renderLargeSpace();
    fireEvent.click(screen.getByRole("button", { name: /加载更多/ }));
    await screen.findByText("第 51 篇");
    expect(screen.getAllByRole("listitem").length).toBe(PAGE_SIZE * 2);

    selectCategory("AI·技术");
    const ai = ofCategory("AI·技术");
    await waitFor(() => expect(h.listSpaceDocs.mock.calls.length).toBe(3));

    // 切过滤 = 回到第一页，不是在原累积列表上追加
    expect(lastOpts()).toMatchObject({ offset: 0, category: "AI·技术" });
    expect(screen.getAllByRole("listitem").length).toBe(ai.length);
    expect(screen.queryByText("第 51 篇")).toBeNull();
  });
});
