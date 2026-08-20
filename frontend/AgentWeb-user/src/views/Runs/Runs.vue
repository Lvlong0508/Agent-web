<script setup>
// 运行记录管理页：分页列表 + 多选删除 + 本地搜索 + 右侧抽屉详情
import { watch, onUnmounted } from 'vue'
import {
  RUNS_TITLE, RUNS_SUBTITLE, SEARCH_PLACEHOLDER, SEARCH_EMPTY,
  EMPTY_RUNS, LOADING, REFRESH, DELETE_SELECTED,
  COL_STATUS, COL_TIME, COL_MODEL, COL_CONVERSATION, COL_TRACE,
  COL_MESSAGES, COL_ERROR, STATUS_OK, STATUS_ERROR, CLOSE,
} from './Text'
import { useRuns } from './Runs'
import './Runs.css'
import RunDetail from '@/components/run-detail/RunDetail.vue'

const {
  runs, filteredRuns, loading, page, totalPages, total,
  selected, allSelected, searchQuery, activeRun, deleting,
  loadRuns, goToPage, toggleRow, toggleAll, deleteSelected,
  openDetail, closeDetail,
} = useRuns()

// 抽屉 Esc 关闭：与 ErrorModal 的惯例一致——打开时给 window 绑 keydown，
// 关闭/卸载时解绑，避免抽屉关闭后 Esc 仍被拦截
function onDrawerKeydown(e) {
  if (e.key === 'Escape') closeDetail()
}
watch(activeRun, (val) => {
  if (val) window.addEventListener('keydown', onDrawerKeydown)
  else window.removeEventListener('keydown', onDrawerKeydown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onDrawerKeydown)
})

// 格式化时间：显示 月/日 时:分:秒
function formatTime(iso) {
  return new Date(iso).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}
</script>

<template>
  <div class="runs-page">
    <div class="runs-container">
      <div class="runs-header">
        <h1>{{ RUNS_TITLE }}</h1>
        <p>{{ RUNS_SUBTITLE }}</p>
      </div>

      <!-- 工具行：本地搜索 + 批量删除 + 刷新 -->
      <div class="runs-toolbar">
        <div class="runs-search">
          <input v-model="searchQuery" :placeholder="SEARCH_PLACEHOLDER" />
        </div>
        <button class="btn-secondary btn-danger" :disabled="selected.size === 0 || deleting" @click="deleteSelected">
          {{ DELETE_SELECTED }}{{ selected.size ? `（${selected.size}）` : '' }}
        </button>
        <button class="btn-secondary" @click="loadRuns">{{ REFRESH }}</button>
      </div>

      <!-- 表格卡片 -->
      <div class="runs-card">
        <table class="runs-table">
          <thead>
            <tr>
              <th class="cell-check">
                <input type="checkbox" :checked="allSelected" @change="toggleAll" />
              </th>
              <th>{{ COL_TIME }}</th>
              <th>{{ COL_STATUS }}</th>
              <th>{{ COL_MODEL }}</th>
              <th>{{ COL_CONVERSATION }}</th>
              <th>{{ COL_TRACE }}</th>
              <th>{{ COL_MESSAGES }}</th>
              <th>{{ COL_ERROR }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="8" class="runs-empty">{{ LOADING }}</td>
            </tr>
            <tr v-else-if="filteredRuns.length === 0">
              <td colspan="8" class="runs-empty">
                {{ searchQuery ? SEARCH_EMPTY : EMPTY_RUNS }}
              </td>
            </tr>
            <tr v-for="run in filteredRuns" :key="run.id" @click="openDetail(run)">
              <!-- 复选框：点击.stop 避免冒泡触发行点击 -->
              <td class="cell-check" @click.stop>
                <input type="checkbox" :checked="selected.has(run.id)" @change="toggleRow(run.id)" />
              </td>
              <td class="mono" :title="run.created_at">{{ formatTime(run.created_at) }}</td>
              <td>
                <span class="status-badge" :class="run.status">
                  {{ run.status === 'ok' ? STATUS_OK : STATUS_ERROR }}
                </span>
              </td>
              <td>{{ run.model }}</td>
              <!-- 长文本包一层 span 做截断：table-layout:auto 下 td 的 max-width 不可靠，
                    span 用 display:block + overflow 才能稳定截断；title 保留完整内容供悬停查看 -->
              <td class="mono" :title="run.conversation_id">
                <span class="cell-ellipsis">{{ run.conversation_id }}</span>
              </td>
              <td class="mono" :title="run.trace_id">
                <span class="cell-ellipsis">{{ run.trace_id }}</span>
              </td>
              <td>{{ run.messages.length }}</td>
              <td>
                <span v-if="run.error" class="cell-error" :title="run.error">{{ run.error }}</span>
                <span v-else>—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 分页栏 -->
      <div class="runs-pagination">
        <button class="btn-secondary" :disabled="page <= 1" @click="goToPage(page - 1)">上一页</button>
        <span>第 {{ page }} / {{ totalPages || 1 }} 页 · 共 {{ total }} 条</span>
        <button class="btn-secondary" :disabled="page >= totalPages" @click="goToPage(page + 1)">下一页</button>
      </div>
    </div>

    <!-- 右侧详情抽屉 -->
    <template v-if="activeRun">
      <div class="drawer-overlay" @click="closeDetail"></div>
      <aside class="drawer">
        <header class="drawer-header">
          <h2>{{ RUNS_TITLE }} · {{ activeRun.id }}</h2>
          <button class="btn-close" :title="CLOSE" @click="closeDetail">×</button>
        </header>
        <div class="drawer-body">
          <RunDetail :run="activeRun" />
        </div>
      </aside>
    </template>
  </div>
</template>