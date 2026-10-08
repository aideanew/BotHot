// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

/**
 * W9 D.4 —— Pagination 组件不变式
 *
 * 1. totalPages <= 1 不渲染；
 * 2. 页码按钮点击触发 onPageChange；
 * 3. 当前页高亮（aria-current=page）；
 * 4. 首尾页禁用态正确。
 */

function paged() {
  return { page: 3, totalPages: 5, total: 100 };
}

describe("Pagination", () => {
  afterEach(() => cleanup());

  it("totalPages=1 时不渲染", async () => {
    const Pagination = (await import("@/components/Pagination")).default;
    render(createElement(Pagination, { page: 1, totalPages: 1, total: 10, onPageChange: () => {} }));
    expect(screen.queryByRole("navigation")).toBeNull();
  });

  it("当前页高亮 aria-current=page", async () => {
    const Pagination = (await import("@/components/Pagination")).default;
    render(createElement(Pagination, { ...paged(), onPageChange: () => {} }));
    const active = screen.getByRole("button", { name: "3" });
    expect(active.getAttribute("aria-current")).toBe("page");
  });

  it("点击页码触发 onPageChange", async () => {
    const onPageChange = vi.fn();
    const Pagination = (await import("@/components/Pagination")).default;
    render(createElement(Pagination, { ...paged(), onPageChange }));
    fireEvent.click(screen.getByRole("button", { name: "5" }));
    expect(onPageChange).toHaveBeenCalledWith(5);
  });

  it("上一页按钮 disabled 当 page=1", async () => {
    const Pagination = (await import("@/components/Pagination")).default;
    render(createElement(Pagination, { page: 1, totalPages: 3, total: 50, onPageChange: () => {} }));
    expect(screen.getByRole("button", { name: "上一页" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "下一页" }).hasAttribute("disabled")).toBe(false);
  });

  it("下一页按钮 disabled 当 page=totalPages", async () => {
    const Pagination = (await import("@/components/Pagination")).default;
    render(createElement(Pagination, { page: 3, totalPages: 3, total: 50, onPageChange: () => {} }));
    expect(screen.getByRole("button", { name: "下一页" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "上一页" }).hasAttribute("disabled")).toBe(false);
  });
});
