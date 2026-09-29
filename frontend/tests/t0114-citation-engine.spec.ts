import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * T1.1.4 —— 引用块标 engine 字段（ADR-0004 三元 {title, spaceName, engine}）
 *
 * 后端 `chat.py:_citations_from` 已在 meta 帧 cites 中补 engine；本测锁定前端两段差量：
 * ①`engineLabel` 映射口径（builtin/缺省 → 内置；其余原样透出，不臆造中文名）；
 * ②SSE meta 帧 citations 的 engine 字段解析后**逐字保留**（不得被前端解析层丢弃）。
 * 策略同 ask-sse.spec：不改生产代码，stubEnv 切真实态 + stub fetch 直测生产实现。
 */

async function importRealApi() {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_MOCK", "false");
  return import("@/lib/api");
}

function sseResponse(events: unknown[]): Response {
  const text = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  return new Response(text, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("T1.1.4 engineLabel 映射口径", () => {
  it("builtin / 缺省 / 空串 → 统一显示「内置」", async () => {
    const { engineLabel } = await importRealApi();
    expect(engineLabel("builtin")).toBe("内置");
    expect(engineLabel(undefined)).toBe("内置");
    expect(engineLabel(null)).toBe("内置");
    expect(engineLabel("")).toBe("内置");
  });

  it("非 builtin 引擎位 → 原样透出 token（不臆造中文名）", async () => {
    const { engineLabel } = await importRealApi();
    expect(engineLabel("coze")).toBe("coze");
    expect(engineLabel("dify")).toBe("dify");
    expect(engineLabel("fastgpt")).toBe("fastgpt");
    expect(engineLabel("main")).toBe("main");
  });
});

describe("T1.1.4 SSE citations.engine 解析保真", () => {
  it("meta 帧三元引用（含 engine）解析后逐字保留", async () => {
    const { askQuestion } = await importRealApi();
    const cits = [
      { title: "用户手册 v2.3", spaceName: "产品资料库", engine: "builtin" },
      { title: "Coze 专题", spaceName: "产品资料库", engine: "coze" },
    ];
    vi.mocked(fetch).mockImplementation(
      async () =>
        sseResponse([
          { type: "meta", citations: cits },
          { type: "delta", content: "答案" },
          { type: "done", messageId: "m-engine" },
        ]) as Response
    );

    const answer = await askQuestion("sp-001", "问题");
    expect(answer.citations).toEqual(cits);
    expect(answer.citations[0].engine).toBe("builtin");
    expect(answer.citations[1].engine).toBe("coze");
  });

  it("旧后端未补 engine 的二元引用仍可解析（前向/后向兼容，engine 为可选）", async () => {
    const { askQuestion } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () =>
        sseResponse([
          { type: "meta", citations: [{ title: "旧引用", spaceName: "旧空间" }] },
          { type: "delta", content: "答案" },
          { type: "done" },
        ]) as Response
    );

    const answer = await askQuestion("sp-001", "问题");
    expect(answer.citations).toHaveLength(1);
    expect(answer.citations[0].engine).toBeUndefined();
  });
});
