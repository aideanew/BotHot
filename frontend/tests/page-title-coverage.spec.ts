// @vitest-environment node
import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * 覆盖面守卫：新增页面若忘了接 usePageTitle，页签会退回根 layout 的
 * 「BotHot · 知识空间」，多标签并排时无法分辨当前所在页面。
 *
 * 必须跑在 node 环境——happy-dom 下 import.meta.url 不是 file: scheme，
 * fileURLToPath 直接抛 "The URL must be of scheme file"。
 */
describe("路由页签标题覆盖", () => {
  const appDir = fileURLToPath(new URL("../app", import.meta.url));

  function walk(dir: string): string[] {
    return readdirSync(dir).flatMap((name) => {
      const full = `${dir}/${name}`;
      if (statSync(full).isDirectory()) return walk(full);
      return name === "page.tsx" ? [full] : [];
    });
  }

  it("每个 page.tsx 都调用了 usePageTitle", () => {
    const pages = walk(appDir)
      .map((f) => f.replace(/\\/g, "/"))
      .sort();

    expect(pages.length).toBeGreaterThanOrEqual(10);

    // 匹配**调用**而非 import：只引不用等于漏接
    const missing = pages.filter(
      (f) => !readFileSync(f, "utf8").includes("usePageTitle(")
    );
    expect(missing).toEqual([]);
  });
});
