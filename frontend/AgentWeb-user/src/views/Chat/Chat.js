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

    abortController = sendMessageStream(
      activeConvId.value,
      text,
      (token) => { assistantMsg.content += token },
      () => {
        sending.value = false
        abortController = null
      },
      (errMsg) => {
        error.value = errMsg || ERROR_NETWORK
        assistantMsg.content = assistantMsg.content || ERROR_NETWORK
        sending.value = false
        abortController = null
      },
    )
  }

  return {
    conversations, activeConvId, loadingList,
    messages, inputText, sending, error,
    newConversation, selectConversation, removeConversation,
    sendMessage,
  }
}
