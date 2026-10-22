import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * STEP-15b S15b.1.1：mock 开关的默认值三态（D-V10-03 代选：默认值翻转）。
 *
 * 翻转前的形状是 `(process.env.NEXT_PUBLIC_API_MOCK ?? "true") !== "false"` ⇒
 * **未设环境变量就是演示数据**。这条默认值骗过的是最不该被骗的人：
 * 打开页面的开发者。`GET /api/v1/bots/tasks` 在真后端下恒 404（STEP-22 证据 3），
 * 而默认 mock 让开发者看到一份正常列表——缺陷被自己的工具链遮蔽。
 * 翻转后：未设 = 真实后端，只有显式 `"true"` 才回到样例数据
 * （开关本身不删，`prebuild` 守卫与 Dockerfile 一行不动，禁改面）。
 *
 * 为什么这里必须 `resetModules` + 重新 import：`MOCK_ENABLED` 是**模块加载时**求值的常量，
 * 同一个模块实例上改 `process.env` 不会改变它——不重导入的"三态测试"只会测到第一次的结果，
 * 三条断言里两条是假的。
 */

async function loadWith(value?: string): Promise<{ MOCK_ENABLED: boolean; MOCK_LABEL: string }> {
  vi.resetModules();
  if (value === undefined) {
    delete process.env.NEXT_PUBLIC_API_MOCK;
  } else {
    process.env.NEXT_PUBLIC_API_MOCK = value;
  }
  // 从 barrel 读：`http.ts` 里那个常量是内部名，公开名由 barrel 别名转出（S15b.2.3 的判据）
  return import("@/lib/api");
}

afterEach(() => {
  delete process.env.NEXT_PUBLIC_API_MOCK;
  vi.resetModules();
});

describe("MOCK 开关默认值三态", () => {
  it("未设环境变量 ⇒ 关闭 mock（打真实后端）", async () => {
    const { MOCK_ENABLED } = await loadWith(undefined);
    expect(MOCK_ENABLED).toBe(false);
  });

  it('显式 "false" ⇒ 关闭 mock', async () => {
    const { MOCK_ENABLED } = await loadWith("false");
    expect(MOCK_ENABLED).toBe(false);
  });

  it('显式 "true" ⇒ 开启 mock（纯 UI 开发与 e2e 数据面的唯一入口）', async () => {
    const { MOCK_ENABLED, MOCK_LABEL } = await loadWith("true");
    expect(MOCK_ENABLED).toBe(true);
    expect(MOCK_LABEL).toBe("演示数据");
  });

  it("其它取值（拼错、空串、1）⇒ 一律按真实后端处理，不静默回到 mock", async () => {
    for (const value of ["", "TRUE", "1", "yes"]) {
      const { MOCK_ENABLED } = await loadWith(value);
      expect(MOCK_ENABLED, `NEXT_PUBLIC_API_MOCK=${JSON.stringify(value)}`).toBe(false);
    }
  });
});
