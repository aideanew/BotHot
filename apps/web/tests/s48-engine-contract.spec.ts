// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * STEP-48 S48.4：引擎域 mock 样例的**运行时键集合守卫**。
 *
 * 编译期的 `satisfies EngineCapability` 只在源码改错时红；这份用例补的是另一半——
 * 运行时真拿到手的数据形状（经 mock 网关 + 解包管道出来的对象）每条恰好 10 个键、
 * 且键集合与契约键集合逐字相同。少了"编译期改不到、运行时会缺键"的那类漂移
 * （例如某处展开/浅拷贝丢键）这里会红。
 *
 * 键集合在测试里**写死**并注明来源——不是再读一次 dto.ts（那会把"源"和"判据"合一，
 * 生成器坏了两边一起错）；判据的价值恰在于与生成物独立。
 */

/** 源 = packages/contracts/src/engine/dto.ts 的 EngineCapability（STEP-46 生成，S48 收口） */
const CONTRACT_KEYS = [
  "activeSource",
  "allowlisted",
  "available",
  "configured",
  "decryptFailed",
  "description",
  "engine",
  "implemented",
  "keyEnv",
  "reason",
] as const;

async function importApi() {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_MOCK", "true");
  return import("@/lib/api");
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

describe("S48 引擎域 mock 键集合守卫", () => {
  it("GET /engines 每条样例恰好 10 个键，键集合与契约逐字相同", async () => {
    const { listEngines } = await importApi();
    const got = await listEngines();
    expect(got.items.length).toBeGreaterThanOrEqual(5);
    for (const item of got.items) {
      const keys = Object.keys(item).sort();
      expect(keys.length, `键数（${item.engine}）：${keys.join(",")}`).toBe(10);
      expect(keys).toEqual([...CONTRACT_KEYS]);
    }
  });

  it("契约键集合本身 10 键（判据自检：写死的清单若与 dto.ts 漂移，这里先红）", async () => {
    // 独立读取生成物对照：dto.ts 是生成文件，import 它拿运行时键不可行（纯类型），
    // 故以文本方式断言 interface 成员行数——10 个字段各占一行，多删一行即红。
    const { readFileSync } = await import("node:fs");
    const { join } = await import("node:path");
    const dto = readFileSync(
      join(process.cwd(), "../../packages/contracts/src/engine/dto.ts"),
      "utf-8"
    );
    const m = dto.match(/export interface EngineCapability \{([\s\S]*?)\n\}/);
    expect(m, "dto.ts 里找不到 EngineCapability").toBeTruthy();
    const fieldLines = (m?.[1] ?? "")
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.endsWith(";") && !l.startsWith("//") && !l.startsWith("*"));
    expect(fieldLines.length).toBe(10);
    expect(fieldLines.map((l) => l.split(":")[0].trim()).sort()).toEqual([
      ...CONTRACT_KEYS,
    ]);
  });
});
