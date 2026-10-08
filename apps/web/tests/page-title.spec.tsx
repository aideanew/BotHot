// @vitest-environment happy-dom
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { usePageTitle } from "@/components/usePageTitle";

/**
 * 页签标题行为（覆盖面守卫在 page-title-coverage.spec.ts）。
 *
 * 缺陷背景：只有根 layout 导出 metadata，11 个 page.tsx 全是 "use client"，
 * 于是 /jobs、/public、/admin 等页签一律显示「BotHot · 知识空间」，
 * 多标签并排时无法分辨当前所在页面。
 */
describe("usePageTitle", () => {
  function Probe({ title }: { title: string }) {
    usePageTitle(title);
    return <p>{title}</p>;
  }

  it("写入 document.title，标题变化时同步更新", () => {
    const { rerender } = render(<Probe title="任务中心" />);
    expect(document.title).toBe("任务中心 · BotHot");

    rerender(<Probe title="订阅管理" />);
    expect(document.title).toBe("订阅管理 · BotHot");
  });
});
