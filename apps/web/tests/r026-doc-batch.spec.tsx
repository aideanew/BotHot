// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

/**
 * R0.2.6 —— 批量入口 UI（列表多选 + 批量删除 / 批量改分类）
 *
 * 锁四条验收不变式：
 * 1. **ids 按 50 上限切片**：勾 51 篇 → 2 次请求（50 + 1），顺序与总篇数守恒；
 * 2. **批量删除 = 篇级部分成功**：失败篇逐篇列出原因，且保留在选中态（再点一次即只重试
 *    失败篇），成功篇即时退出列表与选中态；
 * 3. **批量改分类 = 整批原子**：单批一次请求全成功；跨批时各批独立生效，被拒批次逐批如实
 *    列出——不把「整批原子」说成「跨批原子」；
 * 4. **与服务端分页共存**：勾选跨「加载更多」保留；切过滤后不可见的行退出选中，
 *    避免批量删除命中用户看不见的文章。
 *
 * 请求 mock 用**服务端仿真**（按请求切片，删除时只移除成功篇），与 R0.1.3/R0.1.4 同口径：
 * 翻页响应取决于页面发出的 offset，手工排响应序列无法表达该因果。
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
  deleteSpaceDocsBatch: vi.fn(),
  recategorizeSpaceDocsBatch: vi.fn(),
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

vi.mock("@/lib/api", async (importOriginal) => {
  // 保留真实 chunkDocIds / ApiError / 常量（本测要验证真实的切片与错误实例判定），
  // 只把网络函数换掉。
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getSpace: h.getSpace,
    listSpaceDocs: h.listSpaceDocs,
    listSpaceDocCategories: h.listSpaceDocCategories,
    deleteSpaceDoc: vi.fn(),
    patchSpaceDocCategory: vi.fn(),
    deleteSpaceDocsBatch: h.deleteSpaceDocsBatch,
    recategorizeSpaceDocsBatch: h.recategorizeSpaceDocsBatch,
  };
});

// 详情页其余区块与本测无关，置空以免各自打接口
vi.mock("@/components/AddArticlePanel", () => ({ default: () => null }));
vi.mock("@/components/PublicLibraryPicker", () => ({ default: () => null }));
vi.mock("@/components/EngineSwitcher", () => ({ default: () => null }));
vi.mock("@/components/SubscribeShortcut", () => ({ default: () => null }));

import SpaceDetailPage from "@/app/spaces/[id]/page";
import { ApiError, BATCH_DOCS_MAX_IDS, type SpaceDoc } from "@/lib/api";

const PAGE_SIZE = 50;

function article(id: string, title: string, category?: string): SpaceDoc {
  return {
    id,
    title,
    source: "公众号A",
    status: "ready",
    updatedAt: "2026-09-22T00:00:00+00:00",
    category,
  };
}

const SPACE = {
  id: "sp-1",
  name: "批量空间",
  description: "",
  docCount: 51,
  engine: "builtin",
  engineKbId: "lb-1",
  createdAt: "2026-09-01T00:00:00+00:00",
  updatedAt: "2026-09-22T00:00:00+00:00",
  stats: { docs: 51, chunks: 200 },
};

/** 51 篇：前 10 篇「教程·实践」，其余「AI·技术」；标题用全局序号，与 offset 直观对应 */
const ALL_DOCS: SpaceDoc[] = Array.from({ length: 51 }, (_, i) =>
  article(`d-${i}`, `第 ${i + 1} 篇`, i < 10 ? "教程·实践" : "AI·技术")
);

/** 可变的服务端视图：删除只移除成功篇，失败篇的记录完整保留（与后端逐篇提交一致） */
let SERVER_DOCS: SpaceDoc[] = [];

function armServer() {
  h.listSpaceDocs.mockImplementation(
    (_id: string, opts: { limit?: number; offset?: number; category?: string } = {}) => {
      const limit = opts.limit ?? 100;
      const offset = opts.offset ?? 0;
      const all = opts.category
        ? SERVER_DOCS.filter((d) => (d.category ?? "") === opts.category)
        : SERVER_DOCS;
      return Promise.resolve({
        items: all.slice(offset, offset + limit),
        total: all.length,
        limit,
        offset,
      });
    }
  );
}

/** 删除仿真：`failures` 中的篇走篇级失败（后端只回登记标签，前端须映射中文） */
function armDelete(failures: string[] = []) {
  h.deleteSpaceDocsBatch.mockImplementation((_id: string, ids: string[]) => {
    const failed = ids
      .filter((id) => failures.includes(id))
      .map((docId) => ({ docId, code: 30002, error: "LANGBOT_API_ERROR" }));
    const kept = new Set(failed.map((f) => f.docId));
    SERVER_DOCS = SERVER_DOCS.filter((d) => !(ids.includes(d.id) && !kept.has(d.id)));
    return Promise.resolve({
      ok: true,
      requested: ids.length,
      docs: ids.length - failed.length,
      assets: 0,
      failed,
    });
  });
}

