import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * STEP-15b S15b.2.1/S15b.2.2：统一 mock 拦截表的行为判据。
 *
 * 这张表要解决的不是"少写几个 if"，而是**演示态绕过了自己要展示的那条管道**：
 * 各域自己 `if (MOCK_ENABLED) return 想要的对象` 时，域函数里的解包与归一化
 * （`d.items`、`encodeURIComponent`、信封 code≠0 → ApiError）只在真实路径上被执行过，
 * 于是"演示永远正确"。收进 `request()` 之后同一段代码两边都跑。
 *
 * 因此本文件的三条硬判据都不是"返回了样例"，而是：
 * ① mock 态命中表 ⇒ **一次 fetch 都不发**（发了就说明拦截点没生效，只是碰巧数据对）；
 * ② mock 态命中表 ⇒ 域函数的解包逻辑被执行（`{items, defaultEngine}` 的 items 被正确取出）；
 * ③ 未登记路径 ⇒ 按 `UNREGISTERED_MOCK_MODE` 走，且这个档位是**可读的常量**而不是散落的行为。
 */

async function importApi(mockEnv?: string) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_MOCK", mockEnv ?? "true");
  return import("@/lib/api");
}

function envelope(data: unknown) {
  return new Response(
    JSON.stringify({ code: 0, message: "ok", data, requestId: "req-mock" }),
    { status: 200, headers: { "content-type": "application/json" } }
  );
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.reject(new Error("mock 态不该发 fetch")))
  );
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("统一 mock 拦截表", () => {
  it("命中表的读接口：零 fetch，且解包管道照跑", async () => {
    const { listEngines } = await importApi();
    const got = await listEngines();
    expect(got.defaultEngine).toBe("builtin");
    expect(got.items.map((e) => e.engine)).toEqual([
      "builtin",
      "main-platform",
      "coze",
      "dify",
      "fastgpt",
    ]);
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  });

  it("命中表的写接口：路径参数从表里解出来，body 参与判断", async () => {
    const { patchSpaceEngine } = await importApi();
    const got = await patchSpaceEngine("sp-42", "builtin");
    expect(got).toEqual({ engine: "builtin", engineKbId: "mock-kb-builtin", spaceId: "sp-42" });
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  });

  it("演示态切未开放引擎：按真后端口径拒 10004，而不是静默成功", async () => {
    const { patchSpaceEngine } = await importApi();
    await expect(patchSpaceEngine("sp-42", "coze")).rejects.toMatchObject({ code: 10004 });
  });

  it("未登记路径：迁移期交给真实 fetch（口径是导出的常量，不是散落行为）", async () => {
    const { UNREGISTERED_MOCK_MODE } = await import("@/lib/api/mock-routes");
    expect(["passthrough", "error"]).toContain(UNREGISTERED_MOCK_MODE);
    const { listJobs } = await importApi();
    if (UNREGISTERED_MOCK_MODE === "passthrough") {
      vi.mocked(fetch).mockImplementation(() =>
        Promise.resolve(envelope({ items: [], total: 0, limit: 20, offset: 0 })) as never
      );
      // 任务域从未有 mock 分支：表里没有 ⇒ 不假装成功，真打（这条也钉住 r024 的订阅域口径）
      await expect(listJobs()).resolves.toBeDefined();
      expect(vi.mocked(fetch)).toHaveBeenCalled();
    } else {
      await expect(listJobs()).rejects.toMatchObject({ code: 50101 });
      expect(vi.mocked(fetch)).not.toHaveBeenCalled();
    }
  });

  it("已迁移的域文件里不许再留自己的 mock 分支（判源码，不判行为措辞）", async () => {
    // 用 cwd 相对路径：vitest 的 `import.meta.url` 在 happy-dom 下是 http 方案，readFileSync 会拒
    // （"The URL must be of scheme file"）——这条本身就是"探针假设了运行环境形状"的一个样本。
    const source = readFileSync("lib/api/engines.ts", "utf-8");
    expect(source).toContain("export async function listEngines"); // 读到的必须是那个文件，不是空串
    expect(source).not.toContain("MOCK_ENABLED");
    expect(source).not.toContain("mockRequest(");
    expect(source).not.toContain("MOCK_ENGINES");
  });
});
