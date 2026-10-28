// @vitest-environment happy-dom
/**
 * STEP-65 U4 —— `ux_states` 对 /hot `success` 态的要求：
 * 「按 hot_score 倒序；score 为 0.0 时显示为「待评分」而非「0 分」
 *   （hot_cluster.py 落 0.0 占位由评分回填）」。
 *
 * 0 值是**占位**不是分数：把它渲成「🔥 0.0」等于告诉用户"这个热点热度为零"，
 * 而真相是"还没评分"。所以两条都判：出现「待评分」，且不出现 0.0 那个形状。
 */
import { createElement } from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

function topic(over: Record<string, unknown> = {}) {
  return {
    id: "hp-1",
    title: "评分还没回填的热点",
    summary: "概述",
    hot_score: 0,
    source_count: 2,
    article_count: 4,
    status: "rising",
    topic_date: "2026-10-28",
    category: "AI·技术",
    created_at: null,
    ...over,
  };
}

const pageResult = <T,>(items: T[]) => ({
  items,
  total: items.length,
  page: 1,
  page_size: 10,
});

beforeEach(() => {
  h.auth.me = {
    sub: "u-65",
    email: "a@b",
    nickname: "测试者",
    tier: "pro",
    wallet: "¥0",
    is_admin: true,
  };
  h.getFeed.mockResolvedValue(
    pageResult([
      {
        id: "f-1",
        item_type: "hot_topic",
        ref_id: "hp-1",
        title: "一条正常的 feed 条目",
        summary: "",
        source_name: "RSS",
        score: 12.3,
        category: "",
        url: "",
        is_pinned: false,
        created_at: null,
      },
    ])
  );
  h.listDailyReports.mockResolvedValue(pageResult([]));
  h.getDailyReport.mockResolvedValue({ id: "d-1", content_markdown: "" });
  h.generateDailyReport.mockResolvedValue({ queued: true });
  h.triggerCluster.mockResolvedValue({ queued: true, days: 1, message: "" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("U4 hot_score 为 0 ⇒ 渲染「待评分」而不是数字", () => {
  it("0 值：出现「待评分」，且 DOM 里不存在 🔥 0.0 这个形状", async () => {
    h.listHotTopics.mockResolvedValue(pageResult([topic({ hot_score: 0 })]));
    const { container } = render(createElement(HotPage));
    await waitFor(() => expect(screen.getByText("评分还没回填的热点")).toBeTruthy());

    expect(screen.getByText("待评分")).toBeTruthy();
    expect(screen.queryByText("🔥 0.0")).toBeNull();
    expect(container.textContent).not.toMatch(/🔥\s*0\.0/);
  });

  it("非 0 值：照旧显示数字且不出现「待评分」（极性：不是把整列改成就写待评分）", async () => {
    h.listHotTopics.mockResolvedValue(
      pageResult([topic({ id: "hp-9", title: "已评分的热点", hot_score: 42 })])
    );
    const { container } = render(createElement(HotPage));
    await waitFor(() => expect(screen.getByText("已评分的热点")).toBeTruthy());

    expect(screen.getByText("🔥 42.0")).toBeTruthy();
    expect(screen.queryByText("待评分")).toBeNull();
  });

  it("0 与「真有低分」的分界由 hot_score 本身决定：极小正数仍走数字支", async () => {
    h.listHotTopics.mockResolvedValue(
      pageResult([topic({ id: "hp-10", title: "低分热点", hot_score: 0.1 })])
    );
    render(createElement(HotPage));
    await waitFor(() => expect(screen.getByText("低分热点")).toBeTruthy());

    expect(screen.getByText("🔥 0.1")).toBeTruthy();
    expect(screen.queryByText("待评分")).toBeNull();
  });
});
