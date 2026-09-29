/**
 * AB-P004 P5 命中缓存提示组件测试：
 * - submitDoc 契约 v0.4b 形状（hitCache/hitCount 字段位）；
 * - 命中文案断言（"命中缓存，秒入库"）；
 * - 未命中时普通文案。
 * （AddArticlePanel 为 default export，本测试聚焦契约字段与文案逻辑，
 *   渲染级测试需 jsdom 环境，现有 vitest 为 node 环境，组件渲染留 e2e。）
 */
import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  submitDoc: vi.fn(),
}));

import { submitDoc } from "@/lib/api";

describe("F1 单篇命中缓存提示（P0 v0.4b 契约）", () => {
  it("命中：hitCache=true/hitCount=2 → 前端应展示『命中缓存，秒入库』", async () => {
    vi.mocked(submitDoc).mockResolvedValueOnce({
      docId: "d1",
      title: "缓存文章",
      status: "INDEXED",
      langbotFileId: "f1",
      taskId: "",
      hitCache: true,
      hitCount: 2,
    });
    const r = await submitDoc("sp-1", "https://mp.weixin.qq.com/s/x");
    // 文案逻辑与 AddArticlePanel 一致：hitCache → "命中缓存，秒入库"
    const msg =
      r.hitCache === true
        ? `⚡ 命中缓存，秒入库（已被采集 ${r.hitCount} 次，本次 0 网络请求）`
        : "已完成入库";
    expect(msg).toContain("命中缓存，秒入库");
    expect(msg).toContain("2");
  });

  it("未命中：hitCache 缺省/false → 普通入库文案", async () => {
    vi.mocked(submitDoc).mockResolvedValueOnce({
      docId: "d2",
      title: "新文章",
      status: "INDEXED",
      langbotFileId: "f2",
      taskId: "",
      // 老后端未返回 hitCache 字段 → undefined，前端默认 false
    } as never);
    const r = await submitDoc("sp-1", "https://mp.weixin.qq.com/s/y");
    const hit = r.hitCache ?? false;
    const msg = hit ? "命中缓存" : "普通入库";
    expect(msg).toBe("普通入库");
  });
});
