<script setup>
import {
  PLACEHOLDER, SEND, NEW_CHAT, DELETE,
  EMPTY_CONVERSATIONS, EMPTY_CHAT, LOADING,
  MODEL_OLLAMA_LABEL, MODEL_DASHSCOPE_LABEL,
  THINKING_MODE_LABEL,
  THINKING,
} from './Text'
import { useChat } from './Chat'
import './Chat.css'

const {
  conversations, activeConvId, loadingList,
  messages, inputText, sending, error, selectedModel,
  thinking, toggleThinking,
  newConversation, selectConversation, removeConversation,
  sendMessage, onModelChange,
} = useChat()
</script>

<template>
  <div class="chat-page">
    <aside class="chat-sidebar">
      <div class="sidebar-header">
        <span>对话</span>
        <button class="btn-new-chat" @click="newConversation">{{ NEW_CHAT }}</button>
      </div>
      <!-- 模型选择下拉：切换当前聊天使用的模型，选择会持久化到 localStorage -->
      <div class="sidebar-model">
        <select :value="selectedModel" @change="onModelChange">
          <option value="ollama-qwen3.5">{{ MODEL_OLLAMA_LABEL }}</option>
          <option value="qwen3.7-flash">{{ MODEL_DASHSCOPE_LABEL }}</option>
        </select>
        <!-- 深度思考开关：只影响回复生成（标题永远快速生成），选择会持久化到 localStorage -->
        <button
          class="btn-thinking"
          :class="{ on: thinking }"
          :disabled="sending"
          @click="toggleThinking"
        >
          {{ THINKING_MODE_LABEL }}
        </button>
      </div>
      <div class="sidebar-list">
        <div v-if="loadingList" class="sidebar-item">{{ LOADING }}</div>
        <div v-else-if="conversations.length === 0" class="sidebar-item">
          {{ EMPTY_CONVERSATIONS }}
        </div>
        <div
          v-for="conv in conversations"
          :key="conv.id"
          :class="['sidebar-item', { active: conv.id === activeConvId }]"
          @click="selectConversation(conv.id)"
        >
          <span class="conv-title">{{ conv.title }}</span>
          <button
            class="btn-delete"
            @click.stop="removeConversation(conv.id)"
            :title="DELETE"
          >×</button>
        </div>
      </div>
    </aside>

    <div class="chat-main">
      <div v-if="!activeConvId" class="empty-state">{{ EMPTY_CHAT }}</div>

      <template v-else>
        <div class="chat-messages">
          <div
            v-for="(msg, i) in messages"
            :key="i"
            :class="['msg-wrap', msg.role]"
          >
            <!-- 思考阶段提示：仅流式首 token 到达前显示在气泡左上方 -->
            <span v-if="msg.thinking" class="thinking">
              {{ THINKING }}
              <span class="dot" aria-hidden="true">.</span><span class="dot" aria-hidden="true">.</span><span class="dot" aria-hidden="true">.</span>
            </span>
            <!-- 正文为空时隐藏气泡：思考阶段不显示空灰泡，token 到达后自动出现 -->
            <div v-if="msg.content" class="message" :class="msg.role">{{ msg.content }}</div>
          </div>
          <div v-if="error" class="message error">{{ error }}</div>
        </div>

        <div class="chat-input-area">
          <textarea
            v-model="inputText"
            :placeholder="PLACEHOLDER"
            class="chat-input"
            rows="1"
            :disabled="sending"
            @keydown.enter.prevent="sendMessage"
          />
          <button
            class="send-btn"
            :disabled="!inputText.trim() || sending"
            @click="sendMessage"
          >{{ SEND }}</button>
        </div>
      </template>
    </div>
  </div>
</template>
