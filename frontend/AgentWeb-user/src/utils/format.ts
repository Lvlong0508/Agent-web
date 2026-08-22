// 时间与数字格式化：详情页与列表页共用，避免各组件重复实现

// 耗时格式化：不足 1 秒显示毫秒，达到 1 秒显示秒（保留两位）
export function formatDuration(ms: number): string {
  if (!ms) return '—'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

// Token 数格式化：千分位分隔，0 显示 —
export function formatTokens(n: number): string {
  return n ? n.toLocaleString() : '—'
}