async function renderPage() {
  SERVER_DOCS = ALL_DOCS.map((d) => ({ ...d }));
  h.getSpace.mockResolvedValue(SPACE);
  armServer();
  armDelete();
  h.listSpaceDocCategories.mockResolvedValue(["AI·技术", "教程·实践"]);
  await act(async () => { render(createElement(SpaceDetailPage, { params: Promise.resolve({ id: "sp-1" }) })); });
  return await screen.findByText("第 1 篇");
}

function rowCheckbox(title: string): HTMLInputElement {
  return screen.getByLabelText(`选择文章：${title}`) as HTMLInputElement;
}

function selectAllLoaded() {
  fireEvent.click(screen.getByLabelText("全选已加载"));
}

function confirmDialog() {
  return within(screen.getByRole("dialog"));
}

beforeEach(() => {
  h.getSpace.mockReset();
  h.listSpaceDocs.mockReset();
  h.listSpaceDocCategories.mockReset();
  h.deleteSpaceDocsBatch.mockReset();
  h.recategorizeSpaceDocsBatch.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("R0.2.6 批量删除：ids 按 50 上限切片", () => {
  it("勾选 51 篇 → 分 2 批请求（50 + 1），顺序与总篇数守恒，成功篇退出选中", async () => {
    await renderPage();
    fireEvent.click(screen.getByRole("button", { name: /加载更多/ }));
    await screen.findByText("第 51 篇");
    selectAllLoaded();
    expect(screen.getByText("已选 51 篇")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /批量删除/ }));
    fireEvent.click(confirmDialog().getByRole("button", { name: "确认批量删除" }));
    await screen.findByText(/批量删除：已生效 51 篇 \/ 共 51 篇/);

    expect(h.deleteSpaceDocsBatch).toHaveBeenCalledTimes(2);
    const [first, second] = h.deleteSpaceDocsBatch.mock.calls.map((c) => c[1]);
    expect(first.length).toBe(BATCH_DOCS_MAX_IDS);
    expect(second).toEqual(["d-50"]);
    expect(first.length + second.length).toBe(51);
    // 全部生效 → 列表回到空态，工具条与行勾选一并消失；批量结果面板仍留存可读
    expect(screen.queryAllByRole("checkbox")).toEqual([]);
    expect(screen.getByText(/该空间还没有文章/)).toBeTruthy();
  });
});

describe("R0.2.6 批量删除：篇级部分成功", () => {
  it("失败篇逐篇列出中文原因、保留在选中态可重试，成功篇即时退出列表", async () => {
    await renderPage();
    armDelete(["d-1", "d-2"]);
    selectAllLoaded();
    expect(screen.getByText("已选 50 篇")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /批量删除/ }));
    fireEvent.click(confirmDialog().getByRole("button", { name: "确认批量删除" }));
    await screen.findByText(/批量删除：已生效 48 篇 \/ 共 50 篇/);

    // 后端 failed[].error 只回 LANGBOT_API_ERROR，前端映射为可读中文
    expect(screen.getByText(/第 2 篇：该篇未能处理：引擎服务异常/)).toBeTruthy();
    expect(screen.getByText(/第 3 篇：该篇未能处理：引擎服务异常/)).toBeTruthy();
    expect(screen.queryByText(/第 4 篇：该篇未能处理/)).toBeNull();

    // 失败篇仍保持勾选 → 再点一次「批量删除」即只重试这 2 篇
    expect(screen.getByText("已选 2 篇")).toBeTruthy();
    expect(rowCheckbox("第 2 篇").checked).toBe(true);
    expect(rowCheckbox("第 3 篇").checked).toBe(true);
    // 成功篇已从列表整体消失（无残留行，也就没有残留勾选）
    expect(screen.queryByText("第 4 篇")).toBeNull();
    expect(screen.queryByLabelText("选择文章：第 4 篇")).toBeNull();

    // 重试只发失败篇：引擎恢复后这 2 篇全部生效，选中态清空
    armDelete();
    fireEvent.click(screen.getByRole("button", { name: /批量删除/ }));
    fireEvent.click(confirmDialog().getByRole("button", { name: "确认批量删除" }));
    await screen.findByText(/批量删除：已生效 2 篇 \/ 共 2 篇/);
    expect(h.deleteSpaceDocsBatch.mock.calls.at(-1)![1]).toEqual(["d-1", "d-2"]);
    expect(await screen.findByText("已选 0 篇")).toBeTruthy();
  });
});

