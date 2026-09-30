// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

/**
 * W4 4.6a —— 热点中心增强 + 日报渲染不变式
 *
 * 锁四条：
 * 1. **聚簇按钮按角色显隐**：is_admin 可见，普通用户不可见（纯前端唯一门禁信号）；
 * 2. **入队语义**：triggerCluster 成功后提示「已入队」，不得谎报「已完成」；
 * 3. **状态徽章过滤 + 热度条形**：点击过滤调 listHotTopics(status=...)，条形按最高分归一；
 * 4. **日报真实 Markdown 渲染 + 翻页**：标题/列表由 markdown 结构渲出，非源文本直出。
 */
const h = vi.hoisted(() => ({
  auth: {
    status: "authed" as "loading" | "guest" | "authed",
    me: null as null | {
      sub: string;
      email: string;
      nickname: string;
      tier: string;
      wallet: string;
      is_admin: boolean;
    },
  },
  getFeed: vi.fn(),
  listHotTopics: vi.fn(),
  triggerCluster: vi.fn(),
  listDailyReports: vi.fn(),
  getDailyReport: vi.fn(),
  generateDailyReport: vi.fn(),
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

vi.mock("@/lib/api/hot", () => ({
  getFeed: h.getFeed,
  listHotTopics: h.listHotTopics,
  triggerCluster: h.triggerCluster,
  listDailyReports: h.listDailyReports,
  getDailyReport: h.getDailyReport,
  generateDailyReport: h.generateDailyReport,
}));

import HotPage from "@/app/hot/page";
import DailyReportPage from "@/app/hot/daily/page";

function topic(over: Record<string, unknown> = {}) {
  return {
    id: "hp-1",
    title: "某大模型发布新版本",
    summary: "概述",
    hot_score: 80,
    source_count: 3,
    article_count: 5,
    status: "hot",
    topic_date: "2026-09-30",
    category: "AI·技术",
    created_at: null,
    ...over,
  };
}

const page = <T,>(items: T[]) => ({
  items,
  total: items.length,
  page: 1,
  page_size: 10,
});

function setMe(isAdmin: boolean) {
  h.auth.me = {
    sub: "u-1",
    email: "a@a",
    nickname: isAdmin ? "管理员" : "普通用户",
    tier: "pro",
    wallet: "¥0",
    is_admin: isAdmin,
  };
}

beforeEach(() => {
  setMe(true);
  h.getFeed.mockResolvedValue(page([]));
  h.listHotTopics.mockResolvedValue(
    page([
      topic(),
      topic({ id: "hp-2", title: "第二热点", hot_score: 40, status: "rising" }),
    ]),
  );
  h.triggerCluster.mockResolvedValue({ queued: true, days: 1, message: "预计几分钟内完成" });
  h.listDailyReports.mockResolvedValue({
    items: [
      { id: "d-1", report_date: "2026-09-30", title: "0930 日报", topic_count: 10, status: "published", generated_by: "auto", created_at: null },
      { id: "d-2", report_date: "2026-09-29", title: "0929 日报", topic_count: 9, status: "published", generated_by: "manual", created_at: null },
    ],
    total: 12,
    page: 1,
    page_size: 10,
  });
  h.getDailyReport.mockResolvedValue({
    id: "d-1",
    report_date: "2026-09-30",
    title: "0930 日报",
    topic_count: 10,
    status: "published",
    generated_by: "auto",
    created_at: null,
    content_markdown: "## 今日头条\n\n- **榜首**：某大模型发布新版本\n",
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("/hot 热点中心", () => {
  it("admin 可见触发聚簇按钮，点击后提示「已入队」", async () => {
    render(createElement(HotPage));
    const btn = await screen.findByRole("button", { name: "触发聚簇" });
    fireEvent.click(btn);
    await waitFor(() => expect(h.triggerCluster).toHaveBeenCalled());
    const toast = await screen.findByText(/已入队/);
    expect(toast.textContent).toContain("预计几分钟内完成");
    expect(screen.queryByText(/已完成/)).toBeNull();
  });

  it("非 admin 普通用户不可见聚簇按钮", async () => {
    setMe(false);
    render(createElement(HotPage));
    await waitFor(() => expect(h.getFeed).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "触发聚簇" })).toBeNull();
  });

  it("热度条形按最高分归一（纯 CSS 宽度比例）", async () => {
    render(createElement(HotPage));
    await screen.findByText("某大模型发布新版本");
    const bars = screen.getAllByRole("progressbar");
    expect(bars).toHaveLength(2);
    expect(bars[0].getAttribute("aria-valuenow")).toBe("100");
    expect(bars[1].getAttribute("aria-valuenow")).toBe("50");
  });

  it("状态徽章点击切换过滤并同步 URL query", async () => {
    render(createElement(HotPage));
    fireEvent.click(await screen.findByRole("button", { name: "上升中" }));
    await waitFor(() =>
      expect(h.listHotTopics).toHaveBeenCalledWith(
        expect.objectContaining({ status: "rising" }),
      ),
    );
    expect(window.location.search).toContain("status=rising");
    // 再点一次取消过滤
    fireEvent.click(screen.getByRole("button", { name: "上升中" }));
    await waitFor(() =>
      expect(h.listHotTopics).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: undefined }),
      ),
    );
    expect(window.location.search).not.toContain("status=rising");
  });
});

describe("/hot/daily 日报页", () => {
  it("以渲染后的 Markdown 展示正文（非源文本直出）", async () => {
    render(createElement(DailyReportPage));
    fireEvent.click(await screen.findByText("2026-09-30"));
    const heading = await screen.findByRole("heading", { name: "今日头条" });
    expect(heading).toBeTruthy();
    // 源文本标记不得裸露
    expect(screen.queryByText(/## 今日头条/)).toBeNull();
    // **粗体** 被解析为 <strong>（证明真实渲染而非直出）
    expect(await screen.findByText("榜首")).toBeTruthy();
  });

  it("日报列表翻页：下一页以 page=2 重新拉取", async () => {
    render(createElement(DailyReportPage));
    const next = await screen.findByRole("button", { name: "下一页" });
    fireEvent.click(next);
    await waitFor(() =>
      expect(h.listDailyReports).toHaveBeenCalledWith(
        expect.objectContaining({ page: 2 }),
      ),
    );
    const page2Btn = await screen.findByRole("button", { name: "2" });
    expect(page2Btn.getAttribute("aria-current")).toBe("page");
  });
});
