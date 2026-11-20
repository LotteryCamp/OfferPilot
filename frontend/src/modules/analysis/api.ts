import axios from 'axios'
import { z } from 'zod'
import { http } from '../../shared/http'
import { assertStartedRun, runResponse } from './contracts'

export interface AnalysisInput {
  source_urls: string[]
  publisher: string
  scope_year: number
  scope?: string
  operation_id: string
}

export async function startAnalysis(matterId: string, input: AnalysisInput, signal: AbortSignal) {
  const response = await http.post<unknown>(`/matters/${matterId}/agent-runs`, input, {
    signal,
    timeout: 120000,
  })
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
