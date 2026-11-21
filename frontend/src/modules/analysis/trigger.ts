export type AnalysisTrigger = 'manual' | 'saved-ranking'

export class AnalysisNotStartedError extends Error {
  override name = 'AnalysisNotStartedError'
}

export function analysisTriggerBlockReason(
  rankingSaving: boolean,
  commonReason: string,
  trigger: AnalysisTrigger,
) {
  if (trigger === 'manual' && rankingSaving) return '排名正在保存和核对，请稍后重试。'
  return commonReason
}
