// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import ParsePreviewCard from "../components/add-article/ParsePreviewCard";
import type { ExtractedArticle } from "../lib/api";

/**
 * ParsePreviewCard 元信息行：publishTime 必须走本地化格式。
 * 缺陷背景：后端返回 ISO（2026-09-24T12:00:00+00:00），直出会让用户把 UTC 时刻
 * 当成北京时间读——预览卡是采集质量的第一个可见出口，这里必须是本地时区文案。
 */

const DATA: ExtractedArticle = {
  title: "苹果20周年版iPhone再确认!无边四曲面设计来了",
  author: "科技美学",
  publishTime: "2026-09-24T12:00:00+00:00",
  paragraphs: ["正文第一段。", "正文第二段。"],
  images: [{ src: "https://mmbiz.qpic.cn/mmbiz_jpg/a/640?wx_fmt=jpeg", caption: "" }],
  wordCount: 838,
  langbotFormat: "# 标题",
  qualityScore: 100,
  qualityPassed: true,
  qualityReasons: [],
};

const PROPS = {
  submitting: false,
  polling: false,
  pollSeconds: 0,
  submitError: "",
  onSubmit: () => undefined,
};

/** 取预览卡内的元信息行（作者 · 时间 · 字数 · 配图） */
function metaText(): string {
  const nodes = Array.from(document.querySelectorAll("p"));
  return nodes.map((n) => n.textContent ?? "").find((t) => t.includes("科技美学")) ?? "";
}

beforeEach(() => {
  // 钉死「今天」：formatTime 按本地日期分档（今天 / 今年 / 跨年），时钟漂移会让断言失效
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-25T10:00:00+08:00"));
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("ParsePreviewCard 元信息行", () => {
  it("跨年外同日：ISO 转本地「9 月 24 日」，原始时间串不外泄", () => {
    render(<ParsePreviewCard data={DATA} {...PROPS} />);
    const meta = metaText();
    expect(meta).toContain("9 月 24 日");
    expect(meta).not.toMatch(/T\d{2}:\d{2}:\d{2}/);
    expect(meta).toContain("838 字 · 1 张配图");
  });

  it("当天发布：走「今天 HH:MM」分档", () => {
    render(
      <ParsePreviewCard
        data={{ ...DATA, publishTime: "2026-09-25T02:00:00+00:00" }}
        {...PROPS}
      />
    );
    expect(metaText()).toContain("今天 10:00");
  });

  it("publishTime 缺失：不留下悬空分隔符，其余字段照常", () => {
    render(<ParsePreviewCard data={{ ...DATA, publishTime: "" }} {...PROPS} />);
    expect(metaText()).toBe("科技美学 · 838 字 · 1 张配图");
  });
});
