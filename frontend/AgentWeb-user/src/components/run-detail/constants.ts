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

// === 三层结构展示配置（spec 2026-08-22）：step_type / call_type / status 的中文名·图标·配色 ===

export interface StepConfig {
  label: string
  icon: string
  color: string
  textColor: string
}

// 节点类型配置：与 ROLE_MAP 同一套 Apple 低饱和度配色体系
export const STEP_MAP: Record<string, StepConfig> = {
  entry: { label: '入口', icon: '🚪', color: '#F5F5F5', textColor: '#8E8E93' },
  planner: { label: '规划', icon: '📋', color: '#FFF3E0', textColor: '#FF9500' },
  agent: { label: '主代理', icon: '🤖', color: '#E8F5E9', textColor: '#34C759' },
  tool: { label: '工具', icon: '🔧', color: '#E0F7FA', textColor: '#00BCD4' },
  verifier: { label: '质检', icon: '✅', color: '#F3E5F5', textColor: '#AF52DE' },
  title: { label: '标题', icon: '🏷', color: '#E3F2FD', textColor: '#2196F3' },
}

// 未知 step_type 兜底：显示原始类型名，通用灰
export function getStepConfig(type: string): StepConfig {
  return STEP_MAP[type] ?? {
    label: type, icon: '💬', color: '#F5F5F5', textColor: '#8E8E93',
  }
}

export interface CallConfig {
  label: string
  icon: string
  color: string
  textColor: string
}

// 调用类型配置：llm 模型调用 / tool 工具调用
export const CALL_MAP: Record<string, CallConfig> = {
  llm: { label: '模型', icon: '🧠', color: '#E8F0FE', textColor: '#007AFF' },
  tool: { label: '工具', icon: '🔧', color: '#E0F7FA', textColor: '#00BCD4' },
}

// 未知 call_type 兜底
export function getCallConfig(type: string): CallConfig {
  return CALL_MAP[type] ?? {
    label: type, icon: '💬', color: '#F5F5F5', textColor: '#8E8E93',
  }
}

export interface StatusConfig {
  label: string
  color: string
  textColor: string
}

// 步骤状态配色：success 绿 / error 红 / degraded 橙
export const STATUS_MAP: Record<string, StatusConfig> = {
  success: { label: '成功', color: '#E8F5E9', textColor: '#34C759' },
  error: { label: '失败', color: '#FFEBEE', textColor: '#FF3B30' },
  degraded: { label: '降级', color: '#FFF3E0', textColor: '#FF9500' },
}

// 未知 status 兜底
export function getStatusConfig(status: string): StatusConfig {
  return STATUS_MAP[status] ?? {
    label: status, color: '#F5F5F5', textColor: '#8E8E93',
  }
}