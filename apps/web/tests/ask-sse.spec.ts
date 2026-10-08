import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * SSE 解析单元测试（C-T7R 步骤②，契约 v0.4 定稿基线）
 *
 * v0.4：POST /api/v1/chat/ask → 200 text/event-stream，每帧 data: <单行JSON>，type 判别：
 *   meta(citations 先发) → delta×N → done；流中 error 帧（保留已发 delta）；
 *   ping 忽略；流前 4xx 走标准信封非流式回退；data-only（无 event: 行）。
 * 策略不变：不改生产代码——stubEnv 切真实态 + stub fetch 直测生产实现。
 */

async function importRealApi() {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_MOCK", "false");
  return import("@/lib/api");
}

/** 构造 SSE 响应：事件数组 → data: 行流 */
function sseResponse(events: unknown[]): Response {
  const text = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  // happy-dom: new Response(text) 的 body 可能是 null，导致 getReader() 失败。
  // 用 ReadableStream 显式包装，保证 jsdom 和 happy-dom 行为一致。
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(text));
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

function jsonEnvelope(data: unknown, code = 0, httpStatus = 200): Response {
  return new Response(
    JSON.stringify({ code, message: code === 0 ? "ok" : "err", data, requestId: "req-v04" }),
    { status: httpStatus, headers: { "content-type": "application/json" } }
  );
}

const CITS = [
  { title: "用户手册 v2.3", spaceName: "产品资料库" },
  { title: "常见问题解答（第 4 期）", spaceName: "产品资料库" },
];

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("v0.4 SSE 解析：正常帧序 meta→delta×N→done", () => {
  it("delta 分片按序拼接并通过 onChunk 累积回调", async () => {
    const { askQuestion } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () =>
        sseResponse([
          { type: "meta", citations: CITS },
          { type: "delta", content: "第一段。" },
          { type: "delta", content: "第二段。" },
          { type: "done", messageId: "m-1" },
        ]) as Response
    );

    const chunks: string[] = [];
    const answer = await askQuestion("sp-001", "问题", (p) => chunks.push(p));

    expect(answer.content).toBe("第一段。第二段。");
    expect(answer.citations).toEqual(CITS);
    expect(answer.error).toBeUndefined();
    expect(chunks).toEqual(["第一段。", "第一段。第二段。"]);
  });

  it("meta 引用先发：onCitations 在 delta 之前即触发", async () => {
    const { askQuestion } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () =>
        sseResponse([
          { type: "meta", citations: CITS },
          { type: "delta", content: "内容" },
          { type: "done", messageId: "m-2" },
        ]) as Response
    );

    const order: string[] = [];
    await askQuestion(
      "sp-001",
      "问题",
      () => order.push("chunk"),
      () => order.push("citations")
    );
    expect(order[0]).toBe("citations"); // 引用先于任何内容回调
  });

  it("空引用 meta 与空内容 delta 均健壮（不产生 undefined 拼接）", async () => {
    const { askQuestion } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () => sseResponse([{ type: "meta" }, { type: "delta" }, { type: "done" }]) as Response
    );

    const answer = await askQuestion("sp-001", "问题");
    expect(answer.content).toBe("");
    expect(answer.citations).toEqual([]);
  });

  it("ping 心跳帧被忽略且不中断流", async () => {
    const { askQuestion } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () =>
        sseResponse([
          { type: "ping" },
          { type: "delta", content: "a" },
          { type: "ping" },
          { type: "delta", content: "b" },
          { type: "done" },
        ]) as Response
    );

    const answer = await askQuestion("sp-001", "问题");
    expect(answer.content).toBe("ab");
  });
});

describe("v0.4 流中 error 帧（B-T9R：AppError 族转 error 帧）", () => {
  it("error 帧保留已发 delta，错误随返回值承载（不抛异常）", async () => {
    const { askQuestion } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () =>
        sseResponse([
          { type: "meta", citations: CITS },
          { type: "delta", content: "已生成部分" },
          { type: "error", code: 30002, message: "机器人服务异常" },
        ]) as Response
    );

    const answer = await askQuestion("sp-001", "问题");
    expect(answer.content).toBe("已生成部分"); // 已发 delta 保留
    expect(answer.citations).toEqual(CITS);
    expect(answer.error).toEqual({ code: 30002, message: "机器人服务异常" });
  });

  it("error 帧缺省 message 时回退 50002 默认文案", async () => {
    const { askQuestion } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () => sseResponse([{ type: "error", code: 30002 }]) as Response
    );

    const answer = await askQuestion("sp-001", "问题");
    expect(answer.error?.message).toBe("依赖服务暂不可用，请稍后重试");
  });
});

