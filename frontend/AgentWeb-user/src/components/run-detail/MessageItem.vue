<template>
  <div class="message-item" :class="{ 'is-expanded': isExpanded }">
    <!-- 头部：整行可点击切换展开 -->
    <div class="message-header" @click="toggle">
      <span class="role-badge" :style="badgeStyle">{{ config.icon }} {{ config.label }}</span>
      <span v-if="msg.id" class="msg-id">{{ truncateId(msg.id) }}</span>
      <span class="summary">{{ summary }}</span>
      <span class="chevron" :class="{ open: isExpanded }">›</span>
    </div>
    <!-- 展开内容区：限高 400px 内部滚动，防止超长提示词撑爆抽屉 -->
    <Transition name="expand">
      <div v-if="isExpanded" class="message-body">
        <ContentRenderer :content="msg.content" :role="msg.role" />
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import type { AgentMessage } from './types'
import { getRoleConfig } from './constants'
import ContentRenderer from './ContentRenderer.vue'

const props = defineProps<{
  msg: AgentMessage
  index: number
}>()

// 展开状态从 RunDetail 统一注入（provide/inject，避免 prop 逐层传递）。
// 注意：RunDetail 注入的是 reactive(new Set())，是响应式 Set 而非 Ref，
// 因此这里直接按 Set<number> 注入，不取 .value，否则运行时拿到 undefined 会报错。
const expandedSet = inject<Set<number>>('expandedSet')!

const config = computed(() => getRoleConfig(props.msg.role))
const isExpanded = computed(() => expandedSet.has(props.index))

const badgeStyle = computed(() => ({
  backgroundColor: config.value.color,
  color: config.value.textColor,
}))

// 差异化摘要：字符串取首行截断 / 数组显示"共 N 条消息" / JSON 显示质检结果
const summary = computed(() => {
  const { content } = props.msg
  const style = config.value.summaryStyle

  if (style === 'count' && Array.isArray(content)) {
    return `共 ${content.length} 条消息`
  }

  if (style === 'json-summary' && typeof content === 'object' && !Array.isArray(content)) {
    const obj = content as Record<string, unknown>
    if (obj.is_accurate === true) return '通过 ✓'
    return '不通过 ✗'
  }

  if (typeof content === 'string') {
    const firstLine = content.split('\n')[0] || ''
    const limit = props.msg.role === 'assistant' ? 120 : 80
    return firstLine.length > limit ? firstLine.slice(0, limit) + '…' : firstLine
  }

  return String(content)
})

function truncateId(id: string) {
  return id.length > 12 ? id.slice(0, 12) + '…' : id
}

function toggle() {
  const s = expandedSet
  if (s.has(props.index)) s.delete(props.index)
  else s.add(props.index)
}
</script>

<style scoped>
/* 单条消息卡片：白底圆角细边框，hover 轻投影，与 Apple 风格一致 */
.message-item {
  border: 1px solid #E5E5EA;
  border-radius: 12px;
  background: #FFFFFF;
  overflow: hidden;
  transition: box-shadow 0.2s ease;
}
.message-item:hover { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06); }

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
}

.role-badge {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.msg-id {
  flex-shrink: 0;
  font-size: 11px;
  color: #8E8E93;
  font-family: 'SF Mono', 'Menlo', monospace;
}

.summary {
  flex: 1;
  font-size: 13px;
  color: #3C3C43;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chevron { flex-shrink: 0; font-size: 18px; color: #8E8E93; transition: transform 0.2s ease; }
.chevron.open { transform: rotate(90deg); }

.message-body {
  border-top: 1px solid #E5E5EA;
  padding: 12px 14px;
  max-height: 400px;
  overflow-y: auto;
}

/* 展开过渡：max-height 近似实现高度动画 */
.expand-enter-active,
.expand-leave-active { transition: all 0.25s ease; max-height: 500px; opacity: 1; }
.expand-enter-from,
.expand-leave-to { max-height: 0; opacity: 0; padding-top: 0; padding-bottom: 0; }
</style>