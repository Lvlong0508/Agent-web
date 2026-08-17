import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
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
  VOICE_UNSUPPORTED,
} from './Text'
import { useErrorModal } from '@/composables/useErrorModal'

export function useChat() {
  const conversations = ref([])
  const activeConvId = ref(null)
  const loadingList = ref(false)
  const messages = ref([])
  const inputText = ref('')
  const sending = ref(false)

  // 全局错误弹窗：所有错误不再写入 error ref 渲染气泡，统一走弹窗提示
  const { showError } = useErrorModal()

  // 会话搜索关键字：只在本地过滤列表，不改动后端数据
  const searchQuery = ref('')

  // 侧边栏折叠状态：默认展开，点击标题栏按钮收起/展开，收起后主区占满
  const sidebarCollapsed = ref(false)

  // 切换侧边栏展开/收起状态
  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  // 消息滚动容器 DOM 引用与"回到底部"按钮显隐状态
  const scrollContainer = ref(null)
  const showScrollBtn = ref(false)

  // 语音输入状态：按住空格开始识别，松开结束
  const listening = ref(false)

  let abortController = null

  // 全局模型选择：从 localStorage 读取，缺省本地 Ollama
  const selectedModel = ref(localStorage.getItem(SELECTED_MODEL_KEY) || DEFAULT_MODEL)

  // 深度思考开关：从 localStorage 读取，默认关闭（加速回复流式输出）
  const thinking = ref(localStorage.getItem(THINKING_MODE_KEY) === 'true')

  // 当前会话标题：用于页面顶部展示，会话删除后回退为空
  const currentTitle = computed(() => {
    const conv = conversations.value.find(c => c.id === activeConvId.value)
    return conv ? conv.title : ''
  })

  // 过滤后的会话列表：搜索框为空时原样返回，否则按标题模糊匹配
  const filteredConversations = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return conversations.value
    return conversations.value.filter(c => (c.title || '').toLowerCase().includes(q))
  })

  // 切换模型：更新响应式状态并持久化到 localStorage，刷新后仍保留选择
  function onModelPick(model) {
    selectedModel.value = model
    localStorage.setItem(SELECTED_MODEL_KEY, model)
  }

  // 切换思考模式：更新响应式状态并持久化，下次发送消息时随请求体传给后端
  function toggleThinking() {
    thinking.value = !thinking.value
    localStorage.setItem(THINKING_MODE_KEY, String(thinking.value))
  }

  // 判断当前滚动位置是否接近底部（120px 视为已到底部附近）
  function nearBottom() {
    const el = scrollContainer.value
    if (!el) return true
    return el.scrollHeight - el.scrollTop - el.clientHeight < 120
  }

  // 平滑滚动到消息区底部：先重置位置再平滑滚动，兼容窄内容容器
  function scrollToBottom() {
    const el = scrollContainer.value
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }

  // 滚动事件：离开底部时显示"回到底部"按钮，回到底部自动隐藏
  function onScroll() {
    showScrollBtn.value = !nearBottom()
  }

  // 新消息产生后自动滚动到底部（仅当用户本就在底部时，避免打扰上翻阅读）
  watch(messages, async () => {
    if (nearBottom()) {
      await nextTick()
      scrollToBottom()
    }
  })

  // 语音识别：优先用浏览器原生 Web Speech API，不支持则静默降级为纯文本
  let recognition = null
  let speechFinal = ''
  let voiceWarned = false

  function initRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return
    recognition = new SR()
    recognition.lang = 'zh-CN'
    recognition.continuous = true
    recognition.interimResults = true
    // 识别结果实时回填输入框：最终结果累积，临时结果做占位预览
    recognition.onresult = (e) => {
      let interim = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) speechFinal += e.results[i][0].transcript
        else interim += e.results[i][0].transcript
      }
      inputText.value = speechFinal + interim
    }
    // 识别结束（手动停止或异常中断）时复位状态
    recognition.onend = () => {
      listening.value = false
    }
  }

  // 全局键盘监听：焦点不在输入框时按住空格即可说话，避免干扰打字
  function onGlobalKeyDown(e) {
    const tag = e.target && e.target.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'BUTTON') return
    if (e.code === 'Space' && !e.repeat) {
      e.preventDefault()
      if (recognition) {
        speechFinal = ''
        listening.value = true
        recognition.start()
      } else if (!voiceWarned) {
        // 浏览器不支持语音时只提示一次，避免每次按空格都报错
        voiceWarned = true
        showError(VOICE_UNSUPPORTED)
      }
    }
  }

  function onGlobalKeyUp(e) {
    if (e.code === 'Space' && listening.value && recognition) {
      recognition.stop()
      listening.value = false
    }
  }

  onMounted(async () => {
    initRecognition()
    window.addEventListener('keydown', onGlobalKeyDown)
    window.addEventListener('keyup', onGlobalKeyUp)
    loadingList.value = true
    try {
      const res = await listConversations()
      conversations.value = res.data
    } finally {
      loadingList.value = false
    }
  })

  // 组件卸载时取消进行中的流、停止语音识别并移除全局键盘监听
  onUnmounted(() => {
    if (abortController) abortController.abort()
    if (recognition) recognition.abort()
    window.removeEventListener('keydown', onGlobalKeyDown)
    window.removeEventListener('keyup', onGlobalKeyUp)
  })

  async function newConversation() {
    try {
      const res = await createConversation()
      const conv = res.data
      conversations.value.unshift(conv)
      selectConversation(conv.id)
    } catch {
      showError('创建对话失败')
    }
  }

  async function selectConversation(convId) {
    activeConvId.value = convId
    messages.value = []
    try {
      const res = await getMessages(convId)
      messages.value = res.data.map(m => ({ role: m.role, content: m.content }))
    } catch {
      showError('加载消息失败')
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
      showError('删除失败')
    }
  }

  function sendMessage() {
    const text = inputText.value.trim()
    if (!text || !activeConvId.value || sending.value) return

    sending.value = true
    inputText.value = ''

    messages.value.push({ role: 'user', content: text })

    // 用 reactive 创建响应式消息对象：普通对象修改不触发 Vue 渲染，
    // 会导致 token 一直攒到流结束才一次性显示（整段出现）；
    // thinking 标记表示"等待首 token 的思考阶段"，正文出现即清除；
    // thinkSeconds 为思考阶段已等待的秒数，用于"正在思考"倒计时提示
    const assistantMsg = reactive({ role: 'assistant', content: '', thinking: true, thinkSeconds: 0 })
    messages.value.push(assistantMsg)

    // 打字机渲染缓冲：token 先进队列，定时器每帧取出一个并入 content，
    // 即使一次收到大量 token 也保证逐字显示（不依赖网络分块时机）
    const pending = []
    let renderTimer = null
    let streamDone = false  // 流是否已结束：结束但队列未空时仍继续逐字渲染
    let thinkTimer = null   // 思考倒计时定时器：每秒为 thinking 中的消息 +1s

    // 思考倒计时：进入思考阶段后每秒累加，等待时长可视化
    thinkTimer = setInterval(() => {
      if (assistantMsg.thinking) assistantMsg.thinkSeconds += 1
    }, 1000)

    // 出错时立即排空渲染队列：不等待打字机逐字效果，直接完成已收内容的渲染
    function stopRenderingImmediately() {
      if (renderTimer) { clearInterval(renderTimer); renderTimer = null }
      if (thinkTimer) { clearInterval(thinkTimer); thinkTimer = null }
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
        // 验证未通过进入重写轮：清空已渲染的首轮残稿与待渲染队列，
        // 复用"正在思考"样式（含点点动画与秒数倒计时），等 final 事件送达最终版
        pending.length = 0
        assistantMsg.content = ''
        assistantMsg.thinking = true
        assistantMsg.thinkSeconds = 0
        // 首轮的倒计时定时器已在首个 token 到达时清除（见 renderTimer），这里需重启
        thinkTimer = setInterval(() => {
          if (assistantMsg.thinking) assistantMsg.thinkSeconds += 1
        }, 1000)
      },
      (text) => {
        // 验证通过收到最终版：清空占位，逐字放入渲染队列保持打字机效果。
        // 最终版内容不再从后端逐 token 推流（重写轮非流式），此处整段送达
        pending.length = 0
        assistantMsg.content = ''
        for (const ch of text) pending.push(ch)
      },
      () => {
        // 流正常结束：只标记结束，剩余 token 交给定时器逐字渲染完
        streamDone = true
      },
      (errMsg) => {
        // 出错：立即渲染已收到的部分，弹窗提示错误，思考标记一并清除防止卡死
        stopRenderingImmediately()
        assistantMsg.thinking = false
        showError(errMsg || ERROR_NETWORK)
        // 无任何内容时移除 AI 气泡（只留用户消息）；已有部分 token 则保留气泡
        if (!assistantMsg.content) {
          const idx = messages.value.indexOf(assistantMsg)
          if (idx !== -1) messages.value.splice(idx, 1)
        }
        sending.value = false
        abortController = null
      },
    )

    // 每帧（30ms）从队列取一个 token 写入消息，形成逐字打字机效果；
    // 队列已空且流已结束时清除定时器并复位状态
    renderTimer = setInterval(() => {
      if (pending.length) {
        // 首个 token 到达：思考阶段结束，提示与倒计时一并清除（重复置 false 无副作用）
        assistantMsg.thinking = false
        if (thinkTimer) { clearInterval(thinkTimer); thinkTimer = null }
        assistantMsg.content += pending.shift()
        return
      }
      if (streamDone) {
        // 流已结束：无论是否有 token 都要清除思考标记（空回复场景兜底），
        // 保证"流结束 = 徽标必消失"这一不变量
        assistantMsg.thinking = false
        if (thinkTimer) { clearInterval(thinkTimer); thinkTimer = null }
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
    messages, inputText, sending, selectedModel,
    thinking, toggleThinking,
    searchQuery, filteredConversations, currentTitle,
    showScrollBtn, listening, scrollContainer,
    sidebarCollapsed, toggleSidebar,
    scrollToBottom, onScroll,
    newConversation, selectConversation, removeConversation,
    sendMessage, onModelPick,
  }
}