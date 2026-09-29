// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { SpaceDoc } from "@/lib/api";

/**
 * R0.2.4 —— 文档行生命周期入口（改分类 / 删除）
 *
 * F-2 收尾的前端半：此前文档零删除/编辑入口，与 F-1（单页 100 条上限）叠加成
 * 「看不全 + 删不掉」死锁。后端 R0.2.1/R0.2.2 已提供 DELETE/PATCH，本测锁定
 * `DocLifecycleActions` 的入口语义：
 * - 改分类下拉 = 规则版六类 + 空串（清空人工标签），选项 value 直取词表原文，
 *   前端不得自行改写（否则与后端 CATEGORY_ALLOWLIST 不一致，静默 422）；
 * - 空串必须**原样提交**（后端回默认口径「其他」），前端不提前补默认值；
 * - 删除为纯确认（无下拉）；
 * - 失败就地展示错误文案，弹窗不关。
 */
const MOCKED = vi.hoisted(() => ({
  categories: ["AI·技术", "产品·商业", "行业·动态", "观点·评论", "教程·实践", "其他"] as const,
  deleteSpaceDoc: vi.fn(),
  patchSpaceDocCategory: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  CATEGORIES: MOCKED.categories,
  deleteSpaceDoc: MOCKED.deleteSpaceDoc,
  patchSpaceDocCategory: MOCKED.patchSpaceDocCategory,
}));

import DocLifecycleActions from "@/components/DocLifecycleActions";

interface Callbacks {
  onDeleted: (docId: string, result: { docs: number; assets: number }) => void;
  onRecategorized: (docId: string, category: string) => void;
}

function doc(overrides: Partial<SpaceDoc> = {}): SpaceDoc {
  return {
    id: "doc-1",
    title: "示例文章",
    source: "公众号A",
    status: "ready",
    updatedAt: "2026-09-22T00:00:00+00:00",
    category: "AI·技术",
    ...overrides,
  };
}

function renderActions(d: SpaceDoc, cbs: Callbacks): void {
  render(createElement(DocLifecycleActions, { spaceId: "sp-1", doc: d, ...cbs }));
}

function modalSelect(): HTMLSelectElement {
  const el = document.querySelector("select");
  if (!el) throw new Error("弹窗未渲染下拉");
  return el as HTMLSelectElement;
}

async function openRecategorize(d: SpaceDoc, cbs: Callbacks): Promise<void> {
  renderActions(d, cbs);
  fireEvent.click(screen.getByRole("button", { name: "改分类" }));
  await screen.findByRole("dialog");
}

async function openDelete(d: SpaceDoc, cbs: Callbacks): Promise<HTMLElement> {
  renderActions(d, cbs);
  fireEvent.click(screen.getByRole("button", { name: "删除" }));
  return await screen.findByRole("dialog");
}

