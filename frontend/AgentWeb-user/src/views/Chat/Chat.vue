<script setup>
import {
  PLACEHOLDER, SEND, NEW_CHAT, DELETE,
  EMPTY_CONVERSATIONS, EMPTY_CHAT, LOADING,
} from './Text'
import { useChat } from './Chat'
import './Chat.css'

const {
  conversations, activeConvId, loadingList,
  messages, inputText, sending, error,
  newConversation, selectConversation, removeConversation,
  sendMessage,
} = useChat()
</script>

<template>
  <div class="chat-page">
    <aside class="chat-sidebar">
      <div class="sidebar-header">
        <span>对话</span>
        <button class="btn-new-chat" @click="newConversation">{{ NEW_CHAT }}</button>
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
            :class="['message', msg.role]"
          >{{ msg.content }}</div>
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
