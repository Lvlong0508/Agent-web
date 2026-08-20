// 运行记录 API 模块：列表分页查询 + 批量删除（axios，请求头由拦截器统一附加）
import http from './index'
import type { AgentRun } from '@/components/run-detail/types'

// 后端 /agent-runs 分页响应结构（对齐 app/schemas/agent_run.py 的 AgentRunListResponse）
export interface AgentRunListResponse {
  items: AgentRun[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// 后端批量删除响应结构（对齐 AgentRunDeleteResponse）
export interface AgentRunDeleteResponse {
  deleted: number
}

// 分页查询运行记录：page 从 1 开始，page_size 1~100
export function listAgentRuns(page: number, pageSize: number) {
  return http.get<AgentRunListResponse>('/agent-runs', { params: { page, page_size: pageSize } })
}

// 批量删除运行记录：传入要删的记录 id 列表
export function deleteAgentRuns(runIds: string[]) {
  return http.delete<AgentRunDeleteResponse>('/agent-runs', { data: { run_ids: runIds } })
}
