/**
 * AB-P004 P4 引擎切换器测试：EngineSwitcher 置灰/确认/切换后显示 engineKbId。
 * mock lib/api：listEngines 返回 5 引擎位（builtin available，SaaS 未配 Key 置灰）；
 * patchSpaceEngine 模拟切换成功。
 */
import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  listEngines: vi.fn().mockResolvedValue({
    defaultEngine: "builtin",
    items: [
      { engine: "builtin", configured: true, available: true, allowlisted: true, keyEnv: "builtin", description: "内置引擎（LangBot 系，默认）" },
      { engine: "main", configured: false, available: false, allowlisted: true, keyEnv: "MAIN_KB_API_KEY", description: "主平台知识库" },
      { engine: "coze", configured: false, available: false, allowlisted: false, keyEnv: "COZE_API_KEY", description: "Coze 知识库 API（SaaS）" },
      { engine: "dify", configured: false, available: false, allowlisted: false, keyEnv: "DIFY_API_KEY", description: "Dify Cloud Knowledge API（SaaS）" },
      { engine: "fastgpt", configured: false, available: false, allowlisted: false, keyEnv: "FASTGPT_API_KEY", description: "FastGPT Cloud Dataset API（SaaS）" },
    ],
  }),
  patchSpaceEngine: vi.fn().mockResolvedValue({
    engine: "main",
    engineKbId: "main-kb-001",
    spaceId: "sp-1",
  }),
}));

import { listEngines, patchSpaceEngine, type EngineItem } from "@/lib/api";

describe("P4 引擎 API（ADR-0004）", () => {
  it("listEngines 返回 5 引擎位，builtin 恒 available", async () => {
    const d = await listEngines();
    expect(d.items.map((e) => e.engine)).toEqual(["builtin", "main", "coze", "dify", "fastgpt"]);
    const builtin = d.items.find((e) => e.engine === "builtin")!;
    expect(builtin.available).toBe(true);
    expect(builtin.configured).toBe(true);
  });

  it("patchSpaceEngine 切换 main 返回 engineKbId（双写）", async () => {
    const r = await patchSpaceEngine("sp-1", "main");
    expect(r.engineKbId).toBe("main-kb-001");
    expect(patchSpaceEngine).toHaveBeenCalledWith("sp-1", "main");
  });

  it("Notion 不在引擎位（按 CMS 对待，ADR-0004 §二）", async () => {
    const d = await listEngines();
    expect(d.items.map((e) => e.engine)).not.toContain("notion");
  });

  it("T5.4 登记态：configured 与 available 可分离，activeSource 显式回报（契约接受登记表来源）", () => {
    // 登记表已登记但该引擎位未实接（ENGINE_IMPLEMENTED=False）：configured 为真、available 仍为假。
    // 该组合在本域合法，前端不得以 available 反推「未配置 Key」。
    const registered: EngineItem = {
      engine: "coze",
      configured: true,
      available: false,
      allowlisted: true,
      keyEnv: "COZE_API_KEY",
      activeSource: "registered",
      decryptFailed: false,
      description: "Coze 知识库 API（SaaS）",
    };
    expect(registered.configured).toBe(true);
    expect(registered.available).toBe(false);
    expect(registered.activeSource).toBe("registered");
    expect(registered.decryptFailed).toBe(false);

    // 旧后端不返回这两字段，须仍可解析（字段可选，不做非空断言）。
    const legacy: EngineItem = {
      engine: "builtin",
      configured: true,
      available: true,
      allowlisted: true,
      keyEnv: "",
      description: "内置引擎（LangBot 系，默认）",
    };
    expect(legacy.activeSource).toBeUndefined();
    expect(legacy.decryptFailed).toBeUndefined();
  });
});
