// 聊天 API 模块：对话 CRUD 与 SSE 流式聊天统一使用 axios（请求头由拦截器统一附加）
import axios from 'axios'
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
export function deleteConversation(convId) {
  return http.delete(`/chat/conversations/${convId}`)
}

// 获取历史消息
export function getMessages(convId) {
  return http.get(`/chat/conversations/${convId}/messages`)
}

// --- 流式聊天（使用 axios onDownloadProgress，支持 SSE）---

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
  const handleProgress = (raw) => {
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
    // 请求头（含 X-User-Id）由 index.js 的拦截器统一附加，这里不再手动处理
    onDownloadProgress: (progressEvent) => {
      handleProgress(progressEvent.currentTarget.responseText || '')
    },
  }).then(() => {
    finish()
  }).catch((err) => {
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
