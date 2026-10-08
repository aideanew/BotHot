// @vitest-environment happy-dom
/**
 * R0.6.1 —— useSseAsk 问答流状态机
 *
 * 该状态机原内联在 app/chat/page.tsx，**零测试覆盖**：`sendQuestion` 与 `retry`
 * 各持一份约 30 行的 askQuestion 调用与终态映射。抽出为 hook 后第一次可测，
 * 故本文件锁死的状态转移即原实现的契约（行为不变，仅搬家）。
 *
 * 覆盖的不变式：
 * 1. 三道守卫（空串 / 回答进行中 / 未选空间）——静默 no-op，不发请求；
 * 2. id 单调递增且 ask 与 retry 的槽位语义不同（ask 追加两条，retry 复用原槽位）；
 * 3. 流中 error 帧**保留已发 delta**，错误叠加而非替换正文；
 * 4. 会话失效（auth code）触发回落回调且**不残留错误气泡**；
 * 5. abort（切换空间/卸载）静默收敛——流随后返回也不得写入已清空的消息流，
 *    且 `asking` 必须回落（否则输入区永久禁用）；
 * 6. 重试回写**原 answerId**，不新增消息。
 */
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, type ChatAnswer } from "@/lib/api";
import { useSseAsk } from "@/components/chat/useSseAsk";

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
    // 与 lib/api/http.ts 的 isAuthError 同口径（会话失效码）
    isAuthError: (code: number) => code === 10001 || code === 10101,
    askQuestion: h.askQuestion,
  };
});

const answer = (over: Partial<ChatAnswer> = {}): ChatAnswer => ({
  content: "已回答",
  citations: [{ title: "用户手册 v2.3", spaceName: "产品空间", engine: "builtin" }],
  ...over,
});

function setup(opts: { spaceId?: string; onUnauthorized?: () => void } = {}) {
  return renderHook(() =>
    useSseAsk({
      spaceId: opts.spaceId ?? "sp-1",
      onUnauthorized: opts.onUnauthorized ?? h.onUnauthorized,
    })
  );
}

beforeEach(() => {
  h.askQuestion.mockReset();
  h.onUnauthorized.mockReset();
});

describe("R0.6.1 守卫：静默 no-op，不发请求", () => {
  it("空串与纯空白不发送", async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.ask("   ");
    });
    expect(h.askQuestion).not.toHaveBeenCalled();
    expect(result.current.messages).toEqual([]);
    expect(result.current.asking).toBe(false);
  });

  it("未选中空间不发送（输入不被吞掉，用户可保留继续编辑）", async () => {
    const { result } = setup({ spaceId: "" });
    await act(async () => {
      result.current.setInput("有哪些内容？");
    });
    await act(async () => {
      await result.current.ask("有哪些内容？");
    });
    expect(h.askQuestion).not.toHaveBeenCalled();
    expect(result.current.input).toBe("有哪些内容？");
  });

  it("回答进行中不重发（双击防抖）", async () => {
    let release!: (v: ChatAnswer) => void;
    h.askQuestion.mockReturnValue(new Promise((res) => {
      release = res;
    }));
    const { result } = setup();
    await act(async () => {
      void result.current.ask("第一问");
    });
    await act(async () => {
      await result.current.ask("第二问");
    });
    await act(async () => {
      release(answer());
    });
    expect(h.askQuestion).toHaveBeenCalledTimes(1);
    expect(result.current.messages).toHaveLength(2);
  });
});

describe("R0.6.1 成功路径：流式增量 → 终态收敛", () => {
  it("追加用户消息 + 助手消息，id 单调递增，终态写入正文与引用", async () => {
    h.askQuestion.mockImplementation(
      (_space: string, question: string, onChunk: (p: string) => void) => {
        onChunk(`${question}，逐步`);
        onChunk(`${question}，完整`);
        return Promise.resolve(answer({ content: "已回答", citations: [] }));
      }
    );
    const { result } = setup();

    await act(async () => {
      await result.current.ask("如何批量导入？");
    });

    expect(h.askQuestion).toHaveBeenCalledWith(
      "sp-1",
      "如何批量导入？",
      expect.any(Function),
      expect.any(Function),
      { signal: expect.any(AbortSignal) }
    );
    const msgs = result.current.messages;
    expect(msgs).toHaveLength(2);
    expect(msgs[0]).toMatchObject({ id: 1, role: "user", content: "如何批量导入？" });
    expect(msgs[1]).toMatchObject({
      id: 2,
      role: "assistant",
      content: "已回答",
      streaming: false,
    });
    expect(msgs[1].citations).toEqual([]);
    // 发送后清空输入框
    expect(result.current.input).toBe("");
    expect(result.current.asking).toBe(false);
  });

  it("流中 error 帧保留已发 delta：错误叠加展示，正文不被清空", async () => {
    h.askQuestion.mockImplementation((_, __, onChunk: (p: string) => void) => {
      onChunk("已生成的一部分");
      return Promise.resolve(
        answer({
          content: "已生成的一部分",
          citations: [],
          error: { code: 50002, message: "回答生成中断，内容可能不完整，请重试" },
        })
      );
    });
    const { result } = setup();
    await act(async () => {
      await result.current.ask("继续说");
    });

    const m = result.current.messages[1];
    expect(m.content).toBe("已生成的一部分");
    expect(m.error?.text).toBe("回答生成中断，内容可能不完整，请重试");
    expect(m.streaming).toBe(false);
    expect(m.error?.question).toBe("继续说");
  });
});

