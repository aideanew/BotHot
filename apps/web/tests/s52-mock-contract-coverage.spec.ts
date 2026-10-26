// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * STEP-52 S52.1：mock 路由 ↔ 契约对照表的**覆盖面守卫**（三条用例）。
 *
 * ① `MOCK_ROUTES` 注册的每条路由都必须在 `MOCK_CONTRACT_MAP` 里有契约类型名——
 *   缺一条即红（"这条路由的样例没有契约约束"），并列出缺失清单。
 * ② 反向：表里登记了但没注册的路由也红（死条目会让覆盖数虚高）。
 * ③ 表与后端权威源 `app/contracts/shapes.py` 的 `MOCK_ROUTE_CONTRACTS` 逐条对名
 *   （只判覆盖面判不住"把类型名换成另一个存在的契约名"这种漂移）。
 *
 * 两侧字符串不同形（注册侧是 RegExp 源串、表侧是后端权威路径串），归一化写在
 * `mock-contract-map.ts` 的 `normalizeRouteKey`——那里注释记着"先换匿名段、再剥首尾锚"
 * 这一步序依赖，反过来会把字符类 `[^/]` 的插入符也删掉，两侧永不相等（假红，实测过）。
 *
 * 先红读数（2026-10-26，@win）：本文件先于 handler satisfies 落地时跑——
 * 引擎 2 条已由 STEP-48 登记，其余 20 条缺失 ⇒ 红，原文见 EVD-V21-52 §S52.1。
 */

async function importMock() {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_MOCK", "true");
  const mod = await import("@/lib/api/mock-routes");
  return mod;
}

async function importMap() {
  return import("@/lib/api/mock-contract-map");
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.reject(new Error("mock 态不该发 fetch")))
  );
});

describe("S52 mock 路由契约覆盖", () => {
  it("MOCK_ROUTES 每条路由都在对照表里（缺失即红，列缺失清单）", async () => {
    const { MOCK_ROUTES } = await importMock();
    const { MOCK_CONTRACT_MAP, normalizeRouteKey } = await importMap();
    const registered = new Set(
      MOCK_ROUTES.map((r) => normalizeRouteKey(r.method, r.pattern.source))
    );
    const mapped = new Set(
      Object.entries(MOCK_CONTRACT_MAP).map(([key]) => {
        // 表键形如 "GET /api/v1/..."，归一其 {named} 段
        const method = key.split(" ")[0];
        const pattern = key.slice(method.length + 1);
        return normalizeRouteKey(method, pattern.replace(/\{[^}]+\}/g, "{seg}"));
      })
    );
    // 三条反坍缩判据（缺一条都可能让"22 条全覆盖"变成假的）：
    // ① 归一后的键数必须等于注册路由数——不相等说明两条路由被归一到同一个键，
    //    其中一条会被另一条的表条目"代签"，缺失清单永远列不出它；
    expect(
      registered.size,
      `归一键数 ${registered.size} 必须等于注册路由数 ${MOCK_ROUTES.length}（有两条路由归一到同一键）`
    ).toBe(MOCK_ROUTES.length);
    // ② 表条目数必须与注册路由数一致（少登记＝漏，多登记＝死条目，死条目另有用例②）；
    expect(MOCK_ROUTES.length, "mock 表路由数必须等于对照表条目数").toBe(
      Object.keys(MOCK_CONTRACT_MAP).length
    );
    // ③ 绝对下限 22（今天 mock 表就是 22 条；将来加路由时这条逼着同步抬，不会静默放行）。
    expect(MOCK_ROUTES.length).toBeGreaterThanOrEqual(22);
    const missing = [...registered].filter((k) => !mapped.has(k));
    expect(missing, `未登记契约的路由：${missing.join("、")}`).toEqual([]);
  });

  it("对照表没有死条目（登记了但 mock 没注册 ⇒ 红）", async () => {
    const { MOCK_ROUTES } = await importMock();
    const { MOCK_CONTRACT_MAP, normalizeRouteKey } = await importMap();
    const registered = new Set(
      MOCK_ROUTES.map((r) => normalizeRouteKey(r.method, r.pattern.source))
    );
    for (const key of Object.keys(MOCK_CONTRACT_MAP)) {
      const method = key.split(" ")[0];
      const pattern = key.slice(method.length + 1).replace(/\{[^}]+\}/g, "{seg}");
      expect(
        registered.has(normalizeRouteKey(method, pattern)),
        `表登记了但 mock 未注册：${key}`
      ).toBe(true);
    }
  });

  it("对照表与后端权威源逐条同名（名对名漂移即红）", async () => {
    const { join } = await import("node:path");
    const { readFileSync } = await import("node:fs");
    const { MOCK_CONTRACT_MAP } = await importMap();
    // 后端是这条对照的唯一权威源（`app/contracts/shapes.py` 的 `MOCK_ROUTE_CONTRACTS`）。
    // 只判"覆盖面"留着一个洞：把某条的类型名改成另一个**同样存在**的契约名，
    // `_AssertTypesExist` 与覆盖面判据都不会红——样例照样 satisfies 一个错的形状。
    // 故在此把表与后端逐条对名（本仓前端测试读源文件的既有口径：cwd 相对路径，
    // vitest 的 `import.meta.url` 在 happy-dom 下是 http 方案，readFileSync 会拒）。
    const py = readFileSync(
      join(process.cwd(), "../../apps/api/app/contracts/shapes.py"),
      "utf-8"
    );
    const start = py.indexOf("MOCK_ROUTE_CONTRACTS: dict[str, str] = {");
    expect(start, "后端权威表必须存在（改名/搬走即红，不许静默跳过）").toBeGreaterThan(-1);
    const body = py.slice(start, py.indexOf("\n}", start));
    const authority = new Map<string, string>();
    for (const m of body.matchAll(/^\s*"([^"]+)"\s*:\s*"([^"]+)"\s*,?\s*$/gm)) {
      authority.set(`${m[1]} -> ${m[2]}`, m[2]);
    }
    const mine = new Map<string, string>(
      Object.entries(MOCK_CONTRACT_MAP).map(([key, name]) => [`${key} -> ${name}`, name])
    );
    expect([...mine.keys()].sort(), "对照表与后端权威表的条目与类型名").toEqual([
      ...authority.keys(),
    ].sort());
    expect(mine.size, "表条目数（少一条就是漏登记）").toBeGreaterThanOrEqual(22);
  });
});
