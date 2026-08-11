import { ref, onMounted } from 'vue'
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

    // 打字机渲染缓冲：token 先攒到 pending，定时器再按帧合并进 content，
    // 避免一次收到大量 token 时整段一次性渲染
    let pending = ''
    let renderTimer = null

    // 把缓冲区的 token 合并进消息内容（每帧调用一次）
    function flushPending() {
      if (!pending) return
      assistantMsg.content += pending
      pending = ''
    }

    // 传入当前选中的模型（selectedModel.value），由后端决定路由到哪个提供商
    abortController = sendMessageStream(
      activeConvId.value,
      text,
      selectedModel.value,
      (token) => { pending += token },
      () => {
        // 流正常结束：立即渲染剩余 token 并复位状态
        if (renderTimer) { clearInterval(renderTimer); renderTimer = null }
        flushPending()
        sending.value = false
        abortController = null
      },
      (errMsg) => {
        // 出错：先渲染已收到的部分，再显示错误文本
        if (renderTimer) { clearInterval(renderTimer); renderTimer = null }
        flushPending()
        error.value = errMsg || ERROR_NETWORK
        assistantMsg.content = assistantMsg.content || ERROR_NETWORK
        sending.value = false
        abortController = null
      },
    )

    // 启动定时器：每 30ms 把 pending 合并进 content，形成逐字打字机效果
    renderTimer = setInterval(flushPending, 30)
  }

  return {
    conversations, activeConvId, loadingList,
    messages, inputText, sending, error, selectedModel,
    newConversation, selectConversation, removeConversation,
    sendMessage, onModelChange,
  }
}
