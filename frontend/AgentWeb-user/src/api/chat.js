// 聊天 API 模块：对话 CRUD 用 axios，流式聊天用原生 fetch

import http from './index'

// API 基础地址（与 http 实例保持同步）
const BASE_URL = 'http://localhost:8000'

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
export function deleteConversation(convId) {
  return http.delete(`/chat/conversations/${convId}`)
}

// 获取历史消息
export function getMessages(convId) {
  return http.get(`/chat/conversations/${convId}/messages`)
}

// --- 流式聊天（使用原生 fetch，支持 SSE）---

/**
 * 发送消息并通过 SSE 接收流式回复
 * @param {string} convId - 对话 ID
 * @param {string} content - 消息内容
 * @param {string} model - 模型标识（如 ollama-qwen3.5 / qwen3.7-flash）
 * @param {boolean} thinking - 是否开启深度思考（仅通义千问生效）
 * @param {function} onToken - 收到每个 token 的回调
 * @param {function} onTitle - 收到后端推送的对话标题的回调（首条消息后自动生成）
 * @param {function} onDone - 流结束回调
 * @param {function} onError - 错误回调
 * @returns {AbortController} - 用于取消请求
 */
export function sendMessageStream(convId, content, model, thinking, onToken, onTitle, onDone, onError) {
  const controller = new AbortController()

  fetch(`${BASE_URL}/chat/conversations/${convId}/messages`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    // 请求体携带 content、模型与思考开关，后端据此路由并决定是否开启思考模式
    body: JSON.stringify({ content, model, thinking }),
    signal: controller.signal,
  }).then(async (response) => {
    if (!response.ok) {
      // 尝试读取错误信息
      const err = await response.json().catch(() => ({}))
      onError(err.detail || `HTTP ${response.status}`)
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''  // 保留不完整的行

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6)
        if (data === '[DONE]') {
          onDone()
          return
        }
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
    // 流正常结束（未收到 [DONE] 时也视为完成）
    onDone()
  }).catch((err) => {
    if (err.name === 'AbortError') {
      // 用户主动取消：视为正常终止，让调用方清理状态
      onDone()
    } else {
      onError(err.message)
    }
  })

  return controller
}
