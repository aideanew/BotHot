import { engineLabel } from "@/lib/api";
import type { ChatMessage } from "./types";

/**
 * 消息流（R0.6.1 由 app/chat/page.tsx 抽出）
 * 用户气泡右、助手气泡左（含引用与错误/重试）；空态卡提示当前空间。
 * 纯展示 + 回调上抛，不持有状态、不发请求。
 */
export default function ChatMessageList({
  messages,
  currentSpaceName,
  onRetry,
}: {
  messages: ChatMessage[];
  /** 空态提示里的当前空间名（未选中时传占位文案） */
  currentSpaceName: string;
  onRetry: (answerId: number) => void;
}) {
  return (
    <div className="flex-1 space-y-4 overflow-y-auto py-6">
      {messages.length === 0 && (
        <div className="card mx-auto mt-10 max-w-2xl p-10 text-center sm:p-14">
          <p className="text-title-sm font-medium text-neutral-900">
            开始向机器人提问
          </p>
          <p className="mt-3 text-neutral-500">
            机器人将基于「{currentSpaceName}」中的文章回答问题。
          </p>
          <p className="mt-2 text-caption text-neutral-400">
            也可以直接粘贴公众号链接发起文章入库（链接识别将在后续版本完善）。
          </p>
        </div>
      )}

      {messages.map((m) =>
        m.role === "user" ? (
          <div key={m.id} className="flex justify-end">
            <div className="max-w-[80%] rounded-card rounded-br-sm bg-brand-500 px-4 py-2.5 text-white">
              {m.content}
            </div>
          </div>
        ) : (
          <div key={m.id} className="flex justify-start">
            <div className="max-w-[85%] rounded-card rounded-bl-sm border border-neutral-200 bg-white px-4 py-3 shadow-card">
              {m.error ? (
                <div>
                  {/* 流中 error 帧：已生成正文保留，错误叠加展示 */}
                  {m.content && (
                    <p className="whitespace-pre-wrap text-base text-neutral-700">
                      {m.content}
                    </p>
                  )}
                  <p className={m.content ? "mt-3 text-danger" : "text-danger"}>
                    {m.error.text}
                  </p>
                  <button
                    onClick={() => onRetry(m.id)}
                    className="mt-3 rounded-input border border-brand-500 px-3 py-1 text-base text-brand-500 hover:bg-brand-50"
                  >
                    重试
                  </button>
                </div>
              ) : m.content ? (
                <p className="whitespace-pre-wrap text-base text-neutral-700">
                  {m.content}
                </p>
              ) : (
                <p className="text-base text-neutral-400">正在思考…</p>
              )}

              {/* 来源文章引用列表 */}
              {m.citations && m.citations.length > 0 && (
                <div className="mt-3 border-t border-neutral-100 pt-3">
                  <p className="text-caption text-neutral-400">来源文章</p>
                  <ul className="mt-1.5 space-y-1">
                    {m.citations.map((c, i) => (
                      <li key={i} className="text-base text-neutral-500">
                        《{c.title}》 · {c.spaceName}
                        {/* 引用块标 engine（ADR-0004 三元 title/spaceName/engine） */}
                        <span className="ml-2 rounded bg-neutral-100 px-1.5 py-0.5 text-caption text-neutral-500">
                          来源引擎：{engineLabel(c.engine)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )
      )}
    </div>
  );
}
