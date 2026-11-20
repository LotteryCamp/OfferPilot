import { http } from '../../shared/http'
import {
  assertSavedRanking,
  rankingReadResponse,
  rankingSaveInput,
  rankingSaveResponse,
} from './rankingFacts'
import type { RankingSaveInput } from './rankingFacts'

export async function readRanking(signal: AbortSignal) {
  const response = await http.get<unknown>('/facts/gpa.rank', { signal })
  return rankingReadResponse.parse(response.data)
}

export async function saveRanking(input: RankingSaveInput, signal: AbortSignal) {
  const body = rankingSaveInput.parse(input)
  const response = await http.put<unknown>('/facts/gpa.rank', body, { signal })
  const result = rankingSaveResponse.parse(response.data)
  assertSavedRanking(result.fact, body)
  return result
}
