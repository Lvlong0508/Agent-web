// 运行记录领域类型：后端 /agent-runs 响应模型 + 消息多态结构。
// 放共享 types 目录（而非组件目录），API 层与组件层共同引用，避免依赖方向倒置。

// content 的三种形态：普通文本 / 嵌套消息数组 / JSON 对象
export type MessageContent = string | NestedMessage[] | Record<string, unknown>

// 工具调用：assistant 消息声明要调用哪个工具（与 tool 消息的 tool_call_id 一一对应）
export interface ToolCall {
  name: string                    // 工具名（如 list_expenses）
  args: Record<string, unknown>   // 调用参数（如 {"page": 1}）
  id: string                      // 调用 ID（tool 消息的 tool_call_id 与之对应）
}

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
  tool_calls?: ToolCall[]
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
  messages: AgentMessage[]   // 兼容字段（旧记录），前端不再渲染
  // === 三层结构：运行级汇总 + 节点级步骤（对齐 AgentRunResponse）===
  duration_ms: number
  total_input_tokens: number
  total_output_tokens: number
  verdict: string | null     // "pass" | "retry" | "fail" | null
  retry_count: number
  steps: TraceStep[]
}

// Call 级：一次 LLM 或工具调用（对齐 backend models/trace.py TraceCall）
export interface TraceCall {
  call_id: string
  call_type: string          // "llm" | "tool"
  model?: string | null      // llm：模型名
  input_tokens: number
  output_tokens: number
  finish_reason?: string | null  // llm：stop / tool_calls
  tool_name?: string | null  // tool：工具名
  tool_call_id?: string | null   // tool：工具调用 ID
  tool_result?: string | null    // tool：工具结果
  start_time?: string | null
  duration_ms: number
}

// Step 级：一次图节点执行（对齐 backend models/trace.py TraceStep）
export interface TraceStep {
  step_id: string
  node_name: string          // agent / tools / planner / verifier / generate_title
  step_type: string          // entry | planner | agent | tool | verifier | title
  status: string             // success | error | degraded
  start_time?: string | null
  end_time?: string | null
  duration_ms: number
  input?: Record<string, unknown> | null
  output?: Record<string, unknown> | null
  metrics?: Record<string, unknown> | null
  error_info?: Record<string, unknown> | null
  calls: TraceCall[]
}