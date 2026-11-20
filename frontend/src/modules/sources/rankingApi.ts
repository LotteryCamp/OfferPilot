import axios from 'axios'
import { z } from 'zod'
import { http } from '../../shared/http'
import {
  assertRankingScope,
  assertSavedRanking,
  rankingReadResponse,
  rankingSaveInput,
  rankingSaveResponse,
} from './rankingFacts'
import type { RankingSaveInput } from './rankingFacts'

function path(matterId: string) {
  return `/matters/${z.uuid().parse(matterId)}/facts/gpa.rank`
}

export async function readRanking(matterId: string, signal: AbortSignal) {
  const response = await http.get<unknown>(path(matterId), { signal })
  const result = rankingReadResponse.parse(response.data)
  assertRankingScope([...result.versions, ...(result.fact ? [result.fact] : [])], matterId)
  return result.fact
}

export async function saveRanking(matterId: string, input: RankingSaveInput, signal: AbortSignal) {
  const body = rankingSaveInput.parse(input)
  const response = await http.put<unknown>(path(matterId), body, { signal })
  const result = rankingSaveResponse.parse(response.data)
  assertRankingScope([result.fact], matterId)
  assertSavedRanking(result.fact, body)
  if (result.affected_plans.some((plan) => plan.matter_id !== matterId))
    throw new Error('保存结果包含其他事项的候选，请重新读取并联系后端核对。')
  return result
}

export function rankingError(cause: unknown) {
  if (axios.isAxiosError(cause)) {
    const parsed = z
      .object({
        error: z.object({
          message: z.string(),
          next: z.string().optional(),
          details: z
            .object({ issues: z.array(z.object({ message: z.string() })).optional() })
            .optional(),
        }),
      })
      .safeParse(cause.response?.data)
    if (parsed.success && cause.response && cause.response.status < 500)
      return [
        parsed.data.error.message,
        ...(parsed.data.error.details?.issues?.map((issue) => issue.message) ?? []),
        parsed.data.error.next,
      ]
        .filter(Boolean)
        .join('；')
    return '暂时无法连接排名服务，请重新读取后核对。'
  }
  if (cause instanceof z.ZodError) return '排名响应不符合约定，请重新读取并联系后端核对。'
  return cause instanceof Error ? cause.message : '排名操作未完成，请重试读取。'
}

export function rankingSaveMayHaveCommitted(cause: unknown) {
  if (!axios.isAxiosError(cause)) return true
  const status = cause.response?.status
  return status === undefined || status === 408 || status === 429 || status >= 500
}
