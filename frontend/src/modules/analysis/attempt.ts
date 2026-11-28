import { analysisAttemptSchema, analysisRequestSchema } from './contracts'
import type { AnalysisAttempt, AnalysisRequest } from './contracts'

export type PreparedAnalysisAttempt = AnalysisAttempt & { request: AnalysisRequest }

export function createAnalysisAttempt(
  matterId: string,
  sourceId: string,
  request: AnalysisRequest,
): PreparedAnalysisAttempt {
  return {
    matterId,
    sourceId,
    operationId: crypto.randomUUID(),
    runId: null,
    status: null,
    request: analysisRequestSchema.parse(request),
  }
}

export function canRecoverAnalysisAttempt(
  attempt: AnalysisAttempt | null,
): attempt is PreparedAnalysisAttempt {
  return !!attempt && attempt.runId === null && attempt.status === null && !!attempt.request
}

export function analysisRecoveryBlockReason(
  attempt: AnalysisAttempt | null,
  matterId: string,
  sourceId: string | null,
  scopeYear: number | null,
): string {
  if (!canRecoverAnalysisAttempt(attempt))
    return '上次记录已有明确状态或缺少恢复参数，请先核对已保存结果。'
  if (attempt.matterId !== matterId || attempt.sourceId !== sourceId)
    return '请返回上次分析所属的事项并选择原来源后恢复。'
  if (attempt.request.scope_year !== scopeYear)
    return '上次分析的适用年度已变化，请先核对已保存结果。'
  return ''
}

export function recoverAnalysisAttempt(
  previous: AnalysisAttempt | null,
  matterId: string,
  sourceId: string,
  scopeYear: number | null,
): PreparedAnalysisAttempt {
  const attempt = analysisAttemptSchema.parse(previous)
  const reason = analysisRecoveryBlockReason(attempt, matterId, sourceId, scopeYear)
  if (reason) throw new Error(reason)
  return { ...attempt, request: analysisRequestSchema.parse(attempt.request) }
}
