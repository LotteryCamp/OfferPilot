import { describe, expect, it } from 'vitest'
import {
  consentBlockReason,
  consentMatches,
  sameDisclosure,
  transferConsentState,
  transferScopeLabel,
} from './consentContracts'

const disclosure = {
  provider: '测试服务商',
  model: null,
  purposes: ['requirement_extraction', 'candidate_planning'],
  field_categories: ['matter_goal', 'public_scope', 'public_sources'],
  consent_scope: '归属当前用户，覆盖全部事项及后续模型服务。',
  data_handling: '发送公开来源和公开范围，不发送个人事实。',
}
const consent = {
  consent_id: 'e0000000-0000-4000-8000-000000000001',
  purposes: [...disclosure.purposes],
  field_categories: [...disclosure.field_categories],
  status: 'active' as const,
  version_no: 1,
  created_at: '2026-11-20T00:00:00Z',
  revoked_at: null,
}

describe('用户级模型传输同意协议', () => {
  it('读取用户级记录和授权范围，模型名称可为空', () => {
    const state = transferConsentState.parse({ disclosure, consent })
    expect(state.disclosure.model).toBeNull()
    expect(state.disclosure.consent_scope).toContain('全部事项')
    expect(consentBlockReason(state)).toBe('')
  })
  it('未读取或未授予时需要用户确认', () => {
    expect(consentBlockReason(null)).not.toBe('')
    expect(consentBlockReason({ disclosure, consent: null })).not.toBe('')
  })
  it('缺少全局范围披露时不可接受授权状态', () => {
    expect(
      transferConsentState.safeParse({
        disclosure: { ...disclosure, consent_scope: undefined },
        consent,
      }).success,
    ).toBe(false)
  })
  it('更换服务商或模型后既有同意保持有效', () => {
    const changed = { ...disclosure, provider: '其他服务商', model: '另一模型' }
    expect(consentMatches(consent, changed)).toBe(true)
    expect(consentBlockReason({ disclosure: changed, consent })).toBe('')
  })
  it('撤回状态或撤回时间存在时不可继续使用', () => {
    expect(consentMatches({ ...consent, status: 'revoked' }, disclosure)).toBe(false)
    expect(consentMatches({ ...consent, revoked_at: '2026-11-20T01:00:00Z' }, disclosure)).toBe(
      false,
    )
  })
  it('用途或发送类别不匹配时停止分析', () => {
    expect(consentMatches({ ...consent, purposes: ['requirement_extraction'] }, disclosure)).toBe(
      false,
    )
    expect(
      consentMatches(
        { ...consent, field_categories: [...consent.field_categories, 'personal_facts'] },
        disclosure,
      ),
    ).toBe(false)
  })

  it('恢复分析前，披露范围与已有同意不匹配时提示重新确认', () => {
    for (const changed of [
      { ...disclosure, purposes: ['requirement_extraction'] },
      { ...disclosure, field_categories: ['public_sources'] },
    ]) {
      expect(consentBlockReason({ disclosure: changed, consent })).toBe(
        '已有授权与披露用途或字段范围不一致，请先撤回后重新确认。',
      )
    }
  })
  it('范围顺序不影响校验，重复类别不能掩盖缺项', () => {
    expect(
      consentMatches({ ...consent, purposes: [...consent.purposes].reverse() }, disclosure),
    ).toBe(true)
    expect(
      consentMatches(
        { ...consent, field_categories: ['matter_goal', 'public_sources', 'public_sources'] },
        disclosure,
      ),
    ).toBe(false)
  })
  it('首次授予前披露发生变化须重新确认', () => {
    expect(sameDisclosure(disclosure, { ...disclosure })).toBe(true)
    expect(sameDisclosure(disclosure, { ...disclosure, model: '新模型' })).toBe(false)
    expect(sameDisclosure(disclosure, { ...disclosure, data_handling: '新说明' })).toBe(false)
    expect(sameDisclosure(disclosure, { ...disclosure, consent_scope: '新授权范围' })).toBe(false)
  })
  it('未知发送类别保留原始说明', () => {
    expect(transferScopeLabel('future_category')).toBe('future_category')
    expect(transferScopeLabel('public_sources')).toContain('公开来源')
  })
})
