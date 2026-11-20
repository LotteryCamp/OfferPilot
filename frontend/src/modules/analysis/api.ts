import axios from 'axios'
import { z } from 'zod'
import { http } from '../../shared/http'
import { assertStartedRun, runResponse } from './contracts'

// One run can perform two model calls of up to 300 seconds each, plus source reading.
const analysisStartTimeoutMs = 650_000

export const analysisInput = z.strictObject({
  source_urls: z.array(z.string().min(1)).min(1),
  publisher: z.string().min(1),
  scope_year: z.number().int(),
  scope: z.string().optional(),
  operation_id: z.uuid(),
})
export type AnalysisInput = z.infer<typeof analysisInput>

export async function startAnalysis(matterId: string, input: AnalysisInput, signal: AbortSignal) {
  const response = await http.post<unknown>(
    `/matters/${matterId}/agent-runs`,
    analysisInput.parse(input),
    {
      signal,
      timeout: analysisStartTimeoutMs,
    },
  )
  const { run } = runResponse.parse(response.data)
  assertStartedRun(run)
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
