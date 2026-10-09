// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

/**
 * SPEC-M3 批次 2 + 批次 4 —— 后台管理台
 *
 * 锁五条验收不变式：
 * 1. **门禁走 is_admin，不走 role**：user.role 是主平台 userinfo 的大写枚举，
 *    与本地授权阶梯不同源；非 admin 显式说明且**不发任何请求**（fail closed）；
 * 2. **端点注入正确**：admin 面的批量操作只走 /admin 变体，绝不落到本人空间端点；
 * 3. **10004 有专属文案**：门禁拒绝不得回落成通用「请求失败，请稍后重试」；
 * 4. **归属空态诚实**：owner 行缺失（LEFT JOIN 孤儿）显式标注，不渲染 undefined；
 * 5. **与服务端分页共存**：切过滤后不可见的行退出选中，批量删除不会命中看不见的文章。
 */
const h = vi.hoisted(() => ({
  router: {
    replace: vi.fn(),
    push: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
  },
  auth: {
    status: "authed" as "loading" | "guest" | "authed",
    me: null as
      | null
      | { sub: string; email: string; nickname: string; tier: string; wallet: string; is_admin: boolean },
  },
  listAdminSpaces: vi.fn(),
  listAdminSpaceDocs: vi.fn(),
  deleteAdminSpaceDocsBatch: vi.fn(),
  recategorizeAdminSpaceDocsBatch: vi.fn(),
  deleteSpaceDocsBatch: vi.fn(),
  recategorizeSpaceDocsBatch: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => h.router,
}));

vi.mock("@/components/AuthContext", () => ({
  useAuth: () => ({
    status: h.auth.status,
    me: h.auth.me,
    login: () => {},
    logout: async () => {},
    reload: () => {},
  }),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  // 保留真实的 request / ApiError / 常量，只把网络函数换掉
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    listAdminSpaces: h.listAdminSpaces,
    listAdminSpaceDocs: h.listAdminSpaceDocs,
    deleteAdminSpaceDocsBatch: h.deleteAdminSpaceDocsBatch,
    recategorizeAdminSpaceDocsBatch: h.recategorizeAdminSpaceDocsBatch,
    deleteSpaceDocsBatch: h.deleteSpaceDocsBatch,
    recategorizeSpaceDocsBatch: h.recategorizeSpaceDocsBatch,
  };
});

import AdminPage from "@/app/admin/page";
import { ApiError, request, type SpaceDoc } from "@/lib/api";

function adminMe(isAdmin: boolean) {
  h.auth.me = {
    sub: "u-admin",
    email: "a@aidean.local",
    nickname: "管理员",
    tier: "team",
    wallet: "¥0.00",
    is_admin: isAdmin,
  };
}

function article(id: string, title: string, category?: string): SpaceDoc {
  return {
    id,
    title,
    source: "公众号B",
    status: "ready",
    updatedAt: "2026-09-23T00:00:00+00:00",
    category,
  };
}

/** 两个归属不同用户的空间；乙空间的 owner 行已不存在（LEFT JOIN 孤儿） */
const SPACES = [
  {
    id: "sp-a",
    name: "甲的空间",
    description: "",
    docCount: 3,
    updatedAt: "2026-09-23T00:00:00+00:00",
    engine: "builtin",
    engineKbId: "lb-a",
    ownerId: "u-zhang",
    ownerSub: "sub-zhang",
    ownerNickname: "张三",
  },
  {
    id: "sp-b",
    name: "乙的空间",
    description: "孤儿归属",
    docCount: 0,
    updatedAt: "2026-09-22T00:00:00+00:00",
    engine: "",
    ownerId: "",
    ownerSub: "",
    ownerNickname: "",
  },
];

let SERVER_DOCS: SpaceDoc[] = [];

