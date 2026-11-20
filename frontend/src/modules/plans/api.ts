import axios from 'axios'
import { z } from 'zod'
import { http } from '../../shared/http'
import {
  assertDecision,
  assertPlanScope,
  decisionResponse,
  planListResponse,
  planResponse,
  taskResponse,
} from './contracts'
import type { Action } from './contracts'

export async function listPlans(matterId: string, signal: AbortSignal) {
  const result = await http.get<unknown>(`/matters/${matterId}/candidate-plans`, { signal })
  const { plans } = planListResponse.parse(result.data)
  if (plans.some((plan) => plan.matter_id !== matterId))
    throw new Error('计划列表包含其他事项，已停止展示。')
  return plans.sort((a, b) => b.version_no - a.version_no)
}

export async function getPlan(matterId: string, planId: string, signal: AbortSignal) {
  const result = await http.get<unknown>(`/candidate-plans/${planId}`, { signal })
  const { plan } = planResponse.parse(result.data)
  assertPlanScope(plan, matterId, planId)
  return plan
}

export async function getTasks(matterId: string, signal: AbortSignal) {
  const result = await http.get<unknown>(`/matters/${matterId}/tasks`, { signal })
  const { tasks } = taskResponse.parse(result.data)
  if (tasks.some((task) => task.matter_id !== matterId))
    throw new Error('任务与当前事项不一致，已停止展示。')
  return tasks
}

export async function decidePlan(matterId: string, planId: string, action: Action, key: string) {
  const result = await http.post<unknown>(`/candidate-plans/${planId}/${action}`, undefined, {
    headers: { 'Idempotency-Key': key },
  })
  const response = decisionResponse.parse(result.data)
  assertDecision(response, matterId, planId, action, key)
  return response
}

const errorBody = z.object({
  error: z.object({ code: z.string(), message: z.string(), next: z.string().optional() }),
})
export function planError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const parsed = errorBody.safeParse(error.response?.data)
    if (parsed.success)
      return [parsed.data.error.message, parsed.data.error.next].filter(Boolean).join('；')
    return '无法连接计划接口或服务暂不可用，请稍后重新读取。'
  }
  if (error instanceof z.ZodError) return '计划接口响应格式不符合约定，请联系后端核对。'
  return error instanceof Error ? error.message : '计划读取失败，请重试。'
}

export function decisionMayBeCommitted(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return true
  const status = error.response?.status
  return status === undefined || status === 408 || status === 429 || status >= 500
}
