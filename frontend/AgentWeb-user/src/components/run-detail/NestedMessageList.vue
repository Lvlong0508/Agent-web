<template>
  <div class="nested-list">
    <div
      v-for="(msg, idx) in messages"
      :key="msg.role + '-' + idx"
      class="nested-item"
    >
      <div class="nested-header" @click="toggle(idx)">
        <span class="nested-role">{{ msg.role }}</span>
        <span class="nested-summary">{{ getSummary(msg) }}</span>
        <span class="chevron" :class="{ open: openSet.has(idx) }">›</span>
      </div>
      <Transition name="expand">
        <div v-if="openSet.has(idx)" class="nested-body">
          <!-- 嵌套消息的 content 若是数组，递归自身 -->
          <NestedMessageList
            v-if="Array.isArray(msg.content)"
            :messages="msg.content"
          />
          <pre v-else class="nested-text">{{ msg.content }}</pre>
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import type { NestedMessage } from './types'

// 递归组件：声明名字供模板内自引用
defineOptions({ name: 'NestedMessageList' })

defineProps<{
  messages: NestedMessage[]
}>()

// 本组件局部的展开集合：嵌套消息各自独立展开/收起
const openSet = reactive(new Set<number>())

function toggle(idx: number) {
  if (openSet.has(idx)) openSet.delete(idx)
  else openSet.add(idx)
}

// 摘要：字符串取首行截断 60 字符；对象（理论上无）转 JSON 后取首行
function getSummary(msg: NestedMessage): string {
  const text = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content)
  const firstLine = text.split('\n')[0] || ''
  return firstLine.length > 60 ? firstLine.slice(0, 60) + '…' : firstLine
}
</script>

<style scoped>
/* 嵌套列表左侧竖线缩进，与上级内容层级区分 */
.nested-list { border-left: 3px solid #E5E5EA; margin-left: 4px; }
.nested-item { margin: 4px 0; }

.nested-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.15s;
}
.nested-header:hover { background: #F5F5F5; }

.nested-role {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  color: #8E8E93;
  text-transform: uppercase;
  min-width: 56px;
}

.nested-summary {
  flex: 1;
  font-size: 12px;
  color: #3C3C43;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chevron { font-size: 16px; color: #8E8E93; transition: transform 0.2s; }
.chevron.open { transform: rotate(90deg); }

.nested-body { padding: 6px 10px 6px 72px; }

.nested-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'SF Mono', 'Menlo', monospace;
  font-size: 12px;
  line-height: 1.5;
  color: #1C1C1E;
}

/* 展开/收起过渡：高度动画用 max-height 近似 */
.expand-enter-active,
.expand-leave-active { transition: all 0.2s ease; max-height: 300px; opacity: 1; }
.expand-enter-from,
.expand-leave-to { max-height: 0; opacity: 0; padding-top: 0; padding-bottom: 0; }
</style>