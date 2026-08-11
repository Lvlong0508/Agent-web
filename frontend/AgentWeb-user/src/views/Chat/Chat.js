import { ref, onMounted, onUnmounted } from 'vue'
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

  // 切换模型时更新响应式状态并持久化到 localStorage，刷新后仍保留选择
  function onModelChange(event) {
    selectedModel.value = event.target.value
    localStorage.setItem(SELECTED_MODEL_KEY, selectedModel.value)
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

    const assistantMsg = { role: 'assistant', content: '' }
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
      (token) => { pending.push(token) },
      () => {
        // 流正常结束：只标记结束，剩余 token 交给定时器逐字渲染完
        streamDone = true
      },
      (errMsg) => {
        // 出错：立即渲染已收到的部分并显示错误文本
        stopRenderingImmediately()
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
        assistantMsg.content += pending.shift()
        return
      }
      if (streamDone) {
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
    newConversation, selectConversation, removeConversation,
    sendMessage, onModelChange,
  }
}
