// 聊天 API 模块：对话 CRUD 使用 axios（请求头由拦截器统一附加）；
// SSE 流式聊天改用原生 fetch + ReadableStream（见 sendMessageStream 内注释，
// 因为 axios 的 onDownloadProgress 存在 333ms 节流与 responseText 流式更新不可靠问题）
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

// --- 流式聊天（使用原生 fetch + ReadableStream，支持 SSE）---

// 回调类型：收到 token / 标题 / 重写中 / 最终版 / 流结束 / 出错
type TokenHandler = (token: string) => void
type TitleHandler = (title: string) => void
type RewritingHandler = () => void
type FinalHandler = (text: string) => void
type DoneHandler = () => void
type ErrorHandler = (message: string) => void

/**
 * 发送消息并通过 SSE 接收流式回复
 *
 * 为什么用 fetch 而不用 axios onDownloadProgress：
 * 1) axios 内部用 throttle(fn, freq=3) 包裹 progress 回调（见 axios 源码
 *    helpers/progressEventReducer.js），即 333ms 最多触发一次，SSE 逐 token
 *    推送远快于此频率，中间 token 会被合并丢弃，导致打字机效果不完整；
 * 2) progress 回调里读取 xhr.responseText 依赖浏览器对 responseType:'text'
 *    的流式响应增量更新 responseText，该行为不可靠（实测只拿到首 token）。
 *    fetch 的 ReadableStream.getReader() 是浏览器标准逐块读取方式，无节流、
 *    逐 token 可靠渲染，是 SSE 流式读取的官方推荐做法。
 *
 * @param convId - 对话 ID
 * @param content - 消息内容
 * @param model - 模型标识（如 ollama-qwen3.5 / qwen3.7-flash）
 * @param thinking - 是否开启深度思考（仅通义千问生效）
 * @param onToken - 收到每个 token 的回调
 * @param onTitle - 收到后端推送的对话标题的回调（首条消息后自动生成）
 * @param onRewriting - 验证未通过进入重写轮的回调（前端显示占位文案）
 * @param onFinal - 收到验证通过后的最终版完整文本的回调
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
  onRewriting: RewritingHandler,
  onFinal: FinalHandler,
  onDone: DoneHandler,
  onError: ErrorHandler,
): AbortController {
  const controller = new AbortController()
  // buffer 保留不完整的最后一行（SSE 按 \n 分行，chunk 可能在行中间截断）
  // 注意：fetch 的 ReadableStream 每次 read() 返回独立 chunk（非累积文本），
  // 直接追加到 buffer 即可，不能用"cursor 取增量"（那是 axios responseText 的做法，
  // 其值随进度累积；若沿用会把后续 chunk 全判成"已处理过"而丢失）
  let buffer = ''
  let finished = false  // 防止 onDone 被多次触发
  // 标记本次中断是否由超时兜底触发（区别于用户主动取消，见 catch 分支）
  let timedOut = false

  const finish = () => {
    if (!finished) {
      finished = true
      onDone()
    }
  }

  // 解析新增的 SSE 文本：追加到 buffer → 拆行 → 提取 data: 行 → JSON 解析
  const handleProgress = (raw: string) => {
    buffer += raw
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
        // 验证未通过进入重写轮：通知前端显示占位文案，避免看到已推的首轮残稿
        if (parsed.rewriting) onRewriting()
        // 验证通过后的最终版完整文本：前端替换占位并打字机渲染
        if (parsed.final) onFinal(parsed.final)
      } catch {
        // 忽略解析失败的行
      }
    }
  }

  // 超时兜底：SSE 是长连接，不能无限等待。60 秒内未结束视为超时，
  // 触发 abort 让下方 catch 分支按超时处理（语义与之前 axios timeout 一致）
  const TIMEOUT_MS = 60000
  const timeoutId = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, TIMEOUT_MS)

  // 手动拼请求头：fetch 不走 axios 拦截器，需自己从 localStorage 附加
  // 用户 ID（与 index.ts 的 axios 拦截器逻辑保持一致），并声明 JSON 请求体
  const uid = localStorage.getItem('agentweb_user_id')
  const baseURL = http.defaults.baseURL  // 复用 axios 实例配置的后端地址
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (uid) headers['X-User-Id'] = uid

  fetch(`${baseURL}/chat/conversations/${convId}/messages`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ content, model, thinking }),
    signal: controller.signal,  // 支持调用方通过 abort() 取消流式请求
  })
    .then(async (res) => {
      // 非 2xx：fetch 不抛异常，需手动读取错误详情（后端统一返回 {"detail": ...}）
      if (!res.ok) {
        let detail = ''
        try {
          const body = await res.json()
          detail = body.detail || ''
        } catch {
          // 响应体不是 JSON（如网关错误页），保持空字符串走兜底文案
        }
        throw new Error(detail || `请求失败（HTTP ${res.status}）`)
      }
      // 取响应体流：这是逐块读取 SSE 的关键入口
      const reader = res.body?.getReader()
      if (!reader) throw new Error('浏览器不支持流式读取')
      const decoder = new TextDecoder('utf-8')
      // 循环读取：每次 read() 返回一块二进制数据，解码成文本后交给解析器
      // （stream: true 表示 chunk 可能截断多字节字符，交由解码器内部缓冲拼接）
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break  // 服务端已发送完整响应体（[DONE] 之后）
        handleProgress(decoder.decode(value, { stream: true }))
      }
      finish()
    })
    .catch((err: Error) => {
      // fetch 的取消/超时统一以 AbortError（name 为 'AbortError'）抛错：
      // 用户主动取消视为正常终止，超时则提示；其余按真实错误弹窗
      if (err.name === 'AbortError') {
        if (timedOut) {
          onError(`timeout of ${TIMEOUT_MS}ms exceeded`)
        }
        finish()
      } else {
        // 网络错误、HTTP 非 2xx 等：透传错误信息（detail 优先）
        onError(err.message)
        finish()
      }
    })
    .finally(() => clearTimeout(timeoutId))

  return controller
}
