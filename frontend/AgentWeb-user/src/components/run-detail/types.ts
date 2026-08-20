// 运行记录详情组件类型定义：消息多态（string / 数组 / 对象）的统一建模

// content 的三种形态：普通文本 / 嵌套消息数组 / JSON 对象
export type MessageContent = string | NestedMessage[] | Record<string, unknown>

// 嵌套消息（input_verdict 的 content 数组元素，content 通常为字符串）
export interface NestedMessage {
  role: string
  content: string | NestedMessage[]
}

// 顶层消息：带 role 与可选附加字段（未来 tool 消息会用到 name/tool_calls）
export interface AgentMessage {
  role: string
  content: MessageContent
  id?: string
  name?: string
  tool_call_id?: string
  tool_calls?: unknown[]
}

// 一条运行记录（来自 GET /agent-runs 响应项）
export interface AgentRun {
  id: string
  conversation_id: string
  user_id: string
  model: string
  status: string        // "ok" | "error"
  error?: string | null
  trace_id: string
  created_at: string
  messages: AgentMessage[]
}