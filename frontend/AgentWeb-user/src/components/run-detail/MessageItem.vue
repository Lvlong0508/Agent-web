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
        <!-- 工具调用块：assistant 声明调用的工具（name + 参数 + 调用id），
             与 tool 结果消息的 tool_call_id 对应，便于还原调用链 -->
        <div v-if="msg.tool_calls && msg.tool_calls.length" class="tool-calls-block">
          <div v-for="(tc, i) in msg.tool_calls" :key="tc.id || i" class="tool-call-item">
            <div class="tool-call-header">
              <span class="tool-call-name">{{ tc.name }}</span>
              <span class="tool-call-id">{{ truncateId(tc.id) }}</span>
            </div>
            <JsonViewer :data="tc.args" />
          </div>
        </div>
        <ContentRenderer :content="msg.content" :role="msg.role" />
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import JsonViewer from './JsonViewer.vue'
import type { AgentMessage, MessageContent } from '@/types/run'
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

// 差异化摘要：工具调用优先 / tool 消息显工具名 / 字符串取首行截断 / 数组计数 / JSON 判定
const summary = computed(() => {
  const { content } = props.msg

  // 1) assistant 带 tool_calls：显示"调用工具 X"，替代空 content 的空摘要
  if (props.msg.tool_calls && props.msg.tool_calls.length) {
    const names = props.msg.tool_calls.map(tc => tc.name).join('、')
    return `调用工具 ${names}`
  }

  // 2) tool 结果消息：优先显示工具名 + 概要，不再直接看一整行 JSON
  if (props.msg.role === 'tool' && props.msg.name) {
    const hint = toolResultHint(content)
    return hint ? `${props.msg.name} · ${hint}` : props.msg.name
  }

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

// tool 结果概要：content 是 JSON 字符串时取关键字段（total / items 条数），
// 解析失败退回首行截断，让摘要比"整段 JSON 挤一行"可读得多
function toolResultHint(content: MessageContent): string {
  if (typeof content !== 'string' || !content) return ''
  try {
    const parsed = JSON.parse(content)
    if (parsed && typeof parsed === 'object') {
      if ('total' in parsed) return `共 ${parsed.total} 条`
      const items = (parsed as Record<string, unknown>).items
      if (Array.isArray(items)) return `共 ${items.length} 项`
    }
  } catch {
    // 非 JSON（如纯文本错误），走首行截断兜底
  }
  const firstLine = content.split('\n')[0] || ''
  return firstLine.length > 40 ? firstLine.slice(0, 40) + '…' : firstLine
}

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

/* 工具调用块：浅青底圆角卡片，与 tool 角色徽标同色系 */
.tool-calls-block { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }

.tool-call-item {
  border: 1px solid #E0F7FA;
  border-radius: 8px;
  padding: 8px 10px;
  background: #F7FDFE;
}

.tool-call-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.tool-call-name {
  font-size: 12px;
  font-weight: 600;
  color: #00BCD4;
  font-family: 'SF Mono', 'Menlo', monospace;
}
.tool-call-id { font-size: 11px; color: #8E8E93; font-family: 'SF Mono', 'Menlo', monospace; }
</style>