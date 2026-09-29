// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const routerMock = { replace: () => {}, push: () => {} };

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    listSpaces: vi.fn(),
  };
});

vi.mock("@/components/AuthContext", () => ({
  useAuth: () => ({
    status: "authed",
    me: null,
    login: () => {},
    logout: async () => {},
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
}));

import SpacesPage from "@/app/spaces/page";
import { listSpaces } from "@/lib/api";

type MockSpace = {
  id: string;
  name: string;
  description: string;
  docCount: number;
  updatedAt: string;
};

function mkSpace(over: Partial<MockSpace> & { id: string }): MockSpace {
  return {
    name: "默认空间",
    description: "",
    docCount: 0,
    updatedAt: "2026-09-23T08:00:00Z",
    ...over,
  };
}

const listSpacesMock = vi.mocked(listSpaces);

beforeEach(() => {
  listSpacesMock.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("R5.2.4 空间列表页", () => {
  it("加载态：listSpaces 未返回前显示骨架屏占位", async () => {
    listSpacesMock.mockImplementation(
      () => new Promise((resolve) => { setTimeout(() => resolve([]), 50); })
    );
    render(<SpacesPage />);
    expect(document.querySelector("[class*='animate-pulse']")).not.toBeNull();
  });

  it("空态：无任何空间时给出口径明确的引导 + 就地新建入口（R0.5 补 create 后不再跳主平台）", async () => {
    listSpacesMock.mockResolvedValue([]);
    render(<SpacesPage />);
    expect(await screen.findByText("还没有知识空间")).toBeTruthy();
    expect(screen.getByText("先建一个空间，再往里面采集公众号文章。")).toBeTruthy();
    expect(screen.getByRole("button", { name: "新建第一个空间" })).toBeTruthy();
    // 头部按钮与空态按钮都开了同一张创建表单，空态不再是死路
    expect(screen.getByRole("button", { name: "新建空间" })).toBeTruthy();
  });

  it("空间卡片渲染：含名称、简介、文章数、更新时间", async () => {
    listSpacesMock.mockResolvedValue([
      mkSpace({ id: "sp-1", name: "AI前沿", description: "AI相关", docCount: 3 }),
    ]);
    render(<SpacesPage />);
    expect(await screen.findByText("AI前沿")).toBeTruthy();
    expect(screen.getByText("AI相关")).toBeTruthy();
    expect(screen.getByText("3 篇文章")).toBeTruthy();
  });

  it("跳转链接：每张卡片 href 指向 /spaces/{id}", async () => {
    listSpacesMock.mockResolvedValue([
      mkSpace({ id: "sp-42", name: "空间42" }),
      mkSpace({ id: "sp-99", name: "空间99" }),
    ]);
    render(<SpacesPage />);
    await screen.findByText("空间42");
    await screen.findByText("空间99");
    expect(screen.getAllByRole("link")).toHaveLength(2);
    expect((screen.getAllByRole("link")[0] as HTMLAnchorElement).href).toContain("/spaces/sp-42");
    expect((screen.getAllByRole("link")[1] as HTMLAnchorElement).href).toContain("/spaces/sp-99");
  });
});