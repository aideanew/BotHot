// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { act, cleanup, render, screen } from "@testing-library/react";

/**
 * R0.5.4 —— 空间详情页「契约诚实性」呈现不变式（F-4 + F-5 前端销账）
 *
 * 两条锁死的原则：**空值 ≠ 能力未实现**。
 * 1. `stats.chunks === null` 表示数据源（LangBot KB 统计）未接线，**必须隐藏该指标**；
 *    渲成「0 个知识分块」会把「指标不可得」谎报成「真的没有分块」，
 *    用户会据此认为索引失败而非功能未就绪。反之 chunks 为数字时必须照常显示，
 *    不能因为类型改成 `number | null` 就过度隐藏。
 * 2. `description` 为空串时显示「（未填写简介）」而非「暂无简介」——
 *    括号式空态表示「字段存在但用户未填写」，「暂无简介」读起来像平台没这能力。
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

import type { SpaceDetail } from "@/lib/api";
import SpaceDetailPage from "@/app/spaces/[id]/page";

const BASE: SpaceDetail = {
  id: "sp-1",
  name: "我的空间",
  description: "",
  docCount: 2,
  engine: "builtin",
  engineKbId: "lb-1",
  createdAt: "2026-09-01T00:00:00+00:00",
  updatedAt: "2026-09-22T00:00:00+00:00",
  stats: { docs: 2, chunks: null },
};

beforeEach(() => {
  h.getSpace.mockReset();
  h.listSpaceDocs.mockReset();
  h.listSpaceDocCategories.mockReset();
  h.listSpaceDocs.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
  h.listSpaceDocCategories.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
});

/** 渲染详情页并等到信息头出现 */
async function renderDetail(space: SpaceDetail) {
  h.getSpace.mockResolvedValue(space);
  await act(async () => { render(createElement(SpaceDetailPage, { params: Promise.resolve({ id: space.id }) })); });
  await screen.findByText(space.name);
}

describe("R0.5.4 chunk 指标：不可得则隐藏", () => {
  it("chunks 为 null → 不渲染分块指标，也不得显示「0 个知识分块」", async () => {
    await renderDetail({ ...BASE, stats: { docs: 2, chunks: null } });

    expect(screen.queryByText(/个知识分块/)).toBeNull();
    expect(screen.queryByText(/0 个/)).toBeNull();
    // 文档计数不受影响
    expect(screen.getByText("2 篇文档")).toBeTruthy();
  });

  it("chunks 为数字 → 照常渲染（类型放宽为 number|null 后不得过度隐藏）", async () => {
    await renderDetail({ ...BASE, stats: { docs: 2, chunks: 486 } });

    expect(screen.getByText("486 个知识分块")).toBeTruthy();
  });
});

describe("R0.5.4 简介空态：区分「空值」与「能力未实现」", () => {
  it("description 为空串 → 「（未填写简介）」而非「暂无简介」", async () => {
    await renderDetail({ ...BASE, description: "" });

    expect(screen.getByText("（未填写简介）")).toBeTruthy();
    expect(screen.queryByText("暂无简介")).toBeNull();
  });

  it("description 有值 → 原样渲染，不显示空态文案", async () => {
    await renderDetail({ ...BASE, description: "运营侧每日更新" });

    expect(screen.getByText("运营侧每日更新")).toBeTruthy();
    expect(screen.queryByText("（未填写简介）")).toBeNull();
  });
});
