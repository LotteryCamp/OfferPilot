import { z } from 'zod'

const scope = {
  purposes: z.array(z.string().min(1)).min(1),
  field_categories: z.array(z.string().min(1)).min(1),
}
export const transferDisclosure = z.object({
  ...scope,
  provider: z.string().min(1),
  model: z.string().nullable(),
  consent_scope: z.string().min(1),
  data_handling: z.string().min(1),
})
export const transferConsent = z.object({
  ...scope,
  consent_id: z.uuid(),
  status: z.enum(['active', 'revoked']),
  version_no: z.number().int().positive(),
  created_at: z.string(),
  revoked_at: z.string().nullable(),
})
export const transferConsentState = z.object({
  disclosure: transferDisclosure,
  consent: transferConsent.nullable(),
})
export const grantConsentResponse = z.object({ consent: transferConsent, created: z.boolean() })
export const revokeConsentResponse = z.object({ consent: transferConsent, revoked: z.boolean() })
export type TransferConsent = z.infer<typeof transferConsent>
export type TransferDisclosure = z.infer<typeof transferDisclosure>
export type TransferConsentState = z.infer<typeof transferConsentState>

function sameSet(a: string[], b: string[]) {
  return (
    a.length === b.length &&
    new Set(a).size === a.length &&
    new Set(b).size === b.length &&
    a.every((value) => b.includes(value))
  )
}

export function sameDisclosure(a: TransferDisclosure, b: TransferDisclosure) {
  return (
    a.provider === b.provider &&
    a.model === b.model &&
    a.data_handling === b.data_handling &&
    a.consent_scope === b.consent_scope &&
    sameSet(a.purposes, b.purposes) &&
    sameSet(a.field_categories, b.field_categories)
  )
}

export function consentMatches(consent: TransferConsent, disclosure: TransferDisclosure) {
  return (
    consent.status === 'active' &&
    consent.revoked_at === null &&
    sameSet(consent.purposes, disclosure.purposes) &&
    sameSet(consent.field_categories, disclosure.field_categories)
  )
}

export function consentBlockReason(state: TransferConsentState | null) {
  if (!state) return '请先读取当前用户的模型传输授权状态。'
  if (state.consent && !consentMatches(state.consent, state.disclosure))
    return '已有授权与披露用途或字段范围不一致，请先撤回后重新确认。'
  if (!state.consent) return '请先阅读下方全部事项共用的披露范围，并由本人确认是否授权。'
  return ''
}

export function transferScopeLabel(value: string) {
  const labels: Record<string, string> = {
    requirement_extraction: '提取通知要求',
    candidate_planning: '生成候选计划',
    matter_goal: '事项目标',
    public_scope: '白名单公开适用范围',
    public_sources: '公开来源正文与引用定位',
  }
  return Object.hasOwn(labels, value) ? labels[value]! : value
}
