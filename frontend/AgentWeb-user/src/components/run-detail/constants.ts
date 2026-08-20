// role 配置表：中文标签 / 图标 / 配色 / 摘要策略 集中管理，新增 role 只需加一条

export interface RoleConfig {
  label: string           // 中文显示名
  icon: string            // emoji 图标（Web 端用 emoji 替代 SF Symbols）
  color: string           // 标签背景色（Apple 低饱和度）
  textColor: string       // 标签文字色
  summaryStyle: 'first-line' | 'count' | 'json-summary'
}

// Apple System Colors 体系：蓝/绿/橙/紫 各角色一色，低饱和底 + 同色文字
export const ROLE_MAP: Record<string, RoleConfig> = {
  user: { label: '用户', icon: '👤', color: '#E8F0FE', textColor: '#007AFF', summaryStyle: 'first-line' },
  assistant: { label: '助手', icon: '🤖', color: '#E8F5E9', textColor: '#34C759', summaryStyle: 'first-line' },
  system: { label: '规划参考', icon: '📋', color: '#F5F5F5', textColor: '#8E8E93', summaryStyle: 'first-line' },
  input_verdict: { label: '质检输入', icon: '📥', color: '#FFF3E0', textColor: '#FF9500', summaryStyle: 'count' },
  verdict: { label: '质检判定', icon: '✅', color: '#F3E5F5', textColor: '#AF52DE', summaryStyle: 'json-summary' },
  tool: { label: '工具调用', icon: '🔧', color: '#E0F7FA', textColor: '#00BCD4', summaryStyle: 'first-line' },
}

// 未知 role 兜底：显示原始 role 名，通用灰
export function getRoleConfig(role: string): RoleConfig {
  return ROLE_MAP[role] ?? {
    label: role,
    icon: '💬',
    color: '#F5F5F5',
    textColor: '#8E8E93',
    summaryStyle: 'first-line',
  }
}