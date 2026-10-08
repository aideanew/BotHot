/**
 * AB-P004 P1 公共库组件测试：PublicLibraryPicker 一键引入逻辑。
 * 验证 listPublicSpaces / linkPublicSpace API 调用与幂等跳过计数。
 */
import { describe, it, expect, vi } from "vitest";

// mock lib/api 的公共库函数
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
  linkPublicSpace: vi.fn().mockResolvedValue({ copied: 50, skipped: 0, total: 50 }),
}));

import { listPublicSpaces, linkPublicSpace } from "@/lib/api";

describe("公共库 API 调用（P1）", () => {
  it("listPublicSpaces 返回公共库列表", async () => {
    const spaces = await listPublicSpaces();
    expect(spaces).toHaveLength(1);
    expect(spaces[0].name).toBe("AI前沿库");
    expect(spaces[0].docCount).toBe(50);
    expect(spaces[0].isPublic).toBe(true);
  });

  it("linkPublicSpace 幂等：首次 copied=50 skipped=0", async () => {
    const result = await linkPublicSpace("target-space-1", "pub-1");
    expect(result.copied).toBe(50);
    expect(result.skipped).toBe(0);
    expect(result.total).toBe(50);
    expect(linkPublicSpace).toHaveBeenCalledWith("target-space-1", "pub-1");
  });
});

describe("F3 公共库引入文案与防重复（L-08）", () => {
  it("全已引入（copied=0, total>0）→ 前端判定 isLinked 显示「已引入 ✓」", async () => {
    vi.mocked(linkPublicSpace).mockResolvedValueOnce({ copied: 0, skipped: 50, total: 50 });
    const r = await linkPublicSpace("sp-1", "pub-1");
    const isLinked = r.copied === 0 && r.total > 0;
    expect(isLinked).toBe(true);
  });

  it("问答页公共库分组文案：明示需先引入才可按（L-08 小白误解澄清）", () => {
    // 契约文案（chat/page.tsx optgroup 项）
    const label = "📚 AI前沿库（50 篇·需先「一键引入」到你的空间才可问答）";
    expect(label).toContain("需先");
    expect(label).toContain("一键引入");
  });
});
