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
  error?: { text: string; question: string };
  /** 流式生成中标记 */
  streaming?: boolean;
}
