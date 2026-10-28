// @vitest-environment happy-dom
/**
 * STEP-65 U5 —— `ux_states` 对 /chat `degraded` 的要求（原字）：
 * 「30002 LANGBOT_API_ERROR / 50002 ⇒ 回落非流式或提示不可用；超时锚 LLM_FIRST_TOKEN_TIMEOUT
 *   触发时给「响应较慢」而非静默」。
 *
 * 本文件判三件事：
 * ① 30002/50002 走**降级分类**：文案「引擎暂不可用，请稍后重试或换个空间」+ `error.kind = "unavailable"`，
 *    其余错误码维持既有文案映射但带 `kind = "failed"`（契约未给新字的那些不动）；
 * ② 首 token 慢：到锚点（15s，与后端 `LLM_FIRST_TOKEN_TIMEOUT` 默认值同数）仍无首个 delta ⇒ `slow = true`，
 *    由 `ChatMessageList` 渲出「响应较慢，仍在生成…」——**提示，不中断流**；
 * ③ 计时器在收到首个 delta 或进入终态时被清掉，不会在已有正文之后又冒出慢响应提示。
 *
 * 协议不改：本卡禁止改 `lib/api/ask.ts` 的码位映射（卡面第 7 格），分流靠既有 `err.code` 判集合。
 */
import { createElement } from "react";
import { act, cleanup, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  askQuestion: vi.fn(),
  onUnauthorized: vi.fn(),
}));

vi.mock("@/lib/api", () => {
  class ApiError extends Error {
    code: number;
    requestId: string;
    constructor(code: number, message: string, requestId = "") {
      super(message);
      this.name = "ApiError";
      this.code = code;
      this.requestId = requestId;
    }
  }
  return {
    ApiError,
    isAuthError: (code: number) => code === 10001 || code === 10101,
    askQuestion: h.askQuestion,
    engineLabel: (e: string) => e,
  };
});

import ChatMessageList from "@/components/chat/ChatMessageList";
import { useSseAsk } from "@/components/chat/useSseAsk";
import type { ChatMessage } from "@/components/chat/types";

const SLOW_ANCHOR_MS = 15_000;
const DEGRADED_TEXT = "引擎暂不可用，请稍后重试或换个空间";

function setup() {
  return renderHook(() => useSseAsk({ spaceId: "sp-1", onUnauthorized: h.onUnauthorized }));
}

/** 取助手那条消息（ask 追加 user + assistant 两条，assistant 在 index 1） */
function assistant(view: ReturnType<typeof setup>): ChatMessage {
  return view.result.current.messages[1];
}