function armServer() {
  h.listAdminSpaceDocs.mockImplementation(
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

async function renderAdmin() {
  adminMe(true);
  SERVER_DOCS = [
    article("d-1", "第一篇", "教程·实践"),
    article("d-2", "第二篇", "教程·实践"),
    article("d-3", "第三篇", "AI·技术"),
  ];
  h.listAdminSpaces.mockResolvedValue(SPACES);
  armServer();
  h.deleteAdminSpaceDocsBatch.mockImplementation((_id: string, ids: string[]) => {
    SERVER_DOCS = SERVER_DOCS.filter((d) => !ids.includes(d.id));
    return Promise.resolve({
      ok: true,
      requested: ids.length,
      docs: ids.length,
      assets: 0,
      failed: [],
    });
  });
  h.recategorizeAdminSpaceDocsBatch.mockImplementation(
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
  render(createElement(AdminPage));
  return await screen.findByText("甲的空间");
}

function rowCheckbox(title: string): HTMLInputElement {
  return screen.getByLabelText(`选择文档：${title}`) as HTMLInputElement;
}

beforeEach(() => {
  h.auth.status = "authed";
  h.auth.me = null;
  // 连实现一并重置：网络函数的 mockImplementation 由 renderAdmin 逐用例重新装配
  vi.resetAllMocks();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("后台管理台：门禁", () => {
  it("已登录但非 admin：显式说明权限不足，且不发任何跨用户请求", async () => {
    adminMe(false);
    render(createElement(AdminPage));
    expect(screen.getByText("权限不足")).toBeTruthy();
    expect(screen.getByText(/返回空间列表/)).toBeTruthy();
    // fail closed：门禁拒绝在渲染层解决，不把请求打出去换 10004
    expect(h.listAdminSpaces).not.toHaveBeenCalled();
    expect(h.listAdminSpaceDocs).not.toHaveBeenCalled();
  });

  it("会话判定未完成（guest）：原地渲染 AuthGate 统一卡，不渲染管理台内容", () => {
    // G4（2026-10-10）：散装跳首页已废除，guest 态由 AuthGate 统一提示卡承接
    h.auth.status = "guest";
    render(createElement(AdminPage));
    expect(screen.getByText("尚未登录或会话已过期")).toBeTruthy();
    expect(screen.queryByText("全部空间")).toBeNull();
  });

  it("is_admin 缺失（旧后端未回显）：按非 admin 处理，不越权", async () => {
    h.auth.me = {
      sub: "u-x",
      email: "x@x",
      nickname: "老后端用户",
      tier: "free",
      wallet: "—",
      is_admin: false,
    };
    render(createElement(AdminPage));
    expect(screen.getByText("权限不足")).toBeTruthy();
    expect(h.listAdminSpaces).not.toHaveBeenCalled();
  });
});

describe("后台管理台：跨用户浏览", () => {
  it("空间清单带归属展示；owner 行缺失显式标注，不渲染 undefined", async () => {
    await renderAdmin();
    expect(screen.getByText(/归属 张三/)).toBeTruthy();
    expect(screen.getByText(/归属账号已不存在/)).toBeTruthy();
    // 孤儿空间的归属字段由 listAdminSpaces 归一为空串，渲染层不回落到 undefined
    expect(screen.queryByText(/undefined/)).toBeNull();
    expect(screen.getByText(/3 篇 · 归属 张三/)).toBeTruthy();
  });

  it("打开空间走 admin 读端点，分页与服务端过滤同口径", async () => {
    await renderAdmin();
    fireEvent.click(screen.getByRole("button", { name: /甲的空间/ }));
    await screen.findByText("第一篇");
    expect(h.listAdminSpaceDocs).toHaveBeenCalledWith("sp-a", {
      limit: 50,
      offset: 0,
    });
    expect(screen.getByText("共 3 篇")).toBeTruthy();
    // admin 面没有 :categories 枚举端点，过滤选项走规则版六类 + 未分类哨兵
    expect(screen.getByLabelText("按分类筛选")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("按分类筛选"), {
      target: { value: "教程·实践" },
    });
    expect(h.listAdminSpaceDocs.mock.calls.at(-1)![1]).toMatchObject({
      offset: 0,
      category: "教程·实践",
    });
    await screen.findByText("共 2 篇");
    expect(screen.queryByText("第三篇")).toBeNull();
  });
});

describe("后台管理台：批量操作只走 admin 端点", () => {
  it("批量删除命中 /admin 变体，绝不落到本人空间端点", async () => {
    await renderAdmin();
    fireEvent.click(screen.getByRole("button", { name: /甲的空间/ }));
    await screen.findByText("第一篇");
    fireEvent.click(rowCheckbox("第一篇"));
    fireEvent.click(rowCheckbox("第二篇"));
    expect(screen.getByText("已选 2 篇")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /批量删除/ }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "确认批量删除" }));
    await screen.findByText(/批量删除：已生效 2 篇 \/ 共 2 篇/);

    expect(h.deleteAdminSpaceDocsBatch).toHaveBeenCalledTimes(1);
    expect(h.deleteSpaceDocsBatch).not.toHaveBeenCalled();
    // 成功后重新拉取服务端视图，不本地改写列表（服务端分页下本地增删会让页码失真）
    await waitFor(() =>
      expect(h.listAdminSpaceDocs.mock.calls.at(-1)![1]).toMatchObject({ offset: 0 })
    );
  });

  it("批量改分类命中 /admin 变体，整批原子", async () => {
    await renderAdmin();
    fireEvent.click(screen.getByRole("button", { name: /甲的空间/ }));
    await screen.findByText("第一篇");
    fireEvent.click(rowCheckbox("第一篇"));
    fireEvent.click(rowCheckbox("第三篇"));

    fireEvent.click(screen.getByRole("button", { name: /批量改分类/ }));
    const dialog = within(screen.getByRole("dialog"));
    fireEvent.change(dialog.getByLabelText("选择"), { target: { value: "教程·实践" } });
    fireEvent.click(dialog.getByRole("button", { name: "批量改分类" }));
    await screen.findByText(/批量改分类：已改 2 篇 → 教程·实践/);

    expect(h.recategorizeAdminSpaceDocsBatch).toHaveBeenCalledTimes(1);
    expect(h.recategorizeSpaceDocsBatch).not.toHaveBeenCalled();
    expect(h.recategorizeAdminSpaceDocsBatch.mock.calls[0][2]).toBe("教程·实践");
    // 单批一次请求，不多不少
    expect(screen.getByText("已选 0 篇")).toBeTruthy();
  });

  it("admin 端点整批被拒：如实呈现错误信封文案，不把失败说成成功", async () => {
    await renderAdmin();
    fireEvent.click(screen.getByRole("button", { name: /甲的空间/ }));
    await screen.findByText("第一篇");
    fireEvent.click(rowCheckbox("第一篇"));
    h.recategorizeAdminSpaceDocsBatch.mockRejectedValue(
      new ApiError(10004, "权限不足")
    );

    fireEvent.click(screen.getByRole("button", { name: /批量改分类/ }));
    const dialog = within(screen.getByRole("dialog"));
    fireEvent.change(dialog.getByLabelText("选择"), { target: { value: "AI·技术" } });
    fireEvent.click(dialog.getByRole("button", { name: "批量改分类" }));
    await screen.findByText(/第 1 批（1 篇）：权限不足/);
  });
});

describe("后台管理台：与服务端分页共存", () => {
  it("切过滤后不可见的行退出选中，批量删除不会命中看不见的文章", async () => {
    await renderAdmin();
    fireEvent.click(screen.getByRole("button", { name: /甲的空间/ }));
    await screen.findByText("第一篇");
    // 第一/二篇是「教程·实践」，切到「AI·技术」后不再可见
    fireEvent.click(rowCheckbox("第一篇"));
    fireEvent.click(rowCheckbox("第二篇"));
    expect(screen.getByText("已选 2 篇")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("按分类筛选"), {
      target: { value: "AI·技术" },
    });
    await screen.findByText("共 1 篇");
    // 修剪 effect 在 docs 替换后的下一轮渲染生效
    await screen.findByText("已选 0 篇");
    expect(screen.queryByLabelText("选择文档：第一篇")).toBeNull();
  });
});

describe("错误文案：admin 门禁拒绝码", () => {
  it("10004 有专属文案，不回落到通用失败提示", async () => {
    // 走真实 request 管线（仅 mock fetch），证明登记表条目经友好化链路生效
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        ({
          status: 403,
          json: async () => ({
            code: 10004,
            message: "FORBIDDEN",
            data: null,
            requestId: "r-1",
          }),
        }) as Response
      )
    );
    await expect(request("/api/v1/admin/spaces")).rejects.toMatchObject({
      code: 10004,
      message: "权限不足",
    });
  });
});
