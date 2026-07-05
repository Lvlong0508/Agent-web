<script setup>
import { PLACEHOLDER, SEND, NO_CONVERSATION } from './Text'
import { useChat } from './Chat'
import './Chat.css'

const { messages, inputText, sendMessage } = useChat()
</script>

<template>
  <div class="chat-page">
    <aside class="chat-sidebar">
      <div class="sidebar-header">对话</div>
      <div class="sidebar-list">
        <div class="sidebar-item">暂无对话</div>
      </div>
    </aside>
    <div class="chat-main">
      <div v-if="messages.length === 0" class="empty-state">
        {{ NO_CONVERSATION }}
      </div>
      <div v-else class="chat-messages">
        <div
          v-for="(msg, i) in messages"
          :key="i"
          :class="['message', msg.role]"
        >
          {{ msg.content }}
        </div>
      </div>
      <div class="chat-input-area">
        <textarea
          v-model="inputText"
          :placeholder="PLACEHOLDER"
          class="chat-input"
          rows="1"
          @keydown.enter.prevent="sendMessage"
        />
        <button
          class="send-btn"
          :disabled="!inputText.trim()"
          @click="sendMessage"
        >
          {{ SEND }}
        </button>
      </div>
    </div>
  </div>
</template>
