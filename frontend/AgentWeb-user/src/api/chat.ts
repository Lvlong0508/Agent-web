// 聊天 API 模块：对话 CRUD 与 SSE 流式聊天统一使用 axios（请求头由拦截器统一附加）
import axios, { type AxiosError } from 'axios'
import http from './index'

// --- 对话 CRUD（使用 axios）---

// 创建新对话
export function createConversation() {
  return http.post('/chat/conversations')
}

// 获取对话列表
export function listConversations() {
  return http.get('/chat/conversations')
}

// 删除对话
export function deleteConversation(convId: string) {
  return http.delete(`/chat/conversations/${convId}`)
}

// 获取历史消息
export function getMessages(convId: string) {
  return http.get(`/chat/conversations/${convId}/messages`)
}

// --- 流式聊天（使用 axios onDownloadProgress，支持 SSE）---

// 回调类型：收到 token / 标题 / 流结束 / 出错
type TokenHandler = (token: string) => void
type TitleHandler = (title: string) => void
type DoneHandler = () => void
type ErrorHandler = (message: string) => void

/**
 * 发送消息并通过 SSE 接收流式回复
 * @param convId - 对话 ID
 * @param content - 消息内容
 * @param model - 模型标识（如 ollama-qwen3.5 / qwen3.7-flash）
 * @param thinking - 是否开启深度思考（仅通义千问生效）
 * @param onToken - 收到每个 token 的回调
 * @param onTitle - 收到后端推送的对话标题的回调（首条消息后自动生成）
 * @param onDone - 流结束回调
 * @param onError - 错误回调
 * @returns AbortController - 用于取消请求
 */
export function sendMessageStream(
  convId: string,
  content: string,
  model: string,
  thinking: boolean,
  onToken: TokenHandler,
  onTitle: TitleHandler,
  onDone: DoneHandler,
  onError: ErrorHandler,
): AbortController {
  const controller = new AbortController()
  // cursor 记录已处理的响应文本长度，buffer 保留不完整的最后一行（SSE 按 \n 分行）
  let cursor = 0
  let buffer = ''
  let finished = false  // 防止 onDone 被多次触发

  const finish = () => {
    if (!finished) {
      finished = true
      onDone()
    }
  }

  // 解析新增的 SSE 文本：拆行 → 提取 data: 行 → JSON 解析
  const handleProgress = (raw: string) => {
    const slice = raw.slice(cursor)  // 只处理本次新增的部分
    cursor = raw.length
    buffer += slice
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''  // 保留可能被截断的最后一行，等下次数据补齐

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6)
      if (data === '[DONE]') { finish(); return }
      try {
        const parsed = JSON.parse(data)
        if (parsed.token) onToken(parsed.token)
        // 后端在首条消息时推送生成的对话标题，直接转交前端更新侧边栏
        if (parsed.title) onTitle(parsed.title)
      } catch {
        // 忽略解析失败的行
      }
    }
  }

  http.post(`/chat/conversations/${convId}/messages`, { content, model, thinking }, {
    responseType: 'text',
    signal: controller.signal,
    // SSE 是长连接流式响应：全局实例默认 timeout: 10000 会让超过 10 秒的
    // 长回复中途报 'timeout of 10000ms exceeded'（标题短秒回不触发，
    // 但完整回复往往超过 10 秒）。这里覆盖为 60000（1 分钟）：
    // 保留超时保护兜底（网络挂死不至于无限等待），同时给足长回复时间
    timeout: 60000,
    // 请求头（含 X-User-Id）由 index.ts 的拦截器统一附加，这里不再手动处理
    onDownloadProgress: (progressEvent) => {
      // axios 的 AxiosProgressEvent 没有 currentTarget 属性，真实的浏览器
      // ProgressEvent（含 currentTarget）在 event 字段里。之前误从
      // progressEvent.currentTarget 取 XHR，拿到 undefined → responseText
      // 永远为空 → 前端收不到任何 token，回复一直显示"（无回复）"。
      const evt = progressEvent.event as unknown as ProgressEvent
      const xhr = evt?.currentTarget as unknown as XMLHttpRequest | null
      handleProgress(xhr?.responseText || '')
    },
  }).then(() => {
    finish()
  }).catch((err: AxiosError<{ detail?: string }>) => {
    if (axios.isCancel(err)) {
      // 用户主动取消：视为正常终止，让调用方清理状态
      finish()
    } else {
      // 优先取后端返回的 detail 错误信息
      onError(err.response?.data?.detail || err.message)
      finish()
    }
  })

  return controller
}
