<template>
  <div class="step-card" :class="statusClass">
    <!-- 头部：整行可点击切换展开 -->
    <div class="step-header" @click="toggle">
      <span class="step-badge" :style="badgeStyle">{{ config.icon }} {{ config.label }}</span>
      <span class="step-node mono">{{ step.node_name }}</span>
      <span class="step-status" :style="statusStyle">{{ statusConfig.label }}</span>
      <span class="step-duration">{{ formatDuration(step.duration_ms) }}</span>
      <span class="chevron" :class="{ open: isExpanded }">›</span>
    </div>
    <!-- 展开区：错误/输入/输出/指标/调用 分块，限高滚动 -->
    <Transition name="expand">
      <div v-if="isExpanded" class="step-body">
        <div v-if="step.error_info" class="block error-block">
          <div class="block-title error">错误信息</div>
          <JsonViewer :data="step.error_info" />
        </div>
        <div v-if="step.input" class="block">
          <div class="block-title">输入</div>
          <JsonViewer :data="step.input" />
        </div>
        <div v-if="step.output" class="block">
          <div class="block-title">输出</div>
          <!-- 多态渲染：planner 的 output.messages 是数组时走 NestedMessageList 逐条可读；
               其余节点 output 无 messages 数组时回退 ContentRenderer 渲染整个对象 -->
          <NestedMessageList v-if="outputMessages" :messages="outputMessages" />
          <ContentRenderer v-else :content="step.output" :role="step.step_type" />
        </div>
        <div v-if="step.metrics" class="block">
          <div class="block-title">指标</div>
          <JsonViewer :data="step.metrics" />
        </div>
        <div v-if="step.calls && step.calls.length" class="block">
          <div class="block-title">调用（{{ step.calls.length }}）</div>
          <div class="calls-list">
            <CallItem v-for="call in step.calls" :key="call.call_id" :call="call" />
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import type { TraceStep, NestedMessage } from '@/types/run'
import { getStepConfig, getStatusConfig } from './constants'
import { formatDuration } from '@/utils/format'
import ContentRenderer from './ContentRenderer.vue'
import JsonViewer from './JsonViewer.vue'
import CallItem from './CallItem.vue'
import NestedMessageList from './NestedMessageList.vue'

const props = defineProps<{
  step: TraceStep
  index: number
}>()

// 展开状态从 RunDetail 统一注入（与 MessageItem 同套 provide/inject 折叠模式）。
// 注意：注入的是响应式 Set 而非 Ref，直接用，不取 .value。
const expandedSet = inject<Set<number>>('expandedSet')!

const config = computed(() => getStepConfig(props.step.step_type))
const statusConfig = computed(() => getStatusConfig(props.step.status))

const badgeStyle = computed(() => ({
  backgroundColor: config.value.color,
  color: config.value.textColor,
}))
const statusStyle = computed(() => ({
  backgroundColor: statusConfig.value.color,
  color: statusConfig.value.textColor,
}))

const isExpanded = computed(() => expandedSet.has(props.index))

// output.messages 是数组时单独用 NestedMessageList 渲染（planner 规划消息逐条可读）；
// 其余节点 output 无 messages 数组时回退 ContentRenderer 多态渲染
const outputMessages = computed(() => {
  const m = props.step.output?.messages
  return Array.isArray(m) ? (m as NestedMessage[]) : null
})

// 状态边框：error 红框 / degraded 橙框 / 其余默认灰框
const statusClass = computed(() => ({
  'is-error': props.step.status === 'error',
  'is-degraded': props.step.status === 'degraded',
}))

function toggle() {
  const s = expandedSet
  if (s.has(props.index)) s.delete(props.index)
  else s.add(props.index)
}
</script>

<style scoped>
/* 节点卡片：白底圆角细边框，hover 轻投影，与 MessageItem 同风格 */
.step-card {
  border: 1px solid #E5E5EA;
  border-radius: 12px;
  background: #FFFFFF;
  overflow: hidden;
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
}
.step-card:hover { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06); }
.step-card.is-error { border-color: #FF3B30; }
.step-card.is-degraded { border-color: #FF9500; }

.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
}

.step-badge {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.step-node {
  flex-shrink: 0;
  font-size: 12px;
  color: #3C3C43;
  font-weight: 500;
}

.step-status {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 5px;
  font-size: 11px;
}

.step-duration { flex-shrink: 0; font-size: 12px; color: #8E8E93; }

.chevron { flex-shrink: 0; font-size: 18px; color: #8E8E93; transition: transform 0.2s ease; }
.chevron.open { transform: rotate(90deg); }

.step-body {
  border-top: 1px solid #E5E5EA;
  padding: 12px 14px;
  max-height: 400px;
  overflow-y: auto;
}

/* 展开过渡：max-height 近似实现高度动画（同 MessageItem） */
.expand-enter-active,
.expand-leave-active { transition: all 0.25s ease; max-height: 500px; opacity: 1; }
.expand-enter-from,
.expand-leave-to { max-height: 0; opacity: 0; padding-top: 0; padding-bottom: 0; }

.block { margin-bottom: 12px; }
.block:last-child { margin-bottom: 0; }
.block-title { font-size: 12px; color: #8E8E93; font-weight: 500; margin-bottom: 6px; }
.block-title.error { color: #FF3B30; }

.error-block {
  background: #FFF5F5;
  border: 1px solid #FFD1CF;
  border-radius: 8px;
  padding: 10px;
}

.calls-list { display: flex; flex-direction: column; }

.mono { font-family: 'SF Mono', 'Menlo', monospace; }
</style>