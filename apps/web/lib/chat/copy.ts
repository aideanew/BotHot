/**
 * `/chat` 的产品文案唯一字面量（D-V24-09 / D-V23-19）。
 * 来源：`docs/任务规划V0.12.0/contracts/ux_states.schema.json#x-core-views[/chat 流式问答]`。
 * 产品组件与 spec 一律从本文件导入，不得再写字面量——上一轮（P-146）同一句文案散在
 * `useSseAsk.ts` / `ask-sse-degraded.spec.ts` / `trunk.spec.ts` 三处，改一处漏两处。
 * ⚠ 不能放 `@bothot/contracts`：该包 `emitDeclarationOnly`，spec 无法运行时 import。
 *
 * 为什么 `interrupted` 与 `interruptedPartial` 是两个键而不是一个：
 * 契约 error 态只给一句「连接中断，可重试」；但**已生成部分内容**时，用户最需要知道的是
 * 「你看到的这段可能不完整」，这层信息契约没写、又不能不写（D-V24-04）。
 * 拆成两键是为了让「哪一处用了哪一句」在 diff 里可见——合成一个键就只能靠调用方传参，
 * 而传参的地方一多就又会散回字面量。
 */
export const CHAT_COPY = {
  /** loading：契约原字「思考中…」 */
  thinking: "思考中…",
  /** loading 的可中断入口 */
  stop: "停止",
  /** error：契约原字「连接中断，可重试」 */
  interrupted: "连接中断，可重试",
  /** error：已渲染部分内容时，保留「可能不完整」这条信息（D-V24-04） */
  interruptedPartial: "连接中断，可重试（已生成内容可能不完整）",
  /** degraded：30002 / 50002 */
  degraded: "引擎暂不可用，请稍后重试或换个空间",
  /** degraded：首 token 慢锚 */
  slow: "响应较慢，仍在生成…",
  /** 用户主动停止（不是错误态，见 S69.3） */
  stopped: "已停止",
} as const;

export type ChatCopy = typeof CHAT_COPY;
