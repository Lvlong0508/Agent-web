<template>
  <div class="content-renderer">
    <!-- tool 结果：content 是 JSON 字符串且可解析 → 结构化渲染（美化） -->
    <JsonViewer v-if="isToolJson" :data="toolJson as Record<string, unknown> | unknown[]" />
    <!-- 字符串：等宽字体保留换行 -->
    <pre v-else-if="isString" class="content-text">{{ content }}</pre>
    <!-- 数组：递归渲染嵌套消息列表 -->
    <NestedMessageList v-else-if="isArray" :messages="content as NestedMessage[]" />
    <!-- 对象：JSON 折叠树 -->
    <JsonViewer v-else-if="isObject" :data="content as Record<string, unknown>" />
    <!-- 兜底：原样转字符串 -->
    <pre v-else class="content-text">{{ String(content) }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { MessageContent, NestedMessage } from '@/types/run'
import NestedMessageList from './NestedMessageList.vue'
import JsonViewer from './JsonViewer.vue'

const props = defineProps<{
  content: MessageContent
  role: string
}>()

// tool 结果美化：role=tool 的 content 是 JSON 字符串（如 {"items":[...],"total":6}），
// 解析成功用 JsonViewer 结构化展示（对象/数组都可），解析失败回退 <pre> 原样文本
const isTool = computed(() => props.role === 'tool' && typeof props.content === 'string')
const toolJson = computed(() => (isTool.value ? tryParseJson(props.content) : null))
const isToolJson = computed(() => isTool.value && toolJson.value !== null)

// 按运行时类型路由到不同渲染组件（多态 content 的核心分发逻辑）
const isString = computed(() => typeof props.content === 'string')
const isArray = computed(() => Array.isArray(props.content))
const isObject = computed(() =>
  typeof props.content === 'object' && props.content !== null && !Array.isArray(props.content)
)

// 尝试把字符串按 JSON 解析；失败返回 null（保持原样渲染）
// 入参用 MessageContent：调用处 isTool 已运行时收窄为 string，此处放宽类型避免 TS 联合类型报错
function tryParseJson(text: MessageContent): unknown {
  if (typeof text !== 'string') return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}
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