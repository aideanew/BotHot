import { readdirSync, readFileSync } from "node:fs";
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

  it("未登记且未豁免的端点：mock 态抛 50101，而不是回一份看起来正常的空数据", async () => {
    const { listJobs } = await importApi();
    vi.mocked(fetch).mockImplementation(() =>
      Promise.resolve(envelope({ items: [], total: 0, limit: 20, offset: 0 })) as never
    );
    // jobs 在豁免清单里 ⇒ 演示态仍真打后端（不假装成功），这一半先钉住清单生效
    await expect(listJobs()).resolves.toBeDefined();
    expect(vi.mocked(fetch)).toHaveBeenCalled();

    const { request } = await importApi();
    vi.mocked(fetch).mockClear();
    await expect(request("/api/v1/never-heard-of-this")).rejects.toMatchObject({ code: 50101 });
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  });

  it("豁免清单的完整性：lib/api 里每一条字面 /api/v1 路径都必须有归属（表或清单）", async () => {
    const { MOCK_PASSTHROUGH, MOCK_ROUTES } = await import("@/lib/api/mock-routes");
    const files = readdirSync("lib/api")
      .filter((f) => f.endsWith(".ts") && f !== "mock-routes.ts")
      .map((f) => [`lib/api/${f}`, readFileSync(`lib/api/${f}`, "utf-8")] as const);
    const seen = new Set<string>();
    for (const [file, src] of files) {
      for (const m of src.matchAll(/["`](\/api\/v1\/[^"'`\s]*)/g)) {
        // 把 `${encodeURIComponent(x)}` 之类的插值填成一个具体段，得到一条可匹配的样例路径
        const concrete = m[1].replace(/\$\{[^}]*\}/g, "sample").split("?")[0];
        seen.add(concrete);
        const covered =
          MOCK_ROUTES.some((r) => r.pattern.test(concrete)) ||
          MOCK_PASSTHROUGH.some((p) => p.path.test(concrete));
        expect(covered, `${file} 里的 ${m[1]} 既不在表里也不在豁免清单里`).toBe(true);
      }
    }
    // 扫描面非空：读不到任何路径就说明正则或目录假设变了，这条判据会静默恒绿
    expect(seen.size).toBeGreaterThan(10);
  });

  it("已迁移的域文件里不许再留自己的 mock 分支（判源码，不判行为措辞）", async () => {
    // 用 cwd 相对路径：vitest 的 `import.meta.url` 在 happy-dom 下是 http 方案，readFileSync 会拒
    // （"The URL must be of scheme file"）——这条本身就是"探针假设了运行环境形状"的一个样本。
    const source = readFileSync("lib/api/engines.ts", "utf-8");
    expect(source).toContain("export async function listEngines"); // 读到的必须是那个文件，不是空串
    expect(source).not.toContain("MOCK_ENABLED");
    expect(source).not.toContain("mockRequest(");
    expect(source).not.toContain("MOCK_ENGINES");
    for (const file of ["auth.ts", "public-library.ts"]) {
      const src = readFileSync(`lib/api/${file}`, "utf-8");
      expect(src, file).not.toContain("MOCK_ENABLED");
      expect(src, file).not.toContain("mockRequest(");
    }
  });

  it("auth 域迁入后：未登录态在 mock 里也是 10001，且同样零 fetch", async () => {
    const { authMe, authLogout } = await importApi();
    await expect(authMe()).rejects.toMatchObject({ code: 10001 });
    await expect(authLogout()).resolves.toBeUndefined();
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  });

  it("auth 域迁入后：登录标记与 /me 读的是同一把 key", async () => {
    const { mockMarkLoggedIn } = await import("@/lib/api/mock-routes");
    const { authMe } = await importApi();
    mockMarkLoggedIn();
    const me = await authMe();
    expect(me.sub).toBe("mock-user-001");
    expect(me.email).toBe("admin@bothot.local");
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  });

  it("public-library 域迁入后：解包管道照跑（表存的是 {items}，不是裸数组）", async () => {
    const { listPublicSpaces } = await importApi();
    const got = await listPublicSpaces();
    expect(got.map((s) => s.id)).toEqual(["mock-public-ai-001"]);
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  });

  it("auth 的整页跳转仍要判模式，但走唯一谓词口而不是自己算环境变量", async () => {
    const src = readFileSync("lib/api/auth.ts", "utf-8");
    expect(src).not.toContain("NEXT_PUBLIC_API_MOCK");
    expect(src).toContain("isMockMode()");
  });
});
