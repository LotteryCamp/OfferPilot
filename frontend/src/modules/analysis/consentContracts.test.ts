import { describe, expect, it } from 'vitest'
import {
  assertConsentMatter,
  consentBlockReason,
  consentMatches,
  sameDisclosure,
  transferConsentState,
  transferScopeLabel,
} from './consentContracts'

const matterId = 'a0000000-0000-4000-8000-000000000001'
const disclosure = {
  provider: '测试服务商',
  model: null,
  purposes: ['requirement_extraction', 'candidate_planning'],
  field_categories: ['matter_goal', 'public_scope', 'public_sources'],
  data_handling: '发送公开来源和公开范围，不发送个人事实。',
}
const consent = {
  consent_id: 'e0000000-0000-4000-8000-000000000001',
  matter_id: matterId,
  provider: disclosure.provider,
  purposes: [...disclosure.purposes],
  field_categories: [...disclosure.field_categories],
  status: 'active' as const,
  version_no: 1,
  created_at: '2026-11-20T00:00:00Z',
  revoked_at: null,
}

describe('事项模型传输同意协议', () => {
  it('接受服务端未配置模型名称时的真实空值', () => {
    const result = transferConsentState.parse({ required: true, disclosure, consent })
    expect(result.disclosure.model).toBeNull()
    expect(consentBlockReason(result, matterId)).toBe('')
  })
  it('未读取授权状态以及需要但尚未授予时停止分析', () => {
    expect(consentBlockReason(null, matterId)).not.toBe('')
    expect(consentBlockReason({ required: true, disclosure, consent: null }, matterId)).not.toBe('')
  })
  it('按后端required=false处理公开分析，不构造同意标识', () => {
    const result = transferConsentState.parse({ required: false, disclosure, consent: null })
    expect(consentBlockReason(result, matterId)).toBe('')
    expect(result.consent).toBeNull()
  })
  it('其他事项的授权不可展示或使用', () => {
    expect(() => assertConsentMatter(consent, crypto.randomUUID())).toThrow()
    expect(consentMatches(consent, disclosure, crypto.randomUUID())).toBe(false)
    expect(
      consentBlockReason({ required: false, disclosure, consent }, crypto.randomUUID()),
    ).not.toBe('')
  })
  it('撤回状态或撤回时间存在时不可继续使用标识', () => {
    expect(consentMatches({ ...consent, status: 'revoked' }, disclosure, matterId)).toBe(false)
    expect(
      consentMatches({ ...consent, revoked_at: '2026-11-20T01:00:00Z' }, disclosure, matterId),
    ).toBe(false)
  })
  it('服务商、用途或发送类别不匹配时需要重新确认', () => {
    expect(consentMatches({ ...consent, provider: '其他服务商' }, disclosure, matterId)).toBe(false)
    expect(
      consentMatches({ ...consent, purposes: ['requirement_extraction'] }, disclosure, matterId),
    ).toBe(false)
    expect(
      consentMatches(
        { ...consent, field_categories: [...consent.field_categories, 'personal_facts'] },
        disclosure,
        matterId,
      ),
    ).toBe(false)
  })
  it('范围顺序不影响校验，重复类别不能掩盖缺少的类别', () => {
    expect(
      consentMatches(
        { ...consent, purposes: [...consent.purposes].reverse() },
        disclosure,
        matterId,
      ),
    ).toBe(true)
    expect(
      consentMatches(
        { ...consent, field_categories: ['matter_goal', 'public_sources', 'public_sources'] },
        disclosure,
        matterId,
      ),
    ).toBe(false)
  })
  it('授予前披露文本或模型变化需重新展示确认', () => {
    expect(sameDisclosure(disclosure, { ...disclosure })).toBe(true)
    expect(sameDisclosure(disclosure, { ...disclosure, model: '新模型' })).toBe(false)
    expect(sameDisclosure(disclosure, { ...disclosure, data_handling: '新的数据处理说明' })).toBe(
      false,
    )
    expect(sameDisclosure(disclosure, { ...disclosure, provider: '新服务商' })).toBe(false)
  })
  it('未知发送类别保留原始说明，不隐去披露内容', () => {
    expect(transferScopeLabel('future_category')).toBe('future_category')
    expect(transferScopeLabel('public_sources')).toContain('公开来源')
  })
})
