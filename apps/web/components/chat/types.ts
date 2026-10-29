import type { ChatCitation } from "@/lib/api";

/**
 * 聊天消息模型（R0.6.1 由 app/chat/page.tsx 抽出）
 *
 * 状态机（useSseAsk）与渲染（ChatMessageList）都要读这个类型，
 * 留在页面里会迫使两边各抄一份定义——定义漂移即是缺陷。
 */
export type Role = "user" | "assistant";

export interface ChatMessage {
  id: number;
  role: Role;
  content: string;
  citations?: ChatCitation[];
  /** 该消息（助手回答）发送失败时的错误信息与重试上下文 */
  error?: {
    text: string;
    question: string;
    /**
     * 终态分类（`08` §3.3 规定的形状）：`unavailable` = 引擎侧不可用（30002/50002，
     * 契约的 degraded 态），`failed` = 其余失败。它不改文案映射——非降级码仍走
     * `lib/api` 的既有映射（本卡第 7 格禁止改那张表）。
     * ⚠ 诚实口径：目前**只有 vitest 消费它**（`tests/ask-sse-degraded.spec.ts`），渲染层不读；
     *    本卡禁止改 `e2e/**`，所以"界面上谁用这个分类"是未决项，登台账 P-143 第六条。
     */
    kind?: "unavailable" | "failed";
  };
  /** 流式生成中标记 */
  streaming?: boolean;
  /** 首 token 慢：到 `LLM_FIRST_TOKEN_TIMEOUT` 锚点仍无首个 delta（提示用，不代表流已中断） */
  slow?: boolean;
  /**
   * 用户主动中止（STEP-69 / S69.3）。
   *
   * 与 `error` 的分界是**责任方**：`error` 是「上游/网络出错」，`stopped` 是「我让它停的」。
   * 混成一个字段会让 UI 把用户的主动操作渲染成红色告警，也会让重试入口的守卫
   * 变成「只有出错才给重试」——而停止后想接着问是更常见的诉求。
   * `stopped` 不携带错误文案，只由 `ChatMessageList` 渲染一行中性灰的「已停止」。
   */
  stopped?: boolean;
}
