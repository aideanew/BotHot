// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import type { EngineItem, Space } from "@/lib/api";

/**
 * R0.3.3 + S15.V17.1 —— EngineSwitcher 的不可用原因。
 *
 * F-3 背景：后端 PATCH 曾只查 allowlist + configured，漏查 ENGINE_IMPLEMENTED，
 * 骨架位「配齐 Key + 全开放」时可被切换；此后 ingest 全 403、delete_space 走
 * SaasAdapter.delete_kb 抛 NotImplementedError 整体回滚 → 空间无法删除。前端
 * `canSelect` 早已挡住点击，但卡片文案只有两态，管理员无法区分「未开放」与
 * 「Key 已配齐却只是骨架实现」——照提示去配 Key 是死循环。
 *
 * S15.V17.1 之后原因**只有一个来源**：契约的 `reason`（STEP-13）。本测因此改成锁两件事——
 * ① 四种 reason 各画哪句文案（口径来自卡面，不来自前端推导）；
 * ② 三个布尔与 reason 矛盾时**按 reason 画**（这条是"前端不再自己推顺序"的反证锚）。
 */

const MOCKED = vi.hoisted(() => ({
  items: [
    // 当前引擎（builtin，回退通道，恒 ok）
    { engine: "builtin", configured: true, available: true, allowlisted: true, reason: "ok", keyEnv: "builtin", description: "内置引擎（LangBot 系，默认）" },
    // 已配 Key + 已开放，但未实接 → reason 给 not_implemented（此前会被误标「未开放」）
    { engine: "main", configured: true, available: false, allowlisted: true, reason: "not_implemented", keyEnv: "MAIN_KB_API_KEY", description: "主平台知识库（RAGFlow 拓展系）" },
    // 已开放但 Key 未配 → key_missing
    { engine: "coze", configured: false, available: false, allowlisted: true, reason: "key_missing", keyEnv: "COZE_API_KEY", description: "Coze 知识库 API（SaaS）" },
    // 未开放且 Key 未配 → not_allowlisted（排序在后端：开放名单先于 Key）
    { engine: "dify", configured: false, available: false, allowlisted: false, reason: "not_allowlisted", keyEnv: "DIFY_API_KEY", description: "Dify Cloud Knowledge API（SaaS）" },
    // 配了 Key 但未开放 → 仍是 not_allowlisted，优先级不因 Key 到位而翻转
    { engine: "fastgpt", configured: true, available: false, allowlisted: false, reason: "not_allowlisted", keyEnv: "FASTGPT_API_KEY", description: "FastGPT Cloud Dataset API（SaaS）" },
  ] as EngineItem[],
}));

vi.mock("@/lib/api", async (importOriginal) => {
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
  // 展开真实模块：被测组件除了两个域函数还要读 ENGINE_REASON_* 两张表，
  // 手写一份"最小可用面"的 mock 会在每次扩面时静默把组件打成 undefined。
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    ApiError,
    listEngines: vi.fn().mockResolvedValue({ defaultEngine: "builtin", items: MOCKED.items }),
    patchSpaceEngine: vi.fn(),
  };
});

import EngineSwitcher from "@/components/EngineSwitcher";
import { listEngines } from "@/lib/api";

const SPACE: Space = {
  id: "sp-1",
  name: "测试空间",
  description: "",
  docCount: 0,
  updatedAt: "2026-09-22T00:00:00Z",
  engine: "builtin",
  engineKbId: "lb-kb-1",
  isPublic: false,
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

describe("R0.3.3 EngineSwitcher 不可用原因（读契约 reason）", () => {
  it("骨架位「配齐 Key + 已开放」显示「暂未接入」，不再误标「未开放」", async () => {
    renderSwitcher();
    await screen.findAllByRole("button");

    expect(card("main").textContent).toContain("暂未接入");
    expect(card("main").getAttribute("title")).toContain("暂未接入");

    const cards = labels();
    expect(cards.some((t) => t.endsWith("暂未接入"))).toBe(true);
    expect(cards.some((t) => t.endsWith("未登记 Key"))).toBe(true);
    expect(cards.some((t) => t.endsWith("未开放"))).toBe(true);
    expect(cards.some((t) => t.endsWith("可用"))).toBe(true);
  });

  it("四种 reason 各画卡面那句文案（口径不来自前端推导）", async () => {
    renderSwitcher();
    await screen.findAllByRole("button");

    expect(card("dify").getAttribute("title")).toContain("未开放，请联系管理员");
    expect(card("coze").getAttribute("title")).toContain("未登记 API Key");
    expect(card("main").getAttribute("title")).toContain("暂未接入");
    // 排序只有后端一份：配了 Key 但未开放，仍然报"未开放"（处置人是管理员开名单）
    expect(card("fastgpt").textContent).toContain("未开放");
  });

  it("reason 与三个布尔矛盾时按 reason 画（前端不再自己推顺序的反证锚）", async () => {
    // 一份"布尔说不通、reason 说了算"的回执：allowlisted=false 但 reason=key_missing
    vi.mocked(listEngines).mockResolvedValueOnce({
      defaultEngine: "builtin",
      items: [
        {
          engine: "coze",
          configured: false,
          available: false,
          allowlisted: false,
          reason: "key_missing",
          activeSource: null,
          decryptFailed: false,
          implemented: false,
          keyEnv: "COZE_API_KEY",
          description: "Coze 知识库 API（SaaS）",
        },
      ],
    });
    renderSwitcher();
    await screen.findAllByRole("button");
    expect(card("coze").textContent).toContain("未登记 Key");
  });

  it("分层优先级：未开放 > 未配置 Key（配了 Key 但未开放仍报未开放）", async () => {
    renderSwitcher();
    await screen.findAllByRole("button");

    // fastgpt：configured=true 但 reason=not_allowlisted → 仍是「未开放」
    expect(card("fastgpt").textContent).toContain("未开放");
    expect(card("fastgpt").getAttribute("title")).toContain("未开放，请联系管理员");
    // dify：两者皆缺 → 同样「未开放」
    expect(card("dify").textContent).toContain("未开放");
    // coze：已开放但缺 Key → key_missing
    expect(card("coze").textContent).toContain("未登记 Key");
    expect(card("coze").getAttribute("title")).toContain("未登记 API Key");
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