beforeEach(() => {
  h.askQuestion.mockReset();
  h.onUnauthorized.mockReset();
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("U5 ① 降级码位分流（30002 / 50002）", () => {
  for (const code of [30002, 50002]) {
    it(`${code} ⇒ 契约的不可用文案 + kind="unavailable"`, async () => {
      const { ApiError } = await import("@/lib/api");
      h.askQuestion.mockRejectedValue(new ApiError(code, "引擎侧炸了"));
      const view = setup();

      await act(async () => {
        await view.result.current.ask("问题");
        await Promise.resolve();
      });

      const msg = assistant(view);
      expect(msg.error?.text).toBe(DEGRADED_TEXT);
      expect(msg.error?.kind).toBe("unavailable");
      expect(msg.error?.question).toBe("问题");
      expect(msg.streaming).toBe(false);
    });
  }

  it("其余错误码维持既有文案映射，只补 kind=\"failed\"（不许顺手改码位表）", async () => {
    const { ApiError } = await import("@/lib/api");
    h.askQuestion.mockRejectedValue(new ApiError(50001, "内部错误，请稍后重试"));
    const view = setup();

    await act(async () => {
      await view.result.current.ask("问题");
      await Promise.resolve();
    });

    const msg = assistant(view);
    expect(msg.error?.text).toBe("内部错误，请稍后重试");
    expect(msg.error?.kind).toBe("failed");
  });

  it("非 ApiError（网络炸/解析错）⇒ 兜底文案 + kind=\"failed\"", async () => {
    h.askQuestion.mockRejectedValue(new TypeError("fetch failed"));
    const view = setup();

    await act(async () => {
      await view.result.current.ask("问题");
      await Promise.resolve();
    });

    const msg = assistant(view);
    expect(msg.error?.text).toBe("回答生成失败，请稍后重试");
    expect(msg.error?.kind).toBe("failed");
  });

  it("会话失效仍走回落回调，不得残留错误气泡（既有不变式不许被分流改动破坏）", async () => {
    const { ApiError } = await import("@/lib/api");
    h.askQuestion.mockRejectedValue(new ApiError(10001, "会话失效"));
    const view = setup();

    await act(async () => {
      await view.result.current.ask("问题");
      await Promise.resolve();
    });

    expect(h.onUnauthorized).toHaveBeenCalledTimes(1);
    expect(assistant(view).error).toBeUndefined();
  });

  it("kind 在状态里可见（本卡不渲它，理由见 types.ts 的注释与台账 P-143 第六条）", async () => {
    const msgs: ChatMessage[] = [
      { id: 1, role: "user", content: "问题" },
      {
        id: 2,
        role: "assistant",
        content: "",
        error: { text: DEGRADED_TEXT, question: "问题", kind: "unavailable" },
      },
    ];
    render(
      createElement(ChatMessageList, {
        messages: msgs,
        currentSpaceName: "产品资料库",
        onRetry: () => {},
      })
    );

    // 判的是"降级句子真的进了 DOM"；`kind` 本身由上面那组用例在状态层判，
    // 这里不再为它加一个只有测试在读的 DOM 属性（那才是真循环）。
    expect(screen.getByText(DEGRADED_TEXT)).toBeTruthy();
    expect(screen.queryByText("正在思考…")).toBeNull();
  });
});

describe("U5 ② 首 token 慢：给提示而不是静默", () => {
  it("到 15s 锚点仍无首个 delta ⇒ slow=true，且流未被中断", async () => {
    h.askQuestion.mockImplementation(() => new Promise(() => {})); // 永不返回，也不发 delta
    const view = setup();

    act(() => {
      void view.result.current.ask("问题");
    });
    await act(async () => {
      vi.advanceTimersByTime(SLOW_ANCHOR_MS);
    });

    const msg = assistant(view);
    expect(msg.slow).toBe(true);
    expect(msg.streaming).toBe(true); // 提示不中断流（契约原字是"给「响应较慢」而非静默"）
    expect(msg.error).toBeUndefined();
  });

  it("锚点之前不得出现慢提示（极性：不是把提示常显）", async () => {
    h.askQuestion.mockImplementation(() => new Promise(() => {}));
    const view = setup();

    act(() => {
      void view.result.current.ask("问题");
    });
    await act(async () => {
      vi.advanceTimersByTime(SLOW_ANCHOR_MS - 1);
    });

    expect(assistant(view).slow).toBeFalsy();
  });

  it("首个 delta 在锚点**之前**到达 ⇒ 推进过锚点也不许冒出慢提示（这条才真在判 clearTimeout）", async () => {
    let emit: ((partial: string) => void) | null = null;
    h.askQuestion.mockImplementation(
      (_space: string, _q: string, onDelta: (partial: string) => void) => {
        emit = onDelta;
        return new Promise<never>(() => {});
      }
    );
    const view = setup();

    act(() => {
      void view.result.current.ask("问题");
    });
    await act(async () => {
      emit?.("第一段正文");
      await Promise.resolve();
    });
    expect(assistant(view).content).toBe("第一段正文");

    // 计时器必须已经被取消：删掉 delta 回调里那句 clearTimeout，这一推进就会把
    // 已经出声的会话标成"响应较慢"（复核指出：原先那条从锚点**之后**才发 delta，
    // 计时器早就烧完，删掉 clearTimeout 也照样绿——那是一条不会红的断言）。
    await act(async () => {
      vi.advanceTimersByTime(SLOW_ANCHOR_MS + 1_000);
    });
    expect(assistant(view).slow).toBeFalsy();
  });

  it("渲染层：slow 的助手消息出「响应较慢，仍在生成…」，不 slow 时出既有占位", () => {
    const mk = (slow?: boolean): ChatMessage[] => [
      { id: 1, role: "assistant", content: "", streaming: true, slow },
    ];

    const { unmount } = render(
      createElement(ChatMessageList, {
        messages: mk(true),
        currentSpaceName: "产品资料库",
        onRetry: () => {},
      })
    );
    expect(screen.getByText("响应较慢，仍在生成…")).toBeTruthy();
    expect(screen.queryByText("正在思考…")).toBeNull();
    unmount();

    render(
      createElement(ChatMessageList, {
        messages: mk(false),
        currentSpaceName: "产品资料库",
        onRetry: () => {},
      })
    );
    expect(screen.getByText("正在思考…")).toBeTruthy();
    expect(screen.queryByText("响应较慢，仍在生成…")).toBeNull();
  });
});
