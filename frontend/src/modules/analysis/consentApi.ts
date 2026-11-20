import axios from 'axios'
import { z } from 'zod'
import { http } from '../../shared/http'
import {
  grantConsentResponse,
  revokeConsentResponse,
  transferConsentState,
} from './consentContracts'

const path = '/model-transfer-consent'
export async function readTransferConsent(signal: AbortSignal) {
  const response = await http.get<unknown>(path, { signal })
  const state = transferConsentState.parse(response.data)
  return state
}
export async function grantTransferConsent(signal: AbortSignal) {
  const response = await http.post<unknown>(path, undefined, { signal })
  const result = grantConsentResponse.parse(response.data)
  if (result.consent.status !== 'active' || result.consent.revoked_at !== null)
    throw new Error('授予响应未返回有效授权，请重新读取核对。')
  return result.consent
}
export async function revokeTransferConsent(consentId: string, signal: AbortSignal) {
  const response = await http.delete<unknown>(`${path}/${z.uuid().parse(consentId)}`, {
    signal,
  })
  const result = revokeConsentResponse.parse(response.data)
  if (
    result.consent.consent_id !== consentId ||
    result.consent.status !== 'revoked' ||
    !result.consent.revoked_at
  )
    throw new Error('撤回响应未与本次授权对应，请重新读取核对。')
  return result.consent
}
export function consentError(cause: unknown) {
  if (axios.isAxiosError(cause)) {
    const parsed = z
      .object({ error: z.object({ message: z.string(), next: z.string().optional() }) })
      .safeParse(cause.response?.data)
    if (parsed.success && cause.response && cause.response.status < 500)
      return [parsed.data.error.message, parsed.data.error.next].filter(Boolean).join('；')
    return '授权服务暂不可用，请重新读取核对。'
  }
  if (cause instanceof z.ZodError) return '授权响应不符合约定，请重新读取并联系后端核对。'
  return cause instanceof Error ? cause.message : '授权操作未完成，请重新读取。'
}
