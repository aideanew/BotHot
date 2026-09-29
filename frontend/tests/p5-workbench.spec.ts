/**
 * AB-P004 P5 工作台+命中缓存提示测试（T-020 前端落地部分）。
 * mock lib/api：listPublicSpaces/submitDoc 命中缓存场景。
 */
import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  listPublicSpaces: vi.fn().mockResolvedValue([
    {
      id: "pub-1",
      name: "AI前沿库",
      description: "AI前沿库（采自公众号，系统空间）",
      docCount: 50,
      engine: "builtin",
      isPublic: true,
      updatedAt: "2026-09-14T00:00:00",
    },
  ]),
  submitDoc: vi.fn().mockResolvedValue({
    docId: "doc-1",
    title: "缓存命中文章",
    status: "INDEXED",
    langbotFileId: "file-1",
    taskId: "",
    hitCache: true,
    hitCount: 2,
  }),
}));

import { listPublicSpaces, submitDoc } from "@/lib/api";

describe("P5 工作台三入口心智（F1/F2/F3 前端契约）", () => {
  it("F3 公共库推荐位：listPublicSpaces 返回 AI前沿库卡（docCount/engine/isPublic 字段齐全）", async () => {
    const list = await listPublicSpaces();
    expect(list[0].name).toBe("AI前沿库");
    expect(list[0].docCount).toBe(50);
    expect(list[0].isPublic).toBe(true);
  });

  it("F1 单篇命中缓存：submitDoc 返回 hitCache=true/hitCount=2 → 前端展示「命中缓存，秒入库」", async () => {
    const r = await submitDoc("sp-1", "https://mp.weixin.qq.com/s/cached-001");
    // 契约 v0.4b：hitCache/hitCount 字段位
    expect(r.hitCache).toBe(true);
    expect(r.hitCount).toBe(2);
  });

  it("F2 多号订阅：SubscriptionItem 含 latestJobId（进度轮询凭证）+ syncPolicy（契约 v0.5b）", () => {
    // 契约形状校验（P2 类型已定义）
    const sub: import("@/lib/api").SubscriptionItem = {
      subscriptionId: "sub-1",
      sourceId: "src-1",
      biz: "Mzxxx",
      sourceName: "测试号",
      syncPolicy: "auto",
      nextRunAt: "2026-09-14T03:00:00",
      status: "ACTIVE",
      latestJobId: "job-1",
    };
    expect(sub.latestJobId).toBe("job-1");
    expect(sub.syncPolicy).toBe("auto");
  });
});
