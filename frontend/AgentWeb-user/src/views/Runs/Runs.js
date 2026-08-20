// 运行记录列表页逻辑：分页加载 / 多选 / 批量删除 / 本地搜索 / 详情抽屉
import { ref, reactive, computed, onMounted } from 'vue'
import { listAgentRuns, deleteAgentRuns } from '@/api/agentRuns'
import { useErrorModal } from '@/composables/useErrorModal'
import {
  LOADING, SEARCH_EMPTY, EMPTY_RUNS, NO_SELECTION,
  CONFIRM_DELETE, DELETE_SUCCESS,
} from './Text'

export function useRuns() {
  // 列表数据与分页状态
  const runs = ref([])
  const loading = ref(false)
  const page = ref(1)
  const pageSize = ref(10)
  const total = ref(0)
  const totalPages = ref(0)

  // 多选集合：记录 id → 选中
  const selected = reactive(new Set())
  // 本地搜索关键字：过滤已加载数据（后端不分页筛选）
  const searchQuery = ref('')
  // 详情抽屉状态：null = 关闭，否则为当前查看的 run
  const activeRun = ref(null)

  const { showError } = useErrorModal()

  // 本地过滤：按对话ID / trace_id / 状态 模糊匹配已加载的当前页数据
  const filteredRuns = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return runs.value
    return runs.value.filter(r =>
      r.conversation_id.toLowerCase().includes(q) ||
      r.trace_id.toLowerCase().includes(q) ||
      (r.status === 'ok' ? '成功' : '失败').includes(q) ||
      r.status.toLowerCase().includes(q),
    )
  })

  // 全选状态：当前页全部选中 / 部分选中
  const allSelected = computed(() => {
    if (filteredRuns.value.length === 0) return false
    return filteredRuns.value.every(r => selected.has(r.id))
  })

  async function loadRuns() {
    loading.value = true
    try {
      const { data } = await listAgentRuns(page.value, pageSize.value)
      runs.value = data.items
      total.value = data.total
      totalPages.value = data.total_pages
      // 页码越界兜底：服务端可能钳制，按返回值校准
      page.value = data.page
    } catch (err) {
      showError(err?.response?.data?.detail || err.message || '加载失败')
    } finally {
      loading.value = false
    }
  }

  function goToPage(p) {
    if (p < 1 || p > totalPages.value || p === page.value) return
    page.value = p
    selected.clear()  // 翻页后清除勾选，避免误删其他页数据
    loadRuns()
  }

  function toggleRow(id) {
    if (selected.has(id)) selected.delete(id)
    else selected.add(id)
  }

  function toggleAll() {
    if (allSelected.value) {
      filteredRuns.value.forEach(r => selected.delete(r.id))
    } else {
      filteredRuns.value.forEach(r => selected.add(r.id))
    }
  }

  async function deleteSelected() {
    if (selected.size === 0) {
      showError(NO_SELECTION)
      return
    }
    if (!window.confirm(CONFIRM_DELETE(selected.size))) return
    try {
      const { data } = await deleteAgentRuns([...selected])
      selected.clear()
      showError(DELETE_SUCCESS(data.deleted))  // 复用全局弹窗提示成功（弹窗标题为"提示"）
      await loadRuns()
    } catch (err) {
      showError(err?.response?.data?.detail || err.message || '删除失败')
    }
  }

  function openDetail(run) {
    activeRun.value = run
  }

  function closeDetail() {
    activeRun.value = null
  }

  onMounted(loadRuns)

  return {
    runs, filteredRuns, loading, page, pageSize, total, totalPages,
    selected, allSelected, searchQuery, activeRun,
    loadRuns, goToPage, toggleRow, toggleAll, deleteSelected,
    openDetail, closeDetail,
  }
}