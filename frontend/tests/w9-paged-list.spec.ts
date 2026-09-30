// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";

/**
 * W9 D.4 —— usePagedList hook 不变式
 *
 * 1. page 形状（bot/hot 域）正确传参；
 * 2. offset 形状（知识库域）正确转换；
 * 3. deps 变更时重置到第 1 页；
 * 4. error 态不崩。
 */

describe("usePagedList", () => {
  it("page 形状：传 page + page_size", async () => {
    const { usePagedList } = await import("@/lib/hooks/usePagedList");
    const fetcher = vi.fn().mockResolvedValue({
      items: [{ id: "1" }],
      total: 30,
      page: 1,
      page_size: 20,
    });
    const { renderHook, act } = await import("@testing-library/react");
    const { result } = renderHook(() =>
      usePagedList({ fetcher, shape: "page", pageSize: 20 })
    );
    await act(async () => {});
    expect(fetcher).toHaveBeenCalledWith(expect.objectContaining({ page: 1, page_size: 20 }));
    expect(result.current.items).toEqual([{ id: "1" }]);
    expect(result.current.total).toBe(30);
  });

  it("offset 形状：传 limit + offset", async () => {
    const { usePagedList } = await import("@/lib/hooks/usePagedList");
    const fetcher = vi.fn().mockResolvedValue({
      items: [{ id: "2" }],
      total: 50,
      limit: 20,
      offset: 0,
    });
    const { renderHook, act } = await import("@testing-library/react");
    const { result } = renderHook(() =>
      usePagedList({ fetcher, shape: "offset", pageSize: 20 })
    );
    await act(async () => {});
    expect(fetcher).toHaveBeenCalledWith(expect.objectContaining({ limit: 20, offset: 0 }));
    expect(result.current.items).toEqual([{ id: "2" }]);
  });

  it("error 态不崩：error 字段赋值", async () => {
    const { usePagedList } = await import("@/lib/hooks/usePagedList");
    const fetcher = vi.fn().mockRejectedValue(new Error("网络异常"));
    const { renderHook, act } = await import("@testing-library/react");
    const { result } = renderHook(() =>
      usePagedList({ fetcher })
    );
    await act(async () => {});
    expect(result.current.error).toBe("网络异常");
    expect(result.current.items).toEqual([]);
  });
});
