// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import type { EngineItem, Space } from "@/lib/api";

/**
 * R0.3.3 —— EngineSwitcher 三态不可用提示（与后端 assert_engine_switchable 同序）。
 *
 * F-3 背景：后端 PATCH 曾只查 allowlist + configured，漏查 ENGINE_IMPLEMENTED，
 * 骨架位「配齐 Key + 全开放」时可被切换；此后 ingest 全 403、delete_space 走
 * SaasAdapter.delete_kb 抛 NotImplementedError 整体回滚 → 空间无法删除。前端
 * `canSelect = e.available` 早已挡住点击，但卡片文案只有两态（未配置 Key / 未开放），
 * 管理员无法区分「未开放」与「Key 已配齐却只是骨架实现」——照提示去配 Key 是死循环。
 *
 * 本测锁定三态分层顺序（未开放 → 未配置 Key → 未实接）与「骨架位不可点」。
 */

const MOCKED = vi.hoisted(() => ({
  items: [
    // 当前引擎（builtin，回退通道，恒 available）
    { engine: "builtin", configured: true, available: true, allowlisted: true, keyEnv: "builtin", description: "内置引擎（LangBot 系，默认）" },
    // 已配 Key + 已开放，但未实接 → 第三态「未实接」（此前会被误标「未开放」）
    { engine: "main", configured: true, available: false, allowlisted: true, keyEnv: "MAIN_KB_API_KEY", description: "主平台知识库（RAGFlow 拓展系）" },
    // 已开放但 Key 未配 → 「未配置 Key」
    { engine: "coze", configured: false, available: false, allowlisted: true, keyEnv: "COZE_API_KEY", description: "Coze 知识库 API（SaaS）" },
    // 未开放且 Key 未配 → 「未开放」（未开放优先于未配 Key）
    { engine: "dify", configured: false, available: false, allowlisted: false, keyEnv: "DIFY_API_KEY", description: "Dify Cloud Knowledge API（SaaS）" },
    // 配了 Key 但未开放 → 仍为「未开放」，验证分层优先级不因 Key 到位而翻转
    { engine: "fastgpt", configured: true, available: false, allowlisted: false, keyEnv: "FASTGPT_API_KEY", description: "FastGPT Cloud Dataset API（SaaS）" },
  ] as EngineItem[],
}));

vi.mock("@/lib/api", () => {
  class ApiError extends Error {
    code: number;
    requestId: string;
    constructor(code: number, message: string, requestId = "") {
      super(message);
      this.name = "ApiError";
      this.code = code;
      this.requestId = requestId;
    }
  }
  return {
    ApiError,
    listEngines: vi.fn().mockResolvedValue({ defaultEngine: "builtin", items: MOCKED.items }),
    patchSpaceEngine: vi.fn(),
  };
});

import EngineSwitcher from "@/components/EngineSwitcher";

const SPACE: Space = {
  id: "sp-1",
  name: "测试空间",
  description: "",
  docCount: 0,
  updatedAt: "2026-09-22T00:00:00Z",
  engine: "builtin",
  engineKbId: "lb-kb-1",
};

function renderSwitcher(): void {
  render(createElement(EngineSwitcher, { space: SPACE }));
}

/** 按引擎展示名取卡片（builtin 显示「内置」；ConfirmModal 关闭时不渲染按钮，故 button 总数恒为 5）。 */
function card(label: string): HTMLElement {
  const found = screen.getAllByRole("button").find((el) => el.textContent?.includes(label));
  return found!;
}

function labels(): string[] {
  return screen.getAllByRole("button").map((el) => el.textContent ?? "");
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("R0.3.3 EngineSwitcher 三态不可用提示", () => {
  it("骨架位「配齐 Key + 已开放」显示第三态「未实接」，不再误标「未开放」", async () => {
    renderSwitcher();
    await screen.findAllByRole("button");

    expect(card("main").textContent).toContain("未实接");
    expect(card("main").getAttribute("title")).toContain("尚未实接");

    const cards = labels();
    expect(cards.some((t) => t.endsWith("未实接"))).toBe(true);
    expect(cards.some((t) => t.endsWith("未配置 Key"))).toBe(true);
    expect(cards.some((t) => t.endsWith("未开放"))).toBe(true);
    expect(cards.some((t) => t.endsWith("可用"))).toBe(true);
  });

  it("分层优先级：未开放 > 未配置 Key（配了 Key 但未开放仍报未开放）", async () => {
    renderSwitcher();
    await screen.findAllByRole("button");

    // fastgpt：configured=true 但 allowlisted=false → 仍是「未开放」
    expect(card("fastgpt").textContent).toContain("未开放");
    expect(card("fastgpt").getAttribute("title")).toContain("未开放");
    // dify：两者皆缺 → 同样「未开放」
    expect(card("dify").textContent).toContain("未开放");
    // coze：已开放但缺 Key → 第三判据不提前触发
    expect(card("coze").textContent).toContain("未配置 Key");
    expect(card("coze").getAttribute("title")).toContain("未配置 API Key");
  });

  it("F-3 护栏：现无已实接的非 builtin 位，全部卡片不可点（骨架位不可被切换）", async () => {
    renderSwitcher();
    const buttons = await screen.findAllByRole("button");

    expect(buttons).toHaveLength(5);
    for (const btn of buttons) {
      expect(btn.hasAttribute("disabled")).toBe(true);
    }
  });

  it("当前引擎 builtin 标记 ✓ 与「可用」，tooltip 提示当前态而非引导切换", async () => {
    renderSwitcher();
    await screen.findAllByRole("button");

    const builtin = card("内置");
    expect(builtin.textContent).toContain("✓");
    expect(builtin.textContent).toContain("可用");
    expect(builtin.getAttribute("title")).toContain("当前：");
    expect(builtin.getAttribute("title")).not.toContain("切换到");
  });
});
