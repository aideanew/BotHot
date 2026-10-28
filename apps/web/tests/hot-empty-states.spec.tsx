// @vitest-environment happy-dom
/**
 * STEP-65 U3 —— `ux_states` 对 /hot `empty` 态的要求：
 * 「「今日暂无热点」+ 最近更新时间；与「聚类未产出」区分并分别埋点」。
 *
 * 现状是一支合并文案（「暂无内容。触发聚簇或生成日报后，内容会出现在这里。」），
 * 两种真相完全不同的空在界面上长同一个样。本卡拆成两支**原字**，并且——复核抓到、我原来没想到的——
 * 再加两档「没资格下结论」的档：feed 自己拉失败、topics 拉失败（`fetchTopics` 的 catch 是既有静默兜底），
 * 这两种情形下说「聚类未产出」就是把"我不知道"说成"系统没产出"。
 *
 * **降级口径**：契约后半句「+ 最近更新时间」不做（S65.0 探针②现读 `hot.py` 只有 `created_at`），
 * 也**不用 `new Date()` 伪造**；「分别埋点」那一半不在允许面内 ⇒ 台账 P-143。
 * 每条用例各自等它该出现的那一支——原先用"两支任选其一"的 waitFor 会让用例在中间态就放行。
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

const pageResult = <T,>(items: T[]) => ({
  items,
  total: items.length,
  page: 1,
  page_size: 10,
});

const topic = () => ({
  id: "hp-1",
  title: "昨天聚出来的热点",
  summary: "概述",
  hot_score: 30,
  source_count: 2,
  article_count: 3,
  status: "cooling",
  topic_date: "2026-10-27",
  category: "AI·技术",
  created_at: null,
});

/** 等这一支文案落地（各用例点到自己那一支，不靠"任一支出现"过关） */
async function renderAndWait(re: RegExp): Promise<HTMLElement> {
  const view = render(createElement(HotPage));
  await waitFor(() => expect(screen.getByText(re)).toBeTruthy());
  return view.container;
}

beforeEach(() => {
  h.auth.me = {
    sub: "u-65",
    email: "a@b",
    nickname: "测试者",
    tier: "pro",
    wallet: "¥0",
    is_admin: true,
  };
  h.getFeed.mockResolvedValue(pageResult([]));
  h.listDailyReports.mockResolvedValue(pageResult([]));
  h.triggerCluster.mockResolvedValue({ queued: true, days: 1, message: "" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("U3 空态：两支原字 + 两档「没资格下结论」", () => {
  it("topics 拉成功且真零条 ⇒「聚类未产出」，另一支不得并存", async () => {
    h.listHotTopics.mockResolvedValue(pageResult([]));
    await renderAndWait(/^聚类未产出$/);

    expect(screen.queryByText(/^今日暂无热点$/)).toBeNull();
  });

  it("topics 拉成功且有产出而 feed 空 ⇒「今日暂无热点」，另一支不得并存", async () => {
    h.listHotTopics.mockResolvedValue(pageResult([topic()]));
    await renderAndWait(/^今日暂无热点$/);

    expect(screen.queryByText(/^聚类未产出$/)).toBeNull();
  });

  it("两条原字逐字即整句（不再有意译后缀）；且不写「最近更新时间」、不伪造当天时间", async () => {
    h.listHotTopics.mockResolvedValue(pageResult([topic()]));
    await renderAndWait(/^今日暂无热点$/);

    const empty = screen.getByText(/^今日暂无热点$/);
    expect(empty.textContent).toBe("今日暂无热点");
    expect(empty.getAttribute("role")).toBe("status");
    expect(empty.textContent).not.toMatch(/最近更新/);
    expect(empty.textContent).not.toMatch(/\d{4}-\d{2}-\d{2}/);
    expect(empty.textContent).not.toMatch(/\d{1,2}[:：]\d{2}/);
  });

  it("topics 拉失败 ⇒ 不许说「聚类未产出」（catch 证明不了没产出），也不许说「今日暂无热点」", async () => {
    h.listHotTopics.mockRejectedValue(new Error("500"));
    await renderAndWait(/热点列表没能加载/);

    expect(screen.queryByText(/^聚类未产出$/)).toBeNull();
    expect(screen.queryByText(/^今日暂无热点$/)).toBeNull();
  });

  it("feed 拉失败 ⇒ 页面既有错误横幅在位，空态那一支不替它下「内容有没有」的结论", async () => {
    h.getFeed.mockRejectedValue(new Error("Feed 拉取失败"));
    h.listHotTopics.mockResolvedValue(pageResult([]));
    await renderAndWait(/Feed 没能加载出来/);

    expect(screen.queryByText(/^聚类未产出$/)).toBeNull();
    expect(screen.queryByText(/^今日暂无热点$/)).toBeNull();
  });

  it("带状态过滤且过滤后零条 ⇒ 归「今日暂无热点」而不是断言「从没产出」", async () => {
    window.history.replaceState({}, "", "/hot?status=archived");
    h.listHotTopics.mockResolvedValue(pageResult([]));
    await renderAndWait(/^今日暂无热点$/);

    expect(screen.queryByText(/^聚类未产出$/)).toBeNull();
  });
});
