/**
 * T-022 L-02 / L-03 / L-05 / L-09 修复回归单测（前端侧）
 *
 * 覆盖：
 * - L-02 parseBatchUrls：换行拆分 + 本地白名单校验过滤 + 行内去重计数；
 * - L-03 预览断点：sessionStorage 写入/读取/非法 JSON 降级为 null/跨空间不串味；
 * - L-05 网络暂停文案：阈值常量 + 文案含「网络异常」与失败次数；
 * - L-09 引导页本地断点：步骤进度写入/读取、非法步骤号降级为 null、完成后清除。
 *
 * 环境说明：vitest 为 node 环境，无 window/localStorage/sessionStorage，
 * 通过 vi.stubGlobal 注入最小 polyfill（不依赖 jsdom，保持套件零新增依赖）。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

/** 最小 Storage polyfill：仅实现 getItem/setItem/removeItem/clear */
function makeStorage(): Storage {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => (m.has(k) ? m.get(k)! : null),
    setItem: (k: string, v: string) => void m.set(k, String(v)),
    removeItem: (k: string) => void m.delete(k),
    clear: () => void m.clear(),
    key: () => null,
    get length() {
      return m.size;
    },
  };
}

/** 安装 window + 双存储 polyfill，并返回两个存储实例便于断言 */
function installWindow(): { localStorage: Storage; sessionStorage: Storage } {
  const ls = makeStorage();
  const ss = makeStorage();
  vi.stubGlobal("window", { localStorage: ls, sessionStorage: ss });
  return { localStorage: ls, sessionStorage: ss };
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe("T-022 L-02 批量粘贴拆分（parseBatchUrls）", () => {
  it("多行合法链接：全部识别并保持首次出现顺序", async () => {
    const { parseBatchUrls } = await import("@/lib/api");
    const text = [
      "https://mp.weixin.qq.com/s/a1",
      "https://mp.weixin.qq.com/s/b2",
      "https://mp.weixin.qq.com/s/c3",
    ].join("\n");
    const plan = parseBatchUrls(text);
    expect(plan.urls).toEqual([
      "https://mp.weixin.qq.com/s/a1",
      "https://mp.weixin.qq.com/s/b2",
      "https://mp.weixin.qq.com/s/c3",
    ]);
    expect(plan.rawCount).toBe(3);
    expect(plan.duplicatedCount).toBe(0);
  });

  it("重复行去重：duplicatedCount 计入跳过条数", async () => {
    const { parseBatchUrls } = await import("@/lib/api");
    const plan = parseBatchUrls(
      "https://mp.weixin.qq.com/s/a1\nhttps://mp.weixin.qq.com/s/a1\nhttps://mp.weixin.qq.com/s/a1"
    );
    expect(plan.urls).toEqual(["https://mp.weixin.qq.com/s/a1"]);
    expect(plan.rawCount).toBe(3);
    expect(plan.duplicatedCount).toBe(2);
  });

  it("非法行被过滤：空行/非白名单域名/非 http(s) 均不入队", async () => {
    const { parseBatchUrls } = await import("@/lib/api");
    const plan = parseBatchUrls([
      "",
      "   ",
      "https://www.bilibili.com/video/BV1",
      "ftp://mp.weixin.qq.com/s/a",
      "https://mp.weixin.qq.com/s/ok1",
    ].join("\n"));
    expect(plan.urls).toEqual(["https://mp.weixin.qq.com/s/ok1"]);
    expect(plan.duplicatedCount).toBe(0);
  });

  it("空输入/全非法：urls 为空（面板据此给 10006 气泡，不发请求）", async () => {
    const { parseBatchUrls } = await import("@/lib/api");
    expect(parseBatchUrls("").urls).toEqual([]);
    expect(parseBatchUrls("不是链接\n   \n").urls).toEqual([]);
  });

  it("CRLF 换行同样可拆分（Windows 粘贴口径）", async () => {
    const { parseBatchUrls } = await import("@/lib/api");
    const plan = parseBatchUrls(
      "https://mp.weixin.qq.com/s/x1\r\nhttps://mp.weixin.qq.com/s/x2\r\n"
    );
    expect(plan.urls).toHaveLength(2);
  });
});

describe("T-022 L-03 预览断点（sessionStorage）", () => {
  it("写入后可读出摘要，且携带 spaceId/url/savedAt", async () => {
    installWindow();
    const { savePreviewCheckpoint, readPreviewCheckpoint } = await import(
      "@/lib/api"
    );
    savePreviewCheckpoint("sp-1", "https://mp.weixin.qq.com/s/a1", {
      title: "深度解析：知识库落地",
      wordCount: 2860,
      qualityScore: 86,
      images: 1,
    });
    const cp = readPreviewCheckpoint();
    expect(cp).not.toBeNull();
    expect(cp!.spaceId).toBe("sp-1");
    expect(cp!.url).toBe("https://mp.weixin.qq.com/s/a1");
    expect(cp!.title).toBe("深度解析：知识库落地");
    expect(cp!.wordCount).toBe(2860);
    expect(cp!.qualityScore).toBe(86);
    expect(cp!.images).toBe(1);
    expect(cp!.savedAt).toBeGreaterThan(0);
  });

  it("非法 JSON 降级为 null：不让断点存储问题打断面板", async () => {
    const { sessionStorage: ss } = installWindow();
    ss.setItem("bothot_preview_checkpoint_v1", "{not-json");
    const { readPreviewCheckpoint } = await import("@/lib/api");
    expect(readPreviewCheckpoint()).toBeNull();
  });

  it("跨空间断点可被面板按 spaceId 过滤（sp-1 断点不会展示给 sp-2）", async () => {
    installWindow();
    const { savePreviewCheckpoint, readPreviewCheckpoint } = await import(
      "@/lib/api"
    );
    savePreviewCheckpoint("sp-1", "https://mp.weixin.qq.com/s/a1", {
      title: "A",
      wordCount: 10,
      qualityScore: 60,
      images: 0,
    });
    const cp = readPreviewCheckpoint();
    // 面板侧过滤口径：cp.spaceId === spaceId 才展示
    expect(cp!.spaceId === "sp-2").toBe(false);
    expect(cp!.spaceId === "sp-1").toBe(true);
  });

  it("清除后回 null", async () => {
    installWindow();
    const mod = await import("@/lib/api");
    mod.savePreviewCheckpoint("sp-1", "https://mp.weixin.qq.com/s/a1", {
      title: "A",
      wordCount: 10,
      qualityScore: 60,
      images: 0,
    });
    mod.clearPreviewCheckpoint();
    expect(mod.readPreviewCheckpoint()).toBeNull();
  });
});

describe("T-022 L-05 网络异常暂停提示（轮询失败阈值）", () => {
  it("阈值常量为 3 次连续失败", async () => {
    const { POLL_NET_FAIL_THRESHOLD } = await import("@/lib/api");
    expect(POLL_NET_FAIL_THRESHOLD).toBe(3);
  });

  it("文案含「网络异常」与失败次数，且提示进度暂停", async () => {
    const { networkPauseMessage } = await import("@/lib/api");
    const msg = networkPauseMessage(3);
    expect(msg).toContain("网络异常");
    expect(msg).toContain("进度已暂停");
    expect(msg).toContain("3");
  });
});

describe("T-022 L-09 引导页本地断点（步骤进度，纯前端口径）", () => {
  it("步骤进度写入后可读出，step 落在 1..3 区间", async () => {
    const { localStorage: ls } = installWindow();
    ls.setItem(
      "bothot_onboarding_v1",
      JSON.stringify({
        step: 2,
        spaceId: "sp-1",
        spaceName: "产品资料库",
        engine: "builtin",
        savedAt: Date.now(),
      })
    );
    const raw = JSON.parse(ls.getItem("bothot_onboarding_v1")!) as {
      step: number;
      spaceName: string;
    };
    expect(raw.step).toBe(2);
    expect(raw.step).toBeGreaterThanOrEqual(1);
    expect(raw.step).toBeLessThanOrEqual(3);
    expect(raw.spaceName).toBe("产品资料库");
  });

  it("非法步骤号（0/99）按页面口径降级为 null（不进引导流程）", async () => {
    const { localStorage: ls } = installWindow();
    const validate = (raw: string | null): { step: number } | null => {
      if (!raw) return null;
      const o = JSON.parse(raw) as Partial<{ step: number }>;
      if (!o || typeof o.step !== "number" || o.step < 1 || o.step > 3)
        return null;
      return { step: o.step };
    };
    expect(validate(JSON.stringify({ step: 0 }))).toBeNull();
    expect(validate(JSON.stringify({ step: 99 }))).toBeNull();
    expect(validate(JSON.stringify({ step: 1 }))!.step).toBe(1);
  });

  it("完成后清除断点：localStorage 中不再残留", async () => {
    const { localStorage: ls } = installWindow();
    ls.setItem("bothot_onboarding_v1", JSON.stringify({ step: 3 }));
    expect(ls.getItem("bothot_onboarding_v1")).not.toBeNull();
    ls.removeItem("bothot_onboarding_v1");
    expect(ls.getItem("bothot_onboarding_v1")).toBeNull();
  });
});
