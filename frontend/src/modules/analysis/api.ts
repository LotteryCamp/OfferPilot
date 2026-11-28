import axios from 'axios'
import { z } from 'zod'
import { http } from '../../shared/http'
import { analysisRequestSchema, assertStartedRun, runResponse } from './contracts'
import type { AnalysisMode } from './contracts'
import { agentRunTimeoutMs } from './timing'

export const analysisInput = analysisRequestSchema.extend({
  operation_id: z.uuid(),
})
export type AnalysisInput = z.infer<typeof analysisInput>

export async function startAnalysis(
  matterId: string,
  input: AnalysisInput,
  signal: AbortSignal,
  mode: AnalysisMode = 'start',
) {
  const response = await http.post<unknown>(
    `/matters/${matterId}/agent-runs`,
    analysisInput.parse(input),
    {
      signal,
      timeout: agentRunTimeoutMs(import.meta.env.VITE_AGENT_RUN_TIMEOUT_SECONDS),
    },
  )
  const { run } = runResponse.parse(response.data)
  assertStartedRun(run, mode)
  return run
}

export async function getAnalysis(runId: string, signal: AbortSignal) {
  const response = await http.get<unknown>(`/agent-runs/${encodeURIComponent(runId)}`, { signal })
  const { run } = runResponse.parse(response.data)
  if (run.run_id !== runId) throw new Error('返回的运行与请求不一致，已停止展示。')
  return run
}

export function isMissingRun(cause: unknown) {
  return (
    axios.isAxiosError(cause) &&
    cause.response?.status === 404 &&
    cause.response.data?.error?.code === 'agent_run_not_found'
  )
}

export function isConsentRejectedStart(cause: unknown) {
  return (
    axios.isAxiosError(cause) &&
    cause.response?.status === 422 &&
    ['model_transfer_consent_required', 'model_transfer_consent_invalid'].includes(
      cause.response.data?.error?.code,
    )
  )
}

export function analysisError(cause: unknown) {
  if (axios.isAxiosError(cause)) {
    if (cause.response?.status === 502 || cause.response?.status === 504)
      return '分析服务未能通过网关返回结果，后端可能仍在执行。请刷新已保存结果并查看候选计划，核对后再决定是否重新发起。'
    if (!cause.response && ['ECONNABORTED', 'ETIMEDOUT'].includes(cause.code ?? ''))
      return '等待分析响应已超过前端时限，后端可能仍在执行。请刷新已保存结果并查看候选计划，核对后再决定是否重新发起。'
    const parsed = z
      .object({ error: z.object({ message: z.string(), next: z.string().optional() }) })
      .safeParse(cause.response?.data)
    if (parsed.success && cause.response && cause.response.status < 500)
      return [parsed.data.error.message, parsed.data.error.next].filter(Boolean).join('；')
    return '运行结果暂无法确认，请先刷新已保存结果，核对来源与候选计划。'
  }
  if (cause instanceof z.ZodError) return '分析响应不符合约定，请核对已保存结果并联系后端。'
  return cause instanceof Error ? cause.message : '分析结果暂无法确认。'
}
