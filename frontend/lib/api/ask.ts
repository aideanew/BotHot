/**
 * lib/api/ask —— 问答域（C-T4 / C-T4R，契约 v0.4 定稿）
 *
 * 契约：POST /api/v1/chat/ask，SSE `type` 判别单事件流（data-only）：
 *   meta（引用先发）→ delta×N → done；流中 error 帧保留已发 delta；ping 忽略；
 *   流前 4xx 走非流式标准信封回退。
 * onChunk：累积内容回调；onCitations：引用就绪回调；opts.signal：取消（不误报服务器故障）。
 */

import { ERROR_MESSAGES, MOCK_ENABLED, delay, friendlyMessage } from "./http";
import { MOCK_SPACE_DETAILS } from "./mock-data";
import { ApiError, type ChatAnswer, type ChatCitation, type Envelope } from "./types";

/** mock 错误注入：提问含关键词时首轮抛 30002，重试放行（供错误态/重试验收复现） */
const MOCK_FAIL_KEY = "bothot_mock_ask_fail";
const MOCK_FAIL_TRIGGER = "触发错误";

/** mock 预置答案：按空间返回 + 2 条引用 */
function mockAnswer(spaceId: string, question: string): ChatAnswer {
  const space = MOCK_SPACE_DETAILS[spaceId];
  const spaceName = space?.name ?? "当前空间";
  // T1.1.4：引用块三元对齐后端（title/spaceName/engine）；mock 空间无 engine → 回退 builtin
  const engine = space?.engine ?? "builtin";
  return {
    content: `关于「${question}」，已从「${spaceName}」中检索到 2 篇相关文章，综合要点如下：\n\n1. 文章对该问题给出了明确的操作指引，建议按步骤执行；\n2. 相关细节与注意事项在第二篇引用中有补充说明。\n\n如需更具体的操作步骤，可以继续追问。`,
    citations: [
      { title: "用户手册 v2.3", spaceName, engine },
      { title: "常见问题解答（第 4 期）", spaceName, engine },
    ],
  };
}

/**
 * 提问入口：POST /api/v1/chat/ask，body {spaceId, question}（契约 v0.4 定稿）。
 * mock 态：本地伪流式——答案切片回调 onChunk，总时长约 1.2~2.5s；
 * 真实态：v0.4 SSE type 判别单事件流（data-only，无 event: 行）：
 *   meta(引用先发) → delta×N → done；流中 error 帧（保留已发 delta，错误叠加）；
 *   ping 忽略；流前 4xx 标准信封走非流式回退。
 * onChunk：累积内容回调；onCitations：引用就绪回调（meta 帧即触发，供先渲染来源区）。
 * 返回最终回答（content + citations + 可选 error）。
 */
