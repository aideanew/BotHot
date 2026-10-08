import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ARTICLE_URL_MAX_LENGTH, validateArticleUrl } from "../lib/api";

/**
 * 链接解析入库域单测（C-T7，契约 v0.3d/e/f；C-T7R 返工追加 URL 本地预校验与幂等用例）
 * 覆盖：错误码中文映射（10006/20001/20002/20003）与解析预览数据形态。
 * 策略沿用 C-T6：不改生产代码，stubEnv 切真实态 + stub fetch 直测生产实现；
 * mock 态样例直接走 MOCK 分支验证预览数据形态。
 */

async function importRealApi() {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_MOCK", "false");
  return import("@/lib/api");
}

async function importMockApi() {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_MOCK", "true");
  return import("@/lib/api");
}

function jsonEnvelope(data: unknown, code = 0, httpStatus = 200): Response {
  return new Response(
    JSON.stringify({ code, message: code === 0 ? "ok" : "err", data, requestId: "req-t7" }),
    { status: httpStatus, headers: { "content-type": "application/json" } }
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("链接解析错误码映射（真实态信封 → 中文文案）", () => {
  const cases: Array<{ code: number; msg: string }> = [
    { code: 10006, msg: "链接格式不正确" },
    { code: 20001, msg: "非公众号文章，请检查链接" },
    { code: 20002, msg: "网络异常，文章抓取失败" },
    { code: 20003, msg: "内容质量不足，无法入库" },
  ];

  for (const { code, msg } of cases) {
    it(`resolveUrl 信封 code=${code} → "${msg}"`, async () => {
      const { resolveUrl } = await importRealApi();
      vi.mocked(fetch).mockImplementation(async () => jsonEnvelope(null, code) as Response);
      await expect(resolveUrl("https://mp.weixin.qq.com/s/x")).rejects.toMatchObject({
        name: "ApiError",
        code,
        message: msg,
      });
    });
  }

  it("401 归一为 10001 未登录", async () => {
    const { resolveUrl } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () =>
        new Response("unauthorized", { status: 401 }) as Response
    );
    await expect(resolveUrl("https://mp.weixin.qq.com/s/x")).rejects.toMatchObject({
      code: 10001,
      message: "尚未登录或会话已过期",
    });
  });
});

describe("入库提交与状态轮询（契约 v0.3h）", () => {
  it("submitDoc 真实态：POST spaces/{id}/docs 返回 202 形状（taskId 恒空串）", async () => {
    const { submitDoc } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () =>
        jsonEnvelope({
          docId: "doc-1",
          title: "某文章",
          status: "INDEXED",
          langbotFileId: "file-9",
          taskId: "",
        }) as Response
    );

    const data = await submitDoc("sp-001", "https://mp.weixin.qq.com/s/x");
    expect(data).toEqual({
      docId: "doc-1",
      title: "某文章",
      status: "INDEXED",
      langbotFileId: "file-9",
      taskId: "",
    });
    // 请求体形状核对：{url}
    const init = vi.mocked(fetch).mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({
      url: "https://mp.weixin.qq.com/s/x",
    });
  });

  it("pollDocStatus：READY 即收敛（单次）", async () => {
    const { pollDocStatus } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () => jsonEnvelope({ docId: "doc-1", status: "READY", langbotFileId: "f" }) as Response
    );
    const r = await pollDocStatus("sp-001", "doc-1");
    expect(r.status).toBe("READY");
    expect(vi.mocked(fetch).mock.calls.length).toBe(1);
  });

  it("pollDocStatus：INDEXED→READY 两轮收敛，间隔 2s", async () => {
    vi.useFakeTimers();
    try {
      const { pollDocStatus } = await importRealApi();
      // 计数器 mock：首次 INDEXED，其后 READY
      let calls = 0;
      vi.mocked(fetch).mockImplementation(async () => {
        calls += 1;
        return jsonEnvelope(
          { docId: "d", status: calls === 1 ? "INDEXED" : "READY", langbotFileId: "f" }
        ) as Response;
      });
      const ticks: number[] = [];
      const promise = pollDocStatus("sp-001", "d", {
        intervalMs: 2000,
        timeoutMs: 120000,
        onTick: (ms) => ticks.push(ms),
      });
      const assertion = promise.then((r) => {
        expect(r.status).toBe("READY");
        expect(calls).toBe(2);
        expect(ticks.length).toBe(1); // 仅第一轮非 READY 后回调一次
      });
      await vi.advanceTimersByTimeAsync(2100);
      await assertion;
    } finally {
      vi.useRealTimers();
    }
  }, 15_000);

  it("pollDocStatus：120s 超时抛 50101 中文超时文案", async () => {
    vi.useFakeTimers();
    try {
      const { pollDocStatus } = await importRealApi();
      vi.mocked(fetch).mockImplementation(
        async () => jsonEnvelope({ docId: "d", status: "INDEXED", langbotFileId: "f" }) as Response
      );
      const p = pollDocStatus("sp-001", "d", { intervalMs: 2000, timeoutMs: 6000 });
      const expectation = expect(p).rejects.toMatchObject({
        code: 50101,
        message: expect.stringContaining("入库超时"),
      });
      await vi.advanceTimersByTimeAsync(7000);
      await expectation;
    } finally {
      vi.useRealTimers();
    }
  });

  it("pollDocStatus：signal 中止抛 50101 操作已取消", async () => {
    const { pollDocStatus } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () => jsonEnvelope({ docId: "d", status: "INDEXED", langbotFileId: "f" }) as Response
    );
    const signal = { aborted: true };
    await expect(
      pollDocStatus("sp-001", "d", { signal })
    ).rejects.toMatchObject({ code: 50101, message: "操作已取消" });
  });

  it("30003 INGEST_FAILED 映射与低质 20003 严格区分", async () => {
    const { pollDocStatus } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () => jsonEnvelope(null, 30003, 502) as Response
    );
    await expect(pollDocStatus("sp-001", "d")).rejects.toMatchObject({
      code: 30003,
      message: "入库失败，请稍后重试",
    });
  });

  it("10005 REQUEST_INVALID（缺 url/body 校验失败）→ 请求参数不合法", async () => {
    const { submitDoc } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () => jsonEnvelope(null, 10005, 422) as Response
    );
    await expect(submitDoc("sp-001", "https://mp.weixin.qq.com/s/x")).rejects.toMatchObject({
      code: 10005,
      message: "请求参数不合法",
    });
  });

  it("30004 RESOURCE_NOT_FOUND（无效空间）→ 可读 message，禁裸 UUID", async () => {
    const { submitDoc } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () => jsonEnvelope(null, 30004, 404) as Response
    );
    await expect(submitDoc("sp-001", "https://mp.weixin.qq.com/s/x")).rejects.toMatchObject({
      code: 30004,
      message: "知识空间不存在或已删除",
    });
  });

  it("pollDocStatus 默认参数：间隔 1.5s / 次数上限 80 次（SPEC §3.2 裁定）", async () => {
    vi.useFakeTimers();
    try {
      const { pollDocStatus } = await importRealApi();
      let calls = 0;
      vi.mocked(fetch).mockImplementation(async () => {
        calls += 1;
        return jsonEnvelope(
          { docId: "d", status: calls === 1 ? "INDEXED" : "READY", langbotFileId: "f" }
        ) as Response;
      });
      const ticks: number[] = [];
      const promise = pollDocStatus("sp-001", "d", { onTick: (ms) => ticks.push(ms) });
      const assertion = promise.then((r) => {
        expect(r.status).toBe("READY");
        // 1.5s 默认间隔：1.6s 后仅发生两次 fetch（首轮 INDEXED + 次轮 READY）
        expect(calls).toBe(2);
        expect(ticks.length).toBe(1); // 仅首轮非 READY 回调一次
      });
      await vi.advanceTimersByTimeAsync(1600);
      await assertion;
    } finally {
      vi.useRealTimers();
    }
  }, 15_000);

  it("pollDocStatus：次数上限超限抛 50101 超时文案（防轮询风暴双保险）", async () => {
    vi.useFakeTimers();
    try {
      const { pollDocStatus } = await importRealApi();
      vi.mocked(fetch).mockImplementation(
        async () => jsonEnvelope({ docId: "d", status: "INDEXED", langbotFileId: "f" }) as Response
      );
      const p = pollDocStatus("sp-001", "d", { intervalMs: 1000, timeoutMs: 120000, maxAttempts: 3 });
      const expectation = expect(p).rejects.toMatchObject({
        code: 50101,
        message: expect.stringContaining("入库超时"),
      });
      await vi.advanceTimersByTimeAsync(3200);
      await expectation;
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("解析预览数据形态（mock 态契约样例）", () => {
  it("正常样例：extract 返回 v0.3f 完整形态且高质量通过", async () => {
    const { extractUrl } = await importMockApi();
    const data = await extractUrl("https://mp.weixin.qq.com/s/mock-ok-001");
    expect(data).toMatchObject({
      title: expect.any(String),
      author: expect.any(String),
      publishTime: expect.any(String),
      paragraphs: expect.any(Array),
      images: expect.any(Array),
      wordCount: expect.any(Number),
      langbotFormat: expect.any(String),
      qualityScore: expect.any(Number),
      qualityPassed: true,
      qualityReasons: [],
    });
    // 图片项形态：{src, caption}（fmt 内部字段不进契约视图）
    for (const img of data.images) {
      expect(Object.keys(img).sort()).toEqual(["caption", "src"]);
    }
    // 阈值语义：passed=true ⇔ score≥30
    expect(data.qualityScore).toBeGreaterThanOrEqual(30);
  });

  it("低质样例（url 含『低质』）：score<30、passed=false、reasons 非空", async () => {
    const { extractUrl } = await importMockApi();
    const data = await extractUrl("https://mp.weixin.qq.com/s/低质-002");
    expect(data.qualityScore).toBeLessThan(30);
    expect(data.qualityPassed).toBe(false);
    expect(data.qualityReasons.length).toBeGreaterThan(0);
  });

  it("resolve 正常样例：契约字段齐全（title/author/publishTime/content/url/biz）", async () => {
    const { resolveUrl } = await importMockApi();
    const data = await resolveUrl("https://mp.weixin.qq.com/s/mock-ok-001");
    expect(Object.keys(data).sort()).toEqual(
      ["author", "biz", "content", "publishTime", "title", "url"].sort()
    );
  });

  it("resolve mock 态非 http 链接 → 10006 链接格式不正确", async () => {
    const { resolveUrl } = await importMockApi();
    await expect(resolveUrl("不是链接")).rejects.toMatchObject({
      code: 10006,
      message: "链接格式不正确",
    });
  });
});

describe("validateArticleUrl 本地预校验（C-T7R 返工，对齐后端 normalize_article_url 五类 10006）", () => {
  it("空串/纯空白 → 本地 10006，不经过网络", async () => {
    expect(validateArticleUrl("")).toMatchObject({ ok: false, code: 10006 });
    expect(validateArticleUrl("   \t ")).toMatchObject({ ok: false, code: 10006 });
    expect(validateArticleUrl(null)).toMatchObject({ ok: false, code: 10006 });
    expect(validateArticleUrl(undefined)).toMatchObject({ ok: false, code: 10006 });
  });

  it(`超长 >${ARTICLE_URL_MAX_LENGTH} → 本地 10006`, async () => {
    const long = `https://mp.weixin.qq.com/s/${"a".repeat(ARTICLE_URL_MAX_LENGTH)}`;
    const r = validateArticleUrl(long);
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.code).toBe(10006);
      expect(r.message).toContain("超长");
    }
  });

  it("非 http(s) scheme（ftp://mp.weixin.qq.com/s/x）→ 本地 10006", async () => {
    const r = validateArticleUrl("ftp://mp.weixin.qq.com/s/abc");
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.code).toBe(10006);
      expect(r.message).toContain("http(s)");
    }
  });

  it("非白名单域名（https://evil.example.com/s/x）→ 本地 10006", async () => {
    const r = validateArticleUrl("https://evil.example.com/s/abc");
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.code).toBe(10006);
      expect(r.message).toContain("不支持");
    }
  });

  it("含控制字符 → 本地 10006（后端 any(ord<32 or 0x7f) 对齐）", async () => {
    const r = validateArticleUrl("https://mp.weixin.qq.com/s/ab\x00cd");
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.code).toBe(10006);
  });

  it("合法 mp.weixin.qq.com 链接（短链/带 query）→ ok 且 trim 化", async () => {
    const ok1 = validateArticleUrl("  https://mp.weixin.qq.com/s/AbCdEfGh123  ");
    expect(ok1).toMatchObject({
      ok: true,
      url: "https://mp.weixin.qq.com/s/AbCdEfGh123",
    });
    const ok2 = validateArticleUrl(
      "https://mp.weixin.qq.com/s?__biz=MzU0OTkwODU2MA==&mid=2247485000&idx=1&sn=abcdef1234567890"
    );
    expect(ok2.ok).toBe(true);
  });

  it("http（非 https）也在白名单 scheme 内（后端 urlsplit 同语义）", async () => {
    const r = validateArticleUrl("http://mp.weixin.qq.com/s/abc");
    expect(r.ok).toBe(true);
  });
});

describe("同 URL 重复提交幂等语义（契约 v0.3h③：覆盖重走 ingest，202 不报错）", () => {
  it("submitDoc 同 url 同空间两次 → 均 202 不抛错，请求体形状一致", async () => {
    const { submitDoc } = await importRealApi();
    const payload = {
      docId: "doc-1",
      title: "某文章",
      status: "INDEXED",
      langbotFileId: "file-9",
      taskId: "",
    };
    vi.mocked(fetch).mockImplementation(async () => jsonEnvelope(payload) as Response);
    const url = "https://mp.weixin.qq.com/s/x";
    const first = await submitDoc("sp-001", url);
    const second = await submitDoc("sp-001", url);
    expect(first.docId).toBe("doc-1");
    expect(second.docId).toBe("doc-1");
    // 两次请求 body 均 {url}，后端幂等覆盖 → 202 不报错
    const bodies = vi.mocked(fetch).mock.calls.map(
      (c) => JSON.parse((c[1] as RequestInit).body as string) as { url: string }
    );
    expect(bodies).toEqual([{ url }, { url }]);
    expect(vi.mocked(fetch).mock.calls.length).toBe(2);
  });
});