describe("C-FRONTEND-HARDENING：SSE 流中断防御（v0.4 契约 done 为终帧）", () => {
  it("读完流未收 done 且已有 delta 内容 → 标记 50002 中断错误，已发内容保留", async () => {
    const { askQuestion } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () =>
        sseResponse([
          { type: "meta", citations: CITS },
          { type: "delta", content: "已生成部分" },
          // 后端断流：无 done、无 error
        ]) as Response
    );

    const answer = await askQuestion("sp-001", "问题");
    expect(answer.content).toBe("已生成部分");
    expect(answer.error?.code).toBe(50002);
    expect(answer.error?.message).toContain("中断");
  });

  it("meta 后断流（无内容无 done）→ 标记 50002 请重试", async () => {
    const { askQuestion } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () => sseResponse([{ type: "meta", citations: CITS }]) as Response
    );

    const answer = await askQuestion("sp-001", "问题");
    expect(answer.content).toBe("");
    expect(answer.error?.code).toBe(50002);
    expect(answer.error?.message).toContain("重新提问");
  });

  it("完全空流（无 meta/delta/done）→ 不标记（空回复可能合法）", async () => {
    const { askQuestion } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () => sseResponse([]) as Response
    );

    const answer = await askQuestion("sp-001", "问题");
    expect(answer.content).toBe("");
    expect(answer.error).toBeUndefined();
  });

  it("正常 done 终帧 → 不触发中断标记", async () => {
    const { askQuestion } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () =>
        sseResponse([
          { type: "meta", citations: CITS },
          { type: "delta", content: "完整回答" },
          { type: "done" },
        ]) as Response
    );

    const answer = await askQuestion("sp-001", "问题");
    expect(answer.content).toBe("完整回答");
    expect(answer.error).toBeUndefined();
  });
});

describe("v0.4 data-only 与前向兼容", () => {
  it("跨 chunk 半包事件缓冲拼接（事件 JSON 被网络分包截断仍完整解析）", async () => {
    const { askQuestion } = await importRealApi();
    // 半包：第一个事件 JSON 被切在 {"type":"delt|a"... 中间
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        const enc = new TextEncoder();
        controller.enqueue(enc.encode('data: {"type":"del'));
        controller.enqueue(enc.encode('ta","content":"前半"}\n\ndata: {"type":"delta","content":"尾"}\n\n'));
        controller.close();
      },
    });
    vi.mocked(fetch).mockImplementation(
      async () =>
        new Response(stream, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }) as Response
    );

    const answer = await askQuestion("sp-001", "问题");
    expect(answer.content).toBe("前半尾");
  });

  it("非 JSON data 行与未知 type 均前向兼容忽略", async () => {
    const { askQuestion } = await importRealApi();
    const text =
      'data: not-json\n\ndata: {"type":"future_event","x":1}\n\ndata: {"type":"delta","content":"ok"}\n\ndata: [DONE]\n\n';
    vi.mocked(fetch).mockImplementation(
      async () =>
        new Response(text, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }) as Response
    );

    const answer = await askQuestion("sp-001", "问题");
    expect(answer.content).toBe("ok");
  });
});

describe("v0.4 流前 4xx 非流式回退", () => {
  it("非 event-stream 响应走信封解包，成功时一次性回调全量", async () => {
    const { askQuestion } = await importRealApi();
    const payload = { content: "完整回答", citations: [{ title: "手册", spaceName: "空间" }] };
    vi.mocked(fetch).mockImplementation(async () => jsonEnvelope(payload) as Response);

    const chunks: string[] = [];
    const answer = await askQuestion("sp-001", "问题", (p) => chunks.push(p));
    expect(answer.content).toBe("完整回答");
    expect(chunks).toEqual(["完整回答"]);
  });

  it("流前错误码位：10001/401、10005/422、30004/404、30002/502 逐码归一", async () => {
    const { askQuestion } = await importRealApi();
    const cases = [
      { code: 10001, http: 401, msg: "尚未登录或会话已过期" },
      { code: 10005, http: 422, msg: "请求参数不合法" },
      { code: 30004, http: 404, msg: "知识空间不存在或已删除" },
      { code: 30002, http: 502, msg: "机器人服务异常，请稍后重试" },
    ];
    for (const c of cases) {
      vi.mocked(fetch).mockImplementation(
        async () => jsonEnvelope(null, c.code, c.http) as Response
      );
      await expect(askQuestion("sp-001", "问题")).rejects.toMatchObject({
        name: "ApiError",
        code: c.code,
        message: c.msg,
      });
    }
  });

  it("网络层异常归一为 50002", async () => {
    const { askQuestion } = await importRealApi();
    vi.mocked(fetch).mockImplementation(() => {
      throw new Error("ECONNREFUSED");
    });
    await expect(askQuestion("sp-001", "问题")).rejects.toMatchObject({
      code: 50002,
    });
  });
});

