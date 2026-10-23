import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * S35.4（P-105 / D-V18-08）反证与钉子：fetch 守卫必须真的在岗。
 *
 * 三条判据：
 * ① 基址已钉 http://localhost:3200/（BotHot 前端宿主端口）——主平台 3000 端口
 *    在单测里结构上不可达；
 * ② 未桩的 fetch 直接抛 guard 错误（setup-fetch-guard.ts 安装的底线桩）；
 * ③ 用例自己的 vi.stubGlobal 优先于底线桩——谁声明谁得到。
 *
 * "删一条桩该用例必须红"的极性：第二发若删掉自己的桩，就会撞上第一发的 guard
 * 错误而转红——这一变异读数在 EVD-V18-35 留案（临时删桩 ⇒ 红，还原 ⇒ 绿）。
 */
describe("S35.4 fetch 守卫", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("happy-dom 文档基址钉在 3200，主平台 3000 不可达", () => {
    expect(window.location.origin).toBe("http://localhost:3200");
  });

  it("未桩的 fetch 抛 guard 错误（不是 ECONNREFUSED，也不发网络包）", async () => {
    await expect(fetch("/api/v1/engines")).rejects.toThrow(/S35\.4 fetch-guard/);
  });

  it("用例自己的桩优先于底线桩——删掉这条桩本发必红（撞上 guard）", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("stub-ok", { status: 200 })),
    );

    const res = await fetch("/api/v1/engines");
    expect(res.status).toBe(200);
    await expect(res.text()).resolves.toBe("stub-ok");
  });
});