export async function askQuestion(
  spaceId: string,
  question: string,
  onChunk?: (partial: string) => void,
  onCitations?: (citations: ChatCitation[]) => void,
  /** C-T4R：请求取消（页面卸载/切换空间时 abort，不误报为服务器故障） */
  opts?: { signal?: AbortSignal }
): Promise<ChatAnswer> {
  if (MOCK_ENABLED) {
    // 错误注入：带触发词的提问首轮失败，重试放行（重试按钮验收路径）
    if (question.includes(MOCK_FAIL_TRIGGER)) {
      const prev = Number(window.sessionStorage.getItem(MOCK_FAIL_KEY) ?? "0");
      if (prev === 0) {
        window.sessionStorage.setItem(MOCK_FAIL_KEY, "1");
        await delay(600);
        throw new ApiError(30002, ERROR_MESSAGES[30002], `mock-${Date.now()}`);
      }
      window.sessionStorage.removeItem(MOCK_FAIL_KEY);
    }

    const answer = mockAnswer(spaceId, question);
    // 伪流式：全文按 6~10 字切片，间隔 80~140ms，总时长 1.2~2.5s
    const chars = Array.from(answer.content);
    const step = 6 + Math.floor(Math.random() * 5);
    let sent = "";
    for (let i = 0; i < chars.length; i += step) {
      await delay(80 + Math.floor(Math.random() * 60));
      if (!MOCK_ENABLED) return answer; // 中途切换模式时立即收敛
      sent += chars.slice(i, i + step).join("");
      onChunk?.(sent);
    }
    return answer;
  }

  // ---- 真实态：v0.4 定稿解析（type 判别单事件流，data-only） ----
  let res: Response;
  try {
    res = await fetch("/api/v1/chat/ask", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spaceId, question }),
      signal: opts?.signal,
    });
  } catch (err) {
    // 主动取消（卸载/切换空间）：原样上抛，由调用方依 signal 静默处理，
    // 不得将 abort 误报为服务器故障（50002）
    if (opts?.signal?.aborted) throw err;
    throw new ApiError(50002, ERROR_MESSAGES[50002]);
  }

  if (res.status === 401) {
    throw new ApiError(10001, ERROR_MESSAGES[10001]);
  }

  const contentType = res.headers.get("content-type") ?? "";

  // 流前错误（鉴权/参数/无效空间）：标准 4xx + JSON 信封，非流式回退承接
  if (!contentType.includes("text/event-stream")) {
    let body: Envelope<ChatAnswer>;
    try {
      body = (await res.json()) as Envelope<ChatAnswer>;
    } catch {
      throw new Error("响应格式异常，请稍后重试");
    }
    if (body.code !== 0) {
      throw new ApiError(
        body.code,
        friendlyMessage(body.code, body.message),
        body.requestId
      );
    }
    onChunk?.(body.data.content);
    return body.data;
  }

  // SSE 主路径：逐帧 data: <单行JSON>，type 判别
  let content = "";
  let citations: ChatCitation[] = [];
  let streamError: { code: number; message: string } | undefined;
  let doneReceived = false; // done 为终帧：其后不再累积正文（防御协议异常帧）
  const reader = res.body?.getReader();
  if (!reader) throw new ApiError(50002, ERROR_MESSAGES[50002]);
  const decoder = new TextDecoder();
  let buffer = "";

  /** 单行处理：data-only 契约，无 event: 行（抽公共函数供循环与尾部冲刷复用） */
  const processLine = (line: string): void => {
    const trimmed = line.trim();
    if (!trimmed.startsWith("data:")) return; // data-only：无 event: 行
    let evt: {
      type?: string;
      citations?: ChatCitation[];
      content?: string;
      code?: number;
      message?: string;
    };
    try {
      evt = JSON.parse(trimmed.slice(5).trim());
    } catch {
      return; // 非 JSON 帧忽略（协议外噪声不中断流）
    }
    switch (evt.type) {
      case "meta":
        // 引用先发：即触发回调供前端先渲染来源区
        citations = evt.citations ?? [];
        onCitations?.(citations);
        break;
      case "delta":
        // 终态守卫：done 已收到或流中 error 后，不再把后续帧追加进正文
        if (doneReceived || streamError) break;
        content += evt.content ?? "";
        onChunk?.(content);
        break;
      case "error":
        // 流中错误帧（B-T9R）：保留已发 delta，错误叠加；服务端随后关流
        streamError = { code: evt.code ?? 50002, message: evt.message ?? ERROR_MESSAGES[50002] };
        break;
      case "done":
        doneReceived = true;
        break;
      case "ping":
        break; // 心跳忽略
      default:
        break; // 未知类型按前向兼容忽略
    }
  };

  for (;;) {
    let readResult: ReadableStreamReadResult<Uint8Array<ArrayBuffer>>;
    try {
      readResult = await reader.read();
    } catch (err) {
      // abort 触发 reader.read() 拒绝：释放 reader 后原样上抛（非服务器故障）
      void reader.cancel().catch(() => {});
      throw err;
    }
    const { done, value } = readResult;
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      processLine(line);
    }
  }
  // 流正常结束：冲刷 decoder 与尾部 buffer（最后一帧未带换行结尾也不丢失）
  buffer += decoder.decode();
  if (buffer.trim() !== "") {
    processLine(buffer);
  }
  // 流中断防御（C-FRONTEND-HARDENING）：v0.4 契约 done 为终帧，读完流却未收到
  // done 且无 error 帧 → 视为异常中断（后端断流/网络截断），已发 delta 保留并标记错误
  if (!streamError && !doneReceived) {
    if (content !== "") {
      streamError = { code: 50002, message: "回答生成中断，内容可能不完整，请重试" };
    } else if (citations.length > 0) {
      streamError = { code: 50002, message: "回答生成中断，请重新提问" };
    }
    // 完全空流不标记（空回复可能合法，避免误报）
  }
  return { content, citations, error: streamError };
}
