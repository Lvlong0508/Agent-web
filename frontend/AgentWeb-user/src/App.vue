<script setup lang="ts">
// 根组件：挂载全局错误弹窗并注入其状态，让任意页面组件都能触发
import { RouterView } from 'vue-router'
import NavBar from '@/components/NavBar.vue'
import ErrorModal from '@/components/ErrorModal.vue'
import { provideErrorModal, useErrorModal } from '@/composables/useErrorModal'

// 提供全局错误状态；下面用 useErrorModal 读出 visible/message 供弹窗绑定
provideErrorModal()
const { visible, message, closeError } = useErrorModal()
</script>

<template>
  <NavBar />
  <RouterView />
  <!-- 全局错误弹窗：visible/message 来自 useErrorModal 全局状态 -->
  <ErrorModal :visible="visible" :message="message" @close="closeError" />
</template>
