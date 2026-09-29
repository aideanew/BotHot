"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  listPublicSpaces,
  listSpaces,
  type PublicSpace,
  type Space,
} from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import AskInputBar from "@/components/chat/AskInputBar";
import ChatMessageList from "@/components/chat/ChatMessageList";
import { useSseAsk } from "@/components/chat/useSseAsk";
import { usePageTitle } from "@/components/usePageTitle";

/**
 * 聊天页（C-T4，重写 C-T1 占位壳；R0.6.1 拆分为
 * useSseAsk 状态机 + ChatMessageList / AskInputBar 两个纯展示子件）
 *
 * 本页只保留：空间选择与加载、路由守卫、URL 首问消费、切换空间确认。
 * 流式问答状态机在 useSseAsk（原 sendQuestion/retry 各持一份重复的
 * askQuestion 调用与终态映射，已收敛为单一实现）。
 *
 * 空间选择器 + 消息流（用户右/助手左含引用）+ 多轮会话（内存态）。
 * 首问：URL ?q= 自动填入并即时发送（消费后清除 URL 防刷新重发）。
 * 回答中 loading 禁止重复发送；错误按错误码中文气泡 + 重试；
 * 切换空间需确认（页内模态），确认后清空消息流。
 */
function ChatPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { status } = useAuth();
  usePageTitle("知识问答");

  const [spaces, setSpaces] = useState<Space[]>([]);
  const [publicSpaces, setPublicSpaces] = useState<PublicSpace[]>([]);
  const [spaceId, setSpaceId] = useState("");
  const [switchTarget, setSwitchTarget] = useState<string | null>(null); // 待确认切换的空间 id
  const firstQuestionRef = useRef<string | null>(null);

  const { messages, asking, input, setInput, ask, retry, reset } = useSseAsk({
    spaceId,
    onUnauthorized: () => router.replace("/"),
  });

  // 未登录跳回首页引导卡
  useEffect(() => {
    if (status === "guest") {
      router.replace("/");
    }
  }, [status, router]);

  // 登录态加载空间列表；?q= 记为首问（只记一次）
  useEffect(() => {
    if (status !== "authed") return;
    let cancelled = false;
    listSpaces()
      .then((list) => {
        if (cancelled) return;
        setSpaces(list);
        if (list.length > 0) {
          setSpaceId((prev) => prev || list[0].id);
        }
      })
      .catch(() => {
        // 列表加载失败不阻塞聊天页，选择器显示空态
      });
    // 加载公共库分组（失败不阻塞）
    listPublicSpaces()
      .then((list) => {
        if (!cancelled) setPublicSpaces(list);
      })
      .catch(() => {
        // 公共库加载失败不阻塞问答页
      });
    const q = searchParams.get("q");
    if (q && firstQuestionRef.current === null) {
      firstQuestionRef.current = q;
      setInput(q);
      // 消费后清除 URL，防止刷新重复首问（TopBar 在 /chat 提交新 q 仍会触发）
      router.replace("/chat");
    }
    return () => {
      cancelled = true;
    };
  }, [status, searchParams, router, setInput]);

  // 自动首问：URL 带入的 q 且会话为空时立即发送
  useEffect(() => {
    if (
      status === "authed" &&
      spaceId &&
      firstQuestionRef.current &&
      messages.length === 0 &&
      !asking
    ) {
      const q = firstQuestionRef.current;
      firstQuestionRef.current = null;
      void ask(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, spaceId, messages.length]);

  /** 确认切换空间：中止进行中请求，清空消息流，开启新会话 */
  function confirmSwitch() {
    if (!switchTarget) return;
    reset();
    firstQuestionRef.current = null;
    setSpaceId(switchTarget);
    setSwitchTarget(null);
  }

  // 未登录跳转进行中
  if (status !== "authed") {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <div className="card p-10 text-center text-neutral-500">正在加载…</div>
      </main>
    );
  }

  return (
    <main className="mx-auto flex h-[calc(100vh-4rem)] w-full max-w-4xl flex-col px-4 sm:px-6">
      <div className="flex flex-col gap-2 border-b border-neutral-200 py-4 sm:flex-row sm:items-center">
        <div>
          <p className="eyebrow">ASK YOUR SOURCES</p>
          <h1 className="text-title-sm font-semibold text-neutral-900">知识问答</h1>
        </div>
        <div className="flex flex-1 items-center gap-3 sm:justify-end">
        <label htmlFor="space-select" className="shrink-0 text-base text-neutral-500">
          当前空间
        </label>
        <select
          id="space-select"
          value={spaceId}
          onChange={(e) => {
            if (e.target.value !== spaceId) {
              setSwitchTarget(e.target.value);
            }
          }}
          disabled={asking}
          className="flex-1 rounded-input border border-neutral-300 bg-white px-3 py-1.5 text-base outline-none focus:border-brand-500 disabled:opacity-50"
        >
          {spaces.length === 0 && publicSpaces.length === 0 && (
            <option value="">（暂无可用空间）</option>
          )}
          <optgroup label="我的空间">
            {spaces.length === 0 && <option value="">（暂无）</option>}
            {spaces.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}（{s.docCount} 篇文章）
              </option>
            ))}
          </optgroup>
          {publicSpaces.length > 0 && (
            <optgroup label="公共库">
              {publicSpaces.map((ps) => (
                <option key={ps.id} value="" disabled>
                  📚 {ps.name}（{ps.docCount} 篇·需先「一键引入」到你的空间才可问答）
                </option>
              ))}
            </optgroup>
          )}
        </select>
        </div>
      </div>

      <ChatMessageList
        messages={messages}
        currentSpaceName={spaces.find((s) => s.id === spaceId)?.name ?? "当前空间"}
        onRetry={(id) => void retry(id)}
      />

      <AskInputBar
        value={input}
        asking={asking}
        canSend={!!spaceId}
        onChange={setInput}
        onSubmit={(q) => void ask(q)}
      />

      {/* 切换空间确认模态（页内，非原生 confirm） */}
      {switchTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="card mx-4 w-full max-w-sm p-6">
            <p className="text-title-sm font-medium text-neutral-900">
              切换空间将开启新会话
            </p>
            <p className="mt-2 text-neutral-500">
              当前会话内容将被清空，确定要切换到「
              {spaces.find((s) => s.id === switchTarget)?.name}」吗？
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setSwitchTarget(null)}
                className="rounded-input border border-neutral-300 px-4 py-1.5 text-base text-neutral-500 hover:border-neutral-400 hover:text-neutral-700"
              >
                取消
              </button>
              <button
                onClick={confirmSwitch}
                className="rounded-input bg-brand-500 px-4 py-1.5 text-white hover:bg-brand-600"
              >
                确认切换
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

/**
 * /chat 页面（useSearchParams 需 Suspense 边界以通过静态预渲染）
 */
export default function ChatPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-3xl px-4 py-10 text-center text-neutral-500">
          正在加载…
        </main>
      }
    >
      <ChatPageInner />
    </Suspense>
  );
}
