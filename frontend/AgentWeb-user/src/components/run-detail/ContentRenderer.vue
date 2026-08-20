<template>
  <div class="content-renderer">
    <!-- 字符串：等宽字体保留换行 -->
    <pre v-if="isString" class="content-text">{{ content }}</pre>
    <!-- 数组：递归渲染嵌套消息列表 -->
    <NestedMessageList v-else-if="isArray" :messages="content as NestedMessage[]" />
    <!-- 对象：JSON 折叠树 -->
    <JsonViewer v-else-if="isObject" :data="content as Record<string, unknown>" />
    <!-- 兜底：原样转字符串 -->
    <pre v-else class="content-text">{{ String(content) }}</pre>
  </div>
</template>

<script setup lang="ts">
import type { MessageContent, NestedMessage } from '@/types/run'
import NestedMessageList from './NestedMessageList.vue'
import JsonViewer from './JsonViewer.vue'

const props = defineProps<{
  content: MessageContent
  role: string
}>()

// 按运行时类型路由到不同渲染组件（多态 content 的核心分发逻辑）
const isString = typeof props.content === 'string'
const isArray = Array.isArray(props.content)
const isObject = typeof props.content === 'object'
  && props.content !== null
  && !Array.isArray(props.content)
</script>

<style scoped>
/* 内容文本：等宽字体 + pre-wrap 保留换行，超长内容由 MessageItem 限高滚动 */
.content-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'SF Mono', 'Menlo', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: #1C1C1E;
}
</style>