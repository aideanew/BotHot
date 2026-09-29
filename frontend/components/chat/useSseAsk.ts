"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, askQuestion, isAuthError } from "@/lib/api";
import type { ChatMessage } from "./types";

/**
 * useSseAsk —— 问答流状态机（R0.6.1 由 app/chat/page.tsx 抽出）
 *
 * 抽出动因：页面原同时承担数据加载、路由守卫、URL 首问消费与流状态机四种职责，
 * 且 `sendQuestion` 与 `retry` 各持一份约 30 行的 askQuestion 调用与终态映射——
 * 两处已实际重复。抽出后：
 * 1. 重复收敛为单一的 `runQuestion(answerId, question)`，终态映射只有一处，
 *    改错误语义不会只改到一半；
 * 2. 状态机与 DOM 无关，可脱离页面单测——**原实现零测试覆盖**，
 *    这是抽出的主要理由，不只是文件拆分。
 *
 * 行为与原页面实现逐条对齐（不改语义）：守卫顺序、id 单调递增、
 * abort 静默、会话失效回落不落错误气泡、`asking` 在 finally 中回落。
 */
export interface UseSseAskOptions {
  /** 当前空间 id；空串 = 未选中空间，ask 静默 no-op */
  spaceId: string;
  /** 会话失效（401/10001/10101）回调，由页面决定回落方式 */
  onUnauthorized: () => void;
}

export interface UseSseAskResult {
  messages: ChatMessage[];
  asking: boolean;
  input: string;
  setInput: (value: string) => void;
  /** 发送提问；空串 / 回答进行中 / 未选空间 → 静默 no-op */
  ask: (question: string) => Promise<void>;
  /** 重试失败的回答；无错误上下文 / 回答进行中 → 静默 no-op */
  retry: (answerId: number) => Promise<void>;
  /** 中止进行中的流并清空会话（切换空间前调用） */
  reset: () => void;
}

export function useSseAsk({ spaceId, onUnauthorized }: UseSseAskOptions): UseSseAskResult {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [asking, setAsking] = useState(false);
  const idRef = useRef(0);
  // 进行中请求的 AbortController（真实态 fetch/reader 可中断；卸载/切换空间时 abort）
  const streamAbortRef = useRef<AbortController | null>(null);

  // 卸载：中止进行中的问答请求，释放 reader/后端资源
  useEffect(() => {
    return () => {
      streamAbortRef.current?.abort();
    };
  }, []);

  /** 定向更新某条消息（按 id 映射，已不存在的 id 忽略） */
  const patch = useCallback((answerId: number, next: Partial<ChatMessage>) => {
    setMessages((prev) => prev.map((m) => (m.id === answerId ? { ...m, ...next } : m)));
  }, []);

  /**
   * 跑一次提问并写入指定 answerId——ask 与 retry 共用。
   * 终态映射、流中 error 叠加、abort 静默在此单点实现。
   */
  const runQuestion = useCallback(
    async (answerId: number, question: string) => {
      // 新请求独立 AbortController；abort 不视为服务器故障，静默收敛
      const ctrl = new AbortController();
      streamAbortRef.current = ctrl;
      try {
        const answer = await askQuestion(
          spaceId,
          question,
          (partial) => {
            if (ctrl.signal.aborted) return; // abort 后不追加新 delta
            patch(answerId, { content: partial });
          },
          (cits) => {
            if (ctrl.signal.aborted) return;
            // meta 帧先发：引用就绪即先渲染来源区
            patch(answerId, { citations: cits });
          },
          { signal: ctrl.signal }
        );
        if (ctrl.signal.aborted) return; // 已取消：不更新消息
        // 流中 error 帧：保留已发 delta，错误叠加展示（不清空正文）
        patch(answerId, {
          content: answer.content,
          citations: answer.citations,
          error: answer.error ? { text: answer.error.message, question } : undefined,
          streaming: false,
        });
      } catch (err) {
        if (ctrl.signal.aborted) return; // 主动取消：不更新已卸载/已清空的消息流
        if (err instanceof ApiError && isAuthError(err.code)) {
          // 会话失效：回落由页面处理，不残留错误气泡
          onUnauthorized();
          return;
        }
        const text =
          err instanceof ApiError ? err.message : "回答生成失败，请稍后重试";
        patch(answerId, { content: "", streaming: false, error: { text, question } });
      } finally {
        if (streamAbortRef.current === ctrl) {
          streamAbortRef.current = null;
        }
        setAsking(false);
      }
    },
    [spaceId, onUnauthorized, patch]
  );

  /** 发送提问 */
  const ask = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || asking || !spaceId) return;
      setAsking(true);
      setInput("");
      const userId = ++idRef.current;
      const answerId = ++idRef.current;
      setMessages((prev) => [
        ...prev,
        { id: userId, role: "user", content: trimmed },
        { id: answerId, role: "assistant", content: "", streaming: true },
      ]);
      await runQuestion(answerId, trimmed);
    },
    [asking, spaceId, runQuestion]
  );

  /** 重试失败的提问（复用原消息槽位，不追加新消息） */
  const retry = useCallback(
    async (answerId: number) => {
      const msg = messages.find((m) => m.id === answerId);
      if (!msg?.error || asking) return; // asking 守卫：防连续重试双发
      const question = msg.error.question;
      patch(answerId, { error: undefined, content: "", streaming: true });
      setAsking(true);
      await runQuestion(answerId, question);
    },
    [messages, asking, patch, runQuestion]
  );

  /** 中止进行中请求并清空会话（切换空间前调用） */
  const reset = useCallback(() => {
    streamAbortRef.current?.abort(); // 切换空间取消旧请求
    streamAbortRef.current = null;
    setMessages([]);
    setInput("");
  }, []);

  return { messages, asking, input, setInput, ask, retry, reset };
}
