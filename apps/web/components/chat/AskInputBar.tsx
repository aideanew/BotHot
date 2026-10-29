import { CHAT_COPY } from "@/lib/chat/copy";

/**
 * 提问输入区（R0.6.1 由 app/chat/page.tsx 抽出）
 * 纯展示 + 回调上抛；是否可发送的判断留在调用方（依赖空间选择与回答状态）。
 *
 * STEP-69 / S69.4：`asking` 时按钮从「禁用」改为「停止」。
 * 为什么不是「禁用 + 另加一个停止按钮」：一行里两个按钮，在移动端会把输入框挤到
 * 不可用宽度，而这两个动作**互斥**（回答中只可能想停，不可能想发），一个按钮切换
 * 语义比两个按钮并排更省空间也更少误触。
 * 输入框仍 `disabled={asking}`——禁的是重复发送，不是禁止中止。
 */
export default function AskInputBar({
  value,
  asking,
  canSend,
  onChange,
  onSubmit,
  onStop,
}: {
  value: string;
  /** 回答生成中：输入框禁用、按钮变「停止」 */
  asking: boolean;
  /** 未选中空间等结构性不可发送 */
  canSend: boolean;
  onChange: (value: string) => void;
  onSubmit: (question: string) => void;
  /** 中止进行中的回答（`asking` 时唯一可达的按钮动作） */
  onStop: () => void;
}) {
  const canSubmit = canSend && !!value.trim();
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        // 回车与点击走同一守卫：回答中按回车不重发（按钮此时是 type=button，不进这里）
        if (asking) return;
        onSubmit(value);
      }}
      className="flex items-center gap-3 border-t border-neutral-200 py-3"
    >
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={asking ? "回答生成中，可点「停止」中止…" : "输入问题，例如：如何批量导入文章？"}
        disabled={asking}
        className="flex-1 rounded-input border border-neutral-300 bg-neutral-50 px-4 py-2 text-base outline-none focus:border-brand-500 focus:bg-white disabled:opacity-60"
      />
      {asking ? (
        <button
          type="button"
          onClick={onStop}
          className="shrink-0 rounded-input border border-neutral-300 px-5 py-2 text-base text-neutral-600 hover:border-neutral-400 hover:text-neutral-800"
        >
          {CHAT_COPY.stop}
        </button>
      ) : (
        <button
          type="submit"
          disabled={!canSubmit}
          className="shrink-0 rounded-input bg-brand-500 px-5 py-2 text-white hover:bg-brand-600 disabled:opacity-50"
        >
          发送
        </button>
      )}
    </form>
  );
}
