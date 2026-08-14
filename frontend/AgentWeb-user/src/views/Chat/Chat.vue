<script setup>
import { computed } from 'vue'
import {
  PLACEHOLDER, SEND, NEW_CHAT, DELETE,
  EMPTY_CONVERSATIONS, EMPTY_CHAT, LOADING,
  SEARCH_PLACEHOLDER, SEARCH_EMPTY, AI_DISCLAIMER,
  JUMP_TO_BOTTOM, RECENT_CONVERSATIONS,
  MODEL_OLLAMA_FULL, MODEL_DASHSCOPE_FULL,
  THINKING_MODE_LABEL, THINKING, LISTENING,
} from './Text'
import { useChat } from './Chat'
import './Chat.css'

const {
  conversations, activeConvId, loadingList,
  messages, inputText, sending, selectedModel,
  thinking, toggleThinking,
  searchQuery, filteredConversations, currentTitle,
  showScrollBtn, listening, scrollContainer,
  sidebarCollapsed, toggleSidebar,
  scrollToBottom, onScroll,
  newConversation, selectConversation, removeConversation,
  sendMessage, onModelPick,
} = useChat()

// 当前激活模型的完整名称：分段控件上显示短名，悬停/标题处显示完整说明
const activeModelFull = computed(() =>
  selectedModel.value === 'qwen3.7-flash' ? MODEL_DASHSCOPE_FULL : MODEL_OLLAMA_FULL,
)
</script>

<template>
  <div class="chat-page" :class="{ 'sidebar-hidden': sidebarCollapsed }">
    <aside class="chat-sidebar">
      <!-- 会话搜索框：按标题本地过滤会话列表 -->
      <div class="search-box">
        <svg class="search-icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
          <path fill="currentColor" d="M10 3a7 7 0 1 0 4.4 12.5l4.3 4.3a1 1 0 0 0 1.4-1.4l-4.3-4.3A7 7 0 0 0 10 3zm0 2a5 5 0 1 1 0 10 5 5 0 0 1 0-10z"/>
        </svg>
        <input v-model="searchQuery" :placeholder="SEARCH_PLACEHOLDER" />
      </div>

      <div class="sidebar-actions">
        <!-- 新建对话 -->
        <button class="btn-new" @click="newConversation">
          <span class="plus">+</span>{{ NEW_CHAT }}
        </button>
      </div>

      <div class="sidebar-section-title">{{ RECENT_CONVERSATIONS }}</div>
      <div class="sidebar-list">
        <div v-if="loadingList" class="sidebar-empty">{{ LOADING }}</div>
        <div v-else-if="filteredConversations.length === 0" class="sidebar-empty">
          {{ searchQuery ? SEARCH_EMPTY : EMPTY_CONVERSATIONS }}
        </div>
        <div
          v-for="conv in filteredConversations"
          :key="conv.id"
          :class="['sidebar-item', { active: conv.id === activeConvId }]"
          @click="selectConversation(conv.id)"
        >
          <span class="conv-title">{{ conv.title || NEW_CHAT }}</span>
          <button
            class="btn-delete"
            @click.stop="removeConversation(conv.id)"
            :title="DELETE"
          >×</button>
        </div>
      </div>
    </aside>

    <div class="chat-main">
      <!-- 顶部标题栏：最左侧收起按钮 + 模型下拉，中间标题始终绝对居中 -->
      <header class="chat-header">
        <div class="header-left">
          <button
            class="sidebar-toggle"
            :title="sidebarCollapsed ? '展开会话列表' : '收起会话列表'"
            @click="toggleSidebar"
          >{{ sidebarCollapsed ? '▶' : '◀' }}</button>
          <select
            class="model-select"
            :value="selectedModel"
            title="选择模型"
            @change="onModelPick($event.target.value)"
          >
            <option value="ollama-qwen3.5">{{ MODEL_OLLAMA_FULL }}</option>
            <option value="qwen3.7-flash">{{ MODEL_DASHSCOPE_FULL }}</option>
          </select>
        </div>
        <div class="header-center">
          <h1 class="chat-title">{{ currentTitle || NEW_CHAT }}</h1>
          <span class="chat-subtitle">{{ AI_DISCLAIMER }}</span>
        </div>
      </header>

      <div v-if="!activeConvId" class="empty-state">{{ EMPTY_CHAT }}</div>

      <template v-else>
        <div ref="scrollContainer" class="chat-messages" @scroll="onScroll">
          <div
            v-for="(msg, i) in messages"
            :key="i"
            :class="['msg-wrap', msg.role]"
          >
            <!-- 思考阶段提示：含已等待秒数倒计时，仅流式首 token 到达前显示 -->
            <span v-if="msg.thinking" class="thinking">
              {{ THINKING }}
              <span class="dots"><span class="dot">.</span><span class="dot">.</span><span class="dot">.</span></span>
              {{ msg.thinkSeconds }}s
            </span>
            <!-- 正文为空时隐藏气泡：思考阶段不显示空灰泡，token 到达后自动出现 -->
            <div v-if="msg.content" class="message" :class="msg.role">{{ msg.content }}</div>
          </div>
        </div>

        <!-- 底部输入坞：包含"回到底部"箭头与输入框、工具行 -->
        <div class="input-dock">
          <button
            v-if="showScrollBtn"
            class="scroll-bottom"
            :title="JUMP_TO_BOTTOM"
            @click="scrollToBottom"
          >↓</button>
          <div class="chat-input-area">
            <div class="input-box">
              <textarea
                v-model="inputText"
                :placeholder="listening ? LISTENING : PLACEHOLDER"
                class="chat-input"
                rows="1"
                :disabled="sending"
                @keydown.enter.prevent="sendMessage"
              />
              <!-- 输入框内部工具行：深度思考靠左、发送按钮靠右，同一水平区域 -->
              <div class="input-inner-tools">
                <button
                  class="tool-btn"
                  :class="{ on: thinking }"
                  :disabled="sending"
                  @click="toggleThinking"
                >{{ THINKING_MODE_LABEL }}</button>
                <span class="tool-spacer"></span>
                <button
                  class="send-btn"
                  :disabled="!inputText.trim() || sending"
                  :title="activeModelFull"
                  @click="sendMessage"
                >{{ SEND }}</button>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>