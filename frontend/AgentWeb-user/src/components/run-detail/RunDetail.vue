<template>
  <div class="run-detail">
    <!-- 运行记录元信息卡片 -->
    <div class="meta-card">
      <div class="meta-row">
        <span class="meta-label">状态</span>
        <!-- 真实 status 取值是 ok（成功）/ error（失败） -->
        <span class="meta-value status" :class="run.status">
          {{ run.status === 'ok' ? '✓ 成功' : '✗ 失败' }}
        </span>
      </div>
      <div class="meta-row">
        <span class="meta-label">模型</span>
        <span class="meta-value">{{ run.model }}</span>
      </div>
      <div class="meta-row">
        <span class="meta-label">时间</span>
        <span class="meta-value">{{ formatTime(run.created_at) }}</span>
      </div>
      <div class="meta-row">
        <span class="meta-label">对话ID</span>
        <span class="meta-value mono">{{ run.conversation_id }}</span>
      </div>
      <div class="meta-row">
        <span class="meta-label">trace_id</span>
        <span class="meta-value mono">{{ run.trace_id }}</span>
      </div>
      <div v-if="run.error" class="meta-row">
        <span class="meta-label">错误</span>
        <span class="meta-value error">{{ run.error }}</span>
      </div>
    </div>

    <!-- 消息统计概览：总条数 + 各 role 计数药丸 + 全部展开/收起 -->
    <div class="stats-bar">
      <span class="stats-total">共 {{ run.messages.length }} 条消息</span>
      <span
        v-for="item in roleStats"
        :key="item.role"
        class="stats-chip"
        :style="{ backgroundColor: item.color, color: item.textColor }"
      >{{ item.icon }} {{ item.label }} ×{{ item.count }}</span>
      <button class="expand-all-btn" @click="toggleAll">
        {{ allExpanded ? '全部收起' : '全部展开' }}
      </button>
    </div>

    <!-- 消息列表：每条约 MessageItem 展开/收起 -->
    <div class="message-list">
      <MessageItem
        v-for="(msg, idx) in run.messages"
        :key="msg.id || idx"
        :msg="msg"
        :index="idx"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, provide, reactive, ref } from 'vue'
import type { AgentRun } from './types'
import { getRoleConfig } from './constants'
import MessageItem from './MessageItem.vue'

const props = defineProps<{
  run: AgentRun
}>()

// 展开状态统一在此管理，通过 provide 下发给所有 MessageItem
const expandedSet = reactive(new Set<number>())
provide('expandedSet', expandedSet)

const allExpanded = ref(false)

function toggleAll() {
  if (allExpanded.value) {
    expandedSet.clear()
  } else {
    props.run.messages.forEach((_, idx) => expandedSet.add(idx))
  }
  allExpanded.value = !allExpanded.value
}

// 统计各 role 出现次数，供概览药丸展示
const roleStats = computed(() => {
  const counts = new Map<string, number>()
  for (const msg of props.run.messages) {
    counts.set(msg.role, (counts.get(msg.role) ?? 0) + 1)
  }
  return Array.from(counts.entries()).map(([role, count]) => {
    const cfg = getRoleConfig(role)
    return { role, count, label: cfg.label, icon: cfg.icon, color: cfg.color, textColor: cfg.textColor }
  })
})

// 时间格式化：只显示月/日/时分秒（本地时区）
function formatTime(iso: string) {
  return new Date(iso).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}
</script>

<style scoped>
/* 详情内容容器：居中列 + 白卡片 + Apple 配色变量 */
.run-detail {
  max-width: 800px;
  margin: 0 auto;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'PingFang SC',
    'Helvetica Neue', 'Microsoft YaHei', sans-serif;
}

.meta-card {
  background: #FFFFFF;
  border: 1px solid #E5E5EA;
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
}

.meta-row { display: flex; align-items: center; gap: 6px; }
.meta-label { font-size: 12px; color: #8E8E93; }
.meta-value { font-size: 13px; color: #1C1C1E; font-weight: 500; }
.meta-value.mono { font-family: 'SF Mono', 'Menlo', monospace; font-weight: 400; font-size: 12px; }

.meta-value.status.ok { color: #34C759; }
.meta-value.status.error { color: #FF3B30; }
.meta-value.error { color: #FF3B30; }

.stats-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 0;
  margin-bottom: 8px;
}

.stats-total { font-size: 13px; color: #8E8E93; margin-right: 4px; }

.stats-chip {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
}

.expand-all-btn {
  margin-left: auto;
  font-size: 12px;
  color: #007AFF;
  background: none;
  border: 1px solid #007AFF;
  border-radius: 6px;
  padding: 2px 10px;
  cursor: pointer;
  transition: all 0.15s;
}
.expand-all-btn:hover { background: #007AFF; color: #FFFFFF; }

.message-list { display: flex; flex-direction: column; gap: 8px; }
</style>