describe("C-T4R：chunk 边界与资源清理", () => {
  it("CRLF（\\r\\n）行尾正确解析", async () => {
    const { askQuestion } = await importRealApi();
    const text =
      'data: {"type":"meta","citations":[]}\r\n\r\ndata: {"type":"delta","content":"甲"}\r\n\r\ndata: {"type":"delta","content":"乙"}\r\n\r\ndata: {"type":"done"}\r\n\r\n';
    vi.mocked(fetch).mockImplementation(
      async () =>
        new Response(text, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }) as Response
    );
    const answer = await askQuestion("sp-001", "问题");
    expect(answer.content).toBe("甲乙");
    expect(answer.error).toBeUndefined();
  });

  it("多个事件行合并进单个 chunk（含空行噪声）完整解析", async () => {
    const { askQuestion } = await importRealApi();
    const text =
      'data: {"type":"delta","content":"一"}\n\ndata: {"type":"delta","content":"二"}\n\n\n\n   \ndata: {"type":"done"}\n\n';
    vi.mocked(fetch).mockImplementation(
      async () =>
        new Response(text, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }) as Response
    );
    const answer = await askQuestion("sp-001", "问题");
    expect(answer.content).toBe("一二");
  });

  it("reader 正常结束时尾部残留 buffer（末帧无换行结尾）不丢失", async () => {
    const { askQuestion } = await importRealApi();
    const text = 'data: {"type":"delta","content":"末帧"}';
    vi.mocked(fetch).mockImplementation(
      async () =>
        new Response(text, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }) as Response
    );
    const answer = await askQuestion("sp-001", "问题");
    expect(answer.content).toBe("末帧");
  });

  it("done 为终帧：其后异常 delta 帧不再追加正文（单次收敛）", async () => {
    const { askQuestion } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () =>
        sseResponse([
          { type: "delta", content: "正常结尾" },
          { type: "done" },
          { type: "delta", content: "（不应出现的异常帧）" },
        ]) as Response
    );
    const chunks: string[] = [];
    const answer = await askQuestion("sp-001", "问题", (p) => chunks.push(p));
    expect(answer.content).toBe("正常结尾");
    expect(chunks.every((c) => !c.includes("不应出现"))).toBe(true);
  });

  it("流中 error 后异常 delta 帧不再追加，已发 delta 保留", async () => {
    const { askQuestion } = await importRealApi();
    vi.mocked(fetch).mockImplementation(
      async () =>
        sseResponse([
          { type: "delta", content: "已生成部分" },
          { type: "error", code: 30002, message: "机器人服务异常" },
          { type: "delta", content: "（error 后异常帧）" },
        ]) as Response
    );
    const answer = await askQuestion("sp-001", "问题");
    expect(answer.content).toBe("已生成部分"); // 不清空已生成正文
    expect(answer.error?.code).toBe(30002);
    expect(answer.content.includes("异常帧")).toBe(false);
  });

  it("abort：signal 传入 fetch，fetch 拒绝 AbortError 时原样上抛（不误报 50002）", async () => {
    const { askQuestion } = await importRealApi();
    const ctrl = new AbortController();
    let capturedInit: RequestInit | undefined;
    vi.mocked(fetch).mockImplementation(async (_input, init) => {
      capturedInit = init;
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener(
          "abort",
          () => reject(new DOMException("This operation was aborted", "AbortError")),
          { once: true }
        );
      });
    });
    const p = askQuestion("sp-001", "问题", undefined, undefined, { signal: ctrl.signal });
    await new Promise((r) => setTimeout(r, 10));
    ctrl.abort();
    await expect(p).rejects.toMatchObject({ name: "AbortError" });
    expect((capturedInit?.signal as AbortSignal | undefined)?.aborted).toBe(true);
  });

  it("abort：流中读取被中止时 reader.read() 拒绝原样上抛，不转成服务器故障", async () => {
    const { askQuestion } = await importRealApi();
    const ctrl = new AbortController();
    let streamController!: ReadableStreamDefaultController<Uint8Array>;
    vi.mocked(fetch).mockImplementation(async (_input, init) => {
      const enc = new TextEncoder();
      const stream = new ReadableStream<Uint8Array>({
        start(c) {
          streamController = c;
          c.enqueue(enc.encode('data: {"type":"delta","content":"部分"}\n\n'));
        },
      });
      init?.signal?.addEventListener(
        "abort",
        () => streamController.error(new DOMException("aborted", "AbortError")),
        { once: true }
      );
      return new Response(stream, {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      }) as Response;
    });
    const p = askQuestion("sp-001", "问题", undefined, undefined, { signal: ctrl.signal });
    await new Promise((r) => setTimeout(r, 10));
    ctrl.abort();
    await expect(p).rejects.toMatchObject({ name: "AbortError" });
  });
});
