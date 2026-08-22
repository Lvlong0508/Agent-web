<template>
  <div class="call-item">
    <span class="call-badge" :style="badgeStyle">{{ config.icon }} {{ config.label }}</span>

    <!-- llm 调用：模型名 + 输入→输出 token + 结束原因 -->
    <template v-if="call.call_type === 'llm'">
      <span class="call-model mono">{{ call.model || '—' }}</span>
      <span class="call-token">{{ call.input_tokens }} → {{ call.output_tokens }} tok</span>
      <span v-if="call.finish_reason" class="call-finish">{{ call.finish_reason }}</span>
    </template>

    <!-- tool 调用：工具名 + 调用 ID + 结果（JSON 自动结构化） -->
    <template v-else>
      <span class="call-tool mono">{{ call.tool_name || '—' }}</span>
      <span v-if="call.tool_call_id" class="call-tool-id mono">{{ truncateId(call.tool_call_id) }}</span>
      <span v-if="call.tool_result" class="call-result">
        <ContentRenderer :content="call.tool_result" role="tool" />
      </span>
    </template>

    <span class="call-duration">{{ formatDuration(call.duration_ms) }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TraceCall } from '@/types/run'
import { getCallConfig } from './constants'
import { formatDuration } from '@/utils/format'
import ContentRenderer from './ContentRenderer.vue'

const props = defineProps<{
  call: TraceCall
}>()

// 按 call_type 取中文名/图标/配色（llm 蓝 / tool 青）
const config = computed(() => getCallConfig(props.call.call_type))

const badgeStyle = computed(() => ({
  backgroundColor: config.value.color,
  color: config.value.textColor,
}))

// 长 ID 截断展示，完整值靠 hover（title）
function truncateId(id: string) {
  return id.length > 12 ? id.slice(0, 12) + '…' : id
}
</script>

<style scoped>
/* 单条调用：等宽信息行，无卡片（Step 内紧凑展示） */
.call-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px dashed #E5E5EA;
  font-size: 12px;
}
.call-item:last-child { border-bottom: none; }

.call-badge {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

.mono {
  font-family: 'SF Mono', 'Menlo', monospace;
  font-size: 12px;
  color: #3C3C43;
}
.call-model { font-weight: 500; }
.call-token { color: #8E8E93; }
.call-finish { color: #AF52DE; }
.call-tool-id { color: #8E8E93; }
.call-duration { margin-left: auto; color: #8E8E93; }

/* 工具结果：限宽避免撑破卡片，内容本身自带换行 */
.call-result {
  flex: 1;
  min-width: 0;
  max-width: 420px;
}
</style>