describe("R0.2.6 批量改分类：整批原子", () => {
  it("单批一次请求全成功，报告目标分类并刷新分类集合（分类是资产级属性）", async () => {
    await renderPage();
    h.recategorizeSpaceDocsBatch.mockImplementation(
      (_id: string, ids: string[], category: string) => {
        SERVER_DOCS.forEach((d) => {
          if (ids.includes(d.id)) d.category = category || "其他";
        });
        return Promise.resolve({
          ok: true,
          requested: ids.length,
          docs: ids.length,
          category: category || "其他",
        });
      }
    );
    selectAllLoaded();
    expect(screen.getByText("已选 50 篇")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /批量改分类/ }));
    fireEvent.change(confirmDialog().getByLabelText("选择"), {
      target: { value: "教程·实践" },
    });
    fireEvent.click(confirmDialog().getByRole("button", { name: "批量改分类" }));
    await screen.findByText(/批量改分类：已改 50 篇 → 教程·实践/);

    // 单批 → 恰好一次请求，不多不少（无「改了一半」中间态）
    expect(h.recategorizeSpaceDocsBatch).toHaveBeenCalledTimes(1);
    expect(h.recategorizeSpaceDocsBatch.mock.calls[0][1].length).toBe(50);
    expect(h.recategorizeSpaceDocsBatch.mock.calls[0][2]).toBe("教程·实践");
    // 选中态清空；分类集合同步刷新
    expect(await screen.findByText("已选 0 篇")).toBeTruthy();
    await waitFor(() => expect(h.listSpaceDocCategories).toHaveBeenCalledTimes(2));
  });

  it("跨批执行中某批被整体拒绝：已生效篇如实呈现、被拒批次逐批列出", async () => {
    await renderPage();
    fireEvent.click(screen.getByRole("button", { name: /加载更多/ }));
    await screen.findByText("第 51 篇");
    selectAllLoaded();
    h.recategorizeSpaceDocsBatch
      .mockResolvedValueOnce({ ok: true, requested: 50, docs: 50, category: "教程·实践" })
      .mockRejectedValueOnce(new ApiError(30004, "知识空间不存在或已删除"));

    fireEvent.click(screen.getByRole("button", { name: /批量改分类/ }));
    fireEvent.change(confirmDialog().getByLabelText("选择"), {
      target: { value: "教程·实践" },
    });
    fireEvent.click(confirmDialog().getByRole("button", { name: "批量改分类" }));
    await screen.findByText(/批量改分类：已改 50 篇 → 教程·实践/);

    expect(h.recategorizeSpaceDocsBatch).toHaveBeenCalledTimes(2);
    // 第 1 批已生效、不回滚；第 2 批逐批如实报出
    expect(screen.getByText(/第 2 批（1 篇）：知识空间不存在或已删除/)).toBeTruthy();
    expect(screen.getByText(/超出单批 50 篇上限，已分 2 批执行，各批独立生效/)).toBeTruthy();
  });
});

describe("R0.2.6 与 R0.1.3 服务端分页共存：跨页多选", () => {
  it("加载更多不丢勾选，「全选已加载」呈半选态", async () => {
    await renderPage();
    fireEvent.click(rowCheckbox("第 3 篇"));
    fireEvent.click(rowCheckbox("第 50 篇"));
    expect(screen.getByText("已选 2 篇")).toBeTruthy();
    // 还有 1 篇未加载：明确提示，不假装「全选」覆盖了全部 51 篇
    expect(screen.getByText(/还有 1 篇未加载/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /加载更多/ }));
    await screen.findByText("第 51 篇");

    // 已勾选项原样保留，新加载的行未被连带选中
    expect(screen.getByText("已选 2 篇")).toBeTruthy();
    expect(rowCheckbox("第 3 篇").checked).toBe(true);
    expect(rowCheckbox("第 50 篇").checked).toBe(true);
    expect(rowCheckbox("第 51 篇").checked).toBe(false);
    expect((screen.getByLabelText("全选已加载") as HTMLInputElement).indeterminate).toBe(true);
    // 全部载入后该提示消失
    expect(screen.queryByText(/未加载/)).toBeNull();
  });

  it("全选已加载一次勾选全部已加载行，再次点击全取消", async () => {
    await renderPage();
    selectAllLoaded();
    expect(screen.getByText("已选 50 篇")).toBeTruthy();
    expect(rowCheckbox("第 1 篇").checked).toBe(true);
    expect(rowCheckbox("第 50 篇").checked).toBe(true);

    selectAllLoaded();
    expect(await screen.findByText("已选 0 篇")).toBeTruthy();
    expect(rowCheckbox("第 1 篇").checked).toBe(false);
  });

  it("切过滤后不可见的行退出选中：批量删除不会命中看不见的文章", async () => {
    await renderPage();
    // 第 1/2 篇是「教程·实践」，切到「AI·技术」后它们不再可见
    fireEvent.click(rowCheckbox("第 1 篇"));
    fireEvent.click(rowCheckbox("第 2 篇"));
    expect(screen.getByText("已选 2 篇")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("按分类筛选"), {
      target: { value: "AI·技术" },
    });
    await screen.findByText("第 11 篇");

    // 不可见的行已退出选中，工具条也不会拿着看不见的 id 去发请求
    expect(await screen.findByText("已选 0 篇")).toBeTruthy();
    expect(screen.queryByLabelText("选择文章：第 1 篇")).toBeNull();
    expect(h.listSpaceDocs.mock.calls.at(-1)![1]).toMatchObject({
      offset: 0,
      category: "AI·技术",
    });
  });
});