describe("R0.6.1 失败路径：错误气泡与回落", () => {
  it("会话失效触发回落回调，且不留错误气泡", async () => {
    h.askQuestion.mockRejectedValue(new ApiError(10001, "登录已过期"));
    const { result } = setup();
    await act(async () => {
      await result.current.ask("任意问题");
    });

    expect(h.onUnauthorized).toHaveBeenCalledTimes(1);
    // 不落错误气泡：回落由页面跳回首页承担
    expect(result.current.messages[1].error).toBeUndefined();
    expect(result.current.asking).toBe(false);
  });

  it("非会话失效的 ApiError → 错误气泡，保留原问题供重试", async () => {
    h.askQuestion.mockRejectedValue(new ApiError(30002, "回答生成失败"));
    const { result } = setup();
    await act(async () => {
      await result.current.ask("重试我");
    });

    const m = result.current.messages[1];
    expect(m.content).toBe("");
    expect(m.streaming).toBe(false);
    expect(m.error).toEqual({ text: "回答生成失败", question: "重试我" });
    expect(h.onUnauthorized).not.toHaveBeenCalled();
  });

  it("非 ApiError（网络异常）→ 兜底文案", async () => {
    h.askQuestion.mockRejectedValue(new Error("boom"));
    const { result } = setup();
    await act(async () => {
      await result.current.ask("网络问题");
    });
    expect(result.current.messages[1].error?.text).toBe("回答生成失败，请稍后重试");
  });
});

describe("R0.6.1 retry：复用原槽位，不追加消息", () => {
  async function seedError() {
    h.askQuestion.mockRejectedValue(new ApiError(30002, "回答生成失败"));
    const hook = setup();
    await act(async () => {
      await hook.result.current.ask("原问题");
    });
    return hook;
  }

  it("重试写回原 answerId：消息总数不变，正文被替换", async () => {
    const { result } = await seedError();
    const answerId = result.current.messages[1].id;
    expect(result.current.messages).toHaveLength(2);

    h.askQuestion.mockResolvedValue(answer({ content: "重试成功" }));
    await act(async () => {
      await result.current.retry(answerId);
    });

    expect(h.askQuestion).toHaveBeenLastCalledWith(
      "sp-1",
      "原问题",
      expect.any(Function),
      expect.any(Function),
      { signal: expect.any(AbortSignal) }
    );
    expect(result.current.messages).toHaveLength(2);
    const m = result.current.messages.find((x) => x.id === answerId)!;
    expect(m.content).toBe("重试成功");
    expect(m.error).toBeUndefined();
    expect(m.streaming).toBe(false);
    expect(result.current.asking).toBe(false);
  });

  it("无错误上下文的消息不可重试；正在回答时不可重试", async () => {
    h.askQuestion.mockResolvedValue(answer());
    const { result } = setup();
    await act(async () => {
      await result.current.ask("正常一问");
    });
    h.askQuestion.mockClear();

    await act(async () => {
      await result.current.retry(result.current.messages[1].id);
    });
    expect(h.askQuestion).not.toHaveBeenCalled();
  });

  it("回答进行中重试第二次被守卫拦截（防连续重试双发）", async () => {
    let release!: (v: ChatAnswer) => void;
    h.askQuestion.mockReturnValue(new Promise((res) => {
      release = res;
    }));
    const { result } = setup();
    await act(async () => {
      void result.current.ask("第一问");
    });
    await act(async () => {
      await result.current.retry(result.current.messages[1].id);
    });
    await act(async () => {
      release(answer());
    });
    expect(h.askQuestion).toHaveBeenCalledTimes(1);
  });
});

describe("R0.6.1 reset：切换空间的收敛", () => {
  it("中止进行中的流并清空消息；流随后返回不得再写入", async () => {
    let release!: (v: ChatAnswer) => void;
    h.askQuestion.mockReturnValue(new Promise((res) => {
      release = res;
    }));
    const { result } = setup();

    await act(async () => {
      void result.current.ask("旧会话的问题");
    });
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.asking).toBe(true);

    await act(async () => {
      result.current.reset();
    });
    expect(result.current.messages).toEqual([]);
    expect(result.current.input).toBe("");
    // 流仍挂起：asking 尚未回落（回落发生在挂起请求收敛时的 finally）
    expect(result.current.asking).toBe(true);

    await act(async () => {
      release(answer({ content: "不该出现" }));
    });
    expect(result.current.messages).toEqual([]);
    // 已 abort 的流收敛后 asking 必须回落，否则输入区永久禁用
    expect(result.current.asking).toBe(false);
  });

  it("无进行中请求时 reset 为空操作且不抛错", () => {
    const { result } = setup();
    expect(() => result.current.reset()).not.toThrow();
    expect(result.current.asking).toBe(false);
  });
});