beforeEach(() => {
  MOCKED.deleteSpaceDoc.mockReset();
  MOCKED.patchSpaceDocCategory.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("R0.2.4 文档行生命周期入口", () => {
  it("初始仅两个入口按钮，无模态无下拉", () => {
    renderActions(doc(), { onDeleted: vi.fn(), onRecategorized: vi.fn() });
    const labels = screen.getAllByRole("button").map((b) => b.textContent);
    expect(labels).toEqual(["改分类", "删除"]);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("改分类下拉 = 六类词表 + 空串（value 与后端白名单逐字一致）", async () => {
    await openRecategorize(doc(), { onDeleted: vi.fn(), onRecategorized: vi.fn() });
    const select = modalSelect();
    expect(Array.from(select.options).map((o) => o.value)).toEqual([
      ...MOCKED.categories,
      "",
    ]);
    // 六类以原文展示，「清空」项明示回默认口径
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual([
      ...MOCKED.categories,
      "清空人工标签（回默认「其他」）",
    ]);
  });

  it("下拉初始选中该文档当前分类", async () => {
    await openRecategorize(doc({ category: "观点·评论" }), {
      onDeleted: vi.fn(),
      onRecategorized: vi.fn(),
    });
    expect(modalSelect().value).toBe("观点·评论");
  });

  it("未分类文档（无 category）→ 下拉初始落在「清空」项", async () => {
    await openRecategorize(doc({ category: undefined }), {
      onDeleted: vi.fn(),
      onRecategorized: vi.fn(),
    });
    expect(modalSelect().value).toBe("");
  });

  it("选定新分类 → PATCH 提交词表原文，回调用后端生效值回写", async () => {
    const onRecategorized = vi.fn();
    MOCKED.patchSpaceDocCategory.mockResolvedValue({
      docId: "doc-1",
      category: "观点·评论",
    });
    await openRecategorize(doc(), { onDeleted: vi.fn(), onRecategorized });

    fireEvent.change(modalSelect(), { target: { value: "观点·评论" } });
    fireEvent.click(screen.getByRole("button", { name: "保存分类" }));

    await waitFor(() =>
      expect(MOCKED.patchSpaceDocCategory).toHaveBeenCalledWith("sp-1", "doc-1", "观点·评论")
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(onRecategorized).toHaveBeenCalledWith("doc-1", "观点·评论");
  });

  it("清空人工标签 → 原样提交空串（不由前端补默认值），回写后端返回的「其他」", async () => {
    const onRecategorized = vi.fn();
    MOCKED.patchSpaceDocCategory.mockResolvedValue({ docId: "doc-1", category: "其他" });
    await openRecategorize(doc(), { onDeleted: vi.fn(), onRecategorized });

    fireEvent.change(modalSelect(), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "保存分类" }));

    await waitFor(() =>
      expect(MOCKED.patchSpaceDocCategory).toHaveBeenCalledWith("sp-1", "doc-1", "")
    );
    expect(onRecategorized).toHaveBeenCalledWith("doc-1", "其他");
  });

  it("删除为纯确认弹窗（无下拉），确认后回调连带清理计数", async () => {
    const onDeleted = vi.fn();
    MOCKED.deleteSpaceDoc.mockResolvedValue({ ok: true, docId: "doc-1", docs: 1, assets: 2 });
    const dialog = await openDelete(doc(), { onDeleted, onRecategorized: vi.fn() });
    expect(dialog.querySelector("select")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
    await waitFor(() => expect(MOCKED.deleteSpaceDoc).toHaveBeenCalledWith("sp-1", "doc-1"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(onDeleted).toHaveBeenCalledWith("doc-1", {
      ok: true,
      docId: "doc-1",
      docs: 1,
      assets: 2,
    });
  });

  it("取消 → 不发任何请求，弹窗关闭", async () => {
    const onDeleted = vi.fn();
    const onRecategorized = vi.fn();
    renderActions(doc(), { onDeleted, onRecategorized });
    fireEvent.click(screen.getByRole("button", { name: "改分类" }));
    await screen.findByRole("dialog");

    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(MOCKED.deleteSpaceDoc).not.toHaveBeenCalled();
    expect(MOCKED.patchSpaceDocCategory).not.toHaveBeenCalled();
    expect(onDeleted).not.toHaveBeenCalled();
    expect(onRecategorized).not.toHaveBeenCalled();
  });

  it("改分类失败 → 错误文案就地展示、弹窗不关、不触发回写", async () => {
    const onRecategorized = vi.fn();
    MOCKED.patchSpaceDocCategory.mockRejectedValue(new Error("请求参数不合法"));
    await openRecategorize(doc(), { onDeleted: vi.fn(), onRecategorized });

    fireEvent.change(modalSelect(), { target: { value: "其他" } });
    fireEvent.click(screen.getByRole("button", { name: "保存分类" }));

    await screen.findByText("请求参数不合法");
    expect(screen.queryByRole("dialog")).not.toBeNull();
    expect(onRecategorized).not.toHaveBeenCalled();
  });

  it("删除失败 → 错误文案就地展示、弹窗不关、不摘行", async () => {
    const onDeleted = vi.fn();
    MOCKED.deleteSpaceDoc.mockRejectedValue(new Error("知识空间不存在或已删除"));
    await openDelete(doc(), { onDeleted, onRecategorized: vi.fn() });

    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    await screen.findByText("知识空间不存在或已删除");
    expect(screen.queryByRole("dialog")).not.toBeNull();
    expect(onDeleted).not.toHaveBeenCalled();
  });
});
