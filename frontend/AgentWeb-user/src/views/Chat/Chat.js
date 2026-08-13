import { ref, reactive, onMounted, onUnmounted } from 'vue'
import {
  listConversations,
  createConversation,
  deleteConversation,
  getMessages,
  sendMessageStream,
} from '@/api/chat'
import {
  LOADING,
  ERROR_NETWORK,
  SELECTED_MODEL_KEY,
  DEFAULT_MODEL,
  THINKING_MODE_KEY,
  EMPTY_REPLY,
} from './Text'

export function useChat() {
  const conversations = ref([])
  const activeConvId = ref(null)
  const loadingList = ref(false)
  const messages = ref([])
  const inputText = ref('')
  const sending = ref(false)
  const error = ref('')

  let abortController = null

  // 全局模型选择：从 localStorage 读取，缺省本地 Ollama
  const selectedModel = ref(localStorage.getItem(SELECTED_MODEL_KEY) || DEFAULT_MODEL)

  // 深度思考开关：从 localStorage 读取，默认关闭（加速回复流式输出）
  const thinking = ref(localStorage.getItem(THINKING_MODE_KEY) === 'true')

  // 切换模型时更新响应式状态并持久化到 localStorage，刷新后仍保留选择
  function onModelChange(event) {
    selectedModel.value = event.target.value
    localStorage.setItem(SELECTED_MODEL_KEY, selectedModel.value)
  }

  // 切换思考模式：更新响应式状态并持久化，下次发送消息时随请求体传给后端
  function toggleThinking() {
    thinking.value = !thinking.value
    localStorage.setItem(THINKING_MODE_KEY, String(thinking.value))
  }

  onMounted(async () => {
    loadingList.value = true
    try {
      const res = await listConversations()
      conversations.value = res.data
    } finally {
      loadingList.value = false
    }
  })

  // 组件卸载时取消进行中的流，避免定时器与请求泄漏
  onUnmounted(() => {
    if (abortController) abortController.abort()
  })

  async function newConversation() {
    try {
      const res = await createConversation()
      const conv = res.data
      conversations.value.unshift(conv)
      selectConversation(conv.id)
    } catch {
      error.value = '创建对话失败'
    }
  }

  async function selectConversation(convId) {
    activeConvId.value = convId
    messages.value = []
    error.value = ''
    try {
      const res = await getMessages(convId)
      messages.value = res.data.map(m => ({ role: m.role, content: m.content }))
    } catch {
      error.value = '加载消息失败'
    }
  }

  async function removeConversation(convId) {
    try {
      await deleteConversation(convId)
      conversations.value = conversations.value.filter(c => c.id !== convId)
      if (activeConvId.value === convId) {
        activeConvId.value = null
        messages.value = []
      }
    } catch {
      error.value = '删除失败'
    }
  }

  function sendMessage() {
    const text = inputText.value.trim()
    if (!text || !activeConvId.value || sending.value) return

    sending.value = true
    error.value = ''
    inputText.value = ''

    messages.value.push({ role: 'user', content: text })

    // 用 reactive 创建响应式消息对象：普通对象修改不触发 Vue 渲染，
    // 会导致 token 一直攒到流结束才一次性显示（整段出现）；
    // thinking 标记表示"等待首 token 的思考阶段"，正文出现即清除
    const assistantMsg = reactive({ role: 'assistant', content: '', thinking: true })
    messages.value.push(assistantMsg)

    // 打字机渲染缓冲：token 先进队列，定时器每帧取出一个并入 content，
    // 即使一次收到大量 token 也保证逐字显示（不依赖网络分块时机）
    const pending = []
    let renderTimer = null
    let streamDone = false  // 流是否已结束：结束但队列未空时仍继续逐字渲染

    // 出错时立即排空队列并显示错误（错误场景不追求逐字效果）
    function stopRenderingImmediately() {
      if (renderTimer) { clearInterval(renderTimer); renderTimer = null }
      while (pending.length) assistantMsg.content += pending.shift()
    }

    // 传入当前选中的模型（selectedModel.value），由后端决定路由到哪个提供商
    abortController = sendMessageStream(
      activeConvId.value,
      text,
      selectedModel.value,
      thinking.value,
      (token) => { pending.push(token) },
      (title) => {
        // 首条消息后后端会生成对话标题并实时推送：就地更新侧边栏对应会话，
        // 无需用户手动刷新页面（conversations 是深响应式的，改 title 即触发重渲染）
        const conv = conversations.value.find(c => c.id === activeConvId.value)
        if (conv) conv.title = title
      },
      () => {
        // 流正常结束：只标记结束，剩余 token 交给定时器逐字渲染完
        streamDone = true
      },
      (errMsg) => {
        // 出错：立即渲染已收到的部分并显示错误文本，思考标记一并清除防止卡死
        stopRenderingImmediately()
        assistantMsg.thinking = false
        error.value = errMsg || ERROR_NETWORK
        assistantMsg.content = assistantMsg.content || ERROR_NETWORK
        sending.value = false
        abortController = null
      },
    )

    // 每帧（30ms）从队列取一个 token 写入消息，形成逐字打字机效果；
    // 队列已空且流已结束时清除定时器并复位状态
    renderTimer = setInterval(() => {
      if (pending.length) {
        // 首个 token 到达：思考阶段结束，提示消失（重复置 false 无副作用）
        assistantMsg.thinking = false
        assistantMsg.content += pending.shift()
        return
      }
      if (streamDone) {
        // 流已结束：无论是否有 token 都要清除思考标记（空回复场景兜底），
        // 保证"流结束 = 徽标必消失"这一不变量
        assistantMsg.thinking = false
        // 流结束时仍无正文（零 token 空回复）：写入占位文案，
        // 避免用户看到"消息发出后毫无回复"的静默失败
        if (!assistantMsg.content) assistantMsg.content = EMPTY_REPLY
        clearInterval(renderTimer)
        renderTimer = null
        sending.value = false
        abortController = null
      }
    }, 30)
  }

  return {
    conversations, activeConvId, loadingList,
    messages, inputText, sending, error, selectedModel,
    thinking, toggleThinking,
    newConversation, selectConversation, removeConversation,
    sendMessage, onModelChange,
  }
}
