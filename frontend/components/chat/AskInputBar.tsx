/**
 * 提问输入区（R0.6.1 由 app/chat/page.tsx 抽出）
 * 纯展示 + 回调上抛；是否可发送的判断留在调用方（依赖空间选择与回答状态）。
 */
export default function AskInputBar({
  value,
  asking,
  canSend,
  onChange,
  onSubmit,
}: {
  value: string;
  /** 回答生成中：输入框禁用、按钮变「回答中…」 */
  asking: boolean;
  /** 未选中空间等结构性不可发送 */
  canSend: boolean;
  onChange: (value: string) => void;
  onSubmit: (question: string) => void;
}) {
  const blocked = asking || !canSend;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(value);
      }}
      className="flex items-center gap-3 border-t border-neutral-200 py-3"
    >
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={asking ? "回答生成中，请稍候…" : "输入问题，例如：如何批量导入文章？"}
        disabled={asking}
        className="flex-1 rounded-input border border-neutral-300 bg-neutral-50 px-4 py-2 text-base outline-none focus:border-brand-500 focus:bg-white disabled:opacity-60"
      />
      <button
        type="submit"
        disabled={blocked || !value.trim()}
        className="shrink-0 rounded-input bg-brand-500 px-5 py-2 text-white hover:bg-brand-600 disabled:opacity-50"
      >
        {asking ? "回答中…" : "发送"}
      </button>
    </form>
  );